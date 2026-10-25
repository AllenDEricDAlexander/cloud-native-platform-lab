#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P03/validate.sh" 01 ;;
    budget) ruby "$P03/lib/review.rb" devices "$DEVICES"; exit ;;
    inspect|all) ;;
    *) die '用法：01/run.sh validate|inspect|budget|all' ;;
esac
start 01 "$action"
export CNPL03_DEVICES_FILE=$DEVICES
export ANSIBLE_CONFIG="$REPO/ops/00-preparation/ansible/ansible.cfg"
ansible=${CNPL03_ANSIBLE:-$HOME/.venvs/cnpl-ansible/bin/ansible-playbook}
"$ansible" "$P03/01/inspect-playbook.yml" 2>&1 | tee "$ATTEMPT/inspection.txt"
shopt -s nullglob
inventory_files=("$ATTEMPT"/storage*-disk-inventory.json)
[[ ${#inventory_files[@]} -eq 3 ]] || die '三台存储主机的整盘清单不完整'
jq -s '[.[] | .hostname as $host | .disks[] | {host:$host,path,bytes,hctl,role,stable_ids,eligible_for_osd}]' "${inventory_files[@]}" | tee "$ATTEMPT/disk-summary.json"
if [[ $action == all ]]; then
    ruby "$P03/lib/review.rb" devices "$DEVICES" | tee "$ATTEMPT/budget.json"
fi
