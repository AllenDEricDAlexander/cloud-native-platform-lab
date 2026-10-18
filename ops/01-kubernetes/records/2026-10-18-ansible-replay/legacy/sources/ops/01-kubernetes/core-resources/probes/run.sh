#!/usr/bin/env bash
# 不修改调用者 shell；由用户一次执行完整批次。所有日志独立保存，失败即停。
set -Eeuo pipefail
CNPL05_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
cd "$CNPL05_ROOT"
CNPL05_RECORDS=${1:-"$PWD/ops/01-kubernetes/records/2026-10-17-restart/evidence/01.05-$(date +%Y%m%d-%H%M%S)"}
CNPL05_MODE=${2:-}
if test "$#" -gt 2 || { test -n "$CNPL05_MODE" && test "$CNPL05_MODE" != --resume; }; then
  printf '用法：bash run.sh [证据目录] [--resume]\n' >&2; exit 1
fi
mkdir -p "$CNPL05_RECORDS"
CNPL05_RECORDS=$(cd "$CNPL05_RECORDS" && pwd)
CNPL05_PY="$HOME/.venvs/cnpl-ansible/bin/python"
CNPL05_LAB="$PWD/ops/01-kubernetes/core-resources/probes"
CNPL05_ARTIFACT="$CNPL05_RECORDS/artifact.json"
if test -f "$CNPL05_RECORDS/state.json" && test "$CNPL05_MODE" != --resume; then
  printf '本批已有状态，请追加 --resume 继续。\n' >&2; exit 1
fi
CNPL05_LOGS=$(mktemp -d "$CNPL05_RECORDS/attempt-$(date +%Y%m%d-%H%M%S)-XXXXXX")
export ANSIBLE_CONFIG="$CNPL05_ROOT/ops/00-preparation/ansible/ansible.cfg"
trap 'printf "批次停止，现场与证据保留：%s\n同一命令追加 --resume 可从未通过组重建后继续。\n" "$CNPL05_RECORDS" >&2' ERR
step() {
  local label=$1
  shift
  printf '\n== %s\n' "$label"
  "$@" 2>&1 | tee "$CNPL05_LOGS/$label.txt"
}
checkpoint() {
  local stage=$1 label=$2 status=no
  shift 2
  if test -f "$CNPL05_RECORDS/state.json"; then
    status=$("$CNPL05_PY" -c 'import json,sys; print("yes" if sys.argv[2] in json.load(open(sys.argv[1]))["passed"] else "no")' "$CNPL05_RECORDS/state.json" "$stage")
  fi
  if test "$status" = yes; then printf '\n== %s 已通过，保留原回执并跳过\n' "$label"; return; fi
  step "$label" "$@"
}
# source 快照及校验值只包含公开脚本，不包含 kubeconfig 或 SSH 私钥。
"$CNPL05_PY" - "$CNPL05_LAB" "$CNPL05_LOGS" <<'PY'
import hashlib,json,sys
from pathlib import Path
source,dest=map(Path,sys.argv[1:]); dest=dest/'implementation'; dest.mkdir()
files=list(source.glob('*.py'))+list(source.glob('*.go'))+[source/'go.mod',source/'run.sh',source.parents[1]/'ansible/playbooks/prepare-probe-image.yml',source.parent/'pods/lab.py']
hashes={}
for path in files:
    name=path.name if path!=source.parent/'pods/lab.py' else 'reused-pod04-lab.py'
    data=path.read_bytes(); (dest/name).write_bytes(data); hashes[name]=hashlib.sha256(data).hexdigest()
(dest/'sha256.json').write_text(json.dumps(hashes,indent=2)+'\n')
PY
step 00-build "$CNPL05_PY" "$CNPL05_LAB/build.py" --output "$CNPL05_LOGS/artifact.json"
# 续跑的物料必须与原批一致；不能先覆盖原索引再比较。
if test -f "$CNPL05_ARTIFACT"; then
  cmp "$CNPL05_ARTIFACT" "$CNPL05_LOGS/artifact.json"
else
  cp "$CNPL05_LOGS/artifact.json" "$CNPL05_ARTIFACT"
fi
step 01-preflight "$CNPL05_PY" "$CNPL05_LAB/lab.py" check --records "$CNPL05_RECORDS"
step 02-image-import "$HOME/.venvs/cnpl-ansible/bin/ansible-playbook" \
  ops/01-kubernetes/ansible/playbooks/prepare-probe-image.yml \
  -e "probe_artifact_file=$CNPL05_ARTIFACT"
step 03-server-dry-run "$CNPL05_PY" "$CNPL05_LAB/lab.py" render --artifact "$CNPL05_ARTIFACT" --records "$CNPL05_LOGS/manifests"
step 04-prepare "$CNPL05_PY" "$CNPL05_LAB/lab.py" prepare --artifact "$CNPL05_ARTIFACT" --records "$CNPL05_RECORDS"
checkpoint startup 05-startup "$CNPL05_PY" "$CNPL05_LAB/lab.py" startup --records "$CNPL05_RECORDS"
checkpoint liveness 06-liveness "$CNPL05_PY" "$CNPL05_LAB/lab.py" liveness --records "$CNPL05_RECORDS"
checkpoint readiness 07-readiness "$CNPL05_PY" "$CNPL05_LAB/lab.py" readiness --records "$CNPL05_RECORDS"
checkpoint termination 08-termination "$CNPL05_PY" "$CNPL05_LAB/lab.py" termination --records "$CNPL05_RECORDS"
checkpoint protocols 09-protocols "$CNPL05_PY" "$CNPL05_LAB/lab.py" protocols --records "$CNPL05_RECORDS"
checkpoint verify 10-verify "$CNPL05_PY" "$CNPL05_LAB/lab.py" verify --records "$CNPL05_RECORDS"
checkpoint cleanup 11-cleanup "$CNPL05_PY" "$CNPL05_LAB/lab.py" cleanup --records "$CNPL05_RECORDS"
printf '\n01.05 批次完成，证据目录：%s\n' "$CNPL05_RECORDS"
