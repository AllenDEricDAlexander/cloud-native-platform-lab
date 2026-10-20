#!/bin/bash
# Mac 仅验证 admin 登录及其他 VM 的拒绝路径，不配置其他 VM 的登录身份。
set -euo pipefail
[[ $(uname -s) == Darwin ]] || { echo '仅在 Mac 执行' >&2; exit 1; }
root=$(cd "$(dirname "$0")/../.." && pwd)
[[ $(ssh -o BatchMode=yes cnpl-admin hostname -f) == admin.mgmt.internal.egon.top ]] || { echo 'admin 公钥登录失败，先解锁个人密钥' >&2; exit 1; }
while IFS= read -r ip; do
    if nc -G 2 -w 2 -z "$ip" 22 >/dev/null 2>&1; then echo "意外允许 Mac -> $ip:22" >&2; exit 1; fi
done < <(awk '$1!="admin" {for(i=2;i<=NF;i++)if($i~/^ansible_host=/){sub(/^ansible_host=/,"",$i);print $i}}' "$root/inputs/hosts.ini")
for endpoint in 192.168.9.10:7890 192.168.9.11:53 192.168.9.17:53 192.168.9.12:443 192.168.9.13:443 192.168.9.14:443; do
    if nc -G 2 -w 2 -z "${endpoint%:*}" "${endpoint##*:}" >/dev/null 2>&1; then echo "意外允许 Mac -> $endpoint" >&2; exit 1; fi
done
echo 'PASS Mac 可登录 admin，其他 VM 管理/私服入口均被拒绝'
