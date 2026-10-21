#!/usr/bin/env bash
set -euo pipefail
set +x
curl_safe() {
    local config=$1 url=$2
    shift 2
    [[ $url =~ ^https://[a-z0-9.-]+\.internal\.egon\.top(/|$) ]] || { echo '仅接受内网 HTTPS API' >&2; return 1; }
    ruby -e 's=File.stat(ARGV[0]);abort "curl config 权限不符" unless s.uid==Process.uid && [0400,0600].include?(s.mode & 0777);File.foreach(ARGV[0]){|l|l=l.strip;next if l.empty? || l.start_with?("#");abort "curl config 只允许认证和 CA 选项" unless l.match?(/\A(header|cacert|user|cert|key)\s*=/)}' "$config"
    curl --config "$config" --fail --silent --show-error --connect-timeout 10 --max-time 60 --proto '=https' "$url" "$@"
}
