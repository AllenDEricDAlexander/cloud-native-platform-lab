#!/bin/sh
# OpenWrt 只读核验专用公钥；不修改 authorized_keys 或任何管理授权。
set -eu
test "$(id -u)" = 0 || exit 1
if test "${1:-}" = check; then shift; fi
test "$#" = 1 || { echo '需要本次备份公钥文件路径' >&2; exit 2; }
key=$(awk '$1=="ssh-ed25519" {print $2}' "$1")
test -n "$key" || { echo '公钥格式不符' >&2; exit 1; }
file=/etc/dropbear/authorized_keys
count=$(awk -v key="$key" '{for(i=1;i<NF;i++)if($i=="ssh-ed25519" && $(i+1)==key)n++} END{print n+0}' "$file")
test "$count" != 0 || exit 3
test "$count" = 1 || { echo '专用公钥重复，停止而不修改授权' >&2; exit 1; }
expected="no-port-forwarding,no-agent-forwarding,no-pty,command=\"tar -czf - /etc/config /etc/dropbear /etc/mihomo /etc/init.d/mihomo\" ssh-ed25519 $key cnpl-admin-openwrt-backup"
grep -Fxq "$expected" "$file" || { echo '已有专用公钥的限制不符，停止而不替换授权' >&2; exit 1; }
echo 'PASS 专用公钥唯一且已限定为固定归档命令'
