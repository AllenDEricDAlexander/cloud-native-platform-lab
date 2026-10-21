#!/usr/bin/env ruby
# 构造/拒绝路径检查；不得访问服务或启动监听进程。
require_relative "../lib/config"
require "tmpdir"
require "open3"
count = 0
assert = lambda { |value,message| abort message unless value; count += 1 }
reject = lambda do |&block|
  failed = false
  begin; block.call; rescue SystemExit, KeyError, ArgumentError; failed = true; end
  assert.call(failed,"应拒绝无效输入")
end
reject.call { documents("a: 1\na: 2\n") }
reject.call { manifests!([object("Pod","bad","test",{"spec"=>{"containers"=>[{"name"=>"bad","image"=>"nginx:latest"}]}})]) }
reject.call { manifests!([object("Secret","bad","test")]) }
reject.call { material("missing-offline-material") }
assert.call(hosts.size==16,"Inventory 目标不完整")
load File.join(ROOT,"01/probes.rb")
checks = probe_export("review").dig("zabbix_export","hosts",0,"items")
assert.call(checks.length==5,"集群外探测缺项")
assert.call(checks.select { |c| c["type"]=="HTTP_AGENT" }.all? { |c| c["ssl_verify_peer"]=="YES" && c["ssl_verify_host"]=="YES" },"探测必须验证 TLS")
Dir.mktmpdir("cnpl05-offline-") do |dir|
  fixture = File.join(dir,"items.json")
  row = %w[system.uptime system.cpu.load[all,avg1] vm.memory.size[available] vfs.fs.size[/,pused] net.if.in[eth0]].map { |k| {"key_"=>k,"lastclock"=>Time.now.to_i,"state"=>"0"} }
  File.write(fixture,JSON.generate(Array.new(16) { row }))
  _,status = Open3.capture2e("ruby",File.join(ROOT,"01/verify.rb"),fixture)
  assert.call(status.success?,"有效新鲜指标被拒绝")
  row[0]["lastclock"] = 0
  File.write(fixture,JSON.generate(Array.new(16) { row }))
  _,status = Open3.capture2e("ruby",File.join(ROOT,"01/verify.rb"),fixture)
  assert.call(!status.success?,"陈旧指标不得计为健康")
end
puts "PASS #{count} 项离线构造/拒绝检查（无外部客户端调用）"
