#!/usr/bin/env bash
# 为控制台签发独立的 24 小时只读 Token；原子替换，不向终端打印凭据。
set -euo pipefail
umask 077

KUBECTL="$HOME/.cnpl/bin/kubectl"
CONFIG="$HOME/.cnpl-secrets/kubeconfig-lab-primary"
ACCESS="$HOME/.cnpl-secrets/consoles/lab-primary"
CLUSTER_UID=4d3e52d7-e203-4daf-aced-9c3a666fcf5b

actual_uid=$("$KUBECTL" --kubeconfig "$CONFIG" --request-timeout=15s \
  get namespace kube-system -o 'jsonpath={.metadata.uid}')
[ "$actual_uid" = "$CLUSTER_UID" ] || { printf '%s\n' '集群 UID 不符，停止签发。' >&2; exit 1; }

mkdir -p "$ACCESS"
TOKEN_TEMP=$(mktemp "$ACCESS/.headlamp-reader.XXXXXX")
trap 'rm -f "$TOKEN_TEMP"' EXIT
"$KUBECTL" --kubeconfig "$CONFIG" --request-timeout=15s \
  -n cnpl-consoles create token cnpl-console-reader --duration=24h > "$TOKEN_TEMP"
test -s "$TOKEN_TEMP"
mv "$TOKEN_TEMP" "$ACCESS/headlamp-reader.token"
printf '只读 Token 已保存到 %s/headlamp-reader.token（请求有效期 24 小时）。\n' "$ACCESS"
