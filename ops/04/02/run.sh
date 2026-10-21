#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P04/validate.sh" 02 ;;
    render) exec ruby "$P04/02/render.rb" ;;
    deploy|check) ;;
    *) die '用法：02/run.sh validate|render|deploy|check；构建使用 build.sh <language>' ;;
esac
start 02 "$action"
ref=$(image buildkit)
worker_gate
cluster_gate
if [[ $action == deploy ]]; then
    private_temp
    jq --arg image "$ref" '.render_images.buildkit=$image' "$INPUTS" > "$PRIVATE_TEMP/inputs.json"
    CNPL04_INPUTS="$PRIVATE_TEMP/inputs.json" render > "$ATTEMPT/buildkit.json"
    apply "$ATTEMPT/buildkit.json"
fi
for trust in trusted untrusted; do
    k -n ci-build rollout status "statefulset/buildkit-$trust" --timeout=180s
    k -n ci-build get "statefulset/buildkit-$trust" -o json > "$ATTEMPT/buildkit-$trust-state.json"
done
