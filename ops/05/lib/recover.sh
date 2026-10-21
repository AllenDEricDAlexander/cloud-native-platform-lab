#!/usr/bin/env bash
set -euo pipefail
CNPL05_INPUTS=$1
export CNPL05_INPUTS
source "$(dirname "$0")/common.sh"
snapshot=$2; attempt=$3; delay=$4
[[ $delay == 0 ]] || sleep "$delay"
[[ ! -f $attempt/restored.json ]] || exit 0
if ! mkdir "$attempt/recovery.lock" 2>/dev/null; then
    for _ in {1..30}; do [[ ! -f $attempt/restored.json ]] || exit 0; sleep 1; done
    die "并发恢复未完成，检查 $attempt"
fi
trap 'rmdir "$attempt/recovery.lock"' EXIT
ns=$(jq -er .namespace "$snapshot"); name=$(jq -er .name "$snapshot"); uid=$(jq -er .uid "$snapshot"); replicas=$(jq -er .replicas "$snapshot")
current=$(k -n "$ns" get deployment "$name" -o json)
jq -e --arg uid "$uid" --arg run "$(required .run_id)" '.metadata.uid==$uid and .metadata.labels["cnpl.io/phase"]=="05" and .metadata.labels["cnpl.io/run"]==$run and (.metadata.annotations["argocd.argoproj.io/tracking-id"] // "")=="" and (.metadata.labels["argocd.argoproj.io/instance"] // "")==""' <<< "$current" >/dev/null || die '恢复目标 UID/归属已变化，拒绝改动替代或 GitOps 对象'
if [[ $(jq .spec.replicas <<< "$current") != "$replicas" ]]; then
    jq -n --arg uid "$uid" --arg rv "$(jq -r .metadata.resourceVersion <<< "$current")" --argjson replicas "$replicas" '[{op:"test",path:"/metadata/uid",value:$uid},{op:"test",path:"/metadata/resourceVersion",value:$rv},{op:"test",path:"/spec/replicas",value:0},{op:"replace",path:"/spec/replicas",value:$replicas}]' > "$attempt/recover-patch.json"
    k -n "$ns" patch deployment "$name" --type=json --patch-file "$attempt/recover-patch.json" > "$attempt/recover.txt"
fi
jq -n --arg uid "$uid" --argjson replicas "$replicas" --arg time "$(date -u +%FT%TZ)" '{uid:$uid,restored_replicas:$replicas,at:$time}' > "$attempt/restored.json"
