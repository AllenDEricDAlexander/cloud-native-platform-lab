#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P05/validate.sh" 07 ;;
    render) exec ruby "$P05/07/render.rb" "${2:-resources}" ;;
    timeline-append) exec ruby "$P05/07/timeline.rb" append ;;
    timeline-report) exec ruby "$P05/07/timeline.rb" report ;;
    install|check|analysis-run|rollout-check) ;;
    *) die '用法：07/run.sh validate|render [resources|rules|rollout-patch]|install|check|analysis-run|rollout-check|timeline-append|timeline-report' ;;
esac
start 07 "$action"
cluster_gate
case "$action" in
    install)
        ruby "$P05/07/render.rb" > "$ATTEMPT/slo.json"; apply "$ATTEMPT/slo.json" ;;
    check)
        service=$(required .slo.service); env=$(required .slo.environment)
        [[ $service =~ ^[a-zA-Z0-9_.-]+$ && $env =~ ^[a-zA-Z0-9_.-]+$ ]] || die 'SLI 标签格式无效'
        query "cnpl05:slo_error_ratio:5m{service=\"$service\",environment=\"$env\"}" "$ATTEMPT/error-ratio.json"
        query "cnpl05:slo_latency_good_ratio:5m{service=\"$service\",environment=\"$env\"}" "$ATTEMPT/latency-ratio.json" ;;
    analysis-run)
        ns=$(required .slo.rollout_namespace)
        k -n "$ns" get analysistemplate "cnpl05-$RUN-slo" -o json > "$ATTEMPT/template.json"
        ownership_gate <(jq '{items:[.]}' "$ATTEMPT/template.json")
        name=cnpl05-$RUN-$(date -u +%H%M%S)
        jq --arg name "$name" '{apiVersion:"argoproj.io/v1alpha1",kind:"AnalysisRun",metadata:{name:$name,namespace:.metadata.namespace},spec:.spec}' "$ATTEMPT/template.json" > "$ATTEMPT/analysis.json"
        apply "$ATTEMPT/analysis.json"
        for _ in {1..90}; do
            k -n "$ns" get analysisrun "$name" -o json > "$ATTEMPT/analysis-status.json"
            phase=$(jq -r '.status.phase // "Pending"' "$ATTEMPT/analysis-status.json")
            case "$phase" in Successful) exit 0 ;; Failed|Error|Inconclusive) die "AnalysisRun=$phase" ;; esac
            sleep 5
        done
        die 'AnalysisRun 等待超时，保留现场' ;;
    rollout-check)
        k -n "$(required .slo.rollout_namespace)" get rollout "$(required .slo.rollout_name)" -o json > "$ATTEMPT/rollout.json"
        jq -e --arg uid "$(required .slo.rollout_uid)" --arg template "cnpl05-$RUN-slo" '.metadata.uid==$uid and any(.spec.strategy.canary.analysis.templates[]; .templateName==$template)' "$ATTEMPT/rollout.json" >/dev/null || die 'Rollout UID/分析接入不符'
        printf '已保存真实状态；暂停/批准/中止/回退与客户端结果仍需发布流程验收。\n' ;;
esac
