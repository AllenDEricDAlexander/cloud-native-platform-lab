#!/usr/bin/env ruby
require "json"
require "time"
d = JSON.parse(File.read(ARGV.fetch(0)))
abort "两条恢复路线必须单独报告" unless %w[etcd-restore fresh-cluster].include?(d["recovery_route"])
times = %w[failure_started_at recovery_started_at infrastructure_ready_at business_verified_at source_last_acknowledged_at latest_recovered_data_time].map do |key|
  raw = d.fetch(key)
  abort "时间必须包含明确时区" unless raw.is_a?(String) && raw.match?(/(?:Z|[+-]\d{2}:\d{2})\z/)
  Time.iso8601(raw)
end
failure,recovery,infrastructure,business,source,latest = times
abort "恢复里程碑时间倒置" unless failure<=recovery && recovery<=infrastructure && infrastructure<=business
abort "数据时间倒置或晚于业务验证" unless latest<=source && source<=business
%w[lost_records duplicate_records rto_target_seconds rpo_target_seconds].each { |k| abort "缺少非负整数：#{k}" unless d[k].is_a?(Integer) && d[k]>=0 }
rto = (business-failure).to_i
rpo = (source-latest).to_i
result = {"recovery_route"=>d["recovery_route"],"rto_seconds"=>rto,"rpo_seconds"=>rpo,"lost_records"=>d["lost_records"],"duplicate_records"=>d["duplicate_records"],"targets_met"=>rto<=d["rto_target_seconds"] && rpo<=d["rpo_target_seconds"],"runtime_accepted"=>false,"phase_complete"=>false}
puts JSON.pretty_generate(result)
exit(result["targets_met"] && d["lost_records"]==0 && d["duplicate_records"]==0 ? 0 : 1)
