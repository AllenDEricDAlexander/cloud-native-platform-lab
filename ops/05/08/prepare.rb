#!/usr/bin/env ruby
require_relative "../lib/config"
perf = INPUT.fetch("performance")
target = URI(required("performance","target_url"))
abort "压测只允许授权的内部 HTTPS 实验服务" unless target.scheme=="https" && target.host.to_s.end_with?(".k8s.internal.egon.top", ".svc.cluster.local") && !target.userinfo && !target.query && !target.fragment && ["","/"].include?(target.path)
abort "并发/时间超出实验上限" unless perf["vus"].is_a?(Integer) && perf["vus"].between?(1,20) && perf["duration_seconds"].is_a?(Integer) && perf["duration_seconds"].between?(10,600)
abort "阈值必须明确" unless perf["p95_ms"].is_a?(Numeric) && perf["p95_ms"]>0 && perf["error_rate"].is_a?(Numeric) && perf["error_rate"].between?(0,0.1)
dataset = JSON.parse(File.read(verified(required("performance","dataset_file"),required("performance","dataset_sha256"))))
abort "空数据集" unless dataset.is_a?(Array) && !dataset.empty?
dataset.each do |row|
  abort "请求必须是有限的相对实验路径" unless row.fetch("path").match?(%r{\A/(?!/)[a-zA-Z0-9_./-]*\z}) && !row["path"].include?("..") && %w[GET POST].include?(row.fetch("method","GET"))
end
verified(required("performance","ca_file"),required("performance","ca_sha256"))
rules = required("performance","safety_queries")
abort "缺少测试端/共享资源保护信号" unless (%w[load_client_cpu load_client_memory ceph_capacity datastore_free]-rules.map { |r| r["name"] }).empty?
rules.each do |r|
  abort "安全查询必须有明确阈值" unless r["expr"].is_a?(String) && %w[min max].any? { |k| r[k].is_a?(Numeric) && r[k].finite? }
end
info = material("k6_or_locust")
puts JSON.pretty_generate({"k6_file"=>info.fetch("file"),"k6_sha256"=>info.fetch("sha256"),"k6_needs_version"=>info.fetch("version")})
