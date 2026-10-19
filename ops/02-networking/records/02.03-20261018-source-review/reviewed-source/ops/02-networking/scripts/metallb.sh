#!/bin/bash
# 完整 02.03 一个入口；故障与恢复始终同批完成。
set -euo pipefail
umask 077
root=$(cd "$(dirname "$0")/../../.." && pwd)
mode=${1:-all}
records=${2:-}
case "$mode" in all|validate|run|cleanup|recover) ;; *) echo '用法：metallb.sh all|validate|run|cleanup|recover 绝对证据目录' >&2; exit 2 ;; esac
case "$records" in "$root"/ops/02-networking/records/02.03-*) ;; *) echo '目录必须位于 records/02.03-... 下' >&2; exit 2 ;; esac
[[ "$records" =~ ^[a-zA-Z0-9_./-]+$ && "$records" != *'/../'* && "$records" != */.. && "$records" != *'/./'* ]]
mkdir -p "$records" "$root/ops/02-networking/records/components"
guard="$root/ops/02-networking/records/components/.metallb-batch.lock"
input=$(mktemp "$records/.invocation.XXXXXX")
trap 'result=$?; rm -f "$input"; if [ "$result" -ne 0 ]; then printf "\n未完成，原始证据已保留；恢复入口：bash %s/ops/02-networking/scripts/metallb.sh recover %s\n" "$root" "$records" >&2; fi' EXIT
printf '{"metallb_mode":"%s","metallb_records":"%s"}\n' "$mode" "$records" > "$input"
export ANSIBLE_CONFIG="$root/ops/00-preparation/ansible/ansible.cfg"
log=$(mktemp "$records/ansible-$mode-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
"$HOME/.venvs/cnpl-ansible/bin/python" -c '
import fcntl, os, sys
fd = os.open(sys.argv[1], os.O_CREAT | os.O_RDWR, 0o600)
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    sys.exit("已有 MetalLB 批次运行，请先确认原进程状态。")
os.set_inheritable(fd, True)
os.execv(sys.argv[2], sys.argv[2:])
' "$guard" "$HOME/.venvs/cnpl-ansible/bin/ansible-playbook" "$root/ops/02-networking/ansible/playbooks/metallb.yml" -e "@$input" 2>&1 | tee "$log"
printf '\n完整日志：%s\n' "$log"
