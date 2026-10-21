#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P06/validate.sh" 16 ;;
    render) export STAGE=16; exec ruby "$P06/16/render.rb" "${2:-backup}" ;;
    inventory-check) exec ruby "$P06/16/inventory-check.rb" ;;
    install|location|backup|check|restore|restore-check|cleanup-plan) ;;
    *) die '用法：16/run.sh validate|render <location|backup|restore>|inventory-check|install|location|backup|check|restore|restore-check|cleanup-plan' ;;
esac
start 16 "$action"
if [[ $action == cleanup-plan ]]; then cleanup_plan; exit; fi
backup_gate
ruby "$P06/16/inventory-check.rb" > "$ATTEMPT/inventory-summary.json"
if [[ $action == install ]]; then ruby "$P06/lib/config.rb" material velero >/dev/null; fi
if [[ $action == restore || $action == restore-check ]]; then
    [[ $(required .recovery.isolated) == true ]] || die '恢复环境必须隔离'
    TARGET=recovery
    [[ $(required .clusters.recovery.uid) != "$(required .clusters.primary.uid)" ]] || die '恢复不能使用源集群'
    evidence_gate recovery evidence
fi
cluster_gate
ns=$(required .backup.velero_namespace)
name=cnpl06-$RUN
jq -n --arg ns "$ns" '{namespaces:[$ns],cluster_resources:[]}' > "$ATTEMPT/scope.json"
case "$action" in
    install) install_component velero ;;
    location|backup)
        k -n "$ns" get backupstoragelocation "$(required .backup.location)" -o json > "$ATTEMPT/location-before.json" 2>/dev/null || [[ $action == location ]]
        if [[ $action == backup ]]; then jq -e '.status.phase=="Available"' "$ATTEMPT/location-before.json" >/dev/null || die '备份目的地不可用'; fi
        render "$action" > "$ATTEMPT/velero.json"
        apply_file "$ATTEMPT/velero.json" "$ATTEMPT/scope.json"
        ;;
    check)
        owned backups.velero.io "$name" "$ns" > "$ATTEMPT/backup.json" || die '备份不属于本批'
        jq -e '.status.phase=="Completed" and (.status.errors // 0)==0 and (.status.validationErrors // []|length)==0' "$ATTEMPT/backup.json" >/dev/null || die '备份未完整完成'
        if [[ $(required .backup.data_movement) == csi ]]; then resource=datauploads; else resource=podvolumebackups; fi
        k -n "$ns" get "$resource" -l "velero.io/backup-name=$name" -o json > "$ATTEMPT/data-movement.json"
        jq -e '(.items|length)>0 and all(.items[];.status.phase=="Completed")' "$ATTEMPT/data-movement.json" >/dev/null || die '没有完整数据搬运证据'
        ;;
    restore)
        destination=cnpl06-16-restored-$RUN
        [[ -z $(k get namespace "$destination" --ignore-not-found -o name) ]] || die '只恢复到全新目标空间，不能覆盖旧数据'
        k -n "$ns" get backup "$name" -o json | jq -e '.status.phase=="Completed"' >/dev/null || die '恢复目标未同步到完整备份'
        k -n "$ns" get backupstoragelocation "$(required .backup.location)" -o json | jq -e '.spec.accessMode=="ReadOnly" and .status.phase=="Available"' >/dev/null || die '恢复端目的地须只读且可用'
        render restore > "$ATTEMPT/restore.json"
        apply_file "$ATTEMPT/restore.json" "$ATTEMPT/scope.json"
        ;;
    restore-check)
        owned restores.velero.io "$name-restore" "$ns" > "$ATTEMPT/restore-status.json" || die '恢复不属于本批'
        jq -e '.status.phase=="Completed" and (.status.errors // 0)==0' "$ATTEMPT/restore-status.json" >/dev/null || die '恢复未完整完成'
        k -n "cnpl06-16-restored-$RUN" get pods,pvc -o json | redact_objects > "$ATTEMPT/restored-resources.json"
        printf '还需源存储隔离、真实文件/对象 SHA 与原生数据库/消息业务回执验证。\n'
        ;;
esac
