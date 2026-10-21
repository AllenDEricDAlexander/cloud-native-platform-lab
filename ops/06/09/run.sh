#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P06/validate.sh" 09 ;;
    render) export STAGE=09; exec ruby "$P06/09/render.rb" ;;
    plan) exec ruby "$P06/09/plan.rb" ;;
    install|apply|check|destroy|cleanup-plan) ;;
    *) die '用法：09/run.sh validate|render|plan|install <capi|capv>|apply|check|destroy|cleanup-plan' ;;
esac
start 09 "$action"
if [[ $action == cleanup-plan ]]; then cleanup_plan; exit; fi
TARGET=$(required .capi.management_target)
case "$TARGET" in primary|management) ;; *) die '必须明确选择 primary 或独立 management' ;; esac
ruby "$P06/09/plan.rb" > "$ATTEMPT/plan.json"
if [[ $action == install ]]; then
    component=${2:-}; case "$component" in capi|capv) ;; *) die '仅允许 capi/capv' ;; esac
    ruby "$P06/lib/config.rb" material "$component" >/dev/null
fi
if [[ $action == apply ]]; then render > "$ATTEMPT/scope.json"; ruby "$P06/09/bundle.rb" > "$ATTEMPT/cluster.json"; fi
cluster_gate
case "$action" in
    install) install_component "$component" ;;
    apply) apply_file "$ATTEMPT/scope.json"; apply_file "$ATTEMPT/cluster.json" ;;
    check)
        check_namespace
        k -n "$NS" get clusters.cluster.x-k8s.io,machinedeployments,machines -o json > "$ATTEMPT/management-state.json"
        TARGET=secondary; cluster_gate
        ;;
    destroy)
        backup_gate
        evidence_gate capi management_backup
        expected=$(required .capi.approved_cluster_uid)
        delete_owned clusters.cluster.x-k8s.io "$(required .capi.cluster_name)" "$NS" "$expected"
        printf '仅提交 Cluster 删除请求；等待 Provider 清理并核对 VM/盘/DNS 后才算回收完成。\n'
        ;;
esac
