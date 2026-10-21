#!/usr/bin/env ruby
# 只使用标准库；物料未知即失败，不在离线检查中选择版本。
require "json"
require "yaml"
require "digest"
ROOT = File.expand_path("..", __dir__)
REPO = File.expand_path("../..", ROOT)
INPUT = JSON.parse(File.read(ENV.fetch("CNPL04_INPUTS", File.join(ROOT, "inputs.json"))))
def required(*keys)
  value = INPUT.dig(*keys)
  abort "尚未确认输入：#{keys.join('.')}" if value.nil? || value == ""
  value
end
def documents(text)
  ast = Psych.parse_stream(text)
  check = lambda do |n|
    if n.is_a?(Psych::Nodes::Mapping)
      keys = n.children.each_slice(2).map { |k,_| k.respond_to?(:value) ? k.value : nil }.compact
      abort "YAML 重复键" unless keys.uniq.size == keys.size
    end
    (n.respond_to?(:children) ? n.children : nil).to_a.each { |c| check.call(c) }
  end
  check.call(ast)
  YAML.load_stream(text).compact.flat_map { |d| d["kind"] == "List" ? d.fetch("items") : [d] }
end
def list(items)
  {"apiVersion"=>"v1", "kind"=>"List", "items"=>items}
end
def walk(value, &block)
  yield value
  case value
  when Hash then value.each_value { |v| walk(v, &block) }
  when Array then value.each { |v| walk(v, &block) }
  end
end
def digest_image(value)
  abort "镜像必须固定 Harbor Digest" unless value.is_a?(String) && value.match?(%r{\Aharbor\.k8s\.internal\.egon\.top/[a-zA-Z0-9_./-]+@sha256:[a-f0-9]{64}\z})
  value
end
def label(items)
  run = ENV.fetch("RUN", INPUT["run_id"].to_s)
  abort "未设置 run_id" unless run.match?(/\A[a-z][a-z0-9-]{2,19}\z/)
  items.each do |d|
    d["metadata"] ||= {}
    d["metadata"]["labels"] ||= {}
    d["metadata"]["labels"].merge!({"cnpl.io/phase"=>"04","cnpl.io/run"=>run})
  end
  list(items)
end
def verified(path, sha)
  abort "物料文件或 SHA256 无效" unless path.is_a?(String) && path.start_with?("/") && File.file?(path) && sha.is_a?(String) && sha.match?(/\A[a-f0-9]{64}\z/) && Digest::SHA256.file(path).hexdigest == sha
end
if $PROGRAM_NAME == __FILE__
  mode = ARGV.shift
  case mode
  when "source"
    abort "输入 schema 不符" unless INPUT["schema_version"] == 1
    Dir.glob(File.join(ROOT,"**","*")).select { |p| File.file?(p) && !p.include?("/records/") }.each do |path|
      case File.extname(path)
      when ".yaml", ".yml" then documents(File.read(path)) unless path.include?("/templates/")
      when ".json" then JSON.parse(File.read(path))
      end
    end
    puts "PASS JSON/YAML、重复键、输入 schema（未访问网络）"
  when "list" then puts JSON.pretty_generate(label(documents(File.read(ARGV.fetch(0)))))
  when "post-render" then puts YAML.dump(label(documents(STDIN.read)))
  when "manifests"
    data = JSON.parse(File.read(ARGV.fetch(0)))
    data.fetch("items").each do |d|
      abort "Secret 只允许引用预先建立的受控对象" if d["kind"] == "Secret"
      walk(d) { |n| digest_image(n["image"]) if n.is_a?(Hash) && n.key?("image") }
    end
  when "crds"
    data = JSON.parse(File.read(ARGV.fetch(0)))
    data.fetch("items").each do |d|
      d["metadata"]["annotations"] ||= {}
      d["metadata"]["annotations"]["cnpl.io/source-spec-sha256"] = Digest::SHA256.hexdigest(JSON.generate(d.fetch("spec")))
    end
    puts JSON.pretty_generate(data)
  when "material"
    key = ARGV.fetch(0)
    materials = JSON.parse(File.read(ENV.fetch("CNPL04_MATERIALS", File.join(ROOT,"materials.json"))))
    item = materials.fetch("components").fetch(key) { abort "物料未锁定：#{key}" }
    abort "版本未确认" unless item["version"].is_a?(String) && !item["version"].empty?
    verified(item["compatibility_file"], item["compatibility_sha256"])
    lock = YAML.load_file(File.join(REPO,"ops/versions.lock.yaml")).fetch("components").fetch(key) { abort "未登记主版本锁：#{key}" }
    abort "版本与主锁不符" unless lock["version"].to_s == item["version"]
    leaves = []; walk(lock) { |v| leaves << v unless v.is_a?(Hash) || v.is_a?(Array) }
    %w[image sha256].each { |k| abort "物料 Digest/SHA 与主锁不符" if item[k] && !leaves.include?(item[k]) }
    digest_image(item["image"]) if item["image"]
    puts JSON.generate(item)
  when "nodes"
    expected = YAML.load_file(File.join(REPO,"ops/inventory/hosts.yaml")).fetch("kubernetes_nodes").map { |n| [n.fetch("fqdn"),n.fetch("ip")] }.sort
    live = JSON.parse(File.read(ARGV.fetch(0))).fetch("items")
    actual = live.map { |n| [n.dig("metadata","name"),n.fetch("status").fetch("addresses").find { |a| a["type"]=="InternalIP" }.fetch("address")] }.sort
    abort "十节点 FQDN/IP/Ready 基线不符" unless actual == expected && live.all? { |n| n.dig("status","conditions").any? { |c| c["type"]=="Ready" && c["status"]=="True" } }
  when "worker"
    workers = YAML.load_file(File.join(REPO,"ops/inventory/hosts.yaml")).fetch("kubernetes_nodes").select { |n| n["role"]=="worker" }.map { |n| n["fqdn"] }
    abort "构建节点必须是显式登记的 worker FQDN" unless workers.include?(ARGV.fetch(0))
  else abort "未知配置动作"
  end
end
