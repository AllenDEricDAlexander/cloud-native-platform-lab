#!/usr/bin/env ruby
require "json"
root = File.expand_path("..",__dir__)
expected = File.read(File.join(root,"../../plan/05-observability.md")).scan(/^### (05\.\d{2}\.\d{2}) /).flatten
data = JSON.parse(File.read(File.join(root,"coverage.json")))
rows = data.fetch("steps")
abort "42 步文件索引不完整/重复" unless expected.size==42 && rows.map { |r| r.fetch("id") }.sort==expected.sort
abort "离线交付不能提升运行状态" unless data["runtime_accepted"]==false && data["phase_complete"]==false && rows.all? { |r| r["runtime_status"]=="not_executed" }
rows.each do |row|
  abort "子阶段目录编号不符" unless row.fetch("directory")==row.fetch("id").split('.')[1]
  abort "缺少交付文件" if row.fetch("files").empty?
  row.fetch("files").each do |path|
    abort "引用文件不在对应子阶段或不存在" unless path.start_with?(row.fetch("directory")+"/") && !path.include?("..") && File.file?(File.join(root,path))
  end
end
puts "PASS 42 步交付/人工边界索引；运行状态均未执行"
