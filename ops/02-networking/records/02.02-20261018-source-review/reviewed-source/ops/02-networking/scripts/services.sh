#!/bin/bash
# 一个入口覆盖完整 02.02；专题 playbook 分开，默认 all 一次校验、执行、清理。
set -euo pipefail
umask 077
root=$(cd "$(dirname "$0")/../../.." && pwd)
mode=${1:-all}
records=${2:-}
case "$mode" in all|validate|run|cleanup|recover) ;; *) echo '用法：services.sh all|validate|run|cleanup|recover 绝对证据目录' >&2; exit 2 ;; esac
case "$records" in "$root"/ops/02-networking/records/02.02-*) ;; *) echo '目录必须位于 records/02.02-... 下' >&2; exit 2 ;; esac
[[ "$records" =~ ^[a-zA-Z0-9_./-]+$ && "$records" != *'/../'* && "$records" != */.. && "$records" != *'/./'* ]]
mkdir -p "$records"
if ! mkdir "$records/.lock" 2>/dev/null; then echo '本批已有命令运行，请先确认原进程状态。' >&2; exit 2; fi
input=$(mktemp "$records/.invocation.XXXXXX")
trap 'result=$?; rm -f "$input"; rmdir "$records/.lock"; if [ "$result" -ne 0 ]; then printf "\n本次未完成；日志和现场已保留。清理入口：bash %s/ops/02-networking/scripts/services.sh recover %s\n" "$root" "$records" >&2; fi' EXIT
printf '{"services_mode":"%s","services_records":"%s"}\n' "$mode" "$records" > "$input"
export ANSIBLE_CONFIG="$root/ops/00-preparation/ansible/ansible.cfg"
log=$(mktemp "$records/ansible-$mode-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
"$HOME/.venvs/cnpl-ansible/bin/ansible-playbook" "$root/ops/02-networking/ansible/playbooks/services.yml" -e "@$input" 2>&1 | tee "$log"
printf '\n完整日志：%s\n' "$log"
