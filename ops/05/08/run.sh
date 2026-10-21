#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P05/validate.sh" 08 ;;
    render) exec ruby "$P05/08/render.rb" ;;
    languages-report) exec ruby "$P05/08/report.rb" languages ;;
    ci-report) exec ruby "$P05/08/report.rb" ci ;;
    load|install-opencost|cost-check) ;;
    *) die '用法：08/run.sh validate|render|load|install-opencost|cost-check|languages-report|ci-report' ;;
esac
start 08 "$action"
cluster_gate
if [[ $action == load ]]; then
    private_file "$(required .performance.safety_private_file)"
    token=$(jq -r '.performance.token_file // ""' "$INPUTS"); [[ -z $token ]] || private_file "$token"
    private_temp
    ruby "$P05/08/prepare.rb" > "$PRIVATE_TEMP/load.json"
    ansible=${CNPL05_ANSIBLE:-$HOME/.venvs/cnpl-ansible/bin/ansible-playbook}
    [[ -x $ansible ]] || die '缺少既有 Ansible'
    export ANSIBLE_CONFIG="$REPO/ops/00-preparation/ansible/ansible.cfg" ANSIBLE_LOG_PATH=/dev/null
    "$ansible" -i "$REPO/ops/00-preparation/ansible/inventories/lab/hosts.yml" "$P05/08/load.yml" --extra-vars "@$INPUTS" --extra-vars "@$PRIVATE_TEMP/load.json" > "$ATTEMPT/ansible.txt" 2>&1
elif [[ $action == install-opencost ]]; then
    private_temp
    ruby "$P05/08/render.rb" > "$PRIVATE_TEMP/values.yaml"
    chart opencost cnpl05-opencost "$(required .namespaces.metrics)" "$PRIVATE_TEMP/values.yaml"
else
    ruby "$P05/08/render.rb" >/dev/null
    http "$(required .performance.opencost_curl_config)" "$(required .performance.opencost_url)/allocation" --get --data-urlencode 'window=1h' --data-urlencode 'aggregate=namespace,controller' --data-urlencode 'includeIdle=true' > "$ATTEMPT/allocation.json"
    jq -e '.code==200 and (.data|length)>0 and ([.data[] | to_entries[].value.totalCost]|add)>0' "$ATTEMPT/allocation.json" >/dev/null || die '成本为空或全零，检查模型/指标覆盖'
    query 'sum by(namespace) (kube_pod_container_resource_requests{resource="cpu"})' "$ATTEMPT/cpu-requests.json"
    query 'sum by(namespace) (rate(container_cpu_usage_seconds_total{container!=""}[5m]))' "$ATTEMPT/cpu-used.json"
    query 'sum by(namespace) (container_memory_working_set_bytes{container!=""})' "$ATTEMPT/memory-used.json"
fi
