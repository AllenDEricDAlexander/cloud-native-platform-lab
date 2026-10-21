#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P06/validate.sh" 01 ;;
    render) export STAGE=01; exec ruby "$P06/01/render.rb" ;;
    install|apply|check|realm|cleanup-plan) ;;
    *) die '用法：01/run.sh validate|render|install|realm|apply|check|cleanup-plan' ;;
esac
start 01 "$action"
if [[ $action == cleanup-plan ]]; then cleanup_plan; exit; fi
if [[ $action == realm ]]; then
    verify_file "$(required .prerequisites.file)" "$(required .prerequisites.sha256)"
    verify_file "$(required .identity.realm_file)" "$(required .identity.realm_sha256)"
    private_file "$(required .identity.kcadm_config)"
    ruby "$P06/01/realm-check.rb"
    # 认证由预先建立的私有 kcadm 会话提供；不在 argv 传口令。
    kcadm.sh create realms --config "$(required .identity.kcadm_config)" -f "$(required .identity.realm_file)" >/dev/null
    exit
fi
if [[ $action == install ]]; then ruby "$P06/lib/config.rb" material keycloak >/dev/null; fi
cluster_gate
case "$action" in
    install) install_component keycloak ;;
    apply) render > "$ATTEMPT/identity.json"; apply_file "$ATTEMPT/identity.json" ;;
    check)
        check_namespace
        k -n "$NS" rollout status deployment/identity-demo --timeout=180s
        for who in user emergency; do
            file=$(required ".identity.${who}_kubeconfig"); context=$(required ".identity.${who}_context")
            private_file "$file"
            server=$(kubectl --kubeconfig "$file" --context "$context" config view --minify -o jsonpath='{.clusters[0].cluster.server}')
            [[ $server == "$(cluster_endpoint primary)" ]] || die '身份 kubeconfig 指向其他 API 入口'
            kubectl --kubeconfig "$file" --context "$context" --request-timeout=30s auth whoami -o json > "$ATTEMPT/$who-whoami.json"
        done
        [[ $(kubectl --kubeconfig "$(required .identity.emergency_kubeconfig)" --context "$(required .identity.emergency_context)" --request-timeout=30s auth can-i patch namespaces) == yes ]] || die '独立恢复身份无管理权限'
        user_k() { kubectl --kubeconfig "$(required .identity.user_kubeconfig)" --context "$(required .identity.user_context)" --request-timeout=30s "$@"; }
        [[ $(user_k auth can-i get pods -n "$NS") == yes ]] || die '真实用户未获得允许权限'
        answer=$(user_k auth can-i delete secrets -n "$NS" || true)
        [[ $answer == no ]] || die '真实用户删除 Secret 未被拒绝'
        answer=$(user_k auth can-i get secrets -n kube-system || true)
        [[ $answer == no ]] || die '真实用户跨团队读取 Secret 未被拒绝'
        ;;
esac
