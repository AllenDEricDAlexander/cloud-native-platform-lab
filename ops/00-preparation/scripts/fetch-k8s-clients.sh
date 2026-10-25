#!/usr/bin/env bash
# 管理端 Kubernetes 客户端与 Cilium Chart（01.02）：在管理 Mac 上运行，经 Mac 的代理下载。
# 版本与 SHA256 见 versions.lock.yaml（k8s_clients、cilium）；校验不符即停止。可重复运行。
#   ~/.cnpl/bin/{kubectl,helm,cilium}   管理端客户端（darwin/arm64）
#   种子目录/cilium/cilium-<版本>.tgz     Cilium Helm Chart（与 helm.cilium.io 索引中的 digest 一致）
# 使用：export PATH="$HOME/.cnpl/bin:$PATH"（或在剧本中写全路径）
set -euo pipefail

KUBECTL_VERSION=v1.36.5
KUBECTL_SHA256=c5850a4a6b9469b26cce47c1ab456285f58e308283dcdf72b4ddda3db49b0ec0
HELM_VERSION=v4.3.0
HELM_SHA256=d3870437e1e95b67f8edbde964156c84a26503f560821d40c542441658934fba
CILIUM_CLI_VERSION=v0.20.1
CILIUM_CLI_SHA256=3521cb6af8f621d64dac63c7537fd9aa2ff878fb1f7a6f50e69b31bf45c02cb8
CILIUM_CHART_VERSION=1.20.2
CILIUM_CHART_SHA256=b2afd87b7f75f875f92a14559f14f59b7babbb479d968e3fd625a20bf30ec20e

BIN=$HOME/.cnpl/bin
SEED=${SEED_DIR:-$HOME/Downloads/cloud-native-lab-seed-2026-10-14}
DL=$SEED/k8s-clients
mkdir -p "$BIN" "$DL" "$SEED/cilium"

fetch() {  # 文件 URL SHA256
  local f=$1 url=$2 sum=$3
  [ -s "$f" ] || { echo "下载 ${url}"; curl -fL --retry 3 -o "$f.part" "$url"; mv "$f.part" "$f"; }
  echo "${sum}  ${f}" | shasum -a 256 -c -
}

fetch "$DL/kubectl-${KUBECTL_VERSION}" "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/darwin/arm64/kubectl" "$KUBECTL_SHA256"
install -m 0755 "$DL/kubectl-${KUBECTL_VERSION}" "$BIN/kubectl"

fetch "$DL/helm-${HELM_VERSION}-darwin-arm64.tar.gz" "https://get.helm.sh/helm-${HELM_VERSION}-darwin-arm64.tar.gz" "$HELM_SHA256"
tar -xzf "$DL/helm-${HELM_VERSION}-darwin-arm64.tar.gz" -C "$DL" darwin-arm64/helm
install -m 0755 "$DL/darwin-arm64/helm" "$BIN/helm"

fetch "$DL/cilium-darwin-arm64-${CILIUM_CLI_VERSION}.tar.gz" "https://github.com/cilium/cilium-cli/releases/download/${CILIUM_CLI_VERSION}/cilium-darwin-arm64.tar.gz" "$CILIUM_CLI_SHA256"
tar -xzf "$DL/cilium-darwin-arm64-${CILIUM_CLI_VERSION}.tar.gz" -C "$DL" cilium
install -m 0755 "$DL/cilium" "$BIN/cilium"

fetch "$SEED/cilium/cilium-${CILIUM_CHART_VERSION}.tgz" "https://helm.cilium.io/cilium-${CILIUM_CHART_VERSION}.tgz" "$CILIUM_CHART_SHA256"

echo "== 版本"
"$BIN/kubectl" version --client | head -1
"$BIN/helm" version --short
"$BIN/cilium" version --client 2>/dev/null | head -1
echo "Chart：$SEED/cilium/cilium-${CILIUM_CHART_VERSION}.tgz"
