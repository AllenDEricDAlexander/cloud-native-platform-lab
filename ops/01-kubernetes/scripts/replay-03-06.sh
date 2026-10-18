#!/bin/bash
# 唯一的薄入口：参数与日志交给 shell，所有实际执行步骤在 Ansible YAML。
set -euo pipefail
umask 077
root=$(cd "$(dirname "$0")/../../.." && pwd)
mode=${1:-validate}
records=${2:-}
topics=${3:-03,04,05,06}
resume=false
case "$mode" in
  resume) mode=run; resume=true ;;
  validate|run|images|recover|cleanup) ;;
  *) echo '用法：replay-03-06.sh validate|run|resume|images|recover|cleanup 绝对记录目录 [03,04,05,06]' >&2; exit 2 ;;
esac
case "$records" in
  "$root"/ops/01-kubernetes/records/2026-10-18-ansible-replay/runs/*) ;;
  *) echo '记录目录必须是本仓库 ops/01-kubernetes/records/2026-10-18-ansible-replay/runs/ 下的新目录' >&2; exit 2 ;;
esac
# 此限制使参数文件无需任何 shell/JSON 转义，也阻止目录越界。
[[ "$records" =~ ^[a-zA-Z0-9_./-]+$ && "$records" != *'/../'* && "$records" != */.. && "$records" != *'/./'* ]]
[[ "$topics" =~ ^0[3-6](,0[3-6])*$ ]]
ansible="$HOME/.venvs/cnpl-ansible/bin/ansible-playbook"
[[ -x "$ansible" ]]
export ANSIBLE_CONFIG="$root/ops/00-preparation/ansible/ansible.cfg"
mkdir -p "$records"
vars=$(mktemp "$records/.invocation.XXXXXX")
trap 'rm -f "$vars"' EXIT
printf '{"replay_mode":"%s","replay_records":"%s","replay_topics":["%s"],"replay_resume":%s}\n' "$mode" "$records" "${topics//,/\",\"}" "$resume" > "$vars"
log=$(mktemp "$records/ansible-${mode}-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
"$ansible" "$root/ops/01-kubernetes/ansible/playbooks/replay.yml" --extra-vars "@$vars" 2>&1 | tee "$log"
printf '\n本次 Ansible 完整日志：%s\n' "$log"
