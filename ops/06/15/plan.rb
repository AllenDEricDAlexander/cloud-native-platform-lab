#!/usr/bin/env ruby
require_relative "../lib/config"
versions = %w[source_version target_version].map { |k| required("upgrade",k) }
parsed = versions.map { |v| v.match(/\Av(1)\.(\d+)\.(\d+)\z/) || abort("版本须为精确 v1.x.y") }
abort "只支持相邻次版本升级" unless parsed[1][2].to_i == parsed[0][2].to_i+1
%w[matrix rehearsal freeze].each { |key| verified(required("upgrade","#{key}_file"),required("upgrade","#{key}_sha256")) }
matrix = JSON.parse(File.read(required("upgrade","matrix_file")))
abort "兼容矩阵源/目标不符" unless matrix["source_version"] == versions[0] && matrix["target_version"] == versions[1]
abort "兼容矩阵不全" unless %w[etcd containerd cilium ceph rook csi gateway operators api_deprecations].all? { |key| matrix.fetch("components").fetch(key,false) == true }
rehearsal = JSON.parse(File.read(required("upgrade","rehearsal_file")))
abort "隔离预演未通过" unless rehearsal["isolated"] == true && rehearsal["target_version"] == versions[1] && rehearsal["business_data_verified"] == true
nodes = YAML.load_file(File.join(REPO,"ops/inventory/hosts.yaml")).fetch("kubernetes_nodes")
order = %w[control_plane worker infra storage].flat_map { |role| nodes.select { |n| n["role"] == role }.map { |n| n["fqdn"] } }
puts JSON.pretty_generate({"source"=>versions[0],"target"=>versions[1],"order"=>order,"one_node_at_a_time"=>true,"runtime_accepted"=>false})
