#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P06/validate.sh" 02 ;;
    render) export STAGE=02; exec ruby "$P06/02/render.rb" ;;
    install|apply|check|cleanup-plan) ;;
    *) die '用法：02/run.sh validate|render|install|apply|check|cleanup-plan' ;;
esac
start 02 "$action"
if [[ $action == cleanup-plan ]]; then cleanup_plan; exit; fi
if [[ $action == install ]]; then ruby "$P06/lib/config.rb" material kyverno >/dev/null; fi
cluster_gate
case "$action" in
    install) install_component kyverno ;;
    apply)
        render > "$ATTEMPT/policies.json"
        jq -n --arg ns "$NS" --arg policy "ClusterPolicy/cnpl06-$RUN-baseline" '{namespaces:[$ns],cluster_resources:[$policy]}' > "$ATTEMPT/scope.json"
        apply_file "$ATTEMPT/policies.json" "$ATTEMPT/scope.json"
        ;;
    check)
        check_namespace
        k -n "$NS" rollout status deployment/restricted-demo --timeout=180s
        render > "$ATTEMPT/policies.json"
        jq --arg ns "$NS" '.items[]|select(.kind=="Deployment")|{apiVersion:"v1",kind:"Pod",metadata:{name:"admission-positive",namespace:$ns,labels:.spec.template.metadata.labels},spec:.spec.template.spec}' "$ATTEMPT/policies.json" > "$ATTEMPT/positive.json"
        k create --dry-run=server -f "$ATTEMPT/positive.json" >/dev/null
        jq '.metadata.name="admission-negative"|.spec.containers[0].securityContext.privileged=true' "$ATTEMPT/positive.json" > "$ATTEMPT/negative.json"
        if k create --dry-run=server -f "$ATTEMPT/negative.json" > "$ATTEMPT/rejection.txt" 2>&1; then die '特权 Pod 未被拒绝'; fi
        ruby -e 'abort "拒绝不是 PSA/Kyverno 策略原因" unless File.read(ARGV[0]).match?(/violates PodSecurity|cnpl06.*baseline|bounded-trusted-pods/)' "$ATTEMPT/rejection.txt"
        [[ $(required .admission.mode) == Enforce ]] || printf '当前是 Audit，供应链强制拒绝尚未验收。\n'
        ;;
esac
