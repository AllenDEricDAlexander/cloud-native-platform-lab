#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P06/validate.sh" 08 ;;
    render) export STAGE=08; exec ruby "$P06/08/render.rb" "${2:-argo}" ;;
    install|apply|queues|check|queue-check|cleanup-plan) ;;
    *) die '用法：08/run.sh validate|render <argo|queues>|install <argo_workflows|argo_events|kueue>|apply|queues|check|queue-check|cleanup-plan' ;;
esac
start 08 "$action"
if [[ $action == cleanup-plan ]]; then cleanup_plan; exit; fi
if [[ $action == install ]]; then
    component=${2:-}; case "$component" in argo_workflows|argo_events|kueue) ;; *) die '未知工作流组件' ;; esac
    ruby "$P06/lib/config.rb" material "$component" >/dev/null
fi
cluster_gate
case "$action" in
    install) install_component "$component" ;;
    apply) render > "$ATTEMPT/argo.json"; apply_file "$ATTEMPT/argo.json" ;;
    queues)
        render queues > "$ATTEMPT/queues.json"
        jq -n --arg ns "$NS" --arg name "cnpl06-$RUN-cpu" '{namespaces:[$ns],cluster_resources:[("ResourceFlavor/"+$name),("ClusterQueue/"+$name)]}' > "$ATTEMPT/scope.json"
        apply_file "$ATTEMPT/queues.json" "$ATTEMPT/scope.json"
        ;;
    check)
        check_namespace
        k -n "$NS" get eventbus,eventsource,sensor,workflows -o json > "$ATTEMPT/argo-state.json"
        ;;
    queue-check)
        check_namespace
        for sample in 1 2 3 4 5 6 7 8; do
            k -n "$NS" get workloads.kueue.x-k8s.io,jobs -o json > "$ATTEMPT/queue-$sample.json"
            date -u +%FT%TZ > "$ATTEMPT/queue-$sample.time"
            sleep 5
        done
        ;;
esac
