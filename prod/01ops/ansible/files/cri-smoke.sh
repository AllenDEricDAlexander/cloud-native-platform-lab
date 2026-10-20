#!/usr/bin/env bash
# 沿用 00 阶段 host-network 探针方法；只接收已核实的 Harbor 摘要，不使用公网回退。
# 只清理本次记录的 ID，任何生命周期、AVC 或清理失败都返回非零。
set -euo pipefail
export LC_ALL=C

[[ "${CRI_SMOKE_CONFIRM:-}" == yes ]] || { echo '需要 CRI_SMOKE_CONFIRM=yes' >&2; exit 2; }
[[ "${SMOKE_IMAGE:-}" =~ ^harbor\.k8s\.internal\.egon\.top/bootstrap/busybox@sha256:[0-9a-f]{64}$ ]] || {
  echo '必须提供已核实的内网镜像摘要' >&2; exit 2;
}
WORK=$(mktemp -d "${TMPDIR:-/run}/cnpl-cri-smoke.XXXXXX")
SID='' CID='' RESULT=FAIL STAGE=pull
cleanup() {
  original_rc=$?
  if [[ "$original_rc" != 0 ]]; then printf 'CRI 探针失败，阶段=%s；请检查本机 containerd / audit 日志。\n' "$STAGE" >&2; fi
  trap - EXIT
  set +e
  cleanup_ok=yes
  if [[ "$CID" =~ ^[0-9a-f]{64}$ ]]; then crictl rm -f "$CID" >/dev/null 2>&1 || cleanup_ok=no; fi
  if [[ "$SID" =~ ^[0-9a-f]{64}$ ]]; then
    crictl stopp "$SID" >/dev/null 2>&1 || cleanup_ok=no
    crictl rmp "$SID" >/dev/null 2>&1 || cleanup_ok=no
  fi
  rm -rf -- "$WORK"
  if [[ "$original_rc" != 0 || "$cleanup_ok" != yes ]]; then RESULT=FAIL; fi
  printf 'smoke_cleanup=%s\nsmoke_result=%s\n' "$cleanup_ok" "$RESULT"
  [[ "$original_rc" == 0 && "$cleanup_ok" == yes && "$RESULT" == PASS ]] || exit 1
}
trap cleanup EXIT
START_DATE=$(date '+%m/%d/%Y')
START_TIME=$(date '+%H:%M:%S')
crictl pull "$SMOKE_IMAGE" > "$WORK/pull.log" 2>&1
mkdir -p "$WORK/log"
cat > "$WORK/sandbox.json" <<JSON
{
  "metadata": {"name":"cnpl-cri-smoke","namespace":"cnpl-preparation","uid":"$(basename "$WORK")","attempt":0},
  "log_directory":"$WORK/log",
  "linux":{"cgroup_parent":"cnplprep.slice","security_context":{"namespace_options":{"network":2}}}
}
JSON
cat > "$WORK/container.json" <<JSON
{
  "metadata":{"name":"smoke","attempt":0},
  "image":{"image":"$SMOKE_IMAGE"},
  "command":["/bin/sh","-c","echo CNPL_CRI_OK"],
  "log_path":"smoke.log",
  "linux":{}
}
JSON
STAGE=runp
SID=$(crictl runp "$WORK/sandbox.json" 2>"$WORK/error.log")
[[ "$SID" =~ ^[0-9a-f]{64}$ ]] || exit 1
STAGE=create
CID=$(crictl create "$SID" "$WORK/container.json" "$WORK/sandbox.json" 2>"$WORK/error.log")
[[ "$CID" =~ ^[0-9a-f]{64}$ ]] || exit 1
STAGE=start
crictl start "$CID" > /dev/null
for _ in $(seq 1 40); do
  STATE=$(crictl inspect "$CID" | jq -r '.status.state')
  [[ "$STATE" == CONTAINER_EXITED ]] && break
  sleep 0.5
done
EXIT_CODE=$(crictl inspect "$CID" | jq -r '.status.exitCode')
LOG=$(crictl logs "$CID")
STAGE=audit
# 显式使用日志输入，避免 ausearch 消费调用方的标准输入。
set +e
ausearch --input-logs -m AVC,USER_AVC -ts "$START_DATE" "$START_TIME" > "$WORK/avc.log" 2> "$WORK/audit-error.log"
AUDIT_RC=$?
set -e
[[ "$AUDIT_RC" == 0 || "$AUDIT_RC" == 1 ]] || exit 1
if [[ -s "$WORK/audit-error.log" ]] && grep -qvE '^<no matches>$|^$' "$WORK/audit-error.log"; then
  echo 'audit 查询失败，不能把它当成没有 AVC' >&2; exit 1
fi
AVC=$(grep -cE 'type=(AVC|USER_AVC)' "$WORK/avc.log" || true)
printf 'smoke_image=%s\nsmoke_sandbox_id=%s\nsmoke_container_id=%s\n' "$SMOKE_IMAGE" "$SID" "$CID"
printf 'smoke_state=%s\nsmoke_exit_code=%s\nsmoke_log=%s\nsmoke_avc=%s\n' "$STATE" "$EXIT_CODE" "$LOG" "$AVC"
[[ "$STATE" == CONTAINER_EXITED && "$EXIT_CODE" == 0 && "$LOG" == CNPL_CRI_OK && "$AVC" == 0 ]] || exit 1
RESULT=PASS
