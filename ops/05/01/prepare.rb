#!/usr/bin/env ruby
require_relative "../lib/config"
require "ipaddr"
begin
  vars = JSON.parse(File.read(ARGV.fetch(0)))
rescue JSON::ParserError
  abort "私有 Zabbix JSON 无效（不输出原文）"
end
action = ARGV.fetch(1)
list = hosts
if %w[install configure].include?(action)
  psks = vars.fetch("zbx_psks")
  abort "每机 PSK 必须完整、有效且不同" unless psks.keys.sort == list.map { |h| h["id"] }.sort && psks.values.uniq.size == 16 && psks.values.all? { |v| v.is_a?(String) && v.match?(/\A[a-fA-F0-9]{64}\z/) }
end
if action=="install"
  vars.fetch("zbx_web_sources").each { |s| abort "仅允许管理网段 IPv4" unless IPAddr.new(s).ipv4? && IPAddr.new("192.168.9.0/24").include?(IPAddr.new(s)) }
end
(action=="install" ? %w[zbx_ca_file zbx_tls_cert_file zbx_tls_key_file] : %w[zbx_ca_file]).each do |key|
  p = vars.fetch(key)
  abort "证书文件不可用" unless File.file?(p) && p.start_with?("/") && !File.realpath(p).start_with?(REPO+"/")
end
out = {}
if action == "install"
  key_stat = File.stat(vars.fetch("zbx_tls_key_file"))
  abort "私钥权限无效" unless key_stat.uid == Process.uid && [0600,0400].include?(key_stat.mode & 0777)
  out["zbx_firewall_rules"] = list.map { |h| {"source"=>h["ip"]+"/32","port"=>"10051"} } + vars.fetch("zbx_web_sources").map { |s| {"source"=>s,"port"=>"8443"} }
  m = material("zabbix")
  abort "本阶段基线为 Zabbix 7.0 LTS 精确补丁" unless m.fetch("version").match?(/\A7\.0\.\d+\z/)
  packages = JSON.parse(File.read(m.fetch("file")))
  %w[server_packages agent_packages keys].each do |group|
    abort "空的 RPM/密钥清单" if packages.fetch(group).empty?
    packages.fetch(group).each { |p| verified(p["file"],p["sha256"]) }
  end
  %w[server_packages agent_packages].each do |group|
    packages.fetch(group).each { |p| abort "RPM NEVRA 格式无效" unless p.fetch("nevra").match?(/\A[\w+.-]+-\d+:[\w+~.-]+\.[\w]+\z/) }
  end
  out.merge!({"zbx_server_packages"=>packages.fetch("server_packages"),"zbx_agent_packages"=>packages.fetch("agent_packages"),"zbx_package_keys"=>packages.fetch("keys"),"zbx_schema_file"=>packages.fetch("schema_file"),"zbx_schema_sha256"=>packages.fetch("schema_sha256")})
end
if %w[install configure].include?(action)
  probe_file = File.join(ENV.fetch("PRIVATE_TEMP"),"probes.json")
  load File.join(__dir__,"probes.rb")
  probes = probe_export(required("run_id")).dig("zabbix_export","hosts",0,"items")
  triggers = []
  items = probes.map do |p|
    p.fetch("triggers").each do |t|
      trigger = {"description"=>t.fetch("name"),"expression"=>t.fetch("expression"),"priority"=>4}
      trigger["comments"] = "cnpl05-#{required('run_id')}:#{Digest::SHA256.hexdigest(JSON.generate(trigger))}"
      triggers << trigger
    end
    item = {"name"=>p.fetch("name"),"key_"=>p.fetch("key"),"type"=>{"ZABBIX_ACTIVE"=>7,"SIMPLE"=>3,"HTTP_AGENT"=>19}.fetch(p["type"]),"value_type"=>(p["value_type"]=="TEXT" ? 4 : 3),"delay"=>"60s","history"=>"7d","trends"=>(p["value_type"]=="TEXT" ? "0" : "90d"),"timeout"=>"5s"}
    item.merge!({"url"=>p["url"],"verify_peer"=>1,"verify_host"=>1,"follow_redirects"=>0}) if p["url"]
    item["description"] = "cnpl05-#{required('run_id')}:#{Digest::SHA256.hexdigest(JSON.generate(item))}"
    item
  end
  File.write(probe_file,JSON.pretty_generate({"items"=>items,"triggers"=>triggers}))
  out["zbx_probe_export_file"] = probe_file
end
puts JSON.pretty_generate(out)
