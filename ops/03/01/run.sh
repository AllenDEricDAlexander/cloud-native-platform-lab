#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P03/validate.sh" 01 ;;
    budget) ruby "$P03/lib/review.rb" devices "$DEVICES"; exit ;;
    inspect) ;;
    *) die '用法：01/run.sh validate|inspect|budget' ;;
esac
start 01 "$action"
export CNPL03_DEVICES_FILE=$DEVICES
export ANSIBLE_CONFIG="$REPO/ops/00-preparation/ansible/ansible.cfg"
ansible=${CNPL03_ANSIBLE:-$HOME/.venvs/cnpl-ansible/bin/ansible-playbook}
"$ansible" "$P03/01/inspect-playbook.yml" 2>&1 | tee "$ATTEMPT/inspection.txt"
