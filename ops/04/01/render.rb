#!/usr/bin/env ruby
require_relative "../lib/config"
items = []
%w[apps-dev apps-staging apps-prod-like ci-build ci-gitlab ci-jenkins].each do |ns|
  items << {"apiVersion"=>"v1","kind"=>"Namespace","metadata"=>{"name"=>ns,"labels"=>{"pod-security.kubernetes.io/enforce"=>"restricted"}}}
  items << {"apiVersion"=>"v1","kind"=>"ResourceQuota","metadata"=>{"name"=>"budget","namespace"=>ns},"spec"=>{"hard"=>{"requests.cpu"=>"2","requests.memory"=>"4Gi","limits.cpu"=>"4","limits.memory"=>"8Gi","requests.ephemeral-storage"=>"8Gi","persistentvolumeclaims"=>"4","requests.storage"=>"30Gi","pods"=>"12"}}}
  items << {"apiVersion"=>"v1","kind"=>"LimitRange","metadata"=>{"name"=>"defaults","namespace"=>ns},"spec"=>{"limits"=>[{"type"=>"Container","defaultRequest"=>{"cpu"=>"100m","memory"=>"128Mi","ephemeral-storage"=>"256Mi"},"default"=>{"cpu"=>"1","memory"=>"1Gi","ephemeral-storage"=>"2Gi"}}]}}
  items << {"apiVersion"=>"v1","kind"=>"ServiceAccount","metadata"=>{"name"=>"application","namespace"=>ns},"automountServiceAccountToken"=>false}
  items << {"apiVersion"=>"networking.k8s.io/v1","kind"=>"NetworkPolicy","metadata"=>{"name"=>"default-deny","namespace"=>ns},"spec"=>{"podSelector"=>{},"policyTypes"=>["Ingress","Egress"]}}
  items << {"apiVersion"=>"networking.k8s.io/v1","kind"=>"NetworkPolicy","metadata"=>{"name"=>"dns","namespace"=>ns},"spec"=>{"podSelector"=>{},"policyTypes"=>["Egress"],"egress"=>[{"to"=>[{"namespaceSelector"=>{"matchLabels"=>{"kubernetes.io/metadata.name"=>"kube-system"}},"podSelector"=>{"matchLabels"=>{"k8s-app"=>"kube-dns"}}}],"ports"=>[{"protocol"=>"UDP","port"=>53},{"protocol"=>"TCP","port"=>53}]}]}}
  next unless ns.start_with?("ci-")
  # 固定三台仓库地址来自主台账；禁止 CI 默认任意外网出口。
  hosts = YAML.load_file(File.join(REPO,"ops/inventory/hosts.yaml")).fetch("bootstrap_services").select { |h| %w[gitlab harbor nexus].include?(h["id"]) }
  items << {"apiVersion"=>"networking.k8s.io/v1","kind"=>"NetworkPolicy","metadata"=>{"name"=>"internal-repositories","namespace"=>ns},"spec"=>{"podSelector"=>{},"policyTypes"=>["Egress"],"egress"=>[{"to"=>hosts.map { |h| {"ipBlock"=>{"cidr"=>"#{h.fetch('ip')}/32"}} },"ports"=>[{"protocol"=>"TCP","port"=>443}]}]}}
end
puts JSON.pretty_generate(label(items))
