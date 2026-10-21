#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P06/validate.sh" 11 ;;
    render) export STAGE=11; exec ruby "$P06/11/render.rb" ;;
    inspect-host|install|apply|check|start|stop|restart|migrate|cleanup-plan) ;;
    *) die '用法：11/run.sh validate|render|inspect-host|install <kubevirt|cdi>|apply|check|start|stop|restart|migrate|cleanup-plan' ;;
esac
start 11 "$action"
if [[ $action == cleanup-plan ]]; then cleanup_plan; exit; fi
node=$(required .virtualization.node); node_ip "$node" >/dev/null
if [[ $action != inspect-host ]]; then evidence_gate virtualization evidence; fi
if [[ $action == migrate ]]; then evidence_gate virtualization migration_evidence; backup_gate; fi
if [[ $action == install ]]; then
    component=${2:-}; case "$component" in kubevirt|cdi) ;; *) die '仅允许 kubevirt/cdi' ;; esac
    ruby "$P06/lib/config.rb" material "$component" >/dev/null
fi
cluster_gate
case "$action" in
    inspect-host) remote_node "$node" "$P06/11/inspect-host.sh" > "$ATTEMPT/kvm.txt" ;;
    install) install_component "$component" ;;
    apply) render > "$ATTEMPT/vm.json"; apply_file "$ATTEMPT/vm.json" ;;
    check)
        check_namespace
        k -n "$NS" get vm,vmi,datavolumes,pvc -o json > "$ATTEMPT/virtualization.json"
        ;;
    start|stop|restart|migrate)
        owned virtualmachines.kubevirt.io vm-demo "$NS" >/dev/null
        if [[ $action == start ]]; then k -n "$NS" wait datavolume/vm-root '--for=jsonpath={.status.phase}=Succeeded' --timeout=300s; fi
        if [[ $action == migrate ]]; then k -n "$NS" get vmi vm-demo -o json | jq -e '.status.conditions[]|select(.type=="LiveMigratable" and .status=="True")' >/dev/null || die 'VMI 不可热迁移'; fi
        virtctl --kubeconfig "$(required .clusters.primary.kubeconfig)" --context "$(required .clusters.primary.context)" -n "$NS" "$action" vm-demo
        ;;
esac
