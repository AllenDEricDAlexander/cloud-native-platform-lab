#!/usr/bin/env bash
# 保留最低监控和所有持久数据，只暂停有明确空闲证据的本批 Deployment。
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:?pause/resume}
start 09 "$action"
cluster_gate
selected=$(required .handoff.selected_log_backend)
[[ $selected == elk || $selected == loki ]] || die '必须明确保留的主日志后端'
if [[ $action == pause ]]; then
    proof=$(required .handoff.idle_proof_file)
    verify_file "$proof" "$(required .handoff.idle_proof_sha256)"
    jq -e '.writers_stopped==true and .queues_flushed==true and .configuration_archived==true' "$proof" >/dev/null || die '先停用本次对照写入、刷空队列并归档配置'
    jq -e '.handoff.pause_targets|length>0' "$INPUTS" >/dev/null || die '未选择暂停目标'
    jq -n '[]' > "$ATTEMPT/snapshot.json"
    while IFS=$'\t' read -r ns name uid expr; do
        [[ $ns == "$(required .namespaces.backends)" || $ns == "$(required .namespaces.logging)" ]] || die '暂停目标超出观测命名空间'
        case "$name" in loki) [[ $selected != loki ]] || die '必须保留主 Loki' ;; logstash) [[ $selected != elk ]] || die '必须保留主 ELK' ;; tempo|pyroscope) ;; *) die '暂停白名单仅 loki/logstash/tempo/pyroscope，最低监控禁止暂停' ;; esac
        query "$expr" "$ATTEMPT/$name-idle.json"
        jq -e 'all(.data.result[]; (.value[1]|tonumber)==0)' "$ATTEMPT/$name-idle.json" >/dev/null || die '队列/写入未归零'
        k -n "$ns" get deployment "$name" -o json > "$ATTEMPT/$name-before.json"
        ownership_gate <(jq '{items:[.]}' "$ATTEMPT/$name-before.json")
        jq -e --arg uid "$uid" '.metadata.uid==$uid and .spec.replicas>0' "$ATTEMPT/$name-before.json" >/dev/null || die '暂停 UID/副本不符'
        jq '{namespace:.metadata.namespace,name:.metadata.name,uid:.metadata.uid,resource_version:.metadata.resourceVersion,replicas:.spec.replicas}' "$ATTEMPT/$name-before.json" > "$ATTEMPT/one.json"
        jq --slurpfile item "$ATTEMPT/one.json" '.+[$item[0]]' "$ATTEMPT/snapshot.json" > "$ATTEMPT/next.json"; mv "$ATTEMPT/next.json" "$ATTEMPT/snapshot.json"
        jq -n --arg uid "$uid" --arg rv "$(jq -r .resource_version "$ATTEMPT/one.json")" '[{op:"test",path:"/metadata/uid",value:$uid},{op:"test",path:"/metadata/resourceVersion",value:$rv},{op:"replace",path:"/spec/replicas",value:0}]' > "$ATTEMPT/patch.json"
        k -n "$ns" patch deployment "$name" --type=json --patch-file "$ATTEMPT/patch.json" > "$ATTEMPT/$name-paused.txt"
    done < <(jq -r '.handoff.pause_targets[]|[.namespace,.name,.uid,.idle_query]|@tsv' "$INPUTS")
    printf '已保留暂停前副本 snapshot.json；若部分失败，也用本次 snapshot 显式 resume，不删除 PVC/bucket。\n'
else
    snapshot=$(required .handoff.paused_snapshot_file)
    verify_file "$snapshot" "$(required .handoff.paused_snapshot_sha256)"
    while IFS= read -r row; do
        ns=$(jq -er .namespace <<< "$row"); name=$(jq -er .name <<< "$row")
        [[ $ns == "$(required .namespaces.backends)" || $ns == "$(required .namespaces.logging)" ]] || die '恢复目标超出观测命名空间'
        case "$name" in loki|logstash|tempo|pyroscope) ;; *) die '恢复目标不在白名单' ;; esac
        k -n "$ns" get deployment "$name" -o json > "$ATTEMPT/$name-current.json"
        ownership_gate <(jq '{items:[.]}' "$ATTEMPT/$name-current.json")
        mkdir "$ATTEMPT/$name"
        printf '%s\n' "$row" > "$ATTEMPT/$name/target.json"
        bash "$P05/lib/recover.sh" "$INPUTS" "$ATTEMPT/$name/target.json" "$ATTEMPT/$name" 0
        k -n "$ns" rollout status "deployment/$name" --timeout=300s > "$ATTEMPT/$name-ready.txt"
    done < <(jq -c '.[]' "$snapshot")
fi
query 'prometheus_build_info' "$ATTEMPT/minimum-prometheus.json"
query 'kube_node_info' "$ATTEMPT/minimum-kubernetes.json"
printf '集群外 Zabbix 请按 01 verify 复查；暂停不等于完成清理/阶段验收。\n'
