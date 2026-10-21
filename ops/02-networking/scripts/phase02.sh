#!/bin/bash
# 02.07–10 专题独立入口的公共启动器；全局网络批次按顺序执行。
set -euo pipefail
umask 077
root=$(cd "$(dirname "$0")/../../.." && pwd)
topic=${1:?缺少专题}
stage=${2:?缺少步骤}
mode=${3:-all}
records=${4:-}
case "$mode" in all|validate|cleanup|recover) ;; *) echo '模式仅支持 all|validate|cleanup|recover' >&2; exit 2 ;; esac
case "$topic:$stage" in scheduling:02.07|resource-governance:02.08|dataplane:02.09|mesh:02.10) ;; *) echo '专题与步骤不匹配' >&2; exit 2 ;; esac
case "$records" in "$root"/ops/02-networking/records/"$stage"-*) ;; *) echo '证据目录必须是本专题 records 下的绝对路径' >&2; exit 2 ;; esac
[[ "$records" =~ ^[a-zA-Z0-9_./-]+$ && "$records" != *'/../'* && "$records" != */.. ]]
mkdir -p "$records"
input=$(mktemp "$records/.invocation.XXXXXX")
log=''
finish() {
  status=$?
  trap - EXIT
  rm -f "$input"
  if [ -n "$log" ]; then
    "$HOME/.venvs/cnpl-ansible/bin/python" "$root/ops/02-networking/tests/integration/phase02/summary.py" \
      --log "$log" --records "$records" --status "$status" --mode "$mode" | tee -a "$log" || {
        printf '\n汇总生成失败，原执行退出码：%s\n完整日志：%s\n' "$status" "$log" >&2
        if [ "$status" -eq 0 ]; then status=1; fi
      }
  fi
  exit "$status"
}
trap finish EXIT
printf '{"phase_mode":"%s","phase_records":"%s"}\n' "$mode" "$records" > "$input"
export ANSIBLE_CONFIG="$root/ops/00-preparation/ansible/ansible.cfg"
log=$(mktemp "$records/ansible-$mode-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
"$HOME/.venvs/cnpl-ansible/bin/python" "$root/ops/02-networking/tests/integration/phase02/entry.py" "$topic" "$mode" "$records" "$input" 2>&1 | tee "$log"
