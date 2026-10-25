#!/usr/bin/env ruby
# 不输出身份密钥。connection bundle 是同版本官方导入结果的结构化转存。
require "json"
require "base64"
bundle = begin
  JSON.parse(File.read(ARGV.fetch(0)))
rescue JSON::ParserError
  abort "连接材料 JSON 无效；为保护密钥不回显原文"
end
abort "需要 Kubernetes List 结构" unless bundle["apiVersion"] == "v1" && bundle["kind"] == "List"
abort "FSID 不匹配" unless bundle.fetch("fsid") == ARGV.fetch(1)
items = bundle.fetch("items")
names = %w[rook-ceph-mon rook-ceph-mon-endpoints rook-ceph-csi-config csi-rbd-node csi-rbd-provisioner csi-cephfs-node csi-cephfs-provisioner]
required = names - %w[rook-ceph-csi-config]
names += %w[rook-csi-rbd-node rook-csi-rbd-provisioner rook-csi-cephfs-node rook-csi-cephfs-provisioner]
abort "连接材料缺少必需对象" unless (required - items.map { |x| x.dig("metadata", "name") }).empty?
abort "重复连接对象" unless items.map { |x| [x["kind"],x.dig("metadata","name")] }.uniq.size == items.size
items.each do |item|
  abort "连接材料超出作用域" unless %w[Secret ConfigMap].include?(item["kind"]) && names.include?(item.dig("metadata", "name")) && item.dig("metadata", "namespace") == "cnpl03-external"
  data = item.fetch("data", {}).merge(item.fetch("stringData", {}))
  if item["kind"] == "Secret"
    data.each do |key,value|
      plain = item.fetch("stringData", {}).key?(key) ? value : Base64.strict_decode64(value)
      abort "禁止导入管理员密钥或身份" if (key == "admin-secret" && !plain.empty?) || (%w[userID adminID ceph-username].include?(key) && plain.match?(/\A(?:client\.)?admin\z/))
    end
    if item.dig("metadata", "name") == "rook-ceph-mon"
      name = data["ceph-username"]
      name = Base64.strict_decode64(name) if name && !item.fetch("stringData", {}).key?("ceph-username")
      abort "必须使用受限健康检查身份" if name.nil? || name.empty?
    end
  end
end
puts "PASS 连接材料结构、FSID 和无管理员身份；实际 caps 需现场审计"
