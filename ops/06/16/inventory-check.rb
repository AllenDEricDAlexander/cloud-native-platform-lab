#!/usr/bin/env ruby
require_relative "../lib/config"
verified(required("backup","inventory_file"),required("backup","inventory_sha256"))
data = JSON.parse(File.read(required("backup","inventory_file")))
expected = JSON.parse(File.read(File.join(__dir__,"inventory.json")))
abort "备份分层不全" unless data.fetch("layers").map { |l| l["name"] }.sort == expected.fetch("layers").map { |l| l["name"] }.sort
data.fetch("layers").each do |layer|
  abort "备份层字段不全" unless expected.fetch("required_per_layer").all? { |k| layer.key?(k) && !layer[k].nil? && layer[k] != "" && layer[k] != [] }
  abort "备份目标不独立或未抽样恢复" unless layer["outside_primary_ceph"] == true && layer["outside_three_esxi"] == true && layer["sample_restore_verified"] == true
end
puts JSON.generate({"inventory_consistent"=>true,"runtime_accepted"=>false})
