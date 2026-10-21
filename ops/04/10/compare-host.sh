#!/usr/bin/env bash
# 只在显式批准的worker VM执行；不改containerd配置，不清理镜像。
set -euo pipefail
umask 077
expected=$1 image=$2 mode=$3 temperature=$4 expected_config=$5
[[ $(hostname -f) == "$expected" && $image =~ ^harbor\.k8s\.internal\.egon\.top/.+@sha256:[a-f0-9]{64}$ ]] || exit 2
[[ $mode == direct || $mode == p2p ]] || exit 2
[[ $temperature == cold || $temperature == warm ]] || exit 2
[[ $(sha256sum /etc/containerd/config.toml | awk '{print $1}') == "$expected_config" ]] || { echo 'containerd配置与批准SHA不符' >&2; exit 1; }
work=$(mktemp -d); trap 'rm -rf -- "$work"' EXIT
crictl images -o json > "$work/before.json"
present=$(jq --arg ref "$image" '[.images[]|select((.repoDigests // [])|index($ref))]|length' "$work/before.json")
if [[ $temperature == cold ]]; then [[ $present == 0 ]] || { echo '节点已有镜像，不能当冷拉取；选全新测试Digest' >&2; exit 1; }; else [[ $present -gt 0 ]] || exit 1; fi
started=$(date +%s%N)
crictl pull "$image" > "$work/pull.txt" 2>&1
finished=$(date +%s%N)
crictl inspecti -o json "$image" > "$work/after.json"
jq -e --arg ref "$image" '.status.repoDigests|index($ref)' "$work/after.json" >/dev/null
jq -n --arg node "$expected" --arg image "$image" --arg mode "$mode" --arg temperature "$temperature" --argjson ns "$((finished-started))" '{node:$node,image:$image,mode:$mode,temperature:$temperature,elapsed_nanoseconds:$ns,digest_verified:true,p2p_hit_verified:false}'
