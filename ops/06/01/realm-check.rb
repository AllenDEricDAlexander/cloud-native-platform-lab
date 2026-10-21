#!/usr/bin/env ruby
require_relative "../lib/config"
issuer = URI.parse(required("identity","issuer"))
abort "OIDC 必须为内网 HTTPS issuer" unless issuer.scheme == "https" && issuer.host.to_s.end_with?(".internal.egon.top") && issuer.path.match?(%r{\A/realms/[a-z0-9-]+\z}) && !issuer.userinfo
realm = parse_json(File.read(required("identity","realm_file")))
session = parse_json(File.read(required("identity","kcadm_config")))
server = URI.parse(session.fetch("serverUrl"))
abort "kcadm 会话与审核 issuer 不同" unless [server.scheme,server.host,server.port] == [issuer.scheme,issuer.host,issuer.port]
abort "Realm 与 issuer 不同或未启用" unless realm["realm"] == issuer.path.split("/").last && realm["enabled"] == true
walk(realm) { |v| abort "Realm 文件不得内嵌凭据" if v.is_a?(Hash) && %w[credentials secret clientSecret password].any? { |key| v.key?(key) && v[key] != [] && v[key] != nil } }
