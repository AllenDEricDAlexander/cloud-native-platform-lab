#!/bin/bash
# 完整 02.05 一个入口；公网按已确认范围记为 BLOCKED。
set -euo pipefail
umask 077
root=$(cd "$(dirname "$0")/../../.." && pwd)
mode=${1:-all}
records=${2:-}
case "$mode" in all|run|validate|cleanup|recover) ;; *) echo '用法：certificates.sh all|run|validate|cleanup|recover 绝对证据目录' >&2; exit 2 ;; esac
case "$records" in "$root"/ops/02-networking/records/02.05-*) ;; *) echo '目录必须位于 records/02.05-... 下' >&2; exit 2 ;; esac
[[ "$records" =~ ^[a-zA-Z0-9_./-]+$ && "$records" != *'/../'* && "$records" != */.. && "$records" != *'/./'* ]]
mkdir -p "$records"
input=$(mktemp "$records/.invocation.XXXXXX")
trap 'result=$?; rm -f "$input"; if [ "$result" -ne 0 ]; then if [ -f "$records/state/protected.json" ]; then printf "\n原始证据已保留；恢复：bash %s/ops/02-networking/scripts/certificates.sh recover %s\n" "$root" "$records" >&2; else printf "\n前检或签发材料准备失败，未执行集群变更；修复后可用原目录重新 all。\n" >&2; fi; fi' EXIT
printf '{"tls_mode":"%s","tls_records":"%s"}\n' "$mode" "$records" > "$input"
export ANSIBLE_CONFIG="$root/ops/00-preparation/ansible/ansible.cfg"
log=$(mktemp "$records/ansible-$mode-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
"$HOME/.venvs/cnpl-ansible/bin/python" "$root/ops/02-networking/tests/integration/certificates/entry.py" "$mode" "$records" "$input" 2>&1 | tee "$log"
printf '\n完整日志：%s\n' "$log"
