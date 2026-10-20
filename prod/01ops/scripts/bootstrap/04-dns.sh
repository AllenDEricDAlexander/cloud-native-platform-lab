#!/usr/bin/env bash
source "$(dirname "$0")/../lib/common.sh"
root
case "${1:-}" in
  zone-precheck)
    [[ $(role) == dns ]] || die '主区域预检只在 dns 执行'
    serial() { awk '/SOA/ {seen=1} seen {for(i=1;i<=NF;i++)if($i~/^[0-9]+$/){print $i;exit}}' "$1"; }
    for zone in forward reverse; do
        desired=$CNPL_ROOT/config/cnpl-$zone.zone
        current=/var/named/cnpl-$zone.zone
        if [[ -f $current ]] && ! cmp -s "$desired" "$current"; then
            next=$(serial "$desired"); before=$(serial "$current")
            [[ $next =~ ^[0-9]+$ && $before =~ ^[0-9]+$ ]] || die 'SOA serial 不合法'
            ((10#$next > 10#$before && 10#$next <= 4294967295)) || die '区域内容变化但 serial 未递增，停止发布'
        fi
    done
    ;;
  server)
    case $(role) in dns) type=primary;; dns02) type=secondary;; *) die '只能在 dns/dns02 执行';; esac
    source /etc/profile.d/cnpl-proxy.sh
    if [[ -e /etc/yum.repos.d/cnpl-private.repo ]]; then private_install bind bind-utils chrony; else dnf -y --setopt=proxy=http://192.168.9.10:7890 install bind bind-utils chrony; fi
    put "$CNPL_ROOT/config/named-$type.conf" /etc/named.conf
    if [[ $type == primary ]]; then
        bash "$0" zone-precheck
        for zone in forward reverse; do
            put "$CNPL_ROOT/config/cnpl-$zone.zone" "/var/named/cnpl-$zone.zone" 0640
            chown root:named "/var/named/cnpl-$zone.zone"
        done
        named-checkzone internal.egon.top /var/named/cnpl-forward.zone
        named-checkzone 9.168.192.in-addr.arpa /var/named/cnpl-reverse.zone
    fi
    named-checkconf
    put "$CNPL_INPUTS/chrony-server.conf" /etc/chrony.conf
    restorecon -RF /var/named /etc/named.conf
    vm_ipset
    for pair in '53 udp' '53 tcp' '123 udp'; do
        read -r port protocol <<< "$pair"
        rich_rule "rule family=\"ipv4\" source ipset=\"cnpl-vms\" port port=\"$port\" protocol=\"$protocol\" accept"
    done
    firewall-cmd --check-config; firewall-cmd --reload
    systemctl enable --now named chronyd
    if [[ $CNPL_CHANGED == 1 ]]; then systemctl reload named; systemctl restart chronyd; fi
    chronyc waitsync 30 1 0 2
    ;;
  client)
    case $(role) in dns|dns02) die 'DNS 服务器须保留上游 NTP 配置';; esac
    connection=$(nmcli -g GENERAL.CONNECTION device show ens33)
    [[ -n $connection && $connection != -- ]] || die 'ens33 未连接，先在 Web 控制台修正'
    nmcli connection modify "$connection" ipv4.dns '192.168.9.11 192.168.9.17' ipv4.ignore-auto-dns yes ipv6.dns '' ipv6.ignore-auto-dns yes
    nmcli device reapply ens33
    diff -u <(printf '192.168.9.11\n192.168.9.17\n') <(awk '/^nameserver/{print $2}' /etc/resolv.conf)
    put "$CNPL_ROOT/config/chrony-client.conf" /etc/chrony.conf
    systemctl enable --now chronyd
    if [[ $CNPL_CHANGED == 1 ]]; then systemctl restart chronyd; fi
    chronyc waitsync 30 1 0 2
    ;;
  verify)
    need dig
    for ip in 192.168.9.11 192.168.9.17; do
        [[ $(dig +short +time=3 +tries=1 @"$ip" harbor.k8s.internal.egon.top A) == 192.168.9.12 ]]
        [[ $(dig +short +tcp +time=3 +tries=1 @"$ip" -x 192.168.9.14) == nexus.svc.internal.egon.top. ]]
    done
    [[ $(getent ahostsv4 nexus.svc.internal.egon.top | awk 'NR==1{print $1}') == 192.168.9.14 ]]
    chronyc waitsync 30 1 0 2
    printf 'PASS 双 DNS UDP/TCP、PTR、系统解析与时间同步\n'
    ;;
  *) die '用法：04-dns.sh zone-precheck|server|client|verify';;
esac
result
