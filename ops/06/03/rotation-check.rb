#!/usr/bin/env ruby
require_relative "../lib/config"
data = JSON.parse(File.read(ARGV.fetch(0)))
expected = YAML.load_file(File.join(REPO,"ops/inventory/hosts.yaml")).fetch("kubernetes_nodes").select { |n| n["role"] == "control_plane" }.map { |n| n["fqdn"] }.sort
entries = data.fetch("control_planes")
abort "控制平面数量/身份不全" unless entries.map { |e| e["node"] }.sort == expected
abort "所有 API Server 必须具有同一配置 SHA 和新写密钥" unless entries.map { |e| e["encryption_config_sha256"] }.uniq.size == 1 && entries.map { |e| e["write_key_name"] }.uniq.size == 1 && entries.all? { |e| e["old_key_retained"] == true && e["old_canary_read_ok"] == true && e["new_canary_read_ok"] == true && e["encryption_config_sha256"].to_s.match?(/\A[0-9a-f]{64}\z/) }
abort "备份历史密钥未确认" unless data["historical_backup_keys_retained"] == true && data["isolated_restore_ok"] == true
puts JSON.pretty_generate({"receipt_consistent"=>true,"key_retirement_authorized"=>false,"runtime_accepted"=>false})
