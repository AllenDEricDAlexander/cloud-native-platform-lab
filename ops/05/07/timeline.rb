#!/usr/bin/env ruby
require_relative "../lib/config"
require "time"
require "fileutils"
mode = ARGV.fetch(0)
run = required("run_id")
abort "run_id 格式无效" unless run.match?(/\A[a-z][a-z0-9-]{2,19}\z/)
directory = File.join(ROOT,"07/records",run)
FileUtils.mkdir_p(directory, :mode=>0700)
path = File.join(directory,"timeline.jsonl")
if mode=="append"
  event = JSON.parse(File.read(verified(required("slo","timeline_event_file"),required("slo","timeline_event_sha256"))))
  abort "时间线字段超出白名单" unless (event.keys-%w[id phase observed_at source subject revision evidence_file evidence_sha256 summary]).empty?
  abort "时间线必须有明确 UTC 时间" unless event.fetch("observed_at").match?(/Z\z/) && Time.iso8601(event["observed_at"])
  abort "非法时间线阶段" unless %w[change failure_started detected response_started service_restored data_verified].include?(event.fetch("phase"))
  verified(event.fetch("evidence_file"),event.fetch("evidence_sha256"))
  File.open(path,File::RDWR|File::CREAT,0600) do |file|
    file.flock(File::LOCK_EX)
    rows = file.each_line.map { |line| JSON.parse(line) }
    abort "重复 event ID，保留原事件" if rows.any? { |r| r["id"]==event.fetch("id") }
    file.seek(0,IO::SEEK_END); file.puts(JSON.generate(event)); file.flush
  end
  puts "已追加实际事件：#{event.fetch('id')}"
elsif mode=="report"
  rows = File.readlines(path).map { |line| JSON.parse(line) }.sort_by { |r| Time.iso8601(r.fetch("observed_at")) }
  phases = %w[failure_started detected response_started service_restored data_verified]
  abort "恢复时间线不完整" unless phases.all? { |phase| rows.count { |r| r["phase"]==phase }==1 }
  times = phases.map { |phase| Time.iso8601(rows.find { |r| r["phase"]==phase }.fetch("observed_at")) }
  abort "恢复时间线次序不合法" unless times==times.sort
  puts JSON.pretty_generate({"events"=>rows,"detection_seconds"=>times[1]-times[0],"response_seconds"=>times[2]-times[1],"service_restore_seconds"=>times[3]-times[0],"data_verified_seconds"=>times[4]-times[0],"note"=>"仅对应此次有证据的事件；RPO 需另核对已确认数据"})
else abort "用法：timeline.rb append|report"
end
