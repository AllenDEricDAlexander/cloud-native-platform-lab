#!/usr/bin/env ruby
# 与现有 inventory 生成器一致，仅使用 Ruby 标准库；不访问网络。
require "json"
require "yaml"
require "digest"
root = File.expand_path("..", __dir__)
def reject(message)
  abort "失败：#{message}"
end
def walk(node, &block)
  yield node
  case node
  when Hash then node.each_value { |v| walk(v, &block) }
  when Array then node.each { |v| walk(v, &block) }
  end
end
def documents(path)
  stream = Psych.parse_stream(File.read(path))
  walk_ast = lambda do |node|
    if node.is_a?(Psych::Nodes::Mapping)
      keys = node.children.each_slice(2).map { |k, _| k.respond_to?(:value) ? k.value : nil }.compact
      reject("重复 YAML 键：#{path}") unless keys.uniq.size == keys.size
    end
    (node.respond_to?(:children) ? node.children : nil).to_a.each { |n| walk_ast.call(n) }
  end
  walk_ast.call(stream)
  YAML.load_stream(File.read(path)).compact
end
mode = ARGV.shift
case mode
when "images", "images-json"
  path = ARGV.fetch(0)
  docs = mode == "images-json" || File.extname(path) == ".json" ? [JSON.parse(File.read(path))] : documents(path)
  docs.each do |doc|
    walk(doc) do |node|
      next unless node.is_a?(Hash)
      keys = ["image"]
      keys << "imageName" if node.key?("instances") && node.key?("storage")
      keys.each do |key|
        next unless node[key].is_a?(String)
        reject("渲染镜像未锁内网 Digest") unless node[key].match?(%r{\Aharbor\.k8s\.internal\.egon\.top/.+@sha256:[0-9a-f]{64}\z})
      end
    end
  end
when "devices"
  ledger = YAML.load_file(File.join(root, "../inventory/hosts.yaml"))
  resources = YAML.load_file(File.join(root, "../inventory/resources.yaml"))
  list = JSON.parse(File.read(ARGV.fetch(0))).fetch("devices")
  reject("必须显式批准设备初始化") unless resources.dig("storage", "osd_initialization_allowed") == true
  reject("需要三台存储主机的独立设备") unless list.map { |d| d["host"] }.uniq.sort == %w[storage01 storage02 storage03]
  hosts = ledger.fetch("kubernetes_nodes").select { |h| h["role"] == "storage" }
  domains = hosts.map { |h| h["actual_hypervisor"] }
  reject("三物理故障域未核实") unless domains.compact.uniq.size == 3
  list.each do |d|
    host = hosts.find { |h| h["id"] == d["host"] }
    reject("设备主机不在台账") unless host
    reject("设备未批准") unless d["approved"] == true && d["contains_data"] == false
    reject("必须使用稳定的整盘 ID") unless d.fetch("stable_id").match?(%r{\A/dev/disk/by-id/[a-zA-Z0-9_.:+-]+\z}) && !d["stable_id"].match?(/-part\d+\z/)
    reject("设备必须与主台账相同") unless host.fetch("osd_device_ids").include?(d["stable_id"])
    reject("盘位映射不完整") unless %w[datastore backing_disk raid evidence_file evidence_sha256].all? { |k| d[k].is_a?(String) && !d[k].empty? }
    reject("物理域不符") unless d["hypervisor"] == host["actual_hypervisor"]
    reject("设备字节数无效") unless d["bytes"].is_a?(Integer) && d["bytes"] > 0
    reject("盘位证据缺失或 SHA 不符") unless File.file?(d["evidence_file"]) && Digest::SHA256.file(d["evidence_file"]).hexdigest == d["evidence_sha256"]
  end
  pairs = list.map { |d| [d["host"], d["stable_id"]] }
  reject("设备重复") unless pairs.uniq.size == pairs.size
  raw = list.sum { |d| d["bytes"] }
  # 三域损失一个后不能恢复三份独立副本；只报告预算，不作容量承诺。
  puts JSON.pretty_generate({raw_bytes: raw, theoretical_replica3_bytes: raw / 3, recommended_max_bytes: (raw / 3 * 0.65).floor, full_redundancy_after_domain_loss: false})
when "source"
  files = Dir.glob(File.join(root, "**", "*")).select { |p| File.file?(p) && !p.include?("/records/") && !p.include?("/private/") && !p.include?("/bin/") }
  files.each do |path|
    case File.extname(path)
    when ".yaml", ".yml" then documents(path)
    when ".json" then JSON.parse(File.read(path))
    end
    reject("不允许交付 Python 或 Jinja 模板：#{path}") if path.end_with?(".py", ".j2")
  end
  config = JSON.parse(File.read(ENV.fetch("CNPL03_INPUTS", File.join(root, "inputs.json"))))
  reject("输入 schema 不匹配") unless config["schema_version"] == 1
  reject("水位阈值无效") unless (1..75).cover?(config.dig("ceph", "max_used_percent"))
  fault = config.fetch("fault")
  reject("故障时限无效") unless (5..60).cover?(fault["duration_seconds"]) && fault["watchdog_seconds"] > fault["duration_seconds"] && fault["watchdog_seconds"] <= 180
  puts "PASS JSON/YAML 解析、重复键、离线配置契约；现场未验证"
else reject("未知走查模式")
end
