#!/usr/bin/env bash
source "$(dirname "$0")/../lib/common.sh"
case "${1:-}" in
  import-public)
    root
    install -d -m 0750 /etc/cnpl/inputs
    source_dir=/home/ops/.local/share/cnpl-inputs
    for file in cnpl-root.crt chrony-server.conf ntp-upstream-ip.txt data-disk.json; do
      [[ ! -f $source_dir/$file ]] || put "$source_dir/$file" "/etc/cnpl/inputs/$file" 0644
    done
    if [[ -d $source_dir/rpm-keys ]]; then
      install -d -m 0755 /etc/cnpl/inputs/rpm-keys
      for key in rocky10 epel10 docker kubernetes gitlab cnpl-metadata; do
        for suffix in asc fpr; do put "$source_dir/rpm-keys/$key.$suffix" "/etc/cnpl/inputs/rpm-keys/$key.$suffix"; done
      done
    fi
    ;;
  admin-tools)
    root; expect_host admin
    # 仅安装引导所需命令，Ansible/Helm/kubectl 留在 5.7。
    "$0" proxy
    source /etc/profile.d/cnpl-proxy.sh
    dnf -y --setopt=proxy=http://192.168.9.10:7890 --setopt=sslverify=True --setopt=gpgcheck=True install dnf-plugins-core openssl bind-utils gnupg2 jq
    rpm -q dnf-plugins-core openssl bind-utils gnupg2 jq
    ;;
  ssh-client)
    [[ $(role) == admin && $(id -un) == ops ]] || die '在 admin 的 ops 会话执行'
    install -d -m 0700 "$HOME/.ssh/cnpl.d"
    file="$HOME/.ssh/cnpl.d/management.conf"
    cat > "$file" <<'EOF'
Host cnpl-openwrt 192.168.9.10 openwrt.mgmt.internal.egon.top
    HostName 192.168.9.10
    User root
    IdentityFile ~/.ssh/cnpl_deploy
    IdentitiesOnly yes
    StrictHostKeyChecking yes
    ForwardAgent no
    ClearAllForwardings yes
Host 192.168.9.* *.internal.egon.top
    User ops
    IdentityFile ~/.ssh/cnpl_deploy
    IdentitiesOnly yes
    StrictHostKeyChecking yes
    ForwardAgent no
    ClearAllForwardings yes
EOF
    chmod 0600 "$file"
    touch "$HOME/.ssh/config"; chmod 0600 "$HOME/.ssh/config"
    if ! grep -Fxq 'Include ~/.ssh/cnpl.d/*.conf' "$HOME/.ssh/config"; then
        [[ ! -s $HOME/.ssh/config ]] || die '已有 SSH 配置，请人工把 Include 加在适当位置并核对优先级'
        printf '%s\n' 'Include ~/.ssh/cnpl.d/*.conf' > "$HOME/.ssh/config"
    fi
    ;;
  proxy)
    root
    case $(role) in admin|dns|dns02|nexus|harbor|gitlab) ;; *) die '该角色不允许配置公网代理';; esac
    put "$CNPL_ROOT/config/proxy.sh" /etc/profile.d/cnpl-proxy.sh
    # 通过 config-manager 修改 main，保留原有其他配置。
    need dnf
    if dnf config-manager --help >/dev/null 2>&1; then
        dnf config-manager --save --setopt=proxy=http://192.168.9.10:7890 --setopt=sslverify=True --setopt=gpgcheck=True
    else
        # 插件尚未安装，仅本次用命令参数引导，安装后重跑本入口持久化。
        printf 'DNF 插件尚未安装：后续引导命令必须显式指定代理。\n'
    fi
    ;;
  lock-ssh)
    root
    # 首次指纹核验和 ssh-copy-id 必须已完成。第二个会话验证由操作人执行。
    [[ ${CNPL_SSH_KEY_VERIFIED:-} == yes ]] || die '先验证新公钥会话，再设 CNPL_SSH_KEY_VERIFIED=yes'
    case $(role) in
      admin) users='AllowUsers ops@192.168.9.200'; source_ip=192.168.9.200;;
      gitlab) users='AllowUsers ops@192.168.9.15 git@192.168.9.15 git@192.168.9.160'; source_ip=192.168.9.15;;
      backup) users='AllowUsers ops@192.168.9.15 bk_harbor@192.168.9.12 bk_gitlab@192.168.9.13 bk_nexus@192.168.9.14 bk_admin@192.168.9.15 bk_dns@192.168.9.11 bk_dns02@192.168.9.17'; source_ip=192.168.9.15;;
      *) host_ip "$(role)" >/dev/null; users='AllowUsers ops@192.168.9.15'; source_ip=192.168.9.15;;
    esac
    put "$CNPL_ROOT/config/sshd-auth.conf" /etc/ssh/sshd_config.d/00-cnpl-auth.conf
    temp=$(mktemp); trap 'rm -f "$temp"' EXIT
    printf '%s\n' "$users" > "$temp"; put "$temp" /etc/ssh/sshd_config.d/05-cnpl-users.conf
    sshd -t
    rich_rule "rule family=\"ipv4\" source address=\"$source_ip/32\" port port=\"22\" protocol=\"tcp\" accept"
    if [[ $(role) != admin ]]; then rich_rule 'rule priority="-300" family="ipv4" source address="192.168.9.200/32" drop'; fi
    for service in $(firewall-cmd --permanent --zone=public --list-services); do
      case $service in ssh|cockpit|dhcpv6-client) firewall-cmd --permanent --zone=public --remove-service="$service";; *) die "存在未知全网 service $service，先人工核对";; esac
    done
    firewall-cmd --check-config; firewall-cmd --reload; systemctl reload sshd
    ;;
  proxy-check)
    root; source /etc/profile.d/cnpl-proxy.sh
    response=$(curl --fail --silent --show-error --connect-timeout 5 --max-time 30 --output /dev/null --write-out '%{http_code} %{remote_ip}' https://www.google.com/generate_204)
    [[ $response == '204 192.168.9.10' ]] || die '代理路径或 Google 状态不符合要求'
    printf 'PASS Google HTTP=204 proxy=192.168.9.10\n'
    ;;
  *) die '用法：03-management.sh import-public|admin-tools|ssh-client|proxy|lock-ssh|proxy-check';;
esac
result
