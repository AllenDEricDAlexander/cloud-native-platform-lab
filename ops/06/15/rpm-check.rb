#!/usr/bin/env ruby
require_relative "../lib/config"
lock = YAML.load_file(File.join(REPO,"ops/versions.lock.yaml")).fetch("components").fetch("kubernetes_upgrade") { abort "目标升级物料尚未在主锁登记" }
abort "目标版本主锁不符" unless lock["version"] == required("upgrade","target_version").delete_prefix("v")
leaves = []; walk(lock) { |v| leaves << v if v.is_a?(String) }
%w[kubeadm kubelet kubectl].each do |key|
  file = required("upgrade","#{key}_rpm"); sha = required("upgrade","#{key}_rpm_sha256")
  verified(file,sha)
  abort "升级 RPM SHA 不在主锁" unless leaves.include?(sha)
end
