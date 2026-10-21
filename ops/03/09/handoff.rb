#!/usr/bin/env ruby
require "json"
root = File.expand_path("..", __dir__)
coverage = JSON.parse(File.read(File.join(root,"coverage.json")))
summary = {
  scope: "script_delivery",
  planned_steps: coverage.fetch("steps").length,
  stages: (1..9).map { |n| {stage: format("%02d",n),script: format("%02d/run.sh",n),runtime_accepted: false} },
  phase03_runtime_accepted: false,
  note: "离线源码/测试检查不能替代 VM、数据恢复、故障及人工步骤证据；按各 README 独立验收"
}
puts JSON.pretty_generate(summary)
