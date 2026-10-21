#!/usr/bin/env ruby
# 标准库配置与离线检查；部署物料必须同时匹配主锁和本地校验值。
require "json"
require "yaml"
require "digest"
require "uri"
ROOT = File.expand_path("..", __dir__)
REPO = File.expand_path("../..", ROOT)
INPUT = JSON.parse(File.read(ENV.fetch("CNPL05_INPUTS", File.join(ROOT, "inputs.json"))))
def required(*keys)
  value = INPUT.dig(*keys)
  abort "尚未确认输入：#{keys.join('.')}" if value.nil? || value == "" || value == []
  value
end
def verified(path, checksum)
  abort "文件/SHA256 无效" unless path.is_a?(String) && path.start_with?("/") && File.file?(path) && !File.symlink?(path) && checksum.to_s.match?(/\A[a-f0-9]{64}\z/) && Digest::SHA256.file(path).hexdigest == checksum
  path
end
def documents(text)
  check = lambda do |node|
    if node.is_a?(Psych::Nodes::Mapping)
      keys = node.children.each_slice(2).map { |key,_| key.respond_to?(:value) ? key.value : nil }
      abort "YAML 重复键" unless keys.uniq.length == keys.length
    end
    (node.respond_to?(:children) ? node.children : nil).to_a.each { |child| check.call(child) }
  end
  check.call(Psych.parse_stream(text))
  YAML.load_stream(text).compact.flat_map { |d| d.is_a?(Hash) && d["kind"] == "List" ? d.fetch("items") : [d] }
end
def walk(value, &block)
  yield value
  case value
  when Hash then value.each_value { |v| walk(v, &block) }
  when Array then value.each { |v| walk(v, &block) }
  end
end
def image(key)
  material(key).fetch("image")
end
def material(key)
  data = JSON.parse(File.read(ENV.fetch("CNPL05_MATERIALS", File.join(ROOT,"materials.json"))))
  item = data.fetch("components").fetch(key) { abort "物料未锁定：#{key}" }
  lock = YAML.load_file(File.join(REPO,"ops/versions.lock.yaml")).fetch("components").fetch(key) { abort "未登记主版本锁：#{key}" }
  abort "版本与主锁不符" unless item["version"].is_a?(String) && !item["version"].empty? && lock["version"].to_s == item["version"]
  verified(item["compatibility_file"], item["compatibility_sha256"])
  leaves = []; walk(lock) { |v| leaves << v unless v.is_a?(Hash) || v.is_a?(Array) }
  %w[sha256 image].each { |k| abort "物料 SHA/Digest 未登记主锁" if item[k] && !leaves.include?(item[k]) }
  if item["image"]
    abort "镜像必须固定 Harbor Digest" unless item["image"].match?(%r{\Aharbor\.k8s\.internal\.egon\.top/[\w./-]+@sha256:[a-f0-9]{64}\z})
  end
  verified(item["file"], item["sha256"]) if item["file"]
  item
end
def object(kind, name, ns, spec = {}, api = "v1")
  {"apiVersion"=>api,"kind"=>kind,"metadata"=>{"name"=>name,"namespace"=>ns}}.merge(spec)
end
def labeled(items)
  run = required("run_id")
  abort "run_id 格式无效" unless run.match?(/\A[a-z][a-z0-9-]{2,19}\z/)
  items.each do |d|
    d["metadata"] ||= {}; d["metadata"]["labels"] ||= {}
    d["metadata"]["labels"].merge!({"cnpl.io/phase"=>"05", "cnpl.io/run"=>run})
  end
  {"apiVersion"=>"v1","kind"=>"List","items"=>items}
end
def manifests!(items)
  items.each do |d|
    abort "仅支持有名对象" unless d.is_a?(Hash) && d.dig("metadata","name")
    abort "Secret 必须由受控引用提供" if d["kind"] == "Secret"
    walk(d) do |v|
      next unless v.is_a?(Hash) && v.key?("image")
      abort "镜像必须固定 Harbor Digest" unless v["image"].is_a?(String) && v["image"].match?(%r{\Aharbor\.k8s\.internal\.egon\.top/[\w./-]+@sha256:[a-f0-9]{64}\z})
    end
  end
end
def hosts
  inventory = YAML.load_file(File.join(REPO,"ops/00-preparation/ansible/inventories/lab/hosts.yml"))
  result = {}
  visit = lambda do |g|
    g.fetch("hosts", {}).each { |id,h| result[id] = {"id"=>id,"fqdn"=>h.fetch("node_fqdn"),"ip"=>h.fetch("ansible_host")} }
    g.fetch("children",{}).each_value { |c| visit.call(c) }
  end
  visit.call(inventory.fetch("all"))
  abort "监控 Inventory 必须是既有 16 台 VM" unless result.size == 16 && result.dig("build01","ip") == "192.168.9.160"
  source = YAML.load_file(File.join(REPO,"ops/inventory/hosts.yaml"))
  expected = %w[kubernetes_nodes bootstrap_services lab_clients].flat_map { |k| source.fetch(k) }.select { |h| result.key?(h["id"]) }.map { |h| [h["id"],h["fqdn"],h["ip"]] }.sort
  abort "派生 Inventory 与主台账不符，请先重新生成" unless result.values.map { |h| [h["id"],h["fqdn"],h["ip"]] }.sort == expected
  result.values.sort_by { |h| h["ip"].split('.').map(&:to_i) }
end
if $PROGRAM_NAME == __FILE__
  case ARGV.shift
  when "source"
    abort "输入 schema 不符" unless INPUT["schema_version"] == 1
    Dir.glob(File.join(ROOT,"**","*")).select { |p| File.file?(p) && !p.include?("/records/") }.each do |path|
      case File.extname(path)
      when ".json" then JSON.parse(File.read(path))
      when ".yaml", ".yml" then documents(File.read(path))
      end
    end
    hosts
    puts "PASS JSON/YAML、重复键、16 台台账一致性（离线）"
  when "hosts" then puts JSON.pretty_generate(hosts)
  when "material" then puts JSON.generate(material(ARGV.fetch(0)))
  when "list" then puts JSON.pretty_generate(labeled(documents(File.read(ARGV.fetch(0)))))
  when "post-render" then puts YAML.dump(labeled(documents(STDIN.read)))
  when "manifests" then manifests!(documents(File.read(ARGV.fetch(0))))
  when "nodes"
    live = JSON.parse(File.read(ARGV.fetch(0))).fetch("items")
    expected = YAML.load_file(File.join(REPO,"ops/inventory/hosts.yaml")).fetch("kubernetes_nodes").map { |h| [h["fqdn"],h["ip"]] }.sort
    actual = live.map { |h| [h.dig("metadata","name"),h.dig("status","addresses").find { |a| a["type"]=="InternalIP" }.fetch("address")] }.sort
    abort "十节点 FQDN/IP/Ready 基线不符" unless actual==expected && live.all? { |h| h.dig("status","conditions").any? { |c| c["type"]=="Ready" && c["status"]=="True" } }
  else abort "未知配置动作"
  end
end
