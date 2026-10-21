#!/usr/bin/env ruby
require "json"
root = File.expand_path("..",__dir__)
plan = File.expand_path("../../plan/06-advanced-security-dr.md",root)
ids = File.read(plan).scan(/^#### (06\.\d{2}\.\d{2}) /).flatten.sort
rows = JSON.parse(File.read(File.join(root,"coverage.json"))).fetch("steps")
abort "83 步索引不匹配" unless ids.size == 83 && rows.map { |r| r.fetch("id") }.sort == ids && rows.map { |r| r.fetch("id") }.uniq.size == 83
rows.each do |row|
  abort "索引模式无效" unless %w[script script_and_manual manual_version_gate].include?(row.fetch("mode")) && row["runtime_accepted"] == false
  row.fetch("files").each do |relative|
    path = File.expand_path(relative,root)
    abort "索引文件缺失/越界" unless path.start_with?(root+"/") && File.file?(path) && File.size(path)>0
  end
end
(1..17).each { |i| %w[README.md run.sh].each { |name| abort "子阶段入口缺失" unless File.file?(File.join(root,format("%02d",i),name)) } }
puts "PASS 17 个子阶段、83 步交付文件索引；不表示运行覆盖或验收完成"
