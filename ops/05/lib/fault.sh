#!/usr/bin/env bash
# 一次一个本批观测工作负载；独立管理端 watchdog + EXIT 恢复。
set -euo pipefail
source "$(dirname "$0")/common.sh"
start "${1:?stage}" fault
cluster_gate
ns=$(required .fault.namespace); name=$(required .fault.deployment); uid=$(required .fault.uid)
duration=$(required .fault.duration_seconds)
[[ $duration =~ ^[0-9]+$ && $duration -ge 5 && $duration -le 120 ]] || die '故障窗口必须为 5–120 秒'
get '.namespaces | to_entries[].value' | jq -R -s --arg ns "$ns" 'split("\n") | index($ns) != null' | jq -e . >/dev/null || die '故障仅限本阶段命名空间'
k -n "$ns" get deployment "$name" -o json > "$ATTEMPT/before.json"
jq -e --arg run "$RUN" --arg uid "$uid" '.metadata.uid==$uid and .metadata.labels["cnpl.io/phase"]=="05" and .metadata.labels["cnpl.io/run"]==$run and (.metadata.annotations["argocd.argoproj.io/tracking-id"] // "")=="" and (.metadata.labels["argocd.argoproj.io/instance"] // "")=="" and .spec.replicas>0' "$ATTEMPT/before.json" >/dev/null || die '故障目标 UID/归属/副本不符'
snapshot=$ATTEMPT/target.json
jq '{namespace:.metadata.namespace,name:.metadata.name,uid:.metadata.uid,resource_version:.metadata.resourceVersion,replicas:.spec.replicas}' "$ATTEMPT/before.json" > "$snapshot"
recover() { bash "$P05/lib/recover.sh" "$INPUTS" "$snapshot" "$ATTEMPT" 0; }
RECOVERY_FUNCTION=recover
# 为注入请求预留 35 秒（kubectl request-timeout=30s），避免请求尚未完成时先标记恢复。
nohup bash "$P05/lib/recover.sh" "$INPUTS" "$snapshot" "$ATTEMPT" "$((duration + 35))" > "$ATTEMPT/watchdog.txt" 2>&1 < /dev/null &
printf '%s\n' "$!" > "$ATTEMPT/watchdog.pid"
jq -n --arg uid "$uid" --arg rv "$(jq -r .resource_version "$snapshot")" --argjson replicas "$(jq .replicas "$snapshot")" '[{op:"test",path:"/metadata/uid",value:$uid},{op:"test",path:"/metadata/resourceVersion",value:$rv},{op:"test",path:"/spec/replicas",value:$replicas},{op:"replace",path:"/spec/replicas",value:0}]' > "$ATTEMPT/fault-patch.json"
k -n "$ns" patch deployment "$name" --type=json --patch-file "$ATTEMPT/fault-patch.json" > "$ATTEMPT/scale.txt"
sleep "$duration"
recover
k -n "$ns" rollout status "deployment/$name" --timeout=180s > "$ATTEMPT/recovered.txt"
RECOVERY_FUNCTION=''
