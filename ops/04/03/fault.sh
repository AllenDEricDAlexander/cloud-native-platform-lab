#!/usr/bin/env bash
# 仅删除明确属于本批次的一只 Job/Manager Pod，不修改生产凭据或共享仓库。
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
pod=${1:?指定 ci-gitlab Pod 名}
[[ $pod =~ ^[a-z0-9][a-z0-9.-]+$ ]] || die 'Pod 名无效'
start 03 pod-loss
uid=$(required .fault.approved_uid)
cluster_gate
k -n ci-gitlab get pod "$pod" -o json > "$ATTEMPT/before.json"
jq -e --arg uid "$uid" --arg run "$RUN" '.metadata.uid==$uid and .metadata.labels["cnpl.io/run"]==$run' "$ATTEMPT/before.json" >/dev/null || die 'Pod UID/批次不符'
k -n ci-gitlab delete pod "$pod" --wait=true --timeout=90s
k -n ci-gitlab get pods -o json > "$ATTEMPT/after.json"
