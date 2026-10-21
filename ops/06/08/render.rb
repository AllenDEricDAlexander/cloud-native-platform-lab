#!/usr/bin/env ruby
require_relative "../lib/config"
if ARGV[0] == "queues"
  flavor = "cnpl06-#{run}-cpu"
  queue = "cnpl06-#{run}-cpu"
  items = base+[object("kueue.x-k8s.io/v1beta1","ResourceFlavor",flavor,{"nodeLabels"=>{"kubernetes.io/arch"=>"amd64"}},nil),object("kueue.x-k8s.io/v1beta1","ClusterQueue",queue,{"namespaceSelector"=>{"matchLabels"=>labels},"resourceGroups"=>[{"coveredResources"=>["cpu","memory"],"flavors"=>[{"name"=>flavor,"resources"=>[{"name"=>"cpu","nominalQuota"=>"1"},{"name"=>"memory","nominalQuota"=>"512Mi"}]}]}]},nil),object("kueue.x-k8s.io/v1beta1","LocalQueue","cpu",{"clusterQueue"=>queue})]
  %w[first second].each do |suffix|
    task = job("queue-#{suffix}",["sh","-c","echo admitted; sleep 30"])
    task["metadata"]["labels"]["kueue.x-k8s.io/queue-name"] = "cpu"
    task["spec"]["suspend"] = true
    task["spec"]["template"]["spec"]["containers"][0]["resources"] = {"requests"=>{"cpu"=>"1","memory"=>"256Mi"},"limits"=>{"cpu"=>"1","memory"=>"256Mi"}}
    items << task
  end
  items.find { |d| d["kind"] == "ClusterQueue" }["spec"]["namespaceSelector"] = {"matchLabels"=>{"cnpl.io/phase"=>"06","cnpl.io/run"=>run},"matchExpressions"=>[{"key"=>"cnpl.io/stage","operator"=>"In","values"=>["08","13"]}]}
  emit(items)
  exit
end
items = base
%w[workflow sensor].each do |name|
  items << object("v1","ServiceAccount",name).merge("automountServiceAccountToken"=>true)
  rules = name == "workflow" ? [{"apiGroups"=>["argoproj.io"],"resources"=>["workflowtaskresults"],"verbs"=>["create","patch"]}] : [{"apiGroups"=>["argoproj.io"],"resources"=>["workflows"],"verbs"=>["create"]}]
  items << object("rbac.authorization.k8s.io/v1","Role",name).merge("rules"=>rules)
  items << object("rbac.authorization.k8s.io/v1","RoleBinding",name).merge("subjects"=>[{"kind"=>"ServiceAccount","name"=>name,"namespace"=>namespace}],"roleRef"=>{"kind"=>"Role","name"=>name,"apiGroup"=>"rbac.authorization.k8s.io"})
end
artifact = {"s3"=>{"endpoint"=>required("workflow","artifact_endpoint"),"bucket"=>required("workflow","artifact_bucket"),"insecure"=>false,"keyFormat"=>"cnpl06/#{run}/{{workflow.name}}/{{pod.name}}","accessKeySecret"=>{"name"=>required("workflow","artifact_secret"),"key"=>"access-key"},"secretKeySecret"=>{"name"=>required("workflow","artifact_secret"),"key"=>"secret-key"}}}
items << object("v1","ConfigMap","artifact-repositories").merge("data"=>{"lab"=>YAML.dump(artifact)})
worker = container("work",image("probe"),["sh","-c","printf '%s\\n' \"$LAB_EVENT_ID\" > /work/result.txt"])
worker["env"] = [{"name"=>"LAB_EVENT_ID","value"=>"{{workflow.parameters.event-id}}"}]
worker["volumeMounts"] = [{"name"=>"work","mountPath"=>"/work"}]
template = object("argoproj.io/v1alpha1","WorkflowTemplate","bounded-dag",{"serviceAccountName"=>"workflow","entrypoint"=>"pipeline","parallelism"=>2,"activeDeadlineSeconds"=>180,"ttlStrategy"=>{"secondsAfterCompletion"=>86400},"securityContext"=>security,"artifactRepositoryRef"=>{"configMap"=>"artifact-repositories","key"=>"lab"},"volumes"=>[{"name"=>"work","emptyDir"=>{"sizeLimit"=>"32Mi"}}],"arguments"=>{"parameters"=>[{"name"=>"event-id","value"=>"#{run}-001"}]},"templates"=>[{"name"=>"pipeline","dag"=>{"tasks"=>[{"name"=>"prepare","template"=>"prepare"},{"name"=>"process","dependencies"=>["prepare"],"template"=>"process"},{"name"=>"archive","dependencies"=>["process"],"template"=>"archive","arguments"=>{"artifacts"=>[{"name"=>"result","from"=>"{{tasks.process.outputs.artifacts.result}}"}]}}]}},{"name"=>"prepare","container"=>container("prepare",image("probe"),["sh","-c","echo preparing"])},{"name"=>"process","retryStrategy"=>{"limit"=>"2","retryPolicy"=>"OnError"},"container"=>worker,"outputs"=>{"artifacts"=>[{"name"=>"result","path"=>"/work/result.txt"}]}},{"name"=>"archive","inputs"=>{"artifacts"=>[{"name"=>"result","path"=>"/work/input.txt"}]},"container"=>container("archive",image("probe"),["sh","-c","test -s /work/input.txt; sha256sum /work/input.txt"]).merge("volumeMounts"=>[{"name"=>"work","mountPath"=>"/work"}])}]})
items << template
version = required("workflow","jetstream_version")
abort "JetStream 版本必须锁定" if version == "latest" || version.empty?
items << object("argoproj.io/v1alpha1","EventBus","lab",{"jetstream"=>{"version"=>version,"replicas"=>3,"persistence"=>{"storageClassName"=>required("workflow","jetstream_storage_class"),"volumeSize"=>"1Gi"}}})
items << object("argoproj.io/v1alpha1","EventSource","lab-webhook",{"eventBusName"=>"lab","service"=>{"ports"=>[{"port"=>12000,"targetPort"=>12000}]},"webhook"=>{"orders"=>{"port"=>"12000","endpoint"=>"/events","method"=>"POST","authSecret"=>{"name"=>required("workflow","webhook_secret"),"key"=>"token"}}}})
workflow = object("argoproj.io/v1alpha1","Workflow","event-#{run}-001",{"workflowTemplateRef"=>{"name"=>"bounded-dag"},"arguments"=>{"parameters"=>[{"name"=>"event-id","value"=>"#{run}-001"}]}})
items << object("argoproj.io/v1alpha1","Sensor","bounded-orders",{"eventBusName"=>"lab","template"=>{"serviceAccountName"=>"sensor"},"dependencies"=>[{"name"=>"order","eventSourceName"=>"lab-webhook","eventName"=>"orders","filters"=>{"data"=>[{"path"=>"body.id","type"=>"string","value"=>["^#{run}-001$"]}]}}],"triggers"=>[{"template"=>{"name"=>"one-workflow","k8s"=>{"operation"=>"create","source"=>{"resource"=>workflow}}},"retryStrategy"=>{"steps"=>2,"duration"=>1000000000,"factor"=>2}}]})
emit(items)
