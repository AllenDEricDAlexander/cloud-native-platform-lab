#!/usr/bin/env ruby
require_relative "../lib/config"
plan=JSON.parse(File.read(ARGV.fetch(0)))
allowed=required("iac","allowed_addresses")
abort "只批准一个临时 VM 地址" unless allowed==["vsphere_virtual_machine.test"]
plan.fetch("resource_changes",[]).select { |r| r["mode"]=="managed" }.each do |r|
  abort "Plan 越过允许地址" unless allowed.include?(r["address"])
  actions=r.fetch("change").fetch("actions")
  abort "拒绝删除/替换，需独立销毁审批" if actions.include?("delete")
  name=r.dig("change","after","name") || r.dig("change","before","name")
  abort "只能操作本批全新测试 VM" unless name=="cnpl04-#{required('run_id')}"
end
abort "Plan 错误/不完整" if plan["errored"]==true || plan["complete"]==false
puts "PASS Plan 受控地址/身份/无删除；仍需人工审查保存的二进制 Plan"
