#!/usr/bin/env bash
source "$(dirname "$0")/../lib/common.sh"
root; host=$(role); host_ip "$host" >/dev/null
[[ $(firewall-cmd --policy=cnpl-egress --get-target) == DROP ]] || die '运行期出站策略不是 DROP'
for dns in 192.168.9.11 192.168.9.17; do
    [[ $(dig +short +time=3 +tries=1 @"$dns" harbor.k8s.internal.egon.top A) == 192.168.9.12 ]] || die '内网 DNS 路径失败'
done
chronyc waitsync 10 1 0 2
curl --fail --silent --show-error --noproxy '*' --max-time 10 https://rpm.svc.internal.egon.top/baseos/repodata/repomd.xml -o /dev/null
code=$(curl --silent --show-error --noproxy '*' --max-time 10 --output /dev/null --write-out '%{http_code}' https://harbor.k8s.internal.egon.top/v2/)
[[ $code == 401 ]] || die 'Harbor 直连或 registry 认证异常'
if timeout 5 bash -c 'exec 3<>/dev/tcp/1.1.1.1/443' >/dev/null 2>&1; then die '直接公网 TCP 443 未被拒绝'; fi
case $host in
  admin|dns|dns02|nexus|harbor|gitlab) bash "$CNPL_ROOT/scripts/bootstrap/03-management.sh" proxy-check;;
  *)
    if timeout 5 bash -c 'exec 3<>/dev/tcp/192.168.9.10/7890' >/dev/null 2>&1; then die '普通节点意外得到代理入口'; fi
    ;;
esac
if [[ $host != admin ]]; then
    peer=192.168.9.101; [[ $host != cp01 ]] || peer=192.168.9.102
    if timeout 5 bash -c 'exec 3<>/dev/tcp/$1/22' _ "$peer" >/dev/null 2>&1; then die '普通主机意外得到横向 SSH 通道'; fi
fi
printf 'PASS 内网 DNS/NTP/私服、角色代理、公网与横向拒绝路径\n'
