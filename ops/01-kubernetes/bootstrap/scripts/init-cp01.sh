#!/usr/bin/env bash
# 默认预演；--apply 创建集群，--resume 只恢复已初始化控制平面的 VIP，不再次 init。
set -euo pipefail
STAGE=/root/phase01-bootstrap
CONF=$STAGE/kubeadm/kubeadm-init-cp01.yaml
NODE_IP=192.168.9.101
if [ "$#" -ge 2 ]; then NODE_IP=$2; fi
LOCAL_SERVER=https://$NODE_IP:6443
KUBE_DIR=/etc/kubernetes
ETCD_DIR=/var/lib/etcd
ADMIN=$KUBE_DIR/admin.conf

redact() {
  sed -E 's/[a-z0-9]{6}\.[a-z0-9]{16}/[REDACTED_TOKEN]/g; s/(client-key-data|client-certificate-data|token):.*/\1: [REDACTED]/g'
}

diagnose() {
  echo '== 本机 API'
  kubectl --kubeconfig "$ADMIN" --server "$LOCAL_SERVER" --request-timeout=5s get --raw=/readyz 2>&1 | redact || true
  echo '== VIP API'
  kubectl --kubeconfig "$ADMIN" --request-timeout=5s get --raw=/readyz 2>&1 | redact || true
  echo '== 节点地址'
  ip -4 addr show ens33 || true
  echo '== kube-vip 容器'
  local container_id=""
  container_id=$(crictl ps -a --name kube-vip -q | head -n 1) || true
  if [ -n "$container_id" ]; then
    crictl logs --tail=30 "$container_id" 2>&1 | redact || true
  fi
}

wait_for_vip() {
  local timeout=180 stable=0 pod_state="" last_error='尚未检查'
  if [ "$#" -ge 1 ]; then timeout=$1; fi
  local deadline=$((SECONDS + timeout))
  local expected='127.0.0.1 kubernetes /etc/kubernetes/admin.conf true'
  while [ "$SECONDS" -lt "$deadline" ]; do
    if pod_state=$(kubectl --kubeconfig "$ADMIN" --server "$LOCAL_SERVER" --request-timeout=5s -n kube-system \
      get pod "kube-vip-$(hostname -f)" \
      -o 'jsonpath={.spec.hostAliases[0].ip}{" "}{.spec.hostAliases[0].hostnames[0]}{" "}{.spec.volumes[?(@.name=="kubeconfig")].hostPath.path}{" "}{.status.containerStatuses[?(@.name=="kube-vip")].ready}' 2>&1); then
      if [ "$pod_state" != "$expected" ]; then
        stable=0
        last_error="等待修正后的稳态 kube-vip Pod：$pod_state"
      elif ! last_error=$(kubectl --kubeconfig "$ADMIN" --request-timeout=5s get --raw=/readyz 2>&1); then
        stable=0
      elif ! ip -4 -o addr show ens33 | awk '{print $4}' | grep -qx '192.168.9.100/32'; then
        stable=0
        last_error='VIP 192.168.9.100/32 尚未绑定 ens33'
      else
        stable=$((stable + 1))
        if [ "$stable" -ge 3 ]; then return 0; fi
      fi
    else
      stable=0
      last_error="本机 API 的 kube-vip Pod 查询失败：$pod_state"
    fi
    sleep 2
  done
  printf 'ERROR: 等待 VIP %s 秒未通过：%s\n' "$timeout" "$last_error" | redact >&2
  return 1
}

main() {
  local mode=--dry-run log rc containers pods path
  if [ "$#" -gt 0 ]; then mode=$1; fi
  case "$mode" in --dry-run|--apply|--resume) ;; *) echo '用法: init-cp01.sh [--dry-run|--apply|--resume] [node-ip]' >&2; return 2 ;; esac
  test "$(id -u)" -eq 0 || { echo 'ERROR: 需要 root' >&2; return 2; }
  test "$(hostname -s)" = cp01 || { echo 'ERROR: 仅用于 cp01' >&2; return 2; }
  test "$(getenforce)" = Enforcing || { echo 'ERROR: SELinux 必须保持 Enforcing' >&2; return 2; }

  if [ "$mode" = --resume ]; then
    for path in "$ADMIN" "$KUBE_DIR/pki/ca.crt" "$KUBE_DIR/manifests/kube-apiserver.yaml" "$ETCD_DIR/member"; do
      test -e "$path" || { echo "ERROR: 未发现完整初始化产物 $path，恢复模式不会执行 init。" >&2; return 2; }
    done
    if ! kubectl --kubeconfig "$ADMIN" --server "$LOCAL_SERVER" --request-timeout=5s get --raw=/readyz >/dev/null 2>&1; then
      echo 'ERROR: 本机控制平面尚不健康，停止 VIP 恢复并保留现场。' >&2
      diagnose
      return 1
    fi
  else
    test "$(systemctl is-active kubelet || true)" = inactive || { echo 'ERROR: kubelet 已运行；已完成 init 的节点请使用 --resume。' >&2; return 2; }
    for path in "$KUBE_DIR/pki/ca.key" "$ADMIN" "$KUBE_DIR/manifests/kube-apiserver.yaml" "$ETCD_DIR/member"; do
      test ! -e "$path" || { echo "ERROR: 已有初始化产物 $path；保留现场，已完成 init 时使用 --resume。" >&2; return 2; }
    done
    containers=$(crictl ps -a -q)
    pods=$(crictl pods -q)
    test -z "$containers$pods" || { echo 'ERROR: 已有 CRI 对象，停止初始化。' >&2; return 2; }
    for path in "$KUBE_DIR/enc/encryption-config.yaml" "$KUBE_DIR/audit/policy.yaml" "$KUBE_DIR/patches/kubeletconfiguration+merge.yaml" /etc/systemd/system/kubelet.service.d/20-kubernetes-selinux.conf; do
      test -s "$path" || { echo "ERROR: 缺少 prepare 输入 $path" >&2; return 2; }
    done
    kubeadm config validate --config "$CONF"
    install -d -m 0755 "$KUBE_DIR/manifests"
    install -m 0600 "$STAGE/kube-vip/kube-vip-cp01-init.yaml" "$KUBE_DIR/manifests/kube-vip.yaml"
    restorecon -RF "$KUBE_DIR" "$ETCD_DIR" /var/log/kubernetes/audit
    umask 077
    log=/root/kubeadm-init-dry-run.out
    set -- --config "$CONF" --dry-run
    if [ "$mode" = --apply ]; then
      log=/root/kubeadm-init.out
      set -- --config "$CONF"
      systemctl enable kubelet >/dev/null
    fi
    if kubeadm init "$@" >"$log" 2>&1; then rc=0; else rc=$?; fi
    chmod 0600 "$log"
    grep -E '^\[(init|preflight|certs|kubeconfig|etcd|control-plane|kubelet-start|patches|wait-control-plane|upload-config|mark-control-plane|addons)\]' "$log" \
      | grep -v -E 'token|certificate-key' || true
    if [ "$rc" -ne 0 ]; then
      echo "ERROR: kubeadm 返回 $rc；原始日志 $log（含敏感凭据，勿原样贴出）。" >&2
      diagnose
      return "$rc"
    fi
    if [ "$mode" = --dry-run ]; then
      echo 'dry-run PASS；未初始化、未启动 kubelet。下一步显式使用 --apply。'
      return 0
    fi
  fi

  # init 已完成或显式 resume：只调整 kube-vip，不重建 CA/etcd，也不改动全局 kubeconfig。
  install -m 0600 "$STAGE/kube-vip/kube-vip-control-plane.yaml" "$KUBE_DIR/manifests/kube-vip.yaml"
  if ! wait_for_vip 180; then diagnose; return 1; fi
  kubectl --kubeconfig "$ADMIN" --request-timeout=5s get nodes -o wide
  echo 'cp01 init PASS；本机 API、修正后的稳态 kube-vip 和 VIP API 均已验证，下一步安装 Cilium。'
}

if [ "$BASH_SOURCE" = "$0" ]; then main "$@"; fi
