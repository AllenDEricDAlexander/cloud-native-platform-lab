#!/bin/bash
# 02.06 全组单入口：只读前检 / 全组验证并清理 / 原批恢复。
set -euo pipefail
umask 077
root=$(cd "$(dirname "$0")/../../.." && pwd)
mode=${1:-all}
records=${2:-}
case "$mode" in all|validate|cleanup|recover) ;; *) echo '用法：policies.sh all|validate|cleanup|recover 绝对证据目录' >&2; exit 2 ;; esac
case "$records" in "$root"/ops/02-networking/records/02.06-*) ;; *) echo '证据目录必须位于 records/02.06-... 下' >&2; exit 2 ;; esac
[[ "$records" =~ ^[a-zA-Z0-9_./-]+$ && "$records" != *'/../'* && "$records" != */.. && "$records" != *'/./'* ]]
mkdir -p "$records"
input=$(mktemp "$records/.invocation.XXXXXX")
trap 'result=$?; rm -f "$input"; if [ "$result" -ne 0 ]; then if [ -f "$records/state/protected.json" ]; then printf "\n未完成，原始日志保留。原批恢复入口：bash %s/ops/02-networking/scripts/policies.sh recover %s\n" "$root" "$records" >&2; else printf "\n前检未完成，未开始集群变更；原始日志保留，修复前置后使用新目录 all。\n" >&2; fi; fi' EXIT
printf '{"pol_mode":"%s","pol_records":"%s"}\n' "$mode" "$records" > "$input"
export ANSIBLE_CONFIG="$root/ops/00-preparation/ansible/ansible.cfg"
log=$(mktemp "$records/ansible-$mode-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
"$HOME/.venvs/cnpl-ansible/bin/python" "$root/ops/02-networking/tests/integration/policies/entry.py" "$mode" "$records" "$input" 2>&1 | tee "$log"
printf '\n完整日志：%s\n' "$log"
