#!/usr/bin/env ruby
require "json"
require "yaml"
require "tmpdir"
require "open3"
root = File.expand_path("..",__dir__)
count = 0
Dir.mktmpdir("cnpl05-render-") do |dir|
  input = JSON.parse(File.read(File.join(root,"inputs.json")))
  input["run_id"] = "offline-review"
  input["metrics"].merge!({"storage_class"=>"fixture-rbd","notification_secret"=>"notification","grafana_admin_secret"=>"grafana-admin","gateway_name"=>"internal","gateway_namespace"=>"gateway"})
  path = File.join(dir,"inputs.json"); File.write(path,JSON.generate(input))
  runner = lambda do |stage,mode|
    script = 'require ARGV.shift; def material(key); {"version"=>"0.0.0-fixture","image"=>"harbor.k8s.internal.egon.top/offline/#{key}@sha256:"+"a"*64}; end; load ARGV.shift'
    out,status = Open3.capture2e({"CNPL05_INPUTS"=>path},"ruby","-e",script,File.join(root,"lib/config.rb"),File.join(root,stage,"render.rb"),mode)
    abort out unless status.success?
    count += 1
    %w[values agent-config gateway-config].include?(mode) ? YAML.load(out) : (mode=="saved-objects" ? out.lines.map { |l| JSON.parse(l) } : JSON.parse(out))
  end
  if File.file?(File.join(root,"02/render.rb"))
    values = runner.call("02","values")
    abort "保留/PVC 上界失效" unless values.dig("prometheus","prometheusSpec","retention")=="7d" && values.dig("prometheus","prometheusSpec","retentionSize")=="8GB"
    abort "Alertmanager 通知 Secret 未挂载" unless values.dig("alertmanager","alertmanagerSpec","secrets")==["notify"]
    data = runner.call("02","resources")
    abort "Dashboard 无面板" unless JSON.parse(data.fetch("items").find { |i| i["kind"]=="ConfigMap" }.dig("data","platform.json")).fetch("panels").size>=4
  end
  if File.file?(File.join(root,"03/render.rb"))
    input["sources"] = [{"id"=>"ceph","category"=>"ceph","kind"=>"external","targets"=>["192.168.9.106:9283"],"server_name"=>"storage01.k8s.internal.egon.top","ca_secret"=>"ceph-ca"},{"id"=>"postgresql","category"=>"postgresql","kind"=>"service","namespace"=>"db","service_labels"=>{"app"=>"pg"},"port_name"=>"metrics","server_name"=>"pg.db.svc","ca_secret"=>"pg-ca"}]
    File.write(path,JSON.generate(input))
    data = runner.call("03","resources")
    abort "采集类型缺项" unless data.fetch("items").map { |i| i["kind"] }.include?("ScrapeConfig") && data.fetch("items").map { |i| i["kind"] }.include?("ServiceMonitor")
  end
  if File.file?(File.join(root,"04/render.rb"))
    input["otel"].merge!({"tls_secret"=>"server","client_secret"=>"client","tempo_endpoint"=>"tempo.observability.svc:4317","loki_endpoint"=>"https://loki.observability.svc/otlp","metrics_endpoint"=>"https://prometheus.monitoring.svc/api/v1/otlp","authorized_namespaces"=>["apps-dev"]})
    File.write(path,JSON.generate(input))
    data = runner.call("04","resources")
    abort "缺少 Agent/Gateway" unless data.fetch("items").any? { |i| i["kind"]=="DaemonSet" } && data.fetch("items").any? { |i| i["kind"]=="Deployment" && i.dig("spec","replicas")==1 }
    configs = data.fetch("items").select { |i| i["kind"]=="ConfigMap" }.map { |i| YAML.load(i.dig("data","collector.yaml")) }
    abort "队列无界" unless configs.all? { |c| c["exporters"].values.all? { |e| e.dig("sending_queue","queue_size")==256 && e.dig("retry_on_failure","max_elapsed_time")=="30s" } }
  end
  if File.file?(File.join(root,"05/render.rb"))
    input["elk"].merge!({"namespace"=>"data","elasticsearch_name"=>"search","url"=>"https://search.data.svc:9200","tls_secret"=>"logs-tls","ca_secret"=>"es-ca","credentials_secret"=>"es-creds","kibana_tls_secret"=>"kibana-tls","storage_class"=>"fixture-rbd","selected_namespaces"=>["apps-dev"]})
    input["otel"]["trace_id"] = "a"*32
    File.write(path,JSON.generate(input))
    data = runner.call("05","resources")
    abort "Logstash 队列未独立持久化" unless data.fetch("items").any? { |i| i["kind"]=="PersistentVolumeClaim" && i.dig("metadata","name")=="logstash-queue" }
    %w[ilm index-template query saved-objects].each { |mode| runner.call("05",mode) }
    input["elk"]["route"] = "direct"; File.write(path,JSON.generate(input))
    data = runner.call("05","resources")
    abort "direct 不得同时部署 Logstash" if data.fetch("items").any? { |i| i["kind"]=="Deployment" && i.dig("metadata","name")=="logstash" }
    abort "direct 必须按日索引" unless data.fetch("items").find { |i| i["kind"]=="ConfigMap" }.dig("data","fluent-bit.conf").include?("Logstash_Format On")
  end
end
puts "PASS #{count} 组离线渲染；镜像方法仅在本地构造中替换，不代表物料已锁定"
