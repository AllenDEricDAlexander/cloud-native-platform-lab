#!/usr/bin/env ruby
require_relative "config"
ids=File.read(File.join(REPO,"plan/04-devops-platform.md")).scan(/^### (04\.\d{2}\.\d{2}) /).flatten
rows=JSON.parse(File.read(File.join(ROOT,"coverage.json"))).fetch("steps")
abort "55步索引缺失/重复" unless ids.size==55 && rows.size==55 && rows.map { |r| r["id"] }.sort==ids.sort
rows.each do |r|
  abort "无运行证据不得升级验收" unless r["runtime_accepted"]==false && !r.fetch("manual_checks").empty?
  r.fetch("files").each { |f| abort "交付文件不存在：#{f}" unless File.file?(File.join(ROOT,f)) }
end
puts "PASS 55步交付文件/人工验收边界索引；不代表55步运行完成"
