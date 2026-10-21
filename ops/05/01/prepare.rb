#!/usr/bin/env ruby
require_relative "../lib/config"
require "ipaddr"
vars = JSON.parse(File.read(ARGV.fetch(0)))
action = ARGV.fetch(1)
list = hosts
psks = vars.fetch("zbx_psks")
abort "每机 PSK 必须完整、有效且不同" unless psks.keys.sort == list.map { |h| h["id"] }.sort && psks.values.uniq.size == 16 && psks.values.all? { |v| v.match?(/\A[a-fA-F0-9]{64}\z/) }
vars.fetch("zbx_web_sources").each { |s| abort "仅允许管理网段 IPv4" unless IPAddr.new(s).ipv4? && IPAddr.new("192.168.9.0/24").include?(IPAddr.new(s)) }
%w[zbx_ca_file zbx_tls_cert_file zbx_tls_key_file].each do |key|
  p = vars.fetch(key)
  abort "证书文件不可用" unless File.file?(p) && p.start_with?("/") && !File.realpath(p).start_with?(REPO+"/")
end
key_stat = File.stat(vars.fetch("zbx_tls_key_file"))
abort "私钥权限无效" unless key_stat.uid == Process.uid && [0600,0400].include?(key_stat.mode & 0777)
out = {"zbx_firewall_rules"=>list.map { |h| {"source"=>h["ip"]+"/32","port"=>"10051"} } + vars.fetch("zbx_web_sources").map { |s| {"source"=>s,"port"=>"8443"} }}
if action == "install"
  m = material("zabbix")
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
  File.write(probe_file,JSON.pretty_generate(probe_export(required("run_id"))))
  out["zbx_probe_export_file"] = probe_file
end
puts JSON.pretty_generate(out)
