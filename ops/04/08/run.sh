#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P04/validate.sh" 08 ;;
    render) shift; exec ruby "$P04/08/render.rb" "$@" ;;
    deploy-controllers|deploy-metrics|policy|observe|abort) ;;
    *) die '用法：08/run.sh validate|render canary|bluegreen|metrics|policy|deploy-controllers|deploy-metrics|policy|observe|abort' ;;
esac
start 08 "$action"
case "$action" in
    deploy-controllers) material argo_rollouts >/dev/null; material kyverno >/dev/null ;;
    deploy-metrics) prom=$(image prometheus_minimal); python=$(image probe_python) ;;
esac
cluster_gate
case "$action" in
    deploy-controllers) chart argo_rollouts argo-rollouts argo-rollouts; chart kyverno kyverno kyverno ;;
    deploy-metrics)
        private_temp
        jq --arg prom "$prom" --arg python "$python" '.render_images.prometheus_minimal=$prom | .render_images.probe_python=$python' "$INPUTS" > "$PRIVATE_TEMP/inputs.json"
        CNPL04_INPUTS="$PRIVATE_TEMP/inputs.json" render metrics > "$ATTEMPT/metrics.json"; apply "$ATTEMPT/metrics.json" ;;
    policy) render policy > "$ATTEMPT/policy.json"; apply "$ATTEMPT/policy.json" ;;
    observe)
        name=$(required .release.name)-rollout
        k -n apps-dev get rollout "$name" -o json > "$ATTEMPT/rollout.json"
        k -n apps-dev get analysisruns -o json > "$ATTEMPT/analysis.json"
        k -n apps-dev get httproute "$name" -o json > "$ATTEMPT/route.json"
        jq '{status:.status,desired:.spec.strategy}' "$ATTEMPT/rollout.json" ;;
    abort) material argo_rollouts >/dev/null; k argo rollouts abort "$(required .release.name)-rollout" -n apps-dev ;;
esac
