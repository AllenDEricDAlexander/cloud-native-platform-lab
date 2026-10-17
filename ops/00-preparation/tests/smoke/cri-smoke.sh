#!/usr/bin/env bash
# Phase 00 host-network CRI 自测：在目标节点以 root 运行，逐项输出 smoke_*=value。
#
# 会创建并删除一个 sandbox 和一个容器（不是只读），因此必须显式确认：CRI_SMOKE_CONFIRM=yes。
# 默认只使用节点上已有的 pause 与 smoke 镜像（10.1 种子导入路线）；SMOKE_PULL=yes 时先经 CRI 拉取
# smoke 镜像（10.2 内网仓库路线，验证 registry 配置与 CA 信任）。sandbox 使用主机网络，不需要 CNI。
# 每次运行使用唯一的 uid/attempt，只清理本次创建的对象；工作文件放在 /run 下的临时目录。
#
# 用法（管理端，经 SSH 推送执行）：
#   ssh root@<节点 IP> 'CRI_SMOKE_CONFIRM=yes bash -s' < ops/00-preparation/tests/smoke/cri-smoke.sh
# 可选：SMOKE_IMAGE（默认 registry.k8s.io/e2e-test-images/busybox:1.38.0-1）、
#       CGROUP_PARENT（默认 phase00.slice；containerd 使用 SystemdCgroup=true 时必须是 .slice）、
#       SMOKE_PULL=yes（先执行 crictl pull "$SMOKE_IMAGE"）。
#
# 对应：ops/00-preparation/README.md 第 10.1、10.3 节；汇总入口
#   ops/00-preparation/scripts/collect-node-readiness.sh --with-cri-smoke
#
# 整个主体放在 { ... } </dev/null 中：经 `bash -s` 从标准输入执行时，bash 会先读完整个块，
# 块内命令的标准输入是 /dev/null，不会把脚本剩余部分当成输入读走（ausearch 在非终端
# 标准输入下就会这样做，2026-10-16 首次十节点运行因此提前结束）。
{
set -u
export LC_ALL=C

kv() { printf 'smoke_%s=%s\n' "$1" "$(printf '%s' "$2" | tr '\n' ' ')"; }

if [ "${CRI_SMOKE_CONFIRM:-}" != yes ]; then
  echo "cri-smoke.sh 会创建并删除 CRI 对象，需设置 CRI_SMOKE_CONFIRM=yes" >&2
  exit 2
fi

IMAGE=${SMOKE_IMAGE:-registry.k8s.io/e2e-test-images/busybox:1.38.0-1}
CGROUP_PARENT=${CGROUP_PARENT:-phase00.slice}
STAMP=$(date +%s)
WORK=$(mktemp -d /run/phase00-cri-smoke.XXXXXX)
SID="" CID="" RESULT=FAIL REASON=""

cleanup() {
  local ok=yes
  if [ -n "$CID" ]; then crictl rm -f "$CID" >/dev/null 2>&1 || ok=no; fi
  if [ -n "$SID" ]; then
    crictl stopp "$SID" >/dev/null 2>&1 || ok=no
    crictl rmp "$SID" >/dev/null 2>&1 || ok=no
  fi
  rm -rf "$WORK"
  kv cleanup "$ok"
  kv result "$RESULT"
  kv reason "$REASON"
}
trap cleanup EXIT

kv schema cri-smoke/v1
kv started_at "$(date -Is)"
kv image "$IMAGE"

if [ "${SMOKE_PULL:-no}" = yes ]; then
  if crictl pull "$IMAGE" >/dev/null 2>"$WORK/err"; then
    kv pull ok
  else
    kv pull fail
    REASON="pull 失败：$(head -c 300 "$WORK/err")"
    exit 1
  fi
fi

if ! crictl inspecti "$IMAGE" >/dev/null 2>&1; then
  REASON="镜像不在本地：$IMAGE"
  exit 1
fi

mkdir -p "$WORK/log"
cat > "$WORK/sandbox.json" <<JSON
{
  "metadata": {"name": "phase00-cri-smoke", "namespace": "phase00", "uid": "phase00-cri-smoke-$STAMP", "attempt": $STAMP},
  "log_directory": "$WORK/log",
  "linux": {
    "cgroup_parent": "$CGROUP_PARENT",
    "security_context": {"namespace_options": {"network": 2}}
  }
}
JSON
cat > "$WORK/container.json" <<JSON
{
  "metadata": {"name": "smoke", "attempt": 1},
  "image": {"image": "$IMAGE"},
  "command": ["/bin/sh", "-c", "echo phase00-cri-ok"],
  "log_path": "smoke.log",
  "linux": {}
}
JSON

if ! SID=$(crictl runp "$WORK/sandbox.json" 2>"$WORK/err"); then
  SID=""
  REASON="runp 失败：$(head -c 300 "$WORK/err")"
  exit 1
fi
kv sandbox_id "$SID"
PODJSON=$(crictl inspectp "$SID" 2>/dev/null)
kv sandbox_state "$(jq -r '.status.state' <<<"$PODJSON" 2>/dev/null)"
kv sandbox_network "$(jq -r '.status.linux.namespaces.options.network' <<<"$PODJSON" 2>/dev/null)"
PAUSE_PID=$(jq -r '.info.pid // empty' <<<"$PODJSON" 2>/dev/null)
kv pause_label "$( [ -n "$PAUSE_PID" ] && ps -o label= -p "$PAUSE_PID" 2>/dev/null)"

if ! CID=$(crictl create "$SID" "$WORK/container.json" "$WORK/sandbox.json" 2>"$WORK/err"); then
  CID=""
  REASON="create 失败：$(head -c 300 "$WORK/err")"
  exit 1
fi
if ! crictl start "$CID" >/dev/null 2>"$WORK/err"; then
  REASON="start 失败：$(head -c 300 "$WORK/err")"
  exit 1
fi

STATE=""
for _ in $(seq 1 40); do
  STATE=$(crictl inspect "$CID" 2>/dev/null | jq -r '.status.state' 2>/dev/null)
  [ "$STATE" = CONTAINER_EXITED ] && break
  sleep 0.5
done
CJSON=$(crictl inspect "$CID" 2>/dev/null)
EXIT_CODE=$(jq -r '.status.exitCode' <<<"$CJSON" 2>/dev/null)
LOG=$(crictl logs "$CID" 2>&1)
AVC=$(ausearch --input-logs -m AVC -ts recent 2>/dev/null | grep -c 'type=AVC')
kv container_state "$STATE"
kv container_exit_code "$EXIT_CODE"
kv container_reason "$(jq -r '.status.reason' <<<"$CJSON" 2>/dev/null)"
kv container_log "$LOG"
kv avc_recent "$AVC"
kv selinux "$(getenforce 2>/dev/null)"

if [ "$STATE" = CONTAINER_EXITED ] && [ "$EXIT_CODE" = 0 ] && [ "$LOG" = phase00-cri-ok ] && [ "$AVC" = 0 ]; then
  RESULT=PASS
else
  REASON="state=$STATE exit=$EXIT_CODE avc=$AVC"
fi
} </dev/null
