#!/usr/bin/env ruby
require_relative "../lib/config"
directory = required("handoff","evidence_directory")
abort "证据目录必须在仓库外且存在" unless directory.start_with?("/") && File.directory?(directory) && !File.realpath(directory).start_with?(REPO+"/")
index = JSON.parse(File.read(File.join(directory,"index.json")))
expected = File.read(File.join(REPO,"plan/05-observability.md")).scan(/^### (05\.\d{2}\.\d{2}) /).flatten
abort "42 步证据索引不完整/重复" unless index.fetch("steps").map { |s| s.fetch("id") }.sort==expected.sort
rows = index.fetch("steps").map do |step|
  abort "状态只允许 pending/passed/failed" unless %w[pending passed failed].include?(step.fetch("status"))
  if step["status"]=="passed"
    abort "passed 必须有真实运行说明与证据" unless step["runtime"]==true && step["summary"].is_a?(String) && !step["summary"].empty? && step["evidence"].is_a?(Array) && !step["evidence"].empty?
    step["evidence"].each { |e| verified(e.fetch("file"),e.fetch("sha256")) }
  end
  {"id"=>step["id"],"status"=>step["status"],"summary"=>step["summary"]}
end
puts JSON.pretty_generate({"steps"=>rows,"passed_count"=>rows.count { |r| r["status"]=="passed" },"runtime_accepted"=>false,"phase_complete"=>false,"decision"=>"人工审核每步运行判定、正常/失败/恢复与数据校验；本索引不自动批准验收。06C 第二集群观测另行补测"})
