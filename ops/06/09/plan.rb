#!/usr/bin/env ruby
require_relative "../lib/config"
net = YAML.load_file(File.join(REPO,"ops/inventory/networks.yaml"))
pod = IPAddr.new(required("capi","pod_cidr")); service = IPAddr.new(required("capi","service_cidr"))
reserved = [net.dig("primary_cluster","pod_cidr"),net.dig("primary_cluster","service_cidr"),net.dig("lan","cidr")]+net.dig("lan","vpn_remote_cidrs")
abort "Pod/Service/VPN/主集群网段重叠" if pod.include?(service) || service.include?(pod) || reserved.any? { |s| ip=IPAddr.new(s); [pod,service].any? { |v| ip.include?(v) || v.include?(ip) } }
ips = required("capi","node_ips")+[required("capi","api_ip")]
range = net.fetch("lan").fetch("address_allocations").find { |r| r["purpose"] == "secondary_cluster_reserved" }
abort "节点/API 地址须唯一且在第二集群预留段" unless ips.uniq.size == ips.size && ips.all? { |ip| n=IPAddr.new(ip).to_i; n>=IPAddr.new(range["start"]).to_i && n<=IPAddr.new(range["end"]).to_i }
abort "临时集群名必须带本批前缀" unless required("capi","cluster_name") == "cnpl06-#{run}"
verified(required("capi","capacity_file"),required("capi","capacity_sha256"))
capacity = JSON.parse(File.read(required("capi","capacity_file")))
abort "容量/DHCP/模板/许可证/恢复空间未现场核实" unless %w[primary_minimum_preserved storage_recovery_headroom dhcp_conflicts_absent vsphere_license_verified template_verified vpn_routes_reviewed].all? { |k| capacity[k] == true } && capacity["node_ips"] == INPUT.dig("capi","node_ips") && capacity["api_ip"] == INPUT.dig("capi","api_ip") && capacity["vm_folder"] == required("capi","vm_folder")
puts JSON.pretty_generate({"cluster"=>required("capi","cluster_name"),"pod_cidr"=>pod.to_s,"service_cidr"=>service.to_s,"ips"=>ips,"vm_folder"=>required("capi","vm_folder"),"runtime_accepted"=>false})
