#!/usr/bin/env bash
# 把刚克隆、仍是 DHCP 的 VM 改为台账中的主机名与静态地址，并分发管理端密钥（在管理 Mac 上运行）。
# 名称、地址、网卡连接取自 ops/inventory/hosts.yaml（kubernetes_nodes、bootstrap_services 与 lab_clients），
# 网关、掩码、DNS 取自 networks.yaml。
#
# 用法：bash ops/00-preparation/scripts/set-vm-identity.sh <台账 id> <当前 DHCP 地址>
#   例：bash ops/00-preparation/scripts/set-vm-identity.sh gitlab 192.168.9.35
# 过程中只需输入一次模板的 root 口令（ssh-copy-id），之后都用密钥。
# 首次连接自动接受新主机密钥（accept-new）；已有的旧记录会先删除（DHCP 地址会被不同克隆复用）。
set -euo pipefail

ID=${1:?用法：set-vm-identity.sh <台账 id> <当前 DHCP 地址>}
DHCP_IP=${2:?用法：set-vm-identity.sh <台账 id> <当前 DHCP 地址>}
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
KEY=${LAB_SSH_KEY:-$HOME/.ssh/cnpl_lab_ed25519}
SSH_OPTS=(-i "$KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5)

# 从台账读出：FQDN IP 连接名 前缀长度 网关 DNS
read -r FQDN IP CONN PREFIX GW DNS <<<"$(cd "$ROOT" && ruby -ryaml -e '
  id = ARGV[0]
  h = YAML.load_file("ops/inventory/hosts.yaml")
  svc = (h["kubernetes_nodes"] + h["bootstrap_services"] + h.fetch("lab_clients", [])).find { |s| s["id"] == id } or abort "台账中没有 #{id}"
  lan = YAML.load_file("ops/inventory/networks.yaml")["lan"]
  puts [svc["fqdn"], svc["ip"], svc["network_connection"] || "ens33", lan["cidr"].split("/").last,
        lan["default_gateway"], Array(lan["planned_dns_servers"]).join(",")].join(" ")
' "$ID")"
echo "目标：${FQDN} ${IP}/${PREFIX}，网关 ${GW}，DNS ${DNS}，连接 ${CONN}；当前 DHCP 地址 ${DHCP_IP}"

if ping -c 1 -W 1000 "$IP" >/dev/null 2>&1; then
  echo "${IP} 已有主机应答，可能被占用；确认后再执行（若就是这台 VM，说明已改过地址）" >&2
  exit 1
fi

for h in "$DHCP_IP" "$IP" "$FQDN"; do ssh-keygen -R "$h" >/dev/null 2>&1 || true; done

echo "== 分发密钥（输入一次模板 root 口令）"
ssh-copy-id -i "$KEY.pub" -o StrictHostKeyChecking=accept-new "root@${DHCP_IP}"

echo "== 设置主机名与静态地址（连接在后台重新激活，当前会话随即结束）"
ssh "${SSH_OPTS[@]}" "root@${DHCP_IP}" "set -e
hostnamectl set-hostname '${FQDN}'
nmcli connection modify '${CONN}' ipv4.method manual ipv4.addresses '${IP}/${PREFIX}' \
  ipv4.gateway '${GW}' ipv4.dns '${DNS//,/ }' ipv6.ignore-auto-dns yes
nohup sh -c 'sleep 2; nmcli connection up \"${CONN}\"' </dev/null >/dev/null 2>&1 &
echo 已提交"

echo "== 等待新地址 ${IP} 可以登录"
for _ in $(seq 1 30); do
  if ssh "${SSH_OPTS[@]}" -o BatchMode=yes "root@${IP}" true 2>/dev/null; then break; fi
  sleep 2
done

ssh "${SSH_OPTS[@]}" -o BatchMode=yes "root@${IP}" '
echo "hostname: $(hostnamectl --static)"
echo "address:  $(ip -4 -o addr show scope global | awk "{print \$2, \$4}")"
echo "route:    $(ip -4 route show default)"
echo "dns:      $(awk "/^nameserver/ {print \$2}" /etc/resolv.conf | paste -sd, -)"
ping -c 1 -W 2 '"$GW"' >/dev/null && echo "gateway:  ok" || echo "gateway:  FAIL"
'
ssh-keygen -R "$DHCP_IP" >/dev/null 2>&1 || true
echo "完成：${ID} 现在是 ${FQDN} / ${IP}，密钥登录可用"
