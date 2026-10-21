#!/usr/bin/env ruby
# 只生成明确的CI/API/BuildKit/网关例外，不为应用开放任意出口。
require "ipaddr"
require_relative "../lib/config"
items=[]
nodes=YAML.load_file(File.join(REPO,"ops/inventory/hosts.yaml")).fetch("kubernetes_nodes")
api_ip=required("network","api_service_ip")
IPAddr.new(api_ip)
api_targets=nodes.select { |n| n["role"]=="control_plane" }.map { |n| {"ipBlock"=>{"cidr"=>"#{n['ip']}/32"}} }
# 主台账的控制平面角色若采用control-plane拼写，按节点名集合取已登记地址。
api_targets=nodes.select { |n| %w[cp01 cp02 cp03].include?(n["id"]) }.map { |n| {"ipBlock"=>{"cidr"=>"#{n['ip']}/32"}} } if api_targets.empty?
%w[ci-gitlab ci-jenkins].each do |ns|
  key=ns=="ci-gitlab" ? "gitlab_manager_selector" : "jenkins_controller_selector"
  selector=required("network",key)
  abort "Manager/Controller selector需显式非空" unless selector.is_a?(Hash) && !selector.empty?
  egress=[{"to"=>[{"ipBlock"=>{"cidr"=>"#{api_ip}/32"}}],"ports"=>[{"port"=>443,"protocol"=>"TCP"}]},{"to"=>api_targets,"ports"=>[{"port"=>6443,"protocol"=>"TCP"}]}]
  items << {"apiVersion"=>"networking.k8s.io/v1","kind"=>"NetworkPolicy","metadata"=>{"name"=>"controller-api","namespace"=>ns},"spec"=>{"podSelector"=>{"matchLabels"=>selector},"policyTypes"=>["Egress"],"egress"=>egress}}
  %w[trusted untrusted].each do |trust|
    items << {"apiVersion"=>"networking.k8s.io/v1","kind"=>"NetworkPolicy","metadata"=>{"name"=>"buildkit-#{trust}","namespace"=>ns},"spec"=>{"podSelector"=>{"matchLabels"=>{"cnpl.io/trust"=>trust}},"policyTypes"=>["Egress"],"egress"=>[{"to"=>[{"namespaceSelector"=>{"matchLabels"=>{"kubernetes.io/metadata.name"=>"ci-build"}},"podSelector"=>{"matchLabels"=>{"app.kubernetes.io/name"=>"buildkit-#{trust}"}}}],"ports"=>[{"port"=>1234,"protocol"=>"TCP"}]}]}}
  end
end
gateway_ns=required("network","gateway_namespace")
gateway_selector=required("network","gateway_selector")
abort "Gateway selector需显式非空" unless gateway_selector.is_a?(Hash) && !gateway_selector.empty?
%w[apps-dev apps-staging apps-prod-like ci-jenkins].each do |ns|
  items << {"apiVersion"=>"networking.k8s.io/v1","kind"=>"NetworkPolicy","metadata"=>{"name"=>"gateway-ingress","namespace"=>ns},"spec"=>{"podSelector"=>{},"policyTypes"=>["Ingress"],"ingress"=>[{"from"=>[{"namespaceSelector"=>{"matchLabels"=>{"kubernetes.io/metadata.name"=>gateway_ns}},"podSelector"=>{"matchLabels"=>gateway_selector}}],"ports"=>[{"port"=>8080,"protocol"=>"TCP"}]}]}}
end
%w[Ingress Egress].each do |direction|
  entry={"namespaceSelector"=>{"matchLabels"=>{"kubernetes.io/metadata.name"=>"ci-jenkins"}}}
  entry["podSelector"]={"matchLabels"=>direction=="Ingress" ? {"cnpl.io/purpose"=>"ci-job"} : required("network","jenkins_controller_selector")}
  items << {"apiVersion"=>"networking.k8s.io/v1","kind"=>"NetworkPolicy","metadata"=>{"name"=>"jenkins-websocket-#{direction.downcase}","namespace"=>"ci-jenkins"},"spec"=>{"podSelector"=>{"matchLabels"=>direction=="Ingress" ? required("network","jenkins_controller_selector") : {"cnpl.io/purpose"=>"ci-job"}},"policyTypes"=>[direction],direction.downcase=>[{(direction=="Ingress" ? "from" : "to")=>[entry],"ports"=>[{"port"=>8080,"protocol"=>"TCP"}]}]}}
end
puts JSON.pretty_generate(label(items))
