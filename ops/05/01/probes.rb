#!/usr/bin/env ruby
require "json"
def probe_export(run)
  host = "build01.svc.internal.egon.top"
  checks = [
    ["DNS resolves Harbor","net.dns[192.168.9.11,harbor.k8s.internal.egon.top,A]","ZABBIX_ACTIVE",nil],
    ["Kubernetes API TCP","net.tcp.service[tcp,192.168.9.100,6443]","SIMPLE",nil],
    ["Harbor HTTPS","cnpl.harbor.https","HTTP_AGENT","https://harbor.k8s.internal.egon.top/api/v2.0/health"],
    ["GitLab HTTPS","cnpl.gitlab.https","HTTP_AGENT","https://gitlab.svc.internal.egon.top/-/health"],
    ["OpenWrt proxy TCP","net.tcp.service[tcp,192.168.9.10,7890]","SIMPLE",nil]
  ]
  items = checks.map do |name,key,type,url|
    item = {"name"=>name,"type"=>type,"key"=>key,"delay"=>"60s","history"=>"7d","trends"=>"90d","value_type"=>(url ? "TEXT" : "UNSIGNED"),"timeout"=>"5s"}
    item.merge!({"url"=>url,"ssl_verify_peer"=>"YES","ssl_verify_host"=>"YES","follow_redirects"=>"NO"}) if url
    item["triggers"] = [{"name"=>"#{name} unavailable or stale","expression"=>(url ? "nodata(/#{host}/#{key},3m)=1" : "max(/#{host}/#{key},2m)=0 or nodata(/#{host}/#{key},3m)=1"),"priority"=>"HIGH"}]
    item
  end
  {"zabbix_export"=>{"version"=>"7.0","hosts"=>[{"host"=>host,"items"=>items}]}}
end
puts JSON.pretty_generate(probe_export(ARGV.fetch(0))) if $PROGRAM_NAME == __FILE__
