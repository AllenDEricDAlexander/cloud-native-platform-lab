#!/usr/bin/env ruby
require "json"
require "yaml"
require "tmpdir"
require "open3"
require "digest"
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
    %w[values agent-config gateway-config loki tempo pyroscope rules].include?(mode) ? YAML.load(out) : (mode=="saved-objects" ? out.lines.map { |l| JSON.parse(l) } : JSON.parse(out))
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
  if File.file?(File.join(root,"06/render.rb"))
    input["backends"].merge!({"rgw_endpoint"=>"https://rgw.svc.internal.egon.top","region"=>"lab","loki_bucket"=>"logs","tempo_bucket"=>"traces","pyroscope_bucket"=>"profiles","loki_s3_secret"=>"logs-creds","tempo_s3_secret"=>"trace-creds","pyroscope_s3_secret"=>"profile-creds","tls_secret"=>"backend-tls","storage_class"=>"fixture-rbd","gateway_namespace"=>"gateway","ca_secret"=>"rgw-ca","loki_url"=>"https://loki.k8s.internal.egon.top","tempo_url"=>"https://tempo.k8s.internal.egon.top","pyroscope_url"=>"https://pyroscope.k8s.internal.egon.top"})
    File.write(path,JSON.generate(input))
    data = runner.call("06","resources")
    abort "三个独立 WAL PVC 缺项" unless data.fetch("items").count { |i| i["kind"]=="PersistentVolumeClaim" }==3
    %w[loki tempo pyroscope].each { |mode| runner.call("06",mode) }
    loki = runner.call("06","loki")
    abort "高基数默认 Loki 标签未关闭" unless loki.dig("limits_config","otlp_config","resource_attributes","ignore_defaults")==true
  end
  if File.file?(File.join(root,"07/render.rb"))
    input["slo"].merge!({"service"=>"reference","environment"=>"lab","objective"=>0.99,"latency_seconds"=>0.5,"candidate_version"=>"fixture-v2","rollout_namespace"=>"apps-dev","prometheus_secret"=>"prom-auth"})
    input["metrics"]["url"]="https://prometheus.k8s.internal.egon.top"
    File.write(path,JSON.generate(input))
    rules = runner.call("07","rules")
    abort "SLO 无流量门槛缺失" unless rules["groups"][0]["rules"].select { |r| r["record"].to_s.include?("error_ratio") }.all? { |r| r["expr"].include?(">= 100") }
    data = runner.call("07","resources")
    metrics = data.fetch("items").find { |i| i["kind"]=="AnalysisTemplate" }.dig("spec","metrics")
    abort "候选版本过滤/NaN 阻断缺失" unless metrics.all? { |m| m.dig("provider","prometheus","query").include?('version="{{args.version}}"') && m["failureCondition"].include?("isNaN") }
    runner.call("07","rollout-patch")
  end
  if File.file?(File.join(root,"08/render.rb"))
    evidence = File.join(dir,"assumptions.txt"); File.write(evidence,"offline construction fixture; no actual pricing\n")
    input["performance"].merge!({"cpu_hourly_cost"=>0.01,"ram_gib_hourly_cost"=>0.02,"storage_gib_hourly_cost"=>0.001,"currency"=>"CNY","assumptions_file"=>evidence,"assumptions_sha256"=>Digest::SHA256.file(evidence).hexdigest})
    File.write(path,JSON.generate(input))
    values = runner.call("08","values")
    abort "成本必须显式模型" unless values.dig("opencost","customPricing","enabled")==true && values.dig("opencost","ui","enabled")==false
  end
end
puts "PASS #{count} 组离线渲染；镜像方法仅在本地构造中替换，不代表物料已锁定"
