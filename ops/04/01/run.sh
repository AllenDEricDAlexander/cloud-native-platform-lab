#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P04/validate.sh" 01 ;;
    render) exec ruby "$P04/01/render.rb" ;;
    render-access) exec ruby "$P04/01/access.rb" ;;
    apply|access|check) ;;
    *) die '用法：01/run.sh validate|render|apply|check' ;;
esac
start 01 "$action"
cluster_gate
if [[ $action == apply ]]; then render > "$ATTEMPT/environments.json"; apply "$ATTEMPT/environments.json"; fi
if [[ $action == access ]]; then ruby "$P04/01/access.rb" > "$ATTEMPT/access.json"; apply "$ATTEMPT/access.json"; fi
for ns in apps-dev apps-staging apps-prod-like ci-build ci-gitlab ci-jenkins; do
    k -n "$ns" get resourcequota,limitrange,networkpolicy,serviceaccount -o json > "$ATTEMPT/$ns.json"
done
