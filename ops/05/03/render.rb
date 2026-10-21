#!/usr/bin/env ruby
require_relative "../lib/config"
require "ipaddr"
ns = required("namespaces","metrics")
sources = required("sources")
abort "重复 source ID" unless sources.map { |s| s.fetch("id") }.uniq.size == sources.size
items = sources.map do |s|
  id = s.fetch("id")
  abort "source ID 无效" unless id.match?(/\A[a-z][a-z0-9-]{2,40}\z/)
  tls = {"serverName"=>s.fetch("server_name"),"ca"=>{"secret"=>{"name"=>s.fetch("ca_secret"),"key"=>"ca.crt"}},"insecureSkipVerify"=>false}
  auth = s["authorization_secret"] ? {"type"=>"Bearer","credentials"=>{"name"=>s.fetch("authorization_secret"),"key"=>"token"}} : nil
  if s.fetch("kind") == "service"
    endpoint = {"port"=>s.fetch("port_name"),"path"=>s.fetch("path","/metrics"),"scheme"=>"https","interval"=>"30s","scrapeTimeout"=>"10s","tlsConfig"=>tls,"relabelings"=>[{"targetLabel"=>"cnpl_source","replacement"=>id}]}
    endpoint["authorization"] = auth if auth
    object("ServiceMonitor","cnpl05-#{id}",ns,{"spec"=>{"namespaceSelector"=>{"matchNames"=>[s.fetch("namespace")]},"selector"=>{"matchLabels"=>s.fetch("service_labels")},"sampleLimit"=>10000,"targetLimit"=>16,"labelLimit"=>40,"labelNameLengthLimit"=>100,"labelValueLengthLimit"=>200,"endpoints"=>[endpoint]}},"monitoring.coreos.com/v1")
  elsif s["kind"] == "external"
    s.fetch("targets").each do |target|
      host,port = target.split(":")
      abort "外部指标目标必须在既有管理网段且有显式端口" unless IPAddr.new("192.168.9.0/24").include?(IPAddr.new(host)) && port.to_s.match?(/\A\d{1,5}\z/) && port.to_i.between?(1,65535)
    end
    spec = {"staticConfigs"=>[{"targets"=>s.fetch("targets"),"labels"=>{"cnpl_source"=>id}}],"scheme"=>"HTTPS","metricsPath"=>s.fetch("path","/metrics"),"scrapeInterval"=>"30s","scrapeTimeout"=>"10s","sampleLimit"=>10000,"tlsConfig"=>tls}
    spec["authorization"] = auth if auth
    object("ScrapeConfig","cnpl05-#{id}",ns,{"spec"=>spec},"monitoring.coreos.com/v1alpha1")
  else abort "source kind 只能是 service/external"
  end
end
items << object("PrometheusRule","cnpl05-infrastructure",ns,{"spec"=>YAML.load_file(File.join(__dir__,"rules.yaml"))},"monitoring.coreos.com/v1")
puts JSON.pretty_generate(labeled(items))
