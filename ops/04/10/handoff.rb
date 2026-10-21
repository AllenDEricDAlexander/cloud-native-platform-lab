#!/usr/bin/env ruby
require_relative "../lib/config"
report=JSON.parse(File.read(ARGV.fetch(0)))
ids=File.read(File.join(REPO,"plan/04-devops-platform.md")).scan(/^### (04\.\d{2}\.\d{2}) /).flatten
rows=report.fetch("steps")
abort "55步运行记录缺失/重复" unless rows.map { |r| r["id"] }.sort==ids.sort && rows.size==55
rows.each do |r|
  abort "存在未完成步骤：#{r['id']}" unless r["status"]=="passed" && !r.fetch("evidence").empty?
  r["evidence"].each { |e| verified(e["file"],e["sha256"]) }
end
puts JSON.pretty_generate({"ready_for_human_review"=>true,"phase_complete"=>false,"boundary"=>"仅检查证据索引和SHA；需人工核对14格、IaC锁/恢复、真实灰度、签名拒绝、自助与对照"})
