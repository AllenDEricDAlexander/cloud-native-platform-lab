#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
[[ $action != validate ]] || exec bash "$P04/validate.sh" 10
[[ $action == preview || $action == delete ]] || die '用法 cleanup.sh preview|delete <deployment|service|configmap|role|rolebinding> <name> <tekton-lab|flux-lab> <uid>'
start 10 cleanup-preview
cluster_gate
if [[ $action == delete ]]; then
    kind=${2:?} name=${3:?} ns=${4:?} uid=${5:?}
    [[ $kind =~ ^(deployment|service|configmap|role|rolebinding)$ && $ns =~ ^(tekton-lab|flux-lab)$ && $name =~ ^[a-z0-9][a-z0-9.-]+$ && $uid =~ ^[a-f0-9-]{36}$ ]] || die '清理范围/UID无效'
    k -n "$ns" get "$kind" "$name" -o json > "$ATTEMPT/object.json"
    jq -e --arg run "$RUN" --arg uid "$uid" '.metadata.uid==$uid and .metadata.labels["cnpl.io/phase"]=="04" and .metadata.labels["cnpl.io/run"]==$run' "$ATTEMPT/object.json" >/dev/null || die '拒绝删除非本批对象'
    case "$kind" in
        deployment) prefix=/apis/apps/v1; plural=deployments ;;
        role) prefix=/apis/rbac.authorization.k8s.io/v1; plural=roles ;;
        rolebinding) prefix=/apis/rbac.authorization.k8s.io/v1; plural=rolebindings ;;
        service) prefix=/api/v1; plural=services ;;
        configmap) prefix=/api/v1; plural=configmaps ;;
    esac
    jq -n --arg uid "$uid" '{apiVersion:"v1",kind:"DeleteOptions",preconditions:{uid:$uid},propagationPolicy:"Foreground"}' > "$ATTEMPT/delete-options.json"
    k delete --raw "$prefix/namespaces/$ns/$plural/$name" -f "$ATTEMPT/delete-options.json" > "$ATTEMPT/deletion.json"
    exit
fi
for ns in tekton-lab flux-lab; do
    k -n "$ns" get deployment,service,configmap,role,rolebinding,pvc -l "cnpl.io/phase=04,cnpl.io/run=$RUN" -o json > "$ATTEMPT/$ns.json"
    jq -r '.items[]|[.kind,.metadata.name,.metadata.uid]|@tsv' "$ATTEMPT/$ns.json"
done
