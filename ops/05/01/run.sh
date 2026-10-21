#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P05/validate.sh" 01 ;;
    hosts) exec ruby "$P05/lib/config.rb" hosts ;;
    budget) exec ruby "$P05/01/budget.rb" ;;
    inspect|install|configure|verify) ;;
    *) die '用法：01/run.sh validate|hosts|budget|inspect|install|configure|verify' ;;
esac
start 01 "$action"
ansible=${CNPL05_ANSIBLE:-$HOME/.venvs/cnpl-ansible/bin/ansible-playbook}
[[ -x $ansible ]] || die '缺少既有 Ansible，请设置 CNPL05_ANSIBLE'
vars=$(required .zabbix.private_vars_file)
private_file "$vars"
ruby "$P05/lib/config.rb" hosts > "$ATTEMPT/hosts.json"
private_temp
ruby "$P05/01/prepare.rb" "$vars" "$action" > "$PRIVATE_TEMP/zabbix.json"
export ANSIBLE_CONFIG="$REPO/ops/00-preparation/ansible/ansible.cfg"
export ANSIBLE_ROLES_PATH="$P05/01/roles:$REPO/ops/00-preparation/ansible/roles"
export ANSIBLE_DISPLAY_ARGS_TO_STDOUT=false ANSIBLE_LOG_PATH=/dev/null
case "$action" in
    inspect) playbook=inspect.yml ;;
    install) material zabbix >/dev/null; playbook=install.yml ;;
    configure) playbook=configure.yml ;;
    verify) playbook=verify.yml ;;
esac
"$ansible" -i "$REPO/$(required .zabbix.inventory)" "$P05/01/$playbook" --extra-vars "@$vars" --extra-vars "@$INPUTS" --extra-vars "@$PRIVATE_TEMP/zabbix.json" > "$ATTEMPT/ansible.txt" 2>&1
