#!/usr/bin/env bash
# 用户执行的完整批次：真实命令失败即停，预期故障由 Python 单独断言，不屏蔽失败码。
set -Eeuo pipefail
CNPL04_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
cd "$CNPL04_ROOT"
CNPL04_RECORDS=${1:-"$PWD/ops/01-kubernetes/records/2026-10-17-restart/evidence/01.04-$(date +%Y%m%d-%H%M%S)"}
mkdir -p "$CNPL04_RECORDS"
CNPL04_RECORDS=$(cd "$CNPL04_RECORDS" && pwd)
CNPL04_PY="$HOME/.venvs/cnpl-ansible/bin/python"
CNPL04_LAB="$PWD/ops/01-kubernetes/core-resources/pods"
if test -f "$CNPL04_RECORDS/state.json"; then
  printf '证据目录已有运行状态；先 cleanup 或使用新目录。\n' >&2
  exit 1
fi
trap 'printf "批次停止，证据保留：%s\n恢复命令见 core-resources/pods/README.md。\n" "$CNPL04_RECORDS" >&2' ERR
step() {
  local label=$1
  shift
  printf '\n== %s\n' "$label"
  "$@" 2>&1 | tee "$CNPL04_RECORDS/$label.txt"
}
p04() { "$HOME/.cnpl/bin/kubectl" --kubeconfig "$HOME/.cnpl-secrets/kubeconfig-lab-primary" "$@"; }
step 00-target-check "$CNPL04_PY" "$CNPL04_LAB/lab.py" check --records "$CNPL04_RECORDS"
step 01-dns-apply p04 apply -f ops/01-kubernetes/bootstrap/acceptance/network-smoke.yaml
step 02-dns-ready p04 -n cnpl-phase01-acceptance rollout status daemonset/network-smoke --timeout=5m
step 03-dns-recheck "$CNPL04_PY" ops/01-kubernetes/bootstrap/acceptance/check-network.py --short-name
step 04-dns-cleanup p04 delete -f ops/01-kubernetes/bootstrap/acceptance/network-smoke.yaml --ignore-not-found=true --wait=true --timeout=180s
step 05-render "$CNPL04_PY" "$CNPL04_LAB/lab.py" render --records "$CNPL04_RECORDS/manifests"
step 06-check "$CNPL04_PY" "$CNPL04_LAB/lab.py" check --records "$CNPL04_RECORDS"
step 07-pressure-check "$CNPL04_PY" "$CNPL04_LAB/pressure.py" check --records "$CNPL04_RECORDS"
step 08-prepare "$CNPL04_PY" "$CNPL04_LAB/lab.py" prepare --records "$CNPL04_RECORDS"
step 09-states "$CNPL04_PY" "$CNPL04_LAB/lab.py" states --records "$CNPL04_RECORDS"
step 10-sidecars "$CNPL04_PY" "$CNPL04_LAB/lab.py" sidecars --records "$CNPL04_RECORDS"
step 11-debug "$CNPL04_PY" "$CNPL04_LAB/lab.py" debug --records "$CNPL04_RECORDS"
step 12-memory "$CNPL04_PY" "$CNPL04_LAB/lab.py" memory --records "$CNPL04_RECORDS"
step 13-pressure "$CNPL04_PY" "$CNPL04_LAB/pressure.py" run --records "$CNPL04_RECORDS"
step 14-termination "$CNPL04_PY" "$CNPL04_LAB/lab.py" termination --records "$CNPL04_RECORDS"
step 15-verify "$CNPL04_PY" "$CNPL04_LAB/lab.py" verify --records "$CNPL04_RECORDS"
step 16-cleanup "$CNPL04_PY" "$CNPL04_LAB/lab.py" cleanup --records "$CNPL04_RECORDS"
printf '\n01.04 证据目录：%s\n' "$CNPL04_RECORDS"
