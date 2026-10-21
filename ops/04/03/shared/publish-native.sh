#!/usr/bin/env bash
# Nexus raw hosted禁止重新部署；已有同身份制品只在SHA一致时复用。
set -euo pipefail
set +x
umask 077
source "$(dirname "$0")/api.sh"
: "${NEXUS_CURL_CONFIG:?}" "${NEXUS_RELEASE_REPOSITORY:?}" "${SOURCE_DIR:?}"
[[ $NEXUS_RELEASE_REPOSITORY =~ ^[a-z][a-z0-9-]+$ ]] || exit 2
language=$(jq -er .language release/release.json)
ci=$(jq -er .ci release/release.json)
revision=$(jq -er .source_revision release/release.json)
attempt=$(jq -er .build_attempt_id release/release.json)
[[ $language =~ ^(java|rust|c|cpp|csharp|jsts|python)$ && $ci =~ ^(gitlab|jenkins|tekton)$ && $revision =~ ^[a-f0-9]{40}$ ]] || exit 2
[[ $attempt =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$ ]] || exit 2
expected=$(jq -er .native_artifact_sha256 release/release.json)
[[ $(shasum -a 256 "$SOURCE_DIR/dist/native.tar" | awk '{print $1}') == "$expected" ]] || exit 1
url=https://nexus.svc.internal.egon.top/repository/$NEXUS_RELEASE_REPOSITORY/$language/$ci/$revision/$attempt/native.tar
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
rc=0
status=$(curl_safe "$NEXUS_CURL_CONFIG" "$url" --output "$work/existing" --write-out '%{http_code}') || rc=$?
if [[ $rc == 0 && $status == 200 ]]; then
    [[ $(shasum -a 256 "$work/existing" | awk '{print $1}') == "$expected" ]] || { echo '已有同身份原生包内容不同，拒绝覆盖' >&2; exit 1; }
elif [[ $rc == 22 && $status == 404 ]]; then
    curl_safe "$NEXUS_CURL_CONFIG" "$url" --upload-file "$SOURCE_DIR/dist/native.tar" --output "$work/upload-result"
    curl_safe "$NEXUS_CURL_CONFIG" "$url" --output "$work/verified"
    [[ $(shasum -a 256 "$work/verified" | awk '{print $1}') == "$expected" ]] || exit 1
else echo '原生包仓库读取失败；不把认证/连接失败当作不存在' >&2; exit 1
fi
jq --arg url "$url" '. + {native_artifact_url:$url}' release/release.json > release/native-published.json
mv release/native-published.json release/release.json
