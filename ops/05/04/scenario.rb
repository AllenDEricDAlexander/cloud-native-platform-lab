#!/usr/bin/env ruby
# 只发起真实授权参考请求，不合成后端 spans；异步消息由参考业务发送。
require_relative "../lib/config"
require "securerandom"
require "open3"
scenario = JSON.parse(File.read(ARGV.fetch(0)))
expected = %w[java csharp jsts python rust c cpp]
abort "参考用例必须包含七语言" unless scenario.fetch("services").map { |s| s.fetch("language") }.sort == expected.sort
report = {"trace_id"=>SecureRandom.hex(16),"span_id"=>SecureRandom.hex(8),"requests"=>[]}
scenario.fetch("services").each do |service|
  config = service.fetch("curl_config"); url = service.fetch("url")
  stat = File.stat(config)
  abort "私有 curl 配置权限/路径无效" unless File.absolute_path(config)==config && !File.realpath(config).start_with?(REPO+"/") && stat.uid==Process.uid && [0600,0400].include?(stat.mode & 0777)
  ok = system("ruby",File.join(ROOT,"lib/http-config.rb"),config,url)
  abort "URL/认证配置无效" unless ok
  traceparent = "00-#{report['trace_id']}-#{report['span_id']}-01"
  output = File.join(ARGV.fetch(1),"#{service.fetch('language')}-response.txt")
  _,status = Open3.capture2e("curl","--config",config,"--fail","--silent","--show-error","--max-time","30","--proto","=https","-H","traceparent: #{traceparent}","-H","X-CNPL-Test-Id: #{required('run_id')}","--output",output,url)
  abort "参考请求失败：#{service.fetch('language')}" unless status.success?
  report["requests"] << {"language"=>service.fetch("language"),"url"=>url,"response_file"=>File.basename(output)}
end
File.write(File.join(ARGV.fetch(1),"scenario.json"),JSON.pretty_generate(report))
puts "真实请求已发送；用报告 trace_id 查询同步链，异步链接另查；请求成功不代表遥测已关联"
