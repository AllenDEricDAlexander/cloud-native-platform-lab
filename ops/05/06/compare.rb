#!/usr/bin/env ruby
require_relative "../lib/config"
data = JSON.parse(File.read(verified(required("backends","comparison_file"),required("backends","comparison_sha256"))))
a = data.fetch("elk"); b = data.fetch("loki")
%w[dataset_sha256 duration_seconds requests_per_second retention_days resource_budget query_cases].each do |key|
  abort "ELK/Loki 条件不一致：#{key}" unless a.fetch(key)==b.fetch(key)
end
%w[elk loki].each do |name|
  row = data.fetch(name)
  abort "缺少实测或数据量" unless row["measured"]==true && row.fetch("records").to_i>0
  verified(row.fetch("evidence_file"),row.fetch("evidence_sha256"))
end
puts JSON.pretty_generate({"conditions"=>a.reject { |k,_| %w[evidence_file evidence_sha256].include?(k) },"comparison"=>%w[elk loki].to_h { |name| [name,data.fetch(name).slice("records","ingestion_bytes","query_p95_ms","cpu_seconds","memory_peak_bytes","storage_bytes")] },"inference"=>"仅对本次相同数据与负载有效，不代表通用后端排名"})
