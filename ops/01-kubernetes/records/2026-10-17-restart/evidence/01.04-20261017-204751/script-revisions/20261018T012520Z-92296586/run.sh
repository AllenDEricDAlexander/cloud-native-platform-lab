#!/usr/bin/env bash
# 用户执行的完整批次：真实命令失败即停，预期故障由 Python 单独断言，不屏蔽失败码。
set -Eeuo pipefail
CNPL04_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
cd "$CNPL04_ROOT"
CNPL04_RECORDS=${1:-"$PWD/ops/01-kubernetes/records/2026-10-17-restart/evidence/01.04-$(date +%Y%m%d-%H%M%S)"}
CNPL04_MODE=${2:-}
if test "$#" -gt 2 || { test -n "$CNPL04_MODE" && test "$CNPL04_MODE" != --resume; }; then
  printf '用法：bash run.sh [证据目录] [--resume]\n' >&2
  exit 1
fi
mkdir -p "$CNPL04_RECORDS"
CNPL04_RECORDS=$(cd "$CNPL04_RECORDS" && pwd)
CNPL04_PY="$HOME/.venvs/cnpl-ansible/bin/python"
CNPL04_LAB="$PWD/ops/01-kubernetes/core-resources/pods"
if test -f "$CNPL04_RECORDS/state.json" && test "$CNPL04_MODE" != --resume; then
  printf '证据目录已有运行状态；继续此批请追加 --resume。\n' >&2
  exit 1
fi
if test "$CNPL04_MODE" = --resume && ! test -f "$CNPL04_RECORDS/state.json"; then
  printf '继续执行需要原证据目录中的 state.json。\n' >&2
  exit 1
fi
CNPL04_LOGS="$CNPL04_RECORDS"
if test "$CNPL04_MODE" = --resume; then
  CNPL04_LOGS=$(mktemp -d "$CNPL04_RECORDS/resume-$(date +%Y%m%d-%H%M%S)-XXXXXX")
fi
trap 'printf "批次停止，证据保留：%s\n恢复命令见 core-resources/pods/README.md。\n" "$CNPL04_RECORDS" >&2' ERR
step() {
  local label=$1
  shift
  printf '\n== %s\n' "$label"
  "$@" 2>&1 | tee "$CNPL04_LOGS/$label.txt"
}
checkpoint() {
  local passed=$1 label=$2 status
  shift 2
  if test "$CNPL04_MODE" = --resume; then
    status=$("$CNPL04_PY" -c 'import json,sys; print("yes" if sys.argv[2] in json.load(open(sys.argv[1]))["passed"] else "no")' "$CNPL04_RECORDS/state.json" "$passed")
    if test "$status" = yes; then
      printf '\n== %s 已通过，跳过\n' "$label"
      return
    fi
  fi
  step "$label" "$@"
}
p04() { "$HOME/.cnpl/bin/kubectl" --kubeconfig "$HOME/.cnpl-secrets/kubeconfig-lab-primary" "$@"; }
if test "$CNPL04_MODE" = --resume; then
  step 00-resume-check "$CNPL04_PY" "$CNPL04_LAB/lab.py" resume --records "$CNPL04_RECORDS"
else
  step 00-target-check "$CNPL04_PY" "$CNPL04_LAB/lab.py" check --records "$CNPL04_RECORDS"
  step 01-dns-apply p04 apply -f ops/01-kubernetes/bootstrap/acceptance/network-smoke.yaml
  step 02-dns-ready p04 -n cnpl-phase01-acceptance rollout status daemonset/network-smoke --timeout=5m
  step 03-dns-recheck "$CNPL04_PY" ops/01-kubernetes/bootstrap/acceptance/check-network.py --short-name
  step 04-dns-cleanup p04 delete -f ops/01-kubernetes/bootstrap/acceptance/network-smoke.yaml --ignore-not-found=true --wait=true --timeout=180s
  step 05-render "$CNPL04_PY" "$CNPL04_LAB/lab.py" render --records "$CNPL04_RECORDS/manifests"
  step 06-check "$CNPL04_PY" "$CNPL04_LAB/lab.py" check --records "$CNPL04_RECORDS"
  step 07-pressure-check "$CNPL04_PY" "$CNPL04_LAB/pressure.py" check --records "$CNPL04_RECORDS"
  step 08-prepare "$CNPL04_PY" "$CNPL04_LAB/lab.py" prepare --records "$CNPL04_RECORDS"
fi
checkpoint states 09-states "$CNPL04_PY" "$CNPL04_LAB/lab.py" states --records "$CNPL04_RECORDS"
checkpoint sidecars 10-sidecars "$CNPL04_PY" "$CNPL04_LAB/lab.py" sidecars --records "$CNPL04_RECORDS"
checkpoint debug 11-debug "$CNPL04_PY" "$CNPL04_LAB/lab.py" debug --records "$CNPL04_RECORDS"
checkpoint memory 12-memory "$CNPL04_PY" "$CNPL04_LAB/lab.py" memory --records "$CNPL04_RECORDS"
checkpoint pressure 13-pressure "$CNPL04_PY" "$CNPL04_LAB/pressure.py" run --records "$CNPL04_RECORDS"
checkpoint termination 14-termination "$CNPL04_PY" "$CNPL04_LAB/lab.py" termination --records "$CNPL04_RECORDS"
checkpoint verify 15-verify "$CNPL04_PY" "$CNPL04_LAB/lab.py" verify --records "$CNPL04_RECORDS"
checkpoint cleanup 16-cleanup "$CNPL04_PY" "$CNPL04_LAB/lab.py" cleanup --records "$CNPL04_RECORDS"
printf '\n01.04 证据目录：%s\n' "$CNPL04_RECORDS"
