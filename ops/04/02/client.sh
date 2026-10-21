#!/usr/bin/env bash
# 供受控 CI Agent 使用；凭据文件在 Pod 中挂载，不拷贝入构建上下文。
set -euo pipefail
set +x
buildctl_tls() {
    : "${BUILDKIT_ADDR:?}" "${BUILDKIT_CA:?}" "${BUILDKIT_CERT:?}" "${BUILDKIT_KEY:?}"
    [[ $BUILDKIT_ADDR =~ ^tcp://[a-zA-Z0-9.-]+:1234$ ]] || { echo 'BuildKit endpoint 无效' >&2; return 1; }
    buildctl --addr "$BUILDKIT_ADDR" --tlscacert "$BUILDKIT_CA" --tlscert "$BUILDKIT_CERT" --tlskey "$BUILDKIT_KEY" "$@"
}
cache_key() {
    local language=$1 builder=$2 lock=$3 trust=$4
    [[ $trust == trusted || $trust == untrusted ]] || return 1
    [[ $builder =~ @sha256:[a-f0-9]{64}$ && -f $lock ]] || return 1
    printf '%s-%s-linux-amd64-%s-%s\n' "$language" "$trust" "${builder##*@sha256:}" "$(shasum -a 256 "$lock" | awk '{print $1}')"
}
