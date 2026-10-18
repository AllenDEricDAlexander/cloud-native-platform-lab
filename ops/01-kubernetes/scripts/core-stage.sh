#!/bin/bash
# 每个入口只执行一个专题，Ansible 负责全部 Kubernetes 变更和恢复。
set -euo pipefail
umask 077
root=$(cd "$(dirname "$0")/../../.." && pwd)
stage=${1:?stage required}
mode=${2:-validate}
records=${3:-}
[[ "$stage" =~ ^(07|08|09|10)$ ]]
resume=false
case "$mode" in
  resume) mode=run; resume=true ;;
  validate|run|cleanup) ;;
  *) echo '用法：stage-XX.sh validate|run|resume|cleanup 绝对证据目录' >&2; exit 2 ;;
esac
case "$records" in "$root"/ops/01-kubernetes/records/core-07-10/runs/"$stage"-*) ;; *) echo '请指定 records/core-07-10/runs/XX-... 下的独立证据目录' >&2; exit 2 ;; esac
[[ "$records" =~ ^[a-zA-Z0-9_./-]+$ && "$records" != *'/../'* && "$records" != */.. && "$records" != *'/./'* ]]
ansible="$HOME/.venvs/cnpl-ansible/bin/ansible-playbook"
[[ -x "$ansible" ]]
export ANSIBLE_CONFIG="$root/ops/00-preparation/ansible/ansible.cfg"
mkdir -p "$records"
input=$(mktemp "$records/.invocation.XXXXXX")
trap 'rm -f "$input"' EXIT
printf '{"core_stage":"%s","core_mode":"%s","core_records":"%s","core_resume":%s}\n' "$stage" "$mode" "$records" "$resume" > "$input"
log=$(mktemp "$records/ansible-$mode-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
"$ansible" "$root/ops/01-kubernetes/ansible/playbooks/stage-$stage.yml" -e "@$input" 2>&1 | tee "$log"
printf '\n本阶段完整日志：%s\n' "$log"
