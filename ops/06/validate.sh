#!/usr/bin/env bash
# 所有检查仅本地文件与构造；不调用真实集群/SSH/网络客户端。
set -euo pipefail
root=$(cd "$(dirname "$0")" && pwd)
stage=${1:-all}
[[ $stage == all || $stage =~ ^(0[1-9]|1[0-7])$ ]] || exit 2
while IFS= read -r file; do bash -n "$file"; done < <(find "$root" -type d -name records -prune -o -type f -name '*.sh' -print | sort)
while IFS= read -r file; do ruby -c "$file" >/dev/null; done < <(find "$root" -type d -name records -prune -o -type f -name '*.rb' -print | sort)
ruby "$root/lib/config.rb" source
if [[ -f $root/tests/offline.rb ]]; then ruby "$root/tests/offline.rb"; fi
if [[ -f $root/coverage.json ]]; then ruby "$root/lib/coverage.rb"; fi
printf 'PASS Phase 06 离线检查；未联网、未部署、未启动实验。\n'
