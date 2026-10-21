#!/usr/bin/env ruby
# 标准库共享输入和清单检查；require 不执行外部命令。
require "json"
require "yaml"
require "digest"
require "ipaddr"
require "uri"
class UniqueKeys < Hash
  def []=(key, value)
    abort "JSON 重复键" if key?(key)
    super
  end
end
def parse_json(text)
  JSON.parse(text,object_class:UniqueKeys)
end
P06 = File.expand_path("..", __dir__)
REPO = File.expand_path("../..", P06)
INPUT = parse_json(File.read(ENV.fetch("CNPL06_INPUTS", File.join(P06, "inputs.json"))))
def required(*path)
  v = INPUT.dig(*path)
  abort "输入未确认：#{path.join('.')}" if v.nil? || v == "" || v == []
  v
end
def verified(path, sha)
  abort "文件/SHA256 无效" unless path.is_a?(String) && path.start_with?("/") && File.file?(path) && !File.symlink?(path) && sha.to_s.match?(/\A[a-f0-9]{64}\z/) && Digest::SHA256.file(path).hexdigest == sha
end
def documents(text)
  ast = Psych.parse_stream(text)
  visit = lambda do |n|
    if n.is_a?(Psych::Nodes::Mapping)
      keys = n.children.each_slice(2).map { |k,_| k.respond_to?(:value) ? k.value : nil }.compact
      abort "YAML 重复键" unless keys.uniq.size == keys.size
    end
    abort "不接受 YAML alias" if n.is_a?(Psych::Nodes::Alias)
    (n.respond_to?(:children) ? n.children : nil).to_a.each { |c| visit.call(c) }
  end
  visit.call(ast)
  YAML.load_stream(text).compact.flat_map { |d| d.is_a?(Hash) && d["kind"] == "List" ? d.fetch("items") : [d] }
end
def walk(v, &block)
  yield v
  case v
  when Hash then v.each_value { |x| walk(x, &block) }
  when Array then v.each { |x| walk(x, &block) }
  end
end
def run
  v = required("run_id")
  abort "run_id 需为 3-20 位小写字母/数字/横线" unless v.match?(/\A[a-z][a-z0-9-]{2,19}\z/)
  v
end
def stage
  v = ENV.fetch("STAGE")
  abort "子阶段编号无效" unless v.match?(/\A(0[1-9]|1[0-7])\z/)
  v
end
def namespace
  "cnpl06-#{stage}-#{run}"
end
def labels
  {"cnpl.io/phase"=>"06", "cnpl.io/stage"=>stage, "cnpl.io/run"=>run}
end
def object(api, kind, name, spec = nil, ns = namespace)
  d = {"apiVersion"=>api, "kind"=>kind, "metadata"=>{"name"=>name, "labels"=>labels.dup}}
  d["metadata"]["namespace"] = ns if ns
  d["spec"] = spec if spec
  d
end
def digest_image(v)
  abort "镜像须固定内网 Harbor Digest" unless v.to_s.match?(%r{\Aharbor\.k8s\.internal\.egon\.top/[a-zA-Z0-9_./-]+@sha256:[a-f0-9]{64}\z})
  v
end
def image(key)
  digest_image(required("images", key))
end
def security
  {"runAsNonRoot"=>true,"runAsUser"=>10001,"runAsGroup"=>10001,"fsGroup"=>10001,"seccompProfile"=>{"type"=>"RuntimeDefault"}}
end
def container(name, ref, command = nil)
  c = {"name"=>name,"image"=>digest_image(ref),"imagePullPolicy"=>"IfNotPresent", "resources"=>{"requests"=>{"cpu"=>"100m","memory"=>"128Mi"},"limits"=>{"cpu"=>"500m","memory"=>"256Mi"}}, "securityContext"=>{"allowPrivilegeEscalation"=>false,"readOnlyRootFilesystem"=>true,"capabilities"=>{"drop"=>["ALL"]}}}
  c["command"] = command if command
  c
end
def podspec(containers)
  {"automountServiceAccountToken"=>false,"serviceAccountName"=>"app","securityContext"=>security,"containers"=>containers}
end
def deployment(name, key = "http", replicas = 2)
  c = container("app", image(key))
  c["ports"] = [{"containerPort"=>8080}]
  c["readinessProbe"] = {"httpGet"=>{"path"=>"/health","port"=>8080},"periodSeconds"=>3}
  c["livenessProbe"] = {"httpGet"=>{"path"=>"/health","port"=>8080},"initialDelaySeconds"=>10,"periodSeconds"=>10}
  object("apps/v1","Deployment",name,{"replicas"=>replicas,"selector"=>{"matchLabels"=>{"app"=>name}},"template"=>{"metadata"=>{"labels"=>labels.merge("app"=>name)},"spec"=>podspec([c])}})
end
def service(name)
  object("v1","Service",name,{"selector"=>{"app"=>name},"ports"=>[{"port"=>8080,"targetPort"=>8080}]})
end
def job(name, command, key = "probe")
  object("batch/v1","Job",name,{"backoffLimit"=>0,"activeDeadlineSeconds"=>180,"ttlSecondsAfterFinished"=>3600,"template"=>{"metadata"=>{"labels"=>labels.merge("app"=>name)},"spec"=>podspec([container("probe", image(key), command)]).merge("restartPolicy"=>"Never")}})
end
def base
  ns = object("v1","Namespace",namespace,nil,nil)
  ns["metadata"]["labels"].merge!({"pod-security.kubernetes.io/enforce"=>"restricted","pod-security.kubernetes.io/audit"=>"restricted","pod-security.kubernetes.io/warn"=>"restricted"})
  sa = object("v1","ServiceAccount","app").merge("automountServiceAccountToken"=>false)
  quota = object("v1","ResourceQuota","budget",{"hard"=>{"requests.cpu"=>"4","requests.memory"=>"8Gi","limits.cpu"=>"8","limits.memory"=>"16Gi","pods"=>"20","requests.storage"=>"30Gi"}})
  deny = object("networking.k8s.io/v1","NetworkPolicy","default-deny",{"podSelector"=>{},"policyTypes"=>["Ingress","Egress"]})
  local = object("networking.k8s.io/v1","NetworkPolicy","local-and-dns",{"podSelector"=>{},"policyTypes"=>["Ingress","Egress"],"ingress"=>[{"from"=>[{"podSelector"=>{}}]}],"egress"=>[{"to"=>[{"podSelector"=>{}}]},{"to"=>[{"namespaceSelector"=>{"matchLabels"=>{"kubernetes.io/metadata.name"=>"kube-system"}},"podSelector"=>{"matchLabels"=>{"k8s-app"=>"kube-dns"}}}],"ports"=>[{"protocol"=>"UDP","port"=>53},{"protocol"=>"TCP","port"=>53}]}]})
  INPUT.fetch("network",{}).fetch("egress",[]).each do |e|
    next unless e.fetch("stage") == stage
    ip = IPAddr.new(e.fetch("cidr"))
    abort "出口须限定内网地址与端口" unless ["10.0.0.0/8","172.16.0.0/12","192.168.0.0/16"].any? { |n| IPAddr.new(n).include?(ip) } && e["ports"].is_a?(Array) && !e["ports"].empty? && e["ports"].all? { |p| p["port"].is_a?(Integer) && (1..65535).include?(p["port"]) && ["TCP","UDP"].include?(p["protocol"]) }
    local["spec"]["egress"] << {"to"=>[{"ipBlock"=>{"cidr"=>e["cidr"]}}],"ports"=>e["ports"]}
  end
  INPUT.fetch("network",{}).fetch("ingress",[]).each do |e|
    next unless e.fetch("stage") == stage
    ns_name = e.fetch("namespace"); pod_labels = e.fetch("pod_labels"); ports = e.fetch("ports")
    abort "入口须限定命名空间、非空 Pod 标签和端口" unless ns_name.is_a?(String) && ns_name.match?(/\A[a-z0-9][a-z0-9-]{0,62}\z/) && pod_labels.is_a?(Hash) && !pod_labels.empty? && pod_labels.values.all? { |v| v.is_a?(String) && !v.empty? && !v.include?("*") } && ports.is_a?(Array) && !ports.empty? && ports.all? { |p| p["port"].is_a?(Integer) && (1..65535).include?(p["port"]) && %w[TCP UDP].include?(p["protocol"]) }
    local["spec"]["ingress"] << {"from"=>[{"namespaceSelector"=>{"matchLabels"=>{"kubernetes.io/metadata.name"=>ns_name}},"podSelector"=>{"matchLabels"=>pod_labels}}],"ports"=>ports}
  end
  [ns,sa,quota,deny,local]
end
def emit(items)
  puts JSON.pretty_generate({"apiVersion"=>"v1","kind"=>"List","items"=>items})
end
def image_locks
  lock = YAML.load_file(File.join(REPO,"ops/versions.lock.yaml")).fetch("components")
  values = []
  lock.each_value do |c|
    next unless c.is_a?(Hash) && c["version"] && !c["version"].to_s.empty?
    walk(c) { |v| values << v if v.is_a?(String) && v.include?("@sha256:") }
  end
  values
end
def check_manifests(items, allowed_namespaces, allowed_cluster, locked)
  images = []
  items.each do |d|
    abort "清单对象格式错误" unless d.is_a?(Hash) && d["apiVersion"].to_s.match?(%r{\A[a-zA-Z0-9./-]+\z}) && d["kind"].to_s.match?(/\A[A-Za-z][A-Za-z0-9]*\z/)
    m = d.fetch("metadata")
    abort "必须使用固定资源名" unless m["name"].to_s.match?(/\A[a-z0-9][a-z0-9.-]{0,252}\z/) && !m["generateName"]
    abort "Secret 只允许引用预先创建的对象" if d["kind"] == "Secret"
    abort "清单含 status/受管字段" if d.key?("status") || m.key?("managedFields") || m.key?("uid")
    ns = m["namespace"]
    ref = "#{d['kind']}/#{m['name']}"
    abort "清单越出已审核作用域：#{ref}" unless ns ? allowed_namespaces.include?(ns) : (d["kind"] == "Namespace" ? allowed_namespaces.include?(m["name"]) : allowed_cluster.include?(ref))
    abort "禁止修改系统 Namespace" if d["kind"] == "Namespace" && %w[default kube-system kube-public kube-node-lease].include?(m["name"])
    walk(d) do |v|
      next unless v.is_a?(Hash)
      if v["image"].is_a?(String)
        ref_image = digest_image(v["image"]); images << ref_image
        abort "镜像未在主版本锁确认" if locked && !image_locks.include?(ref_image)
      end
      if v["url"].is_a?(String) && v["url"].start_with?("docker://")
        ref_image = digest_image(v["url"].delete_prefix("docker://")); images << ref_image
        abort "磁盘镜像未在主版本锁确认" if locked && !image_locks.include?(ref_image)
      end
      %w[password clientSecret client_secret privateKey secret secret_key access_key token].each { |k| abort "清单不能内嵌凭据" if v.key?(k) && v[k].is_a?(String) && !v[k].empty? }
    end
    m["labels"] = m.fetch("labels",{}).merge(labels)
  end
  abort "重复资源" unless items.map { |d| [d["apiVersion"],d["kind"],d.dig("metadata","namespace"),d.dig("metadata","name")] }.uniq.size == items.size
  images
end
if $PROGRAM_NAME == __FILE__
  case ARGV.shift
  when "source"
    abort "输入 schema 无效" unless INPUT["schema_version"] == 1
    Dir.glob(File.join(P06,"**","*")).select { |p| File.file?(p) && !p.include?("/records/") }.each do |p|
      case File.extname(p)
      when ".json" then parse_json(File.read(p))
      when ".yaml", ".yml" then documents(File.read(p))
      end
    end
    puts "PASS JSON/YAML/重复键检查（离线）"
  when "private"
    p = ARGV.fetch(0); r = File.realpath(p); s = File.stat(r)
    abort "私有文件须在仓库外、当前用户所有且权限为 0600/0400" unless p.start_with?("/") && !File.symlink?(p) && !r.start_with?(REPO+"/") && s.file? && s.size>0 && s.uid == Process.uid && [0600,0400].include?(s.mode & 0777)
  when "material"
    key = ARGV.fetch(0)
    m = parse_json(File.read(ENV.fetch("CNPL06_MATERIALS",File.join(P06,"materials.json")))).fetch("components").fetch(key) { abort "物料未锁定：#{key}" }
    abort "物料范围/就绪检查缺失" unless m["namespaces"].is_a?(Array) && !m["namespaces"].empty? && m["namespaces"].all? { |v| v.is_a?(String) && v.match?(/\A[a-z0-9][a-z0-9-]{0,62}\z/) } && m["cluster_resources"].is_a?(Array) && m["wait"].is_a?(Array) && !m["wait"].empty?
    abort "物料就绪条件无效" unless m["wait"].all? { |w| w.is_a?(Hash) && m["namespaces"].include?(w["namespace"]) && w["resource"].to_s.match?(%r{\A[a-zA-Z0-9.-]+/[a-z0-9][a-z0-9.-]*\z}) && w["condition"].to_s.match?(/\A[A-Za-z]+\z/) }
    verified(m["compatibility_file"],m["compatibility_sha256"])
    verified(m["manifest_file"],m["manifest_sha256"])
    lock = YAML.load_file(File.join(REPO,"ops/versions.lock.yaml")).fetch("components").fetch(key) { abort "未登记主版本锁：#{key}" }
    abort "组件版本不符" unless m["version"].is_a?(String) && m["version"] != "" && lock["version"].to_s == m["version"]
    leaves = []; walk(lock) { |v| leaves << v if v.is_a?(String) }
    abort "安装清单 SHA 未在主版本锁登记" unless leaves.include?(m["manifest_sha256"])
    puts JSON.generate(m)
  when "prepare"
    items = documents(File.read(ARGV.fetch(0)))
    scope = JSON.parse(File.read(ARGV.fetch(1)))
    check_manifests(items,scope.fetch("namespaces"),scope.fetch("cluster_resources",[]),true)
    emit(items)
  when "nodes"
    target = ARGV.fetch(0); nodes = JSON.parse(File.read(ARGV.fetch(1))).fetch("items")
    expected = if target == "primary"
      YAML.load_file(File.join(REPO,"ops/inventory/hosts.yaml")).fetch("kubernetes_nodes").map { |n| {"name"=>n.fetch("fqdn"),"ip"=>n.fetch("ip")} }
    else
      required("clusters",target,"nodes")
    end
    actual = nodes.map { |n| {"name"=>n.dig("metadata","name"),"ip"=>n.fetch("status").fetch("addresses").find { |a| a["type"]=="InternalIP" }.fetch("address")} }
    abort "节点名称/IP/Ready 基线不符" unless actual.sort_by { |n| n["name"] } == expected.sort_by { |n| n["name"] } && nodes.all? { |n| n.dig("status","conditions").any? { |c| c["type"]=="Ready" && c["status"]=="True" } }
  else abort "未知配置动作"
  end
end
