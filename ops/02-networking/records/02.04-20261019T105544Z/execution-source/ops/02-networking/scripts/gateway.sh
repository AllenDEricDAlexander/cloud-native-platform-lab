#!/bin/bash
# 完整 02.04 一个入口；CA 口令只由 Python 启动进程安全读取一次。
set -euo pipefail
umask 077
root=$(cd "$(dirname "$0")/../../.." && pwd)
mode=${1:-all}
records=${2:-}
case "$mode" in all|validate|run|cleanup|recover) ;; *) echo '用法：gateway.sh all|validate|run|cleanup|recover 绝对证据目录' >&2; exit 2 ;; esac
case "$records" in "$root"/ops/02-networking/records/02.04-*) ;; *) echo '目录必须位于 records/02.04-... 下' >&2; exit 2 ;; esac
[[ "$records" =~ ^[a-zA-Z0-9_./-]+$ && "$records" != *'/../'* && "$records" != */.. && "$records" != *'/./'* ]]
mkdir -p "$records" "$root/ops/02-networking/records/components"
input=$(mktemp "$records/.invocation.XXXXXX")
trap 'result=$?; rm -f "$input"; if [ "$result" -ne 0 ]; then if [ -f "$records/state/protected.json" ]; then printf "\n未完成，原始证据已保留；恢复入口：bash %s/ops/02-networking/scripts/gateway.sh recover %s\n" "$root" "$records" >&2; else printf "\n前检未通过，未执行集群变更；修复后可使用原目录重新运行 all。\n" >&2; fi; fi' EXIT
printf '{"gateway_mode":"%s","gateway_records":"%s"}\n' "$mode" "$records" > "$input"
export ANSIBLE_CONFIG="$root/ops/00-preparation/ansible/ansible.cfg"
log=$(mktemp "$records/ansible-$mode-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
"$HOME/.venvs/cnpl-ansible/bin/python" "$root/ops/02-networking/tests/integration/gateway/entry.py" "$mode" "$records" "$input" 2>&1 | tee "$log"
printf '\n完整日志：%s\n' "$log"
