#!/usr/bin/env ruby
require_relative "../lib/config"
if ARGV[0] == "gitops"
  revision = required("multicluster","revision")
  abort "GitOps 必须锁定完整提交" unless revision.match?(/\A[0-9a-f]{40}\z/)
  appset = object("argoproj.io/v1alpha1","ApplicationSet","cnpl06-#{run}-clusters",{"generators"=>[{"list"=>{"elements"=>%w[primary secondary].map { |key| {"cluster"=>required("multicluster","#{key}_argocd_name")} }}}],"syncPolicy"=>{"preserveResourcesOnDeletion"=>true,"applicationsSync"=>"create-update"},"template"=>{"metadata"=>{"name"=>"cnpl06-#{run}-{{cluster}}","labels"=>labels},"spec"=>{"project"=>required("multicluster","argocd_project"),"source"=>{"repoURL"=>required("multicluster","repository"),"targetRevision"=>revision,"path"=>required("multicluster","path")},"destination"=>{"name"=>"{{cluster}}","namespace"=>namespace},"syncPolicy"=>{"automated"=>{"prune"=>false,"selfHeal"=>false}}}}},required("multicluster","argocd_namespace"))
  emit([appset]); exit
end
if ARGV[0] == "mcs"
  emit([object("multicluster.x-k8s.io/v1alpha1","ServiceExport","global-echo")]); exit
end
target = required("multicluster","target")
abort "必须明确 primary/secondary" unless %w[primary secondary].include?(target)
ids = %w[primary secondary].map { |k| required("multicluster","#{k}_id") }
abort "cluster ID 必须不同且为 1-255" unless ids.uniq.size == 2 && ids.all? { |id| id.is_a?(Integer) && (1..255).include?(id) }
app = deployment("global-echo")
app["spec"]["template"]["spec"]["containers"][0]["env"] = [{"name"=>"CLUSTER_NAME","value"=>required("multicluster","#{target}_name")}]
svc = service("global-echo")
svc["metadata"]["annotations"] = {"service.cilium.io/global"=>"true","service.cilium.io/shared"=>"true"}
policy = object("cilium.io/v2","CiliumNetworkPolicy","cross-cluster-echo",{"endpointSelector"=>{"matchLabels"=>{"app"=>"global-echo"}},"ingress"=>%w[primary secondary].map { |key| {"fromEndpoints"=>[{"matchLabels"=>{"k8s:io.kubernetes.pod.namespace"=>namespace,"k8s:app"=>"global-echo","k8s:io.cilium.k8s.policy.cluster"=>required("multicluster","#{key}_name")}}],"toPorts"=>[{"ports"=>[{"port"=>"8080","protocol"=>"TCP"}]}]} }})
emit(base+[app,svc,policy])
