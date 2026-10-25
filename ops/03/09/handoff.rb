#!/usr/bin/env ruby
require "json"
root = File.expand_path("..", __dir__)
coverage = JSON.parse(File.read(File.join(root,"coverage.json")))
summary = {
  scope: coverage.fetch("scope"),
  planned_steps: coverage.fetch("steps").length,
  stages: (1..9).map { |n| stage=format("%02d",n); {stage: stage,script: "#{stage}/run.sh",runtime_status: coverage.fetch("runtime_summary",{}).fetch(stage,"not_run")} },
  phase03_runtime_accepted: coverage.fetch("runtime_accepted"),
  mainline_handoff_ready: coverage.fetch("mainline_handoff_ready",false),
  runtime_report: coverage["runtime_report"],
  not_accepted: coverage.fetch("not_accepted",[]),
  note: "运行证据按 coverage.json 和执行记录核对；用户取消范围及原故障失败不得提升为通过"
}
puts JSON.pretty_generate(summary)
