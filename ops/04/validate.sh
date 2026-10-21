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
if [[ -f $root/tests/native.sh ]]; then bash "$root/tests/native.sh"; fi
if [[ -f $root/tests/source.py ]]; then
    python=${CNPL04_PYTHON:-python3}
    if ! "$python" -c 'import tomllib' >/dev/null 2>&1; then
        [[ -z ${CNPL04_PYTHON:-} && -x /opt/homebrew/bin/python3 ]] || { echo '需要既有Python3.11+解析TOML：设置CNPL04_PYTHON' >&2; exit 1; }
        python=/opt/homebrew/bin/python3
    fi
    PYTHONDONTWRITEBYTECODE=1 "$python" "$root/tests/source.py"
fi
if [[ -f $root/coverage.json ]]; then ruby "$root/lib/coverage.rb"; fi
printf 'PASS Phase 04 离线检查；未联网、未部署、未运行实验。\n'
