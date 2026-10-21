#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P06/validate.sh" 03 ;;
    render) export STAGE=03; exec ruby "$P06/03/render.rb" ;;
    encrypt|decrypt) exec bash "$P06/03/crypto.sh" "$action" ;;
    install|apply|check|vault-snapshot|rotation-check|cleanup-plan) ;;
    *) die '用法：03/run.sh validate|render|encrypt|decrypt|install <external_secrets|vault>|apply|check|vault-snapshot|rotation-check|cleanup-plan' ;;
esac
start 03 "$action"
if [[ $action == cleanup-plan ]]; then cleanup_plan; exit; fi
if [[ $action == rotation-check ]]; then
    evidence_gate secrets rotation_evidence
    ruby "$P06/03/rotation-check.rb" "$(required .secrets.rotation_evidence_file)" > "$ATTEMPT/rotation-summary.json"
    exit
fi
if [[ $action == vault-snapshot ]]; then
    backup_gate
    private_file "$(required .secrets.vault_curl_config)"
    destination=$(required .secrets.vault_snapshot_file)
    private_temp
    server=$(required .secrets.vault_server)
    [[ $server =~ ^https://[a-z0-9.-]+\.internal\.egon\.top(:[0-9]+)?$ ]] || die 'Vault 必须为内网 HTTPS'
    curl --config "$(required .secrets.vault_curl_config)" --fail --silent --show-error --proto '=https' --max-time 120 --url "$server/v1/sys/storage/raft/snapshot" --output "$PRIVATE_TEMP/snapshot"
    ruby "$P06/03/private-write.rb" "$PRIVATE_TEMP/snapshot" "$destination"
    jq -n --arg sha "$(sha "$destination")" '{snapshot_sha256:$sha,restore_tested:false}' > "$ATTEMPT/vault-snapshot.json"
    exit
fi
if [[ $action == install ]]; then
    component=${2:-external_secrets}
    case "$component" in external_secrets|vault) ;; *) die '仅允许 external_secrets/vault' ;; esac
    ruby "$P06/lib/config.rb" material "$component" >/dev/null
fi
cluster_gate
case "$action" in
    install) install_component "$component" ;;
    apply) render > "$ATTEMPT/secret-references.json"; apply_file "$ATTEMPT/secret-references.json" ;;
    check)
        check_namespace
        k -n "$NS" wait secretstore/vault-lab --for=condition=Ready --timeout=120s
        k -n "$NS" wait externalsecret/lab-reference --for=condition=Ready --timeout=180s
        # 仅保存 Secret 元数据，不读取/输出正文。
        k -n "$NS" get secret lab-synced -o jsonpath='{.metadata.uid}{"\n"}{.metadata.resourceVersion}{"\n"}' > "$ATTEMPT/synced-metadata.txt"
        ;;
esac
