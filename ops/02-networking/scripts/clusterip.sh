#!/bin/bash
# 只运行 02.02.01；复用原 inventory 和显式 kubeconfig，不开启后续专题。
set -euo pipefail
umask 077
root=$(cd "$(dirname "$0")/../../.." && pwd)
mode=${1:-preflight}
records=${2:-}
case "$mode" in preflight|validate|run|cleanup) ;; *) echo '用法：clusterip.sh preflight|validate|run|cleanup 绝对证据目录' >&2; exit 2 ;; esac
case "$records" in "$root"/ops/02-networking/records/02.02.01-*) ;; *) echo '目录必须位于 records/02.02.01-... 下' >&2; exit 2 ;; esac
[[ "$records" =~ ^[a-zA-Z0-9_./-]+$ && "$records" != *'/../'* && "$records" != */.. && "$records" != *'/./'* ]]
mkdir -p "$records"
if ! mkdir "$records/.lock" 2>/dev/null; then echo '本批已有命令运行，请先确认原进程状态。' >&2; exit 2; fi
input=$(mktemp "$records/.invocation.XXXXXX")
trap 'rm -f "$input"; rmdir "$records/.lock"' EXIT
printf '{"svc_mode":"%s","svc_records":"%s"}\n' "$mode" "$records" > "$input"
export ANSIBLE_CONFIG="$root/ops/00-preparation/ansible/ansible.cfg"
log=$(mktemp "$records/ansible-$mode-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
"$HOME/.venvs/cnpl-ansible/bin/ansible-playbook" "$root/ops/02-networking/ansible/playbooks/service-clusterip.yml" -e "@$input" 2>&1 | tee "$log"
printf '\n完整日志：%s\n' "$log"
