#!/usr/bin/env ruby
require_relative "../lib/config"
c = JSON.parse(File.read(File.join(__dir__,"contract.json"))).fetch("budget")
days = [c["metrics_retention_days"],c["logs_retention_days"],c["traces_retention_hours"]/24.0,c["profiles_retention_hours"]/24.0].max
# 上界估计：把全部原始流量按最长保留期计，未扣压缩；真实增长需上线测量。
logical = c.fetch("max_daily_raw_gib") * days
puts JSON.pretty_generate({"raw_logical_upper_gib"=>logical,"replicated_upper_gib"=>logical*c.fetch("storage_replication"),"provisioned_gib_with_reserve"=>(logical*c.fetch("storage_replication")/(1-c.fetch("storage_reserve_fraction"))).ceil,"measured"=>false,"assumption"=>"所有信号按最长保留期、未压缩；Datastore 与其他业务另核算"})
