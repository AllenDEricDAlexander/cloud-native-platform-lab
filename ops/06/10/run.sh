#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P06/validate.sh" 10 ;;
    render) export STAGE=10; exec ruby "$P06/10/render.rb" "${2:-network}" ;;
    apply|gitops|check|mesh-check|failover-plan|cleanup-plan) ;;
    *) die '用法：10/run.sh validate|render <network|gitops|mcs>|apply|gitops|check|mesh-check|failover-plan|cleanup-plan' ;;
esac
start 10 "$action"
if [[ $action == cleanup-plan ]]; then cleanup_plan; exit; fi
TARGET=$(required .multicluster.target)
case "$TARGET" in primary|secondary) ;; *) die '必须明确选择 primary 或 secondary' ;; esac
[[ $(required .clusters.primary.uid) != "$(required .clusters.secondary.uid)" ]] || die '两目标不能是同一集群'
evidence_gate multicluster mesh_evidence
cluster_gate
case "$action" in
    apply) render > "$ATTEMPT/global-service.json"; apply_file "$ATTEMPT/global-service.json" ;;
    gitops)
        render gitops > "$ATTEMPT/applicationset.json"
        jq -n --arg ns "$(required .multicluster.argocd_namespace)" '{namespaces:[$ns],cluster_resources:[]}' > "$ATTEMPT/scope.json"
        apply_file "$ATTEMPT/applicationset.json" "$ATTEMPT/scope.json"
        ;;
    check|mesh-check)
        for TARGET in primary secondary; do
            cluster_gate
            check_namespace
            k -n "$NS" rollout status deployment/global-echo --timeout=180s
            k -n "$NS" get services,endpointslices -o json > "$ATTEMPT/$TARGET-services.json"
            if [[ $action == mesh-check ]]; then cilium --kubeconfig "$(required ".clusters.$TARGET.kubeconfig")" --context "$(required ".clusters.$TARGET.context")" clustermesh status > "$ATTEMPT/$TARGET-mesh.txt"; fi
        done
        ;;
    failover-plan)
        state=$(owned Deployment global-echo "$NS")
        jq '[{op:"test",path:"/metadata/uid",value:.metadata.uid},{op:"test",path:"/metadata/resourceVersion",value:.metadata.resourceVersion},{op:"replace",path:"/spec/replicas",value:0}]' <<< "$state" > "$ATTEMPT/down.json"
        jq '[{op:"test",path:"/metadata/uid",value:.metadata.uid},{op:"test",path:"/spec/replicas",value:0},{op:"replace",path:"/spec/replicas",value:.spec.replicas}]' <<< "$state" > "$ATTEMPT/restore.json"
        printf '已准备 down/restore 补丁；尚未执行故障。先准备独立定时恢复、持续请求与停止阈值，再按 README 执行。\n'
        ;;
esac
