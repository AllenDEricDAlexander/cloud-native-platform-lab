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
    script = 'require ARGV.shift; def material(key); {"image"=>"harbor.k8s.internal.egon.top/offline/#{key}@sha256:"+"a"*64}; end; load ARGV.shift'
    out,status = Open3.capture2e({"CNPL05_INPUTS"=>path},"ruby","-e",script,File.join(root,"lib/config.rb"),File.join(root,stage,"render.rb"),mode)
    abort out unless status.success?
    count += 1
    mode=="values" ? YAML.load(out) : JSON.parse(out)
  end
  if File.file?(File.join(root,"02/render.rb"))
    values = runner.call("02","values")
    abort "保留/PVC 上界失效" unless values.dig("prometheus","prometheusSpec","retention")=="7d" && values.dig("prometheus","prometheusSpec","retentionSize")=="8GB"
    abort "Alertmanager 通知 Secret 未挂载" unless values.dig("alertmanager","alertmanagerSpec","secrets")==["notify"]
    data = runner.call("02","resources")
    abort "Dashboard 无面板" unless JSON.parse(data.fetch("items").find { |i| i["kind"]=="ConfigMap" }.dig("data","platform.json")).fetch("panels").size>=4
  end
end
puts "PASS #{count} 组离线渲染；镜像方法仅在本地构造中替换，不代表物料已锁定"
