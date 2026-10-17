#!/bin/sh
# OpenWrt 旁路由基线（00.05.02、00.05.03）：在 OpenWrt 上以 root 运行，由管理端经 SSH 推送：
#   ssh -i ~/.ssh/cnpl_lab_ed25519 -o IdentitiesOnly=yes root@192.168.9.10 'sh -s' < ops/00-preparation/openwrt/apply-base.sh
#
# 单网卡旁路由：默认网关仍是 .1，只有显式配置代理的程序经过本机（00.06.02）。
# 幂等：只用 uci 写入期望值；没有差异时不提交、不重载。必须经密钥登录执行：
# 脚本会关闭 SSH 口令登录，控制台与 LuCI 仍可用 root 口令。
set -eu

LAN_IP=192.168.9.10
LAN_MASK=255.255.255.0
GATEWAY=192.168.9.1
DNS=192.168.9.11

# 只在值不同时写入：uci set 即使值相同也会记录一条变更，无法据此判断是否需要重载。
uset() { [ "$(uci -q get "$1")" = "$2" ] || uci set "$1=$2"; }

uset system.@system[0].hostname 'openwrt'
uset system.@system[0].zonename 'Asia/Shanghai'
uset system.@system[0].timezone 'CST-8'

uset network.lan.proto 'static'
uset network.lan.ipaddr "$LAN_IP"
uset network.lan.netmask "$LAN_MASK"
uset network.lan.gateway "$GATEWAY"
uset network.lan.dns "$DNS"
# 不在 LAN 上分配 IPv6 前缀；RA 与 DHCPv6 由下面关闭，避免与路由器抢答（00.05.02）。
[ -z "$(uci -q get network.lan.ip6assign)" ] || uci delete network.lan.ip6assign

uset dhcp.lan.ignore '1'
uset dhcp.lan.dhcpv6 'disabled'
uset dhcp.lan.ra 'disabled'

# SSH 只用密钥，只监听 LAN。
uset dropbear.@dropbear[0].PasswordAuth 'off'
uset dropbear.@dropbear[0].RootPasswordAuth 'off'
uset dropbear.@dropbear[0].Interface 'lan'

CHANGES=$(uci changes)
echo "== 待提交的 uci 变更"
echo "${CHANGES:-无}"

if /etc/init.d/odhcpd enabled 2>/dev/null; then
  /etc/init.d/odhcpd disable
  /etc/init.d/odhcpd stop || true
  echo "odhcpd 已停用"
fi

if [ -n "$CHANGES" ]; then
  uci commit
  /etc/init.d/system reload
  /etc/init.d/network reload
  sleep 5
fi

echo "== 状态"
cat /proc/sys/kernel/hostname
ip -4 addr show br-lan | awk '/inet / {print $2}'
ip -4 route
echo "odhcpd: $(/etc/init.d/odhcpd enabled && echo enabled || echo disabled)"
echo "== 连通性"
ping -c 2 -W 2 "$GATEWAY" >/dev/null && echo "gateway ok" || echo "gateway FAIL"
ping -c 2 -W 2 223.5.5.5 >/dev/null && echo "internet ok" || echo "internet FAIL"
# BusyBox nslookup 先输出所用服务器（Server/Address），Name 之后才是解析结果。
for name in harbor.k8s.internal.egon.top downloads.openwrt.org; do
  nslookup "$name" 2>&1 | awk -v n="$name" '/^Name:/ {f = 1} f && /^Address/ {print n " -> " $NF; found = 1; exit} END {if (!found) print n " -> FAIL"}'
done

# 最后在后台重启 dropbear，使口令登录关闭生效；当前会话不受影响。
if echo "$CHANGES" | grep -q '^dropbear'; then
  ( sleep 2; /etc/init.d/dropbear restart ) >/dev/null 2>&1 &
  echo "dropbear 将在 2 秒后重启（已关闭口令登录）"
fi
