#!/usr/bin/env bash
# 离线入口；不调用真实 kubectl/helm/SSH/CI API。
set -euo pipefail
root=$(cd "$(dirname "$0")" && pwd)
stage=${1:-all}
[[ $stage == all || $stage =~ ^(0[1-9]|10)$ ]] || exit 2
while IFS= read -r file; do bash -n "$file"; done < <(find "$root" -type d \( -name records -o -name node_modules -o -name target -o -name build \) -prune -o -type f -name '*.sh' -print | sort)
while IFS= read -r file; do ruby -c "$file" >/dev/null; done < <(find "$root" -type d -name records -prune -o -type f -name '*.rb' -print | sort)
ruby "$root/lib/config.rb" source
if [[ -f $root/tests/offline.sh ]]; then bash "$root/tests/offline.sh"; fi
if [[ -f $root/coverage.json ]]; then ruby "$root/lib/coverage.rb"; fi
printf 'PASS Phase 04 离线检查；未联网、未部署、未运行实验。\n'
