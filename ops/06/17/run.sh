#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P06/validate.sh" 17 ;;
    report) exec ruby "$P06/17/report.rb" "${2:?需要真实时间线JSON}" ;;
    plan|check|handoff|cleanup-plan) ;;
    *) die '用法：17/run.sh validate|plan|check|report <file>|handoff|cleanup-plan' ;;
esac
start 17 "$action"
if [[ $action == cleanup-plan ]]; then cleanup_plan; exit; fi
route=$(required .recovery.route)
case "$route" in etcd-restore|fresh-cluster) ;; *) die '每个恢复批次只允许一条路线' ;; esac
[[ $(required .recovery.isolated) == true ]] || die '恢复目标必须隔离'
backup_gate
evidence_gate recovery evidence
jq -n --arg route "$route" --arg run "$RUN" '{route:$route,run:$run,old_state_import_allowed:($route=="etcd-restore"),runtime_accepted:false,phase_complete:false}' > "$ATTEMPT/route.json"
case "$action" in
    plan) cp "$P06/17/dependencies.json" "$ATTEMPT/dependencies.json" ;;
    check)
        TARGET=recovery
        [[ $(cluster_endpoint recovery) != "$(cluster_endpoint primary)" ]] || die '恢复检查必须使用独立 API 端点'
        if [[ $route == fresh-cluster ]]; then
            [[ $(required .clusters.recovery.uid) != "$(required .clusters.primary.uid)" ]] || die '新集群 UID 不能沿用源集群'
        else
            [[ $(required .clusters.recovery.uid) == "$(required .clusters.primary.uid)" ]] || die '原 etcd 状态恢复应保持对象 UID'
            jq -e '.isolated==true and .old_writers_fenced==true and .recovery_route=="etcd-restore"' "$(required .recovery.evidence_file)" >/dev/null || die '旧写入者未隔离'
        fi
        cluster_gate
        k get pods,pvc -A -o json | redact_objects > "$ATTEMPT/recovery-resources.json"
        k get pv -o json > "$ATTEMPT/recovery-volumes.json"
        evidence_gate recovery business
        jq -e --arg route "$route" '.recovery_route==$route' "$(required .recovery.timeline_file)" >/dev/null || die '时间线恢复路线不符'
        ruby -rjson -e 'd=JSON.parse(File.read(ARGV[0]));abort "业务/数据证据未齐" unless %w[databases messages files objects seven_language_services].all?{|k|d.fetch("checks")[k]==true} && d["lost_records"]==0 && d["duplicate_records"]==0' "$(required .recovery.business_file)"
        ruby "$P06/17/report.rb" "$(required .recovery.timeline_file)" > "$ATTEMPT/rto-rpo.json"
        ;;
    handoff)
        ruby "$P06/lib/coverage.rb" > "$ATTEMPT/coverage.txt"
        printf '脚本文件索引通过；五专题/七阶段实际验收、复制实验、冷启动和清理证据须人工逐项签核。\n'
        ;;
esac
