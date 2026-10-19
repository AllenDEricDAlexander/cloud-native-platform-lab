#!/usr/bin/env bash
# 被正式入口 source；不在加载时安装软件或修改系统。
set -euo pipefail
set +x
export LC_ALL=C
CNPL_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
CNPL_INPUTS=${CNPL_INPUTS:-/etc/cnpl/inputs}
CNPL_CHANGED=0
die() { printf '失败：%s\n' "$*" >&2; exit 1; }
root() { [[ $EUID == 0 ]] || die '本步骤需要 sudo -i 后执行'; }
need() { command -v "$1" >/dev/null || die "缺少前置命令 $1"; }
role() { hostname -s; }
valid_ipv4() {
    local address=$1 octet
    [[ $address =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || return 1
    local parts
    IFS=. read -ra parts <<< "$address"
    for octet in "${parts[@]}"; do ((10#$octet <= 255)) || return 1; done
}
host_ip() {
    local value
    [[ $1 =~ ^[a-z][a-z0-9]*$ ]] || die '非法主机名'
    value=$(awk -v name="$1" '$1==name {for(i=2;i<=NF;i++) if($i~/^ansible_host=/){sub(/^ansible_host=/,"",$i);print $i}}' "$CNPL_ROOT/inputs/hosts.ini")
    [[ $value =~ ^192\.168\.9\.[0-9]{1,3}$ ]] || die "主机 $1 未在正式清单中唯一登记"
    printf '%s\n' "$value"
}
vm_ips() { awk '{for(i=2;i<=NF;i++) if($i~/^ansible_host=/){sub(/^ansible_host=/,"",$i);print $i}}' "$CNPL_ROOT/inputs/hosts.ini" | sort -Vu; }
expect_host() {
    [[ $(role) == "$1" ]] || die "本步骤只用于 $1"
    [[ $(getenforce) == Enforcing ]] || die 'SELinux 必须保持 Enforcing'
    systemctl is-active --quiet firewalld || die 'firewalld 必须运行'
}
put() {
    local source=$1 destination=$2 mode=${3:-0644}
    [[ -f $source ]] || die "缺少输入文件 $source"
    if [[ ! -e $destination ]] || ! cmp -s "$source" "$destination"; then
        if [[ ! -d $(dirname "$destination") ]]; then install -d -m 0755 "$(dirname "$destination")"; fi
        if [[ -e $destination ]]; then
            local saved=/etc/cnpl/config-backups/$(date -u +%Y%m%dT%H%M%S)-$$
            install -d -m 0700 "$saved/$(dirname "${destination#/}")"
            cp -a "$destination" "$saved/${destination#/}"
        fi
        install -o root -g root -m "$mode" "$source" "$destination"
        CNPL_CHANGED=1
    fi
    chmod "$mode" "$destination"
}
secret_hex() {
    local file=$1
    install -d -m 0700 "$(dirname "$file")"
    if [[ ! -e $file ]]; then
        (umask 077; set -o noclobber; openssl rand -hex 32 | tr -d '\n' > "$file")
        CNPL_CHANGED=1
    fi
    [[ -s $file && ! -L $file ]] || die '秘密文件为空或是符号链接'
    chmod 0600 "$file"
}
fcontext() {
    local pattern=$1 type=$2 current
    current=$(semanage fcontext -l | CNPL_CONTEXT_PATTERN="$pattern" awk '$1==ENVIRON["CNPL_CONTEXT_PATTERN"] {print $NF}')
    if [[ -z $current ]]; then
        semanage fcontext -a -t "$type" "$pattern"; CNPL_CHANGED=1
    elif [[ $current != *":$type:"* ]]; then
        semanage fcontext -m -t "$type" "$pattern"; CNPL_CHANGED=1
    fi
}
rich_rule() {
    if ! firewall-cmd --permanent --zone=public --query-rich-rule="$1" >/dev/null; then
        firewall-cmd --permanent --zone=public --add-rich-rule="$1" >/dev/null
        CNPL_CHANGED=1
    fi
}
vm_ipset() {
    if ! firewall-cmd --permanent --get-ipsets | tr ' ' '\n' | grep -Fxq cnpl-vms; then
        firewall-cmd --permanent --new-ipset=cnpl-vms --type=hash:ip >/dev/null; CNPL_CHANGED=1
    fi
    local ip
    while read -r ip; do
        if ! firewall-cmd --permanent --ipset=cnpl-vms --query-entry="$ip" >/dev/null; then
            firewall-cmd --permanent --ipset=cnpl-vms --add-entry="$ip" >/dev/null; CNPL_CHANGED=1
        fi
    done < <(vm_ips)
    diff -u <(vm_ips | sort) <(firewall-cmd --permanent --ipset=cnpl-vms --get-entries | tr ' ' '\n' | sed '/^$/d' | sort) || die 'cnpl-vms 含未知成员，停止而不删除'
}
private_install() { dnf -y --disablerepo='*' --enablerepo='cnpl-*' --setopt=install_weak_deps=False install "$@"; }
result() { printf 'CNPL_CHANGED=%s\n' "$CNPL_CHANGED"; }
