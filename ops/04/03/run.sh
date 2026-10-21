#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
source "$P04/03/shared/api.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P04/validate.sh" 03 ;;
    deploy|check|trigger|lint) ;;
    *) die '用法：03/run.sh validate|deploy|check|lint|trigger' ;;
esac
start 03 "$action"
case "$action" in
    deploy) material gitlab_runner >/dev/null; worker_gate; cluster_gate; chart gitlab_runner runner ci-gitlab ;;
    check) cluster_gate; k -n ci-gitlab get pods -o json > "$ATTEMPT/runner-pods.json" ;;
    lint|trigger)
        config=$(required .gitlab.curl_config); private_file "$config"
        id=$(required .gitlab.project_id); [[ $id =~ ^[0-9]+$ ]] || die 'project_id 无效'
        if [[ $action == lint ]]; then
            jq -n --rawfile content "$P04/03/gitlab-ci.yml" '{content:$content,include_merged_yaml:false}' > "$ATTEMPT/lint-request.json"
            curl_safe "$config" "https://gitlab.svc.internal.egon.top/api/v4/projects/$id/ci/lint" --request POST --header 'Content-Type: application/json' --data-binary "@$ATTEMPT/lint-request.json" > "$ATTEMPT/lint.json"
            jq -e '.valid==true' "$ATTEMPT/lint.json" >/dev/null
        else
            revision=$(required .release.source_revision); [[ $revision =~ ^[a-f0-9]{40}$ ]] || die '需固定源码 SHA'
            curl_safe "$config" "https://gitlab.svc.internal.egon.top/api/v4/projects/$id/pipeline" --request POST --data-urlencode "ref=$(required .gitlab.ref)" > "$ATTEMPT/pipeline.json"
            jq -e --arg rev "$revision" '.sha==$rev' "$ATTEMPT/pipeline.json" >/dev/null || die '触发流水线的提交与批准 SHA 不符；停止并核对该任务'
            printf '已记录 pipeline ID；请完成受保护发布审批、合并 GitOps MR 后执行 observe，触发不代表成功。\n'
        fi ;;
esac
