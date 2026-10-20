#!/usr/bin/env bash
source "$(dirname "$0")/../lib/common.sh"
root; need firewall-cmd
need flock
exec 9> /run/cnpl-network.lock
flock -n 9 || die '本机已有网络变更或回退在执行'
host=$(role); ip=$(host_ip "$host")
pending=/run/cnpl-network.pending
unit=cnpl-network-rollback
case "${1:-}" in
  commit)
    if [[ -s $pending ]]; then
        directory=$(cat "$pending")
        [[ $directory =~ ^/var/lib/cnpl/firewall/[0-9]{8}T[0-9]{6}-[0-9]+$ ]] || die '待确认批次记录异常'
        [[ $(cat "$directory/state") == applied ]] || die '本次未完成应用或已经回退'
        systemctl stop "$unit.timer"
        printf 'committed\n' > "$directory/state"
        rm -f "$pending"
        printf 'PASS 已取消本机网络超时回退\n'
    elif [[ -s /run/cnpl-network.last ]]; then
        directory=$(cat /run/cnpl-network.last)
        [[ $(cat "$directory/state") != rolled-back ]] || die '本次窗口已超时回退，须重新预览和应用'
    fi
    exit 0
    ;;
  plan|apply) ;;
  *) die '用法：network.sh plan|apply|commit';;
esac
[[ $(getenforce) == Enforcing ]] || die 'SELinux 状态异常'
for cluster_file in /etc/kubernetes/admin.conf /etc/kubernetes/kubelet.conf /var/lib/kubelet/config.yaml; do
    [[ ! -e $cluster_file ]] || die '节点已入群，禁止重新套用 00 出站策略，转入 01 的网络维护流程'
done
firewall-cmd --get-active-zones | grep -q public || die '先人工核对 ens33 所在 zone'
[[ $(firewall-cmd --get-zone-of-interface=ens33) == public ]] || die 'ens33 必须位于 public zone'
work=$(mktemp -d); trap 'rm -rf -- "$work"' EXIT
rules=$work/rules; : > "$rules"
allow() {
    local address=$1 port=${2:-} protocol=${3:-tcp}
    [[ $address =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || die '目的地址必须是已登记的 IPv4'
    if [[ -z $port ]]; then
        printf 'rule family="ipv4" destination address="%s/32" accept\n' "$address" >> "$rules"
    else
        [[ $port =~ ^[0-9]+$ && ( $protocol == tcp || $protocol == udp ) ]] || die '非法端口/协议'
        printf 'rule family="ipv4" destination address="%s/32" port port="%s" protocol="%s" accept\n' "$address" "$port" "$protocol" >> "$rules"
    fi
}
allow 127.0.0.1; allow "$ip"
printf '%s\n' 'rule family="ipv6" destination address="::1/128" accept' >> "$rules"
for dns in 192.168.9.11 192.168.9.17; do allow "$dns" 53 tcp; allow "$dns" 53 udp; allow "$dns" 123 udp; done
allow 192.168.9.12 443; allow 192.168.9.14 443
case $host in
  admin)
    allow 192.168.9.10 7890; allow 192.168.9.13 443
    while read -r address; do [[ $address == "$ip" ]] || allow "$address" 22; done < <(vm_ips)
    ;;
  dns|dns02)
    allow 192.168.9.10 7890; allow 192.168.9.1 53 tcp; allow 192.168.9.1 53 udp
    allow 192.168.9.11 53 tcp; allow 192.168.9.17 53 tcp
    [[ -s $CNPL_INPUTS/ntp-upstream-ip.txt ]] || die '先登记并固定两个已验证的 NTP 上游地址'
    while read -r address; do allow "$address" 123 udp; done < "$CNPL_INPUTS/ntp-upstream-ip.txt"
    ;;
  harbor|gitlab|nexus) allow 192.168.9.10 7890;;
  build01) allow 192.168.9.13 22; allow 192.168.9.13 443;;
  backup|cp01|cp02|cp03|infra01|infra02|storage01|storage02|storage03|worker01|worker02) ;;
  *) die '未知角色，停止';;
esac
case $host in admin|dns|dns02|nexus|harbor|gitlab) allow 192.168.9.16 22;; esac
sort -u "$rules" -o "$rules"
if [[ $1 == plan ]]; then cat "$rules"; exit; fi
[[ ! -e $pending ]] || die '已有待确认的网络变更，先完成验收或等待回退'
[[ ! -e /etc/firewalld/policies/cnpl-egress.xml || -f /etc/cnpl/inputs/cnpl-egress.managed ]] || die '存在未纳管的同名 policy，先核对归属'
policy_matches() {
    local mode=${1:-}
    options=(); [[ -z $mode ]] || options+=(--permanent)
    firewall-cmd "${options[@]}" --get-policies | tr ' ' '\n' | grep -Fxq cnpl-egress || return 1
    [[ $(firewall-cmd "${options[@]}" --policy=cnpl-egress --get-target) == DROP ]] || return 1
    [[ $(firewall-cmd "${options[@]}" --policy=cnpl-egress --get-priority) == -500 ]] || return 1
    [[ $(firewall-cmd "${options[@]}" --policy=cnpl-egress --list-ingress-zones) == HOST ]] || return 1
    [[ $(firewall-cmd "${options[@]}" --policy=cnpl-egress --list-egress-zones) == ANY ]] || return 1
    for query in services ports source-ports forward-ports; do
        [[ -z $(firewall-cmd "${options[@]}" --policy=cnpl-egress "--list-$query") ]] || return 1
    done
    diff -q "$rules" <(firewall-cmd "${options[@]}" --policy=cnpl-egress --list-rich-rules | sort -u) >/dev/null
}
if policy_matches && policy_matches permanent; then rm -f /run/cnpl-network.last; printf 'CNPL_CHANGED=0\n'; exit; fi
batch=$(date -u +%Y%m%dT%H%M%S)-$$
directory=/var/lib/cnpl/firewall/$batch
install -d -m 0700 "$directory" /etc/cnpl/inputs
cp -a /etc/firewalld "$directory/firewalld-before"
cat > "$directory/rollback.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec 9> /run/cnpl-network.lock
flock 9
[[ -s /run/cnpl-network.pending && \$(cat /run/cnpl-network.pending) == $directory ]] || exit 0
if [[ -f $directory/firewalld-before/policies/cnpl-egress.xml ]]; then
  cp -a $directory/firewalld-before/policies/cnpl-egress.xml /etc/firewalld/policies/cnpl-egress.xml
else
  rm -f /etc/firewalld/policies/cnpl-egress.xml
fi
firewall-cmd --reload
if systemctl list-unit-files cnpl-harbor-firewall.service --no-legend | grep -q cnpl-harbor-firewall; then systemctl restart cnpl-harbor-firewall; fi
printf 'rolled-back\n' > $directory/state
rm -f /run/cnpl-network.pending
EOF
chmod 0700 "$directory/rollback.sh"
printf '%s\n' "$directory" > "$pending"; chmod 0600 "$pending"
printf '%s\n' "$directory" > /run/cnpl-network.last
systemd-run --quiet --collect --unit="$unit" --on-active=180s --timer-property=AccuracySec=1s /bin/bash "$directory/rollback.sh"
install -d -m 0755 /etc/firewalld/policies
if ! firewall-cmd --permanent --get-policies | tr ' ' '\n' | grep -Fxq cnpl-egress; then firewall-cmd --permanent --new-policy=cnpl-egress >/dev/null; fi
# 只重建本项目 policy，备份与独立定时回退已就绪。
firewall-cmd --permanent --policy=cnpl-egress --set-target=DROP >/dev/null
firewall-cmd --permanent --policy=cnpl-egress --set-priority=-500 >/dev/null
firewall-cmd --permanent --policy=cnpl-egress --query-ingress-zone=HOST >/dev/null || firewall-cmd --permanent --policy=cnpl-egress --add-ingress-zone=HOST >/dev/null
firewall-cmd --permanent --policy=cnpl-egress --query-egress-zone=ANY >/dev/null || firewall-cmd --permanent --policy=cnpl-egress --add-egress-zone=ANY >/dev/null
while IFS= read -r existing; do
    [[ -z $existing ]] || firewall-cmd --permanent --policy=cnpl-egress --remove-rich-rule="$existing" >/dev/null
done < <(firewall-cmd --permanent --policy=cnpl-egress --list-rich-rules)
while IFS= read -r rule; do firewall-cmd --permanent --policy=cnpl-egress --add-rich-rule="$rule" >/dev/null; done < "$rules"
firewall-cmd --check-config
firewall-cmd --reload
if [[ $host == harbor ]]; then systemctl restart cnpl-harbor-firewall; fi
install -m 0600 /dev/null /etc/cnpl/inputs/cnpl-egress.managed
printf 'applied\n' > "$directory/state"
printf 'CNPL_CHANGED=1\n本机 180 秒内未 commit 将自动恢复此前 policy；记录=%s\n' "$directory"
