#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P06/validate.sh" 07 ;;
    render) export STAGE=07; exec ruby "$P06/07/render.rb" ;;
    install|apply|check|invoke|cleanup-plan) ;;
    *) die '用法：07/run.sh validate|render|install|apply|check|invoke|cleanup-plan' ;;
esac
start 07 "$action"
if [[ $action == cleanup-plan ]]; then cleanup_plan; exit; fi
if [[ $action == install ]]; then ruby "$P06/lib/config.rb" material dapr >/dev/null; fi
cluster_gate
case "$action" in
    install) install_component dapr ;;
    apply) render > "$ATTEMPT/dapr.json"; apply_file "$ATTEMPT/dapr.json" ;;
    check|invoke)
        check_namespace
        for language in python java; do k -n "$NS" rollout status "deployment/orders-$language" --timeout=180s; done
        if [[ $action == invoke ]]; then
            owned Deployment orders-python "$NS" >/dev/null
            k -n "$NS" exec deployment/orders-python -c app -- curl --fail --silent --show-error --max-time 10 http://127.0.0.1:3500/v1.0/invoke/orders-java/method/health > "$ATTEMPT/invoke.txt"
        fi
        ;;
esac
