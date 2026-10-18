#!/usr/bin/env bash
# 用户一次启动全部 01.06 场景；失败保留现场，续跑只重建未通过组。
set -Eeuo pipefail
CNPL06_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
cd "$CNPL06_ROOT"
CNPL06_RECORDS=${1:-"$PWD/ops/01-kubernetes/records/2026-10-17-restart/evidence/01.06-$(date +%Y%m%d-%H%M%S)"}
CNPL06_MODE=${2:-}
if test "$#" -gt 2 || { test -n "$CNPL06_MODE" && test "$CNPL06_MODE" != --resume; }; then
  printf '用法：bash run.sh [证据目录] [--resume]\n' >&2; exit 1
fi
mkdir -p "$CNPL06_RECORDS"
CNPL06_RECORDS=$(cd "$CNPL06_RECORDS" && pwd)
CNPL06_PY="$HOME/.venvs/cnpl-ansible/bin/python"
CNPL06_LAB="$CNPL06_ROOT/ops/01-kubernetes/core-resources/controllers"
CNPL06_BUNDLE="$CNPL06_RECORDS/bundle.json"
if test -f "$CNPL06_RECORDS/state.json" && test "$CNPL06_MODE" != --resume; then
  printf '已有本批状态，请追加 --resume。\n' >&2; exit 1
fi
CNPL06_LOGS=$(mktemp -d "$CNPL06_RECORDS/attempt-$(date +%Y%m%d-%H%M%S)-XXXXXX")
export ANSIBLE_CONFIG="$CNPL06_ROOT/ops/00-preparation/ansible/ansible.cfg"
trap 'printf "批次停止，现场和证据保留：%s\n用原证据目录追加 --resume 可从未通过组继续。\n" "$CNPL06_RECORDS" >&2' ERR
step() {
  local label=$1
  shift
  printf '\n== %s\n' "$label"
  "$@" 2>&1 | tee "$CNPL06_LOGS/$label.txt"
}
checkpoint() {
  local stage=$1 label=$2 status=no
  shift 2
  if test -f "$CNPL06_RECORDS/state.json"; then
    status=$("$CNPL06_PY" -c 'import json,sys; print("yes" if sys.argv[2] in json.load(open(sys.argv[1]))["passed"] else "no")' "$CNPL06_RECORDS/state.json" "$stage")
  fi
  if test "$status" = yes; then printf '\n== %s 已通过，保留原回执并跳过\n' "$label"; return; fi
  step "$label" "$@"
}
"$CNPL06_PY" - "$CNPL06_LAB" "$CNPL06_LOGS" <<'PY'
import hashlib,json,sys
from pathlib import Path
source,log=map(Path,sys.argv[1:]);dest=log/'implementation';dest.mkdir();files={}
for path in list(source.glob('*.py'))+list(source.glob('*.go'))+[source/'go.mod',source/'run.sh',source.parents[1]/'ansible/playbooks/prepare-controller-images.yml',source.parents[1]/'ansible/tasks/import-controller-image.yml']:
    files[path.name]=path
for name,path in [('reused-05-lab.py',source.parent/'probes/lab.py'),('reused-05-build.py',source.parent/'probes/build.py'),('reused-04-lab.py',source.parent/'pods/lab.py')]:files[name]=path
hashes={}
for name,path in files.items():
    data=path.read_bytes();(dest/name).write_bytes(data);hashes[name]=hashlib.sha256(data).hexdigest()
(dest/'sha256.json').write_text(json.dumps(hashes,indent=2)+'\n')
PY
step 00-build "$CNPL06_PY" "$CNPL06_LAB/build.py" --output "$CNPL06_LOGS/bundle.json"
if test -f "$CNPL06_BUNDLE"; then cmp "$CNPL06_BUNDLE" "$CNPL06_LOGS/bundle.json"; else cp "$CNPL06_LOGS/bundle.json" "$CNPL06_BUNDLE"; fi
step 01-preflight "$CNPL06_PY" "$CNPL06_LAB/lab.py" check --records "$CNPL06_RECORDS"
step 02-image-import "$HOME/.venvs/cnpl-ansible/bin/ansible-playbook" ops/01-kubernetes/ansible/playbooks/prepare-controller-images.yml -e "controller_bundle_file=$CNPL06_BUNDLE"
step 03-server-dry-run "$CNPL06_PY" "$CNPL06_LAB/lab.py" render --bundle "$CNPL06_BUNDLE" --records "$CNPL06_LOGS/manifests"
step 04-prepare "$CNPL06_PY" "$CNPL06_LAB/lab.py" prepare --bundle "$CNPL06_BUNDLE" --records "$CNPL06_RECORDS"
checkpoint replicas 05-replicas "$CNPL06_PY" "$CNPL06_LAB/lab.py" replicas --records "$CNPL06_RECORDS"
checkpoint history 06-history "$CNPL06_PY" "$CNPL06_LAB/lab.py" history --records "$CNPL06_RECORDS"
checkpoint scale 07-scale "$CNPL06_PY" "$CNPL06_LAB/lab.py" scale --records "$CNPL06_RECORDS"
checkpoint strategies 08-strategies "$CNPL06_PY" "$CNPL06_LAB/lab.py" strategies --records "$CNPL06_RECORDS"
checkpoint rollbacks 09-rollbacks "$CNPL06_PY" "$CNPL06_LAB/lab.py" rollbacks --records "$CNPL06_RECORDS"
checkpoint split 10-split "$CNPL06_PY" "$CNPL06_LAB/lab.py" split --records "$CNPL06_RECORDS"
checkpoint verify 11-verify "$CNPL06_PY" "$CNPL06_LAB/lab.py" verify --records "$CNPL06_RECORDS"
checkpoint cleanup 12-cleanup "$CNPL06_PY" "$CNPL06_LAB/lab.py" cleanup --records "$CNPL06_RECORDS"
printf '\n01.06 批次完成，证据目录：%s\n' "$CNPL06_RECORDS"
