#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P06/validate.sh" 04 ;;
    render) export STAGE=04; exec ruby "$P06/04/render.rb" ;;
    rules) export STAGE=04; exec ruby "$P06/04/rules.rb" "${2:-falco}" ;;
    install|apply|trigger|check|cleanup-plan) ;;
    *) die '用法：04/run.sh validate|render|rules <falco|tetragon>|install <falco|tetragon>|apply|trigger|check|cleanup-plan' ;;
esac
start 04 "$action"
if [[ $action == cleanup-plan ]]; then cleanup_plan; exit; fi
if [[ $action == install ]]; then
    probe=${2:-}; case "$probe" in falco|tetragon) ;; *) die '只允许 falco 或 tetragon' ;; esac
    ruby "$P06/lib/config.rb" material "$probe" >/dev/null
fi
cluster_gate
case "$action" in
    install) install_component "$probe" ;;
    apply) render > "$ATTEMPT/runtime.json"; apply_file "$ATTEMPT/runtime.json" ;;
    trigger)
        check_namespace
        owned Deployment runtime-demo "$NS" >/dev/null
        k -n "$NS" exec deployment/runtime-demo -c app -- sh -c 'id; cat /etc/os-release' > "$ATTEMPT/trigger.txt"
        ;;
    check)
        check_namespace
        k -n "$NS" rollout status deployment/runtime-demo --timeout=180s
        k top pod -n "$NS" > "$ATTEMPT/resources.txt"
        printf '事件应从 05 的受控查询按 namespace/run/pod UID 提取；本动作仅检查样例和资源。\n'
        ;;
esac
