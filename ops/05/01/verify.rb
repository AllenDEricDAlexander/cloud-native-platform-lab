#!/usr/bin/env ruby
require "json"
rows = JSON.parse(File.read(ARGV.fetch(0)))
abort "必须逐台收到 16 台 VM 数据" unless rows.length == 16
patterns = [/^system\.uptime$/, /^system\.cpu\.(load|util)/, /^vm\.memory\.size/, /^vfs\.fs\.(size|pused)/, /^net\.if\.(in|out)/]
rows.each_with_index do |items,index|
  fresh = items.select { |i| i["state"].to_s=="0" && i["lastclock"].to_i >= Time.now.to_i-300 && i["lastclock"].to_i <= Time.now.to_i+30 }
  abort "第 #{index+1} 台核心指标缺失或超过 300 秒未更新" unless patterns.all? { |p| fresh.any? { |i| p.match?(i.fetch("key_")) } }
end
puts "PASS 16 台 VM 核心指标新鲜度；仍需间隔重查、Agent 故障恢复及幂等验收"
