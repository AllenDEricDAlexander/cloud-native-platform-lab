#!/usr/bin/env ruby
# 从资产台账 ops/inventory/hosts.yaml 生成 Ansible Inventory：
#   ops/00-preparation/ansible/inventories/lab/hosts.yml
# 台账是唯一来源；Inventory 只是它的派生视图，不手工修改。台账变更后重新运行本脚本并提交结果。
# 只使用 Ruby 标准库（macOS 自带）。用法：ruby ops/00-preparation/scripts/generate-ansible-inventory.rb
require "yaml"

root = File.expand_path("../../..", __dir__)
ledger = YAML.load_file(File.join(root, "ops/inventory/hosts.yaml"))
target = File.join(root, "ops/00-preparation/ansible/inventories/lab/hosts.yml")

# 台账 role → Inventory 组名（手册第 2 节）
role_groups = { "control_plane" => "control_plane", "infra" => "infra", "storage" => "storage", "worker" => "worker" }
host_keys = %w[fqdn planned_hypervisor network_connection runtime_disk_uuid runtime_disk_scsi_hctl]

groups = {}
ledger.fetch("kubernetes_nodes").each do |node|
  group = role_groups.fetch(node.fetch("role")) { abort "未知角色：#{node["role"]}（#{node["id"]}）" }
  vars = { "ansible_host" => node.fetch("ip") }
  host_keys.each { |k| vars["node_#{k}"] = node[k] unless node[k].nil? }
  (groups[group] ||= {})[node.fetch("id")] = vars
end

# 集群外基础服务：只纳入已开始创建的 VM（vm_status 存在且不是 planned），避免对不存在的主机连接。
services = {}
ledger.fetch("bootstrap_services").each do |svc|
  next if svc["vm_status"].nil? || svc["vm_status"] == "planned"
  vars = { "ansible_host" => svc.fetch("ip"), "node_fqdn" => svc.fetch("fqdn") }
  vars["node_network_connection"] = svc["network_connection"] if svc["network_connection"]
  services[svc.fetch("id")] = vars
end

inventory = {
  "all" => {
    "children" => {
      "k8s_nodes" => { "children" => role_groups.values.each_with_object({}) { |g, h| h[g] = { "hosts" => groups.fetch(g, {}) } } },
      "bootstrap_services" => { "hosts" => services },
    },
  },
}

header = "# 由 ops/00-preparation/scripts/generate-ansible-inventory.rb 从 ops/inventory/hosts.yaml 生成，请勿手改。\n"
body = YAML.dump(inventory).sub(/\A---\n/, "")
# 「数字:数字…」形式（如 SCSI 地址 2:0:1:0）在 Ansible 使用的 PyYAML（YAML 1.1）中会被解析成
# 六十进制整数；Psych 输出时不加引号，这里统一加单引号保证读成字符串。
body = body.gsub(/^(\s*[\w.]+: )(\d+(?::\d+)+)$/) { "#{$1}'#{$2}'" }
File.write(target, header + body)
puts "已生成 #{target.sub(root + "/", "")}：#{groups.values.map(&:size).sum} 台节点（#{groups.map { |g, h| "#{g}=#{h.size}" }.join(" ")}），基础服务 #{services.keys.join(",")}"
