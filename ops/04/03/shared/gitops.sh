#!/usr/bin/env bash
# 只推送审核分支并创建 MR；不写业务 K8s 对象，不自动合并。
set -euo pipefail
set +x
source "$(dirname "$0")/api.sh"
: "${GITOPS_URL:?}" "${GITOPS_PROJECT_ID:?}" "${GITOPS_CURL_CONFIG:?}" "${GITOPS_TOKEN_FILE:?}" "${APP_NAME:?}" "${ENVIRONMENT:?}"
export GIT_ASKPASS=$(cd "$(dirname "$0")" && pwd)/askpass.sh LC_MESSAGES=C
ruby -e 's=File.stat(ARGV[0]);abort "GitOps Token文件权限不符" unless s.uid==Process.uid && [0400,0600].include?(s.mode & 0777)' "$GITOPS_TOKEN_FILE"
[[ $GITOPS_URL =~ ^https://gitlab\.svc\.internal\.egon\.top/[a-zA-Z0-9_./-]+\.git$ && $GITOPS_PROJECT_ID =~ ^[0-9]+$ && $APP_NAME =~ ^[a-z][a-z0-9-]{2,30}$ && $ENVIRONMENT =~ ^(dev|staging|prod-like)$ ]] || exit 2
receipt=${1:-release/release.json}
jq -e '.source_revision|test("^[a-f0-9]{40}$")' "$receipt" >/dev/null
jq -e '.image|test("^harbor\\.k8s\\.internal\\.egon\\.top/.+@sha256:[a-f0-9]{64}$")' "$receipt" >/dev/null
jq -e '.sbom_sha256 != null and .provenance_sha256 != null and .signature_verified == true' "$receipt" >/dev/null
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
export GIT_TERMINAL_PROMPT=0
git clone --quiet --depth=1 "$GITOPS_URL" "$work/repo"
branch=release/$APP_NAME-$ENVIRONMENT-$(jq -r '.ci+"-"+.source_revision' "$receipt")
git -C "$work/repo" checkout -q -b "$branch"
directory=$work/repo/environments/$ENVIRONMENT/$APP_NAME
[[ -f $directory/kustomization.yaml && ! -L $directory ]] || { echo 'GitOps 环境路径未引导' >&2; exit 1; }
cp "$receipt" "$directory/release.json"
ruby -ryaml -rjson -e 'p=ARGV[0];r=JSON.parse(File.read(ARGV[1]));image,digest=r.fetch("image").split("@");d=YAML.load_file(p);d["images"]=[{"name"=>"application","newName"=>image,"digest"=>digest}];File.write(p,YAML.dump(d))' "$directory/kustomization.yaml" "$receipt"
git -C "$work/repo" add -- "environments/$ENVIRONMENT/$APP_NAME"
if git -C "$work/repo" diff --cached --quiet; then echo '目标环境已记录相同制品'; exit 0; fi
git -C "$work/repo" -c user.name=cnpl-release -c user.email=cnpl-release@internal.egon.top commit -q -m "release $APP_NAME $ENVIRONMENT $(jq -r .image "$receipt")"
# 分支不强推。重跑如发现已有分支，先比较内容，不能用新任务覆盖待审批变更。
if git -C "$work/repo" ls-remote --exit-code --heads origin "$branch" > "$work/remote"; then
    git -C "$work/repo" fetch --quiet origin "$branch"
    git -C "$work/repo" diff --exit-code FETCH_HEAD HEAD -- "environments/$ENVIRONMENT/$APP_NAME" >/dev/null
else
    git -C "$work/repo" push --quiet origin "HEAD:refs/heads/$branch"
fi
api=https://gitlab.svc.internal.egon.top/api/v4/projects/$GITOPS_PROJECT_ID/merge_requests
curl_safe "$GITOPS_CURL_CONFIG" "$api" --get --data-urlencode "source_branch=$branch" --data-urlencode state=opened > "$work/mrs.json"
if [[ $(jq length "$work/mrs.json") == 0 ]]; then
    curl_safe "$GITOPS_CURL_CONFIG" "$api" --request POST --data-urlencode "source_branch=$branch" --data-urlencode target_branch=main --data-urlencode "title=Release $APP_NAME to $ENVIRONMENT" > "$work/mr.json"
    jq '{iid,web_url,state}' "$work/mr.json" > release/gitops-mr.json
else jq '.[0]|{iid,web_url,state}' "$work/mrs.json" > release/gitops-mr.json; fi
