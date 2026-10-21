#!/usr/bin/env ruby
require_relative "../lib/config"
verified(required("capi","bundle_file"),required("capi","bundle_sha256"))
items = documents(File.read(required("capi","bundle_file")))
allowed = %w[Cluster VSphereCluster VSphereMachineTemplate KubeadmConfigTemplate KubeadmControlPlane MachineDeployment MachineHealthCheck]
abort "CAPI 包只允许本空间生命周期对象；秘密必须预先建立引用" unless items.all? { |d| allowed.include?(d["kind"]) && d.dig("metadata","namespace") == namespace }
name = required("capi","cluster_name")
abort "集群名必须为本批前缀" unless name == "cnpl06-#{run}"
clusters = items.select { |d| d["kind"] == "Cluster" }
abort "必须只声明一个实验 Cluster" unless clusters.size == 1 && clusters[0].dig("metadata","name") == name
c = clusters[0]
abort "Cluster 网络与规划不符" unless c.dig("spec","clusterNetwork","pods","cidrBlocks") == [required("capi","pod_cidr")] && c.dig("spec","clusterNetwork","services","cidrBlocks") == [required("capi","service_cidr")] && c.dig("spec","controlPlaneEndpoint","host") == required("capi","api_ip")
%w[controlPlaneRef infrastructureRef].each do |key|
  ref = c.fetch("spec").fetch(key)
  abort "Cluster 引用未在本包声明" unless items.any? { |d| d["kind"] == ref["kind"] && d.dig("metadata","name") == ref["name"] }
end
items.each do |d|
  abort "机器模板越出实验 VM 文件夹" if d["kind"] == "VSphereMachineTemplate" && d.dig("spec","template","spec","folder") != required("capi","vm_folder")
  abort "MachineDeployment 指向其他集群" if d["kind"] == "MachineDeployment" && d.dig("spec","clusterName") != name
  d["metadata"]["labels"] = d["metadata"].fetch("labels",{}).merge(labels)
end
emit(items)
