#!/usr/bin/env ruby
require_relative "../lib/config"
file = verified(required("performance","matrix_file"),required("performance","matrix_sha256"))
rows = JSON.parse(File.read(file))
mode = ARGV.fetch(0)
expected = mode=="languages" ? %w[java csharp jsts python rust c cpp] : %w[gitlab-cold gitlab-warm jenkins-cold jenkins-warm]
abort "实验矩阵不完整或重复" unless rows.map { |r| r.fetch("case") }.sort==expected.sort
%w[source_revision dataset_sha256 node_resources dependency_versions duration_seconds load_profile warmup_seconds].each do |key|
  abort "实验条件不一致：#{key}" unless rows.map { |r| r.fetch(key) }.uniq.size==1
end
rows.each do |row|
  abort "必须有真实结果与工具版本" unless row["measured"]==true && row["tool_versions"].is_a?(Hash) && row["metrics"].is_a?(Hash)
  verified(row.fetch("evidence_file"),row.fetch("evidence_sha256"))
  keys = mode=="languages" ? %w[startup_seconds throughput_rps p95_ms p99_ms cpu_seconds memory_peak_bytes] : %w[queue_seconds image_pull_seconds dependencies_seconds compile_seconds test_seconds push_seconds]
  abort "实测字段缺失或无效" unless keys.all? { |k| row["metrics"][k].is_a?(Numeric) && row["metrics"][k].finite? && row["metrics"][k]>=0 }
end
puts JSON.pretty_generate({"mode"=>mode,"rows"=>rows,"limitations"=>"单次家庭实验，仅比较相同业务/硬件/依赖；冷暖缓存采用隔离缓存引用，不清理共享缓存；优化建议须另测性能/可靠性"})
