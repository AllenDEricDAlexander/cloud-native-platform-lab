#!/bin/sh
# OpenWrt 原生 ash/UCI；由 admin 上传后执行，不安装 Docker/Bash/Python。
set -eu
test "$(id -u)" = 0 || exit 1
test "$(uci -q get system.@system[0].hostname)" = openwrt || { echo '只允许在 openwrt 执行' >&2; exit 1; }
case "${1:-}" in
  lock|proxies)
    zone=''
    for index in $(seq 0 20); do
        if test "$(uci -q get "firewall.@zone[$index].name" || true)" = lan; then zone="@zone[$index]"; break; fi
    done
    test -n "$zone" || { echo '没有找到 lan zone' >&2; exit 1; }
    if test "$1" = lock; then
        test "${CNPL_SSH_KEY_VERIFIED:-}" = yes || { echo '先从 admin 验证公钥会话' >&2; exit 1; }
        mkdir -p /etc/cnpl-backups; chmod 700 /etc/cnpl-backups
        stamp=$(date -u +%Y%m%dT%H%M%S)
        cp -p /etc/config/firewall "/etc/cnpl-backups/firewall.$stamp"
        cp -p /etc/config/dropbear "/etc/cnpl-backups/dropbear.$stamp"
        uci set firewall.admin_ssh=rule
        uci set firewall.admin_ssh.name=admin-ssh
        uci set firewall.admin_ssh.src=lan
        uci set firewall.admin_ssh.src_ip=192.168.9.15
        uci set firewall.admin_ssh.family=ipv4
        uci set firewall.admin_ssh.proto=tcp
        uci set firewall.admin_ssh.dest_port=22
        uci set firewall.admin_ssh.target=ACCEPT
        uci set 'dropbear.@dropbear[0].Interface=lan'
        uci set 'dropbear.@dropbear[0].PasswordAuth=off'
        uci set 'dropbear.@dropbear[0].RootPasswordAuth=off'
        uci set 'firewall.@defaults[0].input=REJECT'
        uci set 'firewall.@defaults[0].forward=REJECT'
        uci set "firewall.$zone.input=REJECT"
        uci set "firewall.$zone.forward=REJECT"
        uci set "firewall.$zone.output=ACCEPT"
    fi
    roles='admin'
    test "$1" != proxies || roles='admin dns dns02 harbor gitlab nexus'
    for role in $roles; do
        case "$role" in admin) ip=192.168.9.15;; dns) ip=192.168.9.11;; dns02) ip=192.168.9.17;; harbor) ip=192.168.9.12;; gitlab) ip=192.168.9.13;; nexus) ip=192.168.9.14;; esac
        uci set "firewall.${role}_proxy=rule"
        uci set "firewall.${role}_proxy.name=$role-proxy"
        uci set "firewall.${role}_proxy.src=lan"
        uci set "firewall.${role}_proxy.src_ip=$ip"
        uci set "firewall.${role}_proxy.family=ipv4"
        uci set "firewall.${role}_proxy.proto=tcp"
        uci set "firewall.${role}_proxy.dest_port=7890"
        uci set "firewall.${role}_proxy.target=ACCEPT"
    done
    uci commit firewall; fw4 check; /etc/init.d/firewall reload
    if test "$1" = lock; then uci commit dropbear; /etc/init.d/dropbear restart; fi
    ;;
  dns-ntp)
    uci -q delete network.lan.dns || true
    uci add_list network.lan.dns=192.168.9.11
    uci add_list network.lan.dns=192.168.9.17
    uci -q delete system.ntp.server || true
    uci add_list system.ntp.server=192.168.9.11
    uci add_list system.ntp.server=192.168.9.17
    uci set 'system.@system[0].zonename=UTC'
    uci set 'system.@system[0].timezone=UTC0'
    uci set system.ntp.enabled=1
    uci set system.ntp.enable_server=0
    uci commit network; uci commit system
    /etc/init.d/network reload
    /etc/init.d/sysntpd enable; /etc/init.d/sysntpd restart
    ;;
  verify)
    fw4 check
    test "$(uci get dropbear.@dropbear[0].PasswordAuth)" = off
    lan_zone=$(uci show firewall | sed -n "s/^firewall\.\(.*\)\.name='lan'$/\1/p")
    test -n "$lan_zone"
    test "$(uci get "firewall.$lan_zone.input")" = REJECT
    test "$(uci get "firewall.$lan_zone.forward")" = REJECT
    test "$(uci get firewall.admin_ssh.src_ip)" = 192.168.9.15
    test "$(uci get firewall.admin_ssh.dest_port)" = 22
    for role in admin dns dns02 harbor gitlab nexus; do
        case "$role" in admin) ip=192.168.9.15;; dns) ip=192.168.9.11;; dns02) ip=192.168.9.17;; harbor) ip=192.168.9.12;; gitlab) ip=192.168.9.13;; nexus) ip=192.168.9.14;; esac
        test "$(uci get "firewall.${role}_proxy.src_ip")" = "$ip"
        test "$(uci get "firewall.${role}_proxy.family")" = ipv4
        test "$(uci get "firewall.${role}_proxy.proto")" = tcp
        test "$(uci get "firewall.${role}_proxy.dest_port")" = 7890
        test "$(uci get "firewall.${role}_proxy.target")" = ACCEPT
    done
    for section in $(uci show firewall | sed -n 's/^firewall\.\(.*\)=rule$/\1/p'); do
        test "$(uci -q get "firewall.$section.target" || true)" = ACCEPT || continue
        source_zone=$(uci -q get "firewall.$section.src" || true)
        test -z "$source_zone" || test "$source_zone" = lan || continue
        protocol=$(uci -q get "firewall.$section.proto" || true)
        case "$protocol" in *tcp*|all|'') ;; *) continue;; esac
        port=$(uci -q get "firewall.$section.dest_port" || true)
        source_ip=$(uci -q get "firewall.$section.src_ip" || true)
        case "$port:$source_ip" in
          22:192.168.9.15|7890:192.168.9.15|7890:192.168.9.11|7890:192.168.9.17|7890:192.168.9.12|7890:192.168.9.13|7890:192.168.9.14) ;;
          *) echo '发现额外 LAN TCP 放行规则，停止交付' >&2; exit 1;;
        esac
    done
    test "$(uci get dhcp.lan.ignore)" = 1
    pidof mihomo >/dev/null
    echo 'PASS OpenWrt 管理/代理规则与 Mihomo 进程；实际出口由 admin 验证'
    ;;
  *) echo '用法：03-openwrt.sh lock|proxies|dns-ntp|verify' >&2; exit 2;;
esac
