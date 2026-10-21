#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P06/validate.sh" 05 ;;
    render) export STAGE=05; exec ruby "$P06/05/render.rb" ;;
    verify-messages) exec ruby "$P06/05/messages.rb" "${2:?需要真实消息回执JSON}" ;;
    install|apply|check|observe|cleanup-plan) ;;
    *) die '用法：05/run.sh validate|render|install <vpa|keda>|apply|check|observe|verify-messages <file>|cleanup-plan' ;;
esac
start 05 "$action"
if [[ $action == cleanup-plan ]]; then cleanup_plan; exit; fi
if [[ $action == install ]]; then
    component=${2:-}; case "$component" in vpa|keda) ;; *) die '仅允许 vpa/keda' ;; esac
    ruby "$P06/lib/config.rb" material "$component" >/dev/null
fi
cluster_gate
case "$action" in
    install) install_component "$component" ;;
    apply) render > "$ATTEMPT/scaling.json"; apply_file "$ATTEMPT/scaling.json" ;;
    check|observe)
        check_namespace
        k -n "$NS" get hpa,vpa,scaledobjects -o json | redact_objects > "$ATTEMPT/controllers.json"
        k -n "$NS" rollout status deployment/hpa-demo --timeout=180s
        if [[ $action == observe ]]; then
            for sample in 1 2 3 4 5 6; do
                k -n "$NS" get hpa,vpa,scaledobjects,deployments -o json | redact_objects > "$ATTEMPT/sample-$sample.json"
                date -u +%FT%TZ > "$ATTEMPT/sample-$sample.time"
                sleep 10
            done
        fi
        ;;
esac
