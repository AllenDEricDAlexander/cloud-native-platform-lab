#!/usr/bin/env bash
# Phase 00 节点只读检查：在目标 Rocky 节点上以 root 运行，逐项输出 key=value。
#
# 只读：不修改配置、不创建或删除 CRI 对象、不启停服务；单项命令失败时该项为空值，
# 不中断后续检查。是否通过由管理端汇总脚本按台账与版本锁判断，本脚本只采集事实。
#
# 用法（管理端，经 SSH 推送执行，节点上不需要预先存放本文件）：
#   ssh root@<节点 IP> 'bash -s' < ops/00-preparation/tests/smoke/node-readiness.sh
# 网卡默认 ens33，可用 NIC=<名称> 覆盖：ssh root@<IP> 'NIC=ens192 bash -s' < ...
#
# 对应：ops/00-preparation/README.md 第 2、4–10 节；汇总入口
#   ops/00-preparation/scripts/collect-node-readiness.sh
#
# 主体放在 { ... } </dev/null 中：经 `bash -s` 执行时，块内命令不会把脚本剩余部分当作
# 标准输入读走（见 cri-smoke.sh 中 ausearch 的同类问题）。新增检查项保持在块内。
{
set -u
export LC_ALL=C
NIC=${NIC:-ens33}

# 输出一行 key=value；多行值折叠为 " | "，保证一项一行。
kv() {
  local value
  value=$(printf '%s' "$2" | tr '\n' '\034' | sed 's/\x1c/ | /g')
  printf '%s=%s\n' "$1" "$value"
}

kv schema node-readiness/v1
kv collected_at "$(date -Is)"

# 身份与虚拟硬件
kv hostname "$(hostnamectl --static 2>/dev/null)"
kv machine_id "$(cat /etc/machine-id 2>/dev/null)"
kv product_uuid "$(cat /sys/class/dmi/id/product_uuid 2>/dev/null)"
kv os "$(. /etc/os-release 2>/dev/null && printf '%s' "${PRETTY_NAME:-}")"
kv kernel "$(uname -r)"
kv vcpu "$(nproc)"
kv mem_mib "$(awk '/^MemTotal:/ {printf "%d", $2 / 1024}' /proc/meminfo)"
kv disks "$(lsblk -dn -e7 -o NAME,SIZE,HCTL 2>/dev/null | awk '{printf "%s%s:%s:%s", (NR > 1 ? ";" : ""), $1, $2, $3}')"

# 网络与 SSH 身份
CONN=$(nmcli -g GENERAL.CONNECTION device show "$NIC" 2>/dev/null)
kv nic "$NIC"
kv mac "$(cat "/sys/class/net/$NIC/address" 2>/dev/null)"
kv nic_driver "$(ethtool -i "$NIC" 2>/dev/null | awk '/^driver:/ {print $2}')"
kv nm_connection "$CONN"
kv ipv4_method "$( [ -n "$CONN" ] && nmcli -g ipv4.method connection show "$CONN" 2>/dev/null)"
kv ipv4 "$(ip -4 -o addr show dev "$NIC" 2>/dev/null | awk '{print $4}' | paste -sd, -)"
kv gateway "$(ip -4 route show default 2>/dev/null | awk '{print $3; exit}')"
kv dns "$(awk '/^nameserver/ {print $2}' /etc/resolv.conf 2>/dev/null | paste -sd, -)"
kv ssh_ed25519_fp "$(ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub 2>/dev/null | awk '{print $2}')"

# 系统基线与安全
kv selinux "$(getenforce 2>/dev/null)"
kv firewalld "$(firewall-cmd --state 2>&1)"
kv swap_active "$(swapon --noheadings 2>/dev/null | grep -c .)"
kv cgroup_fs "$(stat -fc %T /sys/fs/cgroup 2>/dev/null)"
kv ip_forward "$(sysctl -n net.ipv4.ip_forward 2>/dev/null)"
kv overlay_loaded "$(lsmod 2>/dev/null | grep -c '^overlay ')"
kv chrony_leap "$(chronyc tracking 2>/dev/null | awk -F': ' '/^Leap status/ {print $2}')"
kv vmtoolsd "$(systemctl is-active vmtoolsd 2>/dev/null)"
kv failed_units "$(systemctl --failed --no-legend --plain 2>/dev/null | grep -c .)"
kv failed_unit_names "$(systemctl --failed --no-legend --plain 2>/dev/null | awk '{print $1}' | paste -sd, -)"

# 运行时盘与 containerd
kv runtime_mount_source "$(findmnt -nr -M /var/lib/containerd -o SOURCE 2>/dev/null)"
kv runtime_mount_uuid "$(findmnt -nr -M /var/lib/containerd -o UUID 2>/dev/null)"
kv runtime_mount_fstype "$(findmnt -nr -M /var/lib/containerd -o FSTYPE 2>/dev/null)"
kv containerd_enabled "$(systemctl is-enabled containerd 2>/dev/null)"
kv containerd_active "$(systemctl is-active containerd 2>/dev/null)"
kv containerd_version "$(containerd --version 2>/dev/null | awk '{print $3}')"
kv runc_version "$(runc --version 2>/dev/null | awk 'NR == 1 {print $3}')"
kv crictl_version "$(crictl --version 2>/dev/null | awk '{print $3}')"
CRI_INFO=$(crictl info 2>/dev/null)
kv runtime_ready "$(jq -r '.status.conditions[] | select(.type == "RuntimeReady") | .status' <<<"$CRI_INFO" 2>/dev/null)"
kv network_ready "$(jq -r '.status.conditions[] | select(.type == "NetworkReady") | .status' <<<"$CRI_INFO" 2>/dev/null)"
kv cri_images "$(crictl images -o json 2>/dev/null | jq -r '[.images[].repoTags[]] | sort | join(",")' 2>/dev/null)"

# 入群工具（00 只安装，不 init/join）
kv kubeadm_version "$(kubeadm version -o short 2>/dev/null)"
kv kubelet_version "$(kubelet --version 2>/dev/null | awk '{print $2}')"
kv kubectl_version "$(kubectl version --client -o json 2>/dev/null | jq -r '.clientVersion.gitVersion' 2>/dev/null)"
kv kubelet_enabled "$(systemctl is-enabled kubelet 2>/dev/null)"
kv cni_netd_files "$(find /etc/cni/net.d -mindepth 1 -maxdepth 1 2>/dev/null | grep -c .)"
} </dev/null
