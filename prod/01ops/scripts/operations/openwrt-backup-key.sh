#!/usr/bin/env bash
source "$(dirname "$0")/../lib/common.sh"
root; expect_host admin
umask 077
install -d -m 0700 /etc/cnpl/secrets /etc/cnpl/backup
private=/etc/cnpl/secrets/openwrt-backup.ssh
if [[ ! -e $private ]]; then
    [[ ! -e $private.pub ]] || die '公钥存在但私钥缺失，停止重建'
    ssh-keygen -q -t ed25519 -N '' -f "$private" -C cnpl-admin-openwrt-backup
fi
ssh-keygen -F 192.168.9.10 -f /home/ops/.ssh/known_hosts | awk '$2=="ssh-ed25519"{print "192.168.9.10 "$2" "$3}' > /etc/cnpl/backup/openwrt-known_hosts
[[ -s /etc/cnpl/backup/openwrt-known_hosts ]] || die '缺少已人工核实的 OpenWrt 主机密钥'
auth=(-i /home/ops/.ssh/cnpl_deploy -o IdentitiesOnly=yes -o UserKnownHostsFile=/home/ops/.ssh/known_hosts -o StrictHostKeyChecking=yes)
scp -O "${auth[@]}" "$private.pub" root@192.168.9.10:/tmp/cnpl-backup.pub
scp -O "${auth[@]}" "$CNPL_ROOT/scripts/operations/10-openwrt-backup.sh" root@192.168.9.10:/tmp/cnpl-backup-restrict.sh
set +e
ssh "${auth[@]}" root@192.168.9.10 'sh /tmp/cnpl-backup-restrict.sh check /tmp/cnpl-backup.pub'
status=$?
set -e
if [[ $status == 3 ]]; then
    key=$(awk '$1=="ssh-ed25519"{print $2}' "$private.pub")
    [[ $key =~ ^[A-Za-z0-9+/=]+$ ]] || die '本机公钥格式异常'
    printf 'no-port-forwarding,no-agent-forwarding,no-pty,command="tar -czf - /etc/config /etc/dropbear /etc/mihomo /etc/init.d/mihomo" ssh-ed25519 %s cnpl-admin-openwrt-backup\n' "$key" > /etc/cnpl/backup/openwrt-restricted.pub
    ssh-copy-id -f -i /etc/cnpl/backup/openwrt-restricted.pub -o IdentityFile=/home/ops/.ssh/cnpl_deploy -o IdentitiesOnly=yes -o UserKnownHostsFile=/home/ops/.ssh/known_hosts -o StrictHostKeyChecking=yes -t /etc/dropbear/authorized_keys root@192.168.9.10
elif [[ $status != 0 ]]; then die '公钥状态异常或管理连接失败，停止而不重复追加'; fi
ssh "${auth[@]}" root@192.168.9.10 'sh /tmp/cnpl-backup-restrict.sh /tmp/cnpl-backup.pub'
work=$(mktemp -d); trap 'rm -rf -- "$work"' EXIT
ssh -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/etc/cnpl/backup/openwrt-known_hosts -i "$private" root@192.168.9.10 'printf CNPL_UNRESTRICTED' > "$work/archive.tar.gz"
tar -tzf "$work/archive.tar.gz" > /dev/null || die '专用身份没有被限制为归档命令'
printf 'PASS OpenWrt 专用身份固定归档、既有部署授权保留\n'
