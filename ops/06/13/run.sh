#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P06/validate.sh" 13 ;;
    render) export STAGE=13; exec ruby "$P06/13/render.rb" "${2:-cpu}" ;;
    cost) exec ruby "$P06/13/cost.rb" "${2:?需要实测成本输入JSON}" ;;
    install|apply|vllm|training|check|predict|cleanup-plan) ;;
    *) die '用法：13/run.sh validate|render <cpu|vllm|training>|install <kserve|kubeflow|llm_d>|apply|vllm|training|check|predict|cost <file>|cleanup-plan' ;;
esac
start 13 "$action"
if [[ $action == cleanup-plan ]]; then cleanup_plan; exit; fi
if [[ $action == predict ]]; then
    private_file "$(required .ai.curl_config)"
    url=$(required .ai.url)
    [[ $url =~ ^https://[a-z0-9.-]+\.internal\.egon\.top(:[0-9]+)?(/.*)?$ ]] || die '预测入口必须是内网 HTTPS'
    private_temp
    ruby -rjson -e 'JSON.parse(File.read(ARGV[0]));JSON.parse(File.read(ARGV[1]))' "$(required .ai.request_file)" "$(required .ai.expected_file)"
    curl --config "$(required .ai.curl_config)" --proto '=https' --fail --silent --show-error --max-time 60 -H 'Content-Type: application/json' --data-binary "@$(required .ai.request_file)" "$url" --output "$PRIVATE_TEMP/response.json"
    ruby -rjson -e 'abort "预测结果不符" unless JSON.parse(File.read(ARGV[0]))==JSON.parse(File.read(ARGV[1]))' "$PRIVATE_TEMP/response.json" "$(required .ai.expected_file)"
    jq -n --arg sha "$(sha "$PRIVATE_TEMP/response.json")" '{response_sha256:$sha,expected_matched:true,runtime_accepted:false}' > "$ATTEMPT/predict.json"
    exit
fi
if [[ $action == vllm ]]; then ruby "$P06/12/gate.rb" > "$ATTEMPT/gpu-plan.json"; fi
if [[ $action == install ]]; then
    component=${2:-}; case "$component" in kserve|kubeflow) ;; llm_d) ruby "$P06/12/gate.rb" > "$ATTEMPT/gpu-plan.json"; evidence_gate ai distributed_evidence ;; *) die '未知 AI 组件' ;; esac
    ruby "$P06/lib/config.rb" material "$component" >/dev/null
fi
cluster_gate
case "$action" in
    install) install_component "$component" ;;
    apply) render cpu > "$ATTEMPT/ai.json"; apply_file "$ATTEMPT/ai.json" ;;
    vllm|training) render "$action" > "$ATTEMPT/ai.json"; apply_file "$ATTEMPT/ai.json" ;;
    check)
        check_namespace
        k -n "$NS" get inferenceservices -o json > "$ATTEMPT/inference.json"
        k -n "$NS" wait inferenceservice/cpu-model --for=condition=Ready --timeout=300s
        ;;
esac
