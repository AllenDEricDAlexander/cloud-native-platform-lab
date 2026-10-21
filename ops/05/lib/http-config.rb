#!/usr/bin/env ruby
require "uri"
uri = URI(ARGV.fetch(1))
abort "仅允许内部 HTTPS API" unless uri.scheme=="https" && uri.host && (uri.host.end_with?(".internal.egon.top", ".svc", ".svc.cluster.local") || uri.host.match?(/\A192\.168\.(9|20)\.\d{1,3}\z/)) && !uri.userinfo && !uri.query && !uri.fragment
allowed = %w[header user cacert capath cert key pass oauth2-bearer]
File.readlines(ARGV.fetch(0)).each do |line|
  value = line.strip
  next if value.empty? || value.start_with?("#")
  option = value.sub(/\A--/,"").split(/[\s=]/,2).first
  abort "curl 配置只允许认证与 CA 选项" unless allowed.include?(option) && !value.end_with?("\\")
end
