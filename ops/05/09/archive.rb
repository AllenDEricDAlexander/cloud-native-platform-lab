#!/usr/bin/env ruby
# 只归档公开执行源与摘要；不复制实际输入、密钥、运行输出或备份。
require_relative "../lib/config"
require "fileutils"
require "open3"
require "time"
destination = required("handoff","archive_directory")
abort "归档必须是仓库外的新绝对目录" unless destination.start_with?("/") && !File.expand_path(destination).start_with?(REPO+"/") && !File.exist?(destination)
parent = File.realpath(File.dirname(destination))
abort "归档父目录不能经软链回到仓库" if parent.start_with?(REPO+"/")
FileUtils.mkdir_p(destination,:mode=>0700)
paths,status = Open3.capture2("git","-C",REPO,"ls-files","-z","--","ops/05","ops/inventory","ops/versions.lock.yaml","plan/05-observability.md","ops/00-preparation/ansible/ansible.cfg","ops/00-preparation/ansible/requirements.yml","ops/00-preparation/ansible/inventories/lab/hosts.yml","ops/00-preparation/ansible/inventories/lab/group_vars/all.yml")
abort "无法取得已提交源文件" unless status.success?
rows = paths.split("\0").map do |path|
  source = File.join(REPO,path)
  abort "拒绝归档私有或运行文件" if path.match?(%r{/(records|private|backups)/}) || path.match?(/\.(key|pem|kubeconfig|tfstate|dump)\z/) || File.symlink?(source)
  target = File.join(destination,path)
  FileUtils.mkdir_p(File.dirname(target),:mode=>0700)
  FileUtils.copy_file(source,target,true)
  {"path"=>path,"sha256"=>Digest::SHA256.file(source).hexdigest,"bytes"=>File.size(source)}
end
revision,success = Open3.capture2("git","-C",REPO,"rev-parse","HEAD")
abort "无法读取源提交" unless success.success?
File.write(File.join(destination,"manifest.json"),JSON.pretty_generate({"source_revision"=>revision.strip,"at"=>Time.now.utc.iso8601,"files"=>rows,"runtime_accepted"=>false,"phase_complete"=>false}))
puts "公开配置归档：#{destination}；不含实际凭据/运行输出/业务数据"
