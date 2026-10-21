#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/cli.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P04/validate.sh" 04 ;;
    render) exec ruby "$P04/04/render.rb" ;;
    deploy|check|trigger) ;;
    *) die '用法：04/run.sh validate|render|deploy|check|trigger' ;;
esac
start 04 "$action"
case "$action" in
    deploy) material jenkins >/dev/null; material jenkins_plugins >/dev/null; worker_gate; cluster_gate; chart jenkins jenkins ci-jenkins ;;
    check) cluster_gate; k -n ci-jenkins rollout status deployment/jenkins --timeout=180s; k -n ci-jenkins get pods,pvc -o json > "$ATTEMPT/jenkins.json" ;;
    trigger)
        revision=$(required .release.source_revision); [[ $revision =~ ^[a-f0-9]{40}$ ]] || die '需完整源码 SHA'
        jenkins_cli build "$(required .jenkins.job)" -s -p "SOURCE_REVISION=$revision" > "$ATTEMPT/build.txt" ;;
esac
