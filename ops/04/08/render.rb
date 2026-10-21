#!/usr/bin/env ruby
require_relative "../lib/config"
name=required("release","name")+"-rollout"
mode=ARGV.fetch(0,"canary")
items=[]
case mode
when "canary", "bluegreen"
  app_image=digest_image(required("release","image"))
  selector={"app.kubernetes.io/name"=>name}
  services=%w[stable canary preview].map { |suffix| {"apiVersion"=>"v1","kind"=>"Service","metadata"=>{"name"=>"#{name}-#{suffix}","namespace"=>"apps-dev"},"spec"=>{"selector"=>selector,"ports"=>[{"name"=>"http","port"=>8080,"targetPort"=>8080}]}} }
  conditions=lambda { |limit| {"successCondition"=>"len(result) == 1 && !isNaN(result[0]) && result[0] < #{limit}","failureCondition"=>"len(result) != 1 || isNaN(result[0]) || result[0] >= #{limit}"} }
  error_query='sum(rate(http_requests_total{job="reference",status="500"}[1m])) / sum(rate(http_requests_total{job="reference"}[1m]))'
  latency_query='histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{job="reference"}[1m])))'
  metrics=[["error-rate",error_query,0.01],["p95-latency",latency_query,0.8]].map { |metric,query,limit| {"name"=>metric,"interval"=>"20s","count"=>5,"failureLimit"=>1,"consecutiveErrorLimit"=>1,"provider"=>{"prometheus"=>{"address"=>"http://prometheus.cnpl04-metrics.svc:9090","query"=>query}}}.merge(conditions.call(limit)) }
  items << {"apiVersion"=>"argoproj.io/v1alpha1","kind"=>"AnalysisTemplate","metadata"=>{"name"=>name,"namespace"=>"apps-dev"},"spec"=>{"metrics"=>metrics}}
  strategy= if mode=="canary"
    {"canary"=>{"stableService"=>"#{name}-stable","canaryService"=>"#{name}-canary","trafficRouting"=>{"plugins"=>{"argoproj-labs/gatewayAPI"=>{"httpRoute"=>name,"namespace"=>"apps-dev"}}},"steps"=>[{"setWeight"=>10},{"pause"=>{"duration"=>"60s"}},{"analysis"=>{"templates"=>[{"templateName"=>name}]}},{"setWeight"=>50},{"pause"=>{}},{"setWeight"=>100}]}}
  else
    {"blueGreen"=>{"activeService"=>"#{name}-stable","previewService"=>"#{name}-preview","autoPromotionEnabled"=>false,"prePromotionAnalysis"=>{"templates"=>[{"templateName"=>name}]},"scaleDownDelaySeconds"=>60}}
  end
  pod={"metadata"=>{"labels"=>selector},"spec"=>{"serviceAccountName"=>"application","automountServiceAccountToken"=>false,"terminationGracePeriodSeconds"=>30,"securityContext"=>{"runAsNonRoot"=>true,"runAsUser"=>1000,"runAsGroup"=>1000,"fsGroup"=>1000,"seccompProfile"=>{"type"=>"RuntimeDefault"}},"containers"=>[{"name"=>"app","image"=>app_image,"ports"=>[{"containerPort"=>8080}],"env"=>[{"name"=>"FAIL_REQUESTS","value"=>(INPUT.dig("progressive","bad_version")==true ? "true" : "false")}],"resources"=>{"requests"=>{"cpu"=>"100m","memory"=>"128Mi"},"limits"=>{"cpu"=>"1","memory"=>"512Mi"}},"securityContext"=>{"allowPrivilegeEscalation"=>false,"capabilities"=>{"drop"=>["ALL"]}},"readinessProbe"=>{"httpGet"=>{"path"=>"/ready","port"=>8080}},"livenessProbe"=>{"httpGet"=>{"path"=>"/health","port"=>8080}}}]}}
  items << {"apiVersion"=>"argoproj.io/v1alpha1","kind"=>"Rollout","metadata"=>{"name"=>name,"namespace"=>"apps-dev"},"spec"=>{"replicas"=>2,"revisionHistoryLimit"=>3,"selector"=>{"matchLabels"=>selector},"strategy"=>strategy,"template"=>pod}}
  refs=[{"name"=>"#{name}-stable","port"=>8080,"weight"=>100}]
  refs<<{"name"=>"#{name}-canary","port"=>8080,"weight"=>0} if mode=="canary"
  items << {"apiVersion"=>"gateway.networking.k8s.io/v1","kind"=>"HTTPRoute","metadata"=>{"name"=>name,"namespace"=>"apps-dev"},"spec"=>{"parentRefs"=>[{"name"=>required("gitops","gateway_name"),"namespace"=>required("gitops","gateway_namespace")}],"hostnames"=>[required("progressive","hostname")],"rules"=>[{"backendRefs"=>refs}]}}
  items.concat(services)
when "metrics"
  ns="cnpl04-metrics"
  items << {"apiVersion"=>"v1","kind"=>"Namespace","metadata"=>{"name"=>ns,"labels"=>{"pod-security.kubernetes.io/enforce"=>"restricted"}}}
  config={"global"=>{"scrape_interval"=>"10s"},"scrape_configs"=>[{"job_name"=>"reference","static_configs"=>[{"targets"=>["reference-probe:9091"]}]}]}
  items << {"apiVersion"=>"v1","kind"=>"ConfigMap","metadata"=>{"name"=>"prometheus","namespace"=>ns},"data"=>{"prometheus.yml"=>YAML.dump(config)}}
  items << {"apiVersion"=>"v1","kind"=>"ConfigMap","metadata"=>{"name"=>"reference-probe","namespace"=>ns},"data"=>{"probe.py"=>File.read(File.join(__dir__,"probe.py"))}}
  %w[prometheus reference-probe].each do |component|
    image=digest_image(required("render_images",component=="prometheus" ? "prometheus_minimal" : "probe_python"))
    container={"name"=>component,"image"=>image,"securityContext"=>{"allowPrivilegeEscalation"=>false,"capabilities"=>{"drop"=>["ALL"]}},"resources"=>{"requests"=>{"cpu"=>"100m","memory"=>"128Mi"},"limits"=>{"cpu"=>"500m","memory"=>"512Mi"}}}
    if component=="prometheus"
      container.merge!({"args"=>["--config.file=/etc/prometheus/prometheus.yml","--storage.tsdb.path=/data","--storage.tsdb.retention.time=2h"],"ports"=>[{"containerPort"=>9090}],"volumeMounts"=>[{"name"=>"config","mountPath"=>"/etc/prometheus"},{"name"=>"data","mountPath"=>"/data"}]})
    else
      container.merge!({"command"=>["python","/config/probe.py"],"env"=>[{"name"=>"TARGET_URL","value"=>required("progressive","url")+"/compute"}],"ports"=>[{"containerPort"=>9091}],"volumeMounts"=>[{"name"=>"config","mountPath"=>"/config"},{"name"=>"ca","mountPath"=>"/ca","readOnly"=>true}]})
    end
    volumes=[{"name"=>"config","configMap"=>{"name"=>component}},{"name"=>"data","emptyDir"=>{"sizeLimit"=>"2Gi"}}]
    volumes<<{"name"=>"ca","secret"=>{"secretName"=>required("progressive","ca_secret")}} if component=="reference-probe"
    items << {"apiVersion"=>"apps/v1","kind"=>"Deployment","metadata"=>{"name"=>component,"namespace"=>ns},"spec"=>{"replicas"=>1,"selector"=>{"matchLabels"=>{"app"=>component}},"template"=>{"metadata"=>{"labels"=>{"app"=>component}},"spec"=>{"automountServiceAccountToken"=>false,"securityContext"=>{"runAsNonRoot"=>true,"runAsUser"=>1000,"runAsGroup"=>1000,"fsGroup"=>1000,"seccompProfile"=>{"type"=>"RuntimeDefault"}},"containers"=>[container],"volumes"=>volumes}}}}
    items << {"apiVersion"=>"v1","kind"=>"Service","metadata"=>{"name"=>component,"namespace"=>ns},"spec"=>{"selector"=>{"app"=>component},"ports"=>[{"port"=>(component=="prometheus" ? 9090 : 9091)}]}}
  end
when "policy"
  public_key=File.read(required("supply_chain","public_key_file"))
  verified(required("supply_chain","public_key_file"),required("supply_chain","public_key_sha256"))
  enforcement=required("supply_chain","enforcement")
  abort "策略必须显式Audit或Enforce" unless %w[Audit Enforce].include?(enforcement)
  items << {"apiVersion"=>"kyverno.io/v1","kind"=>"ClusterPolicy","metadata"=>{"name"=>"cnpl04-trusted-images"},"spec"=>{"validationFailureAction"=>enforcement,"background"=>false,"failurePolicy"=>"Fail","webhookTimeoutSeconds"=>20,"rules"=>[{"name"=>"verify-signature-and-digest","match"=>{"any"=>[{"resources"=>{"kinds"=>["Pod"],"namespaces"=>%w[apps-dev apps-staging apps-prod-like]}}]},"verifyImages"=>[{"imageReferences"=>["harbor.k8s.internal.egon.top/*"],"required"=>true,"mutateDigest"=>false,"verifyDigest"=>true,"attestors"=>[{"entries"=>[{"keys"=>{"publicKeys"=>public_key,"rekor"=>{"ignoreTlog"=>true}}}]}]}]}]}}
else abort "未知渲染模式"
end
puts JSON.pretty_generate(label(items))
