#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P04/validate.sh" 07 ;;
    render) exec ruby "$P04/07/render.rb" ;;
    export) shift; exec ruby "$P04/07/render.rb" export "$@" ;;
    deploy|bootstrap|check) ;;
    *) die '用法：07/run.sh validate|render|export <new-dir>|deploy|bootstrap|check' ;;
esac
start 07 "$action"
[[ $action != deploy ]] || material argocd >/dev/null
cluster_gate
case "$action" in
    deploy) chart argocd argocd argocd ;;
    bootstrap)
        k wait --for=condition=Established --timeout=120s crd/applications.argoproj.io crd/appprojects.argoproj.io crd/applicationsets.argoproj.io
        render > "$ATTEMPT/gitops-bootstrap.json"; apply "$ATTEMPT/gitops-bootstrap.json" ;;
    check)
        k -n argocd get applications -o json > "$ATTEMPT/applications.json"
        jq -e '(.items|length)>0 and all(.items[]; .status.sync.status=="Synced" and .status.health.status=="Healthy")' "$ATTEMPT/applications.json" >/dev/null
        for env in dev staging prod-like; do k -n "apps-$env" get deployment,hpa -o json > "$ATTEMPT/$env-replicas.json"; done ;;
esac
