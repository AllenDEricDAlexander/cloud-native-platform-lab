#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P06/validate.sh" 12 ;;
    render) export STAGE=12; exec ruby "$P06/12/render.rb" "${2:-plugin}" ;;
    inspect-host|plan|install|apply|dra|check|cleanup-plan) ;;
    *) die '用法：12/run.sh validate|render <plugin|dra>|inspect-host|plan|install <gpu_operator|dra_driver>|apply|dra|check|cleanup-plan' ;;
esac
start 12 "$action"
if [[ $action == cleanup-plan ]]; then cleanup_plan; exit; fi
node=$(required .gpu.node); node_ip "$node" >/dev/null
if [[ $action != inspect-host ]]; then ruby "$P06/12/gate.rb" > "$ATTEMPT/gpu-plan.json"; fi
if [[ $action == plan ]]; then exit; fi
if [[ $action == dra ]]; then evidence_gate gpu dra_evidence; fi
if [[ $action == install ]]; then
    component=${2:-}; case "$component" in gpu_operator|dra_driver) ;; *) die '未知 GPU 组件' ;; esac
    ruby "$P06/lib/config.rb" material "$component" >/dev/null
fi
cluster_gate
case "$action" in
    inspect-host) remote_node "$node" "$P06/12/inspect-host.sh" > "$ATTEMPT/hardware.txt" ;;
    install) install_component "$component" ;;
    apply|dra)
        if [[ $action == apply ]]; then
            k get node "$node" -o json | jq -e '(.status.allocatable["nvidia.com/gpu"] // "0" | tonumber) >= 1' >/dev/null || die '节点无可分配 GPU'
            render > "$ATTEMPT/gpu-job.json"
        else
            k get deviceclass "$(required .gpu.device_class)" -o json > "$ATTEMPT/device-class.json"
            render dra > "$ATTEMPT/gpu-job.json"
        fi
        apply_file "$ATTEMPT/gpu-job.json"
        ;;
    check)
        check_namespace
        k -n "$NS" wait job/gpu-smoke --for=condition=Complete --timeout=180s
        k -n "$NS" logs job/gpu-smoke > "$ATTEMPT/gpu-compute.txt"
        ruby -e 'abort "GPU 未完成计算" unless File.read(ARGV[0]).include?("gpu-compute-ok")' "$ATTEMPT/gpu-compute.txt"
        ;;
esac
