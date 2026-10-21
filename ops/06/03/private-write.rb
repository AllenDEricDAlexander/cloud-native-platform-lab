#!/usr/bin/env ruby
require_relative "../lib/config"
source, destination = ARGV
parent = File.realpath(File.dirname(destination))
abort "输出必须在仓库外受控目录" unless destination.start_with?("/") && parent != REPO && !parent.start_with?(REPO+"/") && File.stat(parent).uid == Process.uid && (File.stat(parent).mode & 0077) == 0
abort "输入输出无效" unless File.file?(source) && File.size(source)>0 && File.basename(destination).match?(/\A[a-zA-Z0-9_.-]+\z/)
File.open(File.join(parent,File.basename(destination)),File::WRONLY|File::CREAT|File::EXCL,0600) { |f| f.write(File.binread(source)); f.flush; f.fsync }
