#!/usr/bin/env bash
source "$(dirname "$0")/../lib/common.sh"
root
repos=(baseos appstream crb epel docker-ce-stable kubernetes gitlab-ce)
keys=(rocky10 epel10 docker kubernetes gitlab cnpl-metadata)
verify_keys() {
    local directory=$1 key actual expected
    for key in "${keys[@]}"; do
        [[ -s $directory/$key.asc && -s $directory/$key.fpr ]] || die "缺少 $key 的已核实公钥与指纹记录"
        actual=$(gpg --batch --show-keys --with-colons "$directory/$key.asc" 2>/dev/null | awk -F: '$1=="pub" {want=1} $1=="fpr" && want {print $10;want=0}' | sort -u)
        expected=$(sort -u "$directory/$key.fpr")
        [[ -n $actual && $actual == "$expected" ]] || die "$key 公钥指纹不符"
    done
}
capacity() {
    local repo bytes
    RPM_BYTES=0
    for repo in "${repos[@]}"; do
        bytes=$(dnf -y -q --setopt=reposdir=/etc/cnpl/upstream-repos --setopt=proxy=http://192.168.9.10:7890 --disablerepo='*' --enablerepo="$repo" --showduplicates repoquery --available --qf '%{downloadsize}' -a | awk 'NF {if($0!~/^[0-9]+$/)exit 1;sum+=$1} END {printf "%.0f",sum}') || die "无法评估 $repo 完整下载大小"
        [[ $bytes =~ ^[0-9]+$ && $bytes -gt 0 ]] || die "仓库 $repo 没有有效容量结果"
        printf '%s RPM_BYTES=%s\n' "$repo" "$bytes"
        RPM_BYTES=$((RPM_BYTES+bytes))
    done
    printf 'TOTAL_RPM_BYTES=%s\n' "$RPM_BYTES"
    df -B1 --output=size,avail /srv/nexus
}
case "${1:-}" in
  capacity)
    expect_host nexus
    capacity
    ;;
  upstream)
    expect_host nexus; source /etc/profile.d/cnpl-proxy.sh
    mountpoint -q /srv/nexus || die '先准备 nexus 数据盘'
    dnf -y --setopt=proxy=http://192.168.9.10:7890 install nginx dnf-plugins-core createrepo_c gnupg2 jq epel-release
    dnf config-manager --set-enabled crb
    install -d -m 0755 /srv/nexus/repos/releases /srv/nexus/repos/keys /etc/cnpl/upstream-repos
    curl --fail --silent --show-error --location https://download.docker.com/linux/rhel/docker-ce.repo -o /etc/cnpl/upstream-repos/docker-ce.repo
    cat > /etc/cnpl/upstream-repos/kubernetes.repo <<'EOF'
[kubernetes]
name=Kubernetes v1.36 RPM
baseurl=https://pkgs.k8s.io/core:/stable:/v1.36/rpm/
enabled=1
gpgcheck=1
repo_gpgcheck=1
gpgkey=https://pkgs.k8s.io/core:/stable:/v1.36/rpm/repodata/repomd.xml.key
EOF
    cat > /etc/cnpl/upstream-repos/gitlab-ce.repo <<'EOF'
[gitlab-ce]
name=GitLab CE EL10
baseurl=https://packages.gitlab.com/gitlab/gitlab-ce/el/10/$basearch
enabled=1
gpgcheck=1
repo_gpgcheck=1
sslverify=1
gpgkey=https://packages.gitlab.com/gitlab/gitlab-ce/gpgkey
EOF
    for file in /etc/yum.repos.d/rocky*.repo /etc/yum.repos.d/epel*.repo; do
        [[ -e $file ]] || continue
        destination=/etc/cnpl/upstream-repos/$(basename "$file")
        if [[ -e $destination ]]; then cmp -s "$file" "$destination" || die '原始上游源与留档不同，先审查'; else cp -a "$file" "$destination"; fi
    done
    dnf --setopt=reposdir=/etc/cnpl/upstream-repos --setopt=proxy=http://192.168.9.10:7890 repolist
    ;;
  keys)
    expect_host nexus; source /etc/profile.d/cnpl-proxy.sh
    install -d -m 0755 /srv/nexus/repos/keys
    cp /etc/pki/rpm-gpg/RPM-GPG-KEY-Rocky-10 /srv/nexus/repos/keys/rocky10.asc
    cp /etc/pki/rpm-gpg/RPM-GPG-KEY-EPEL-10 /srv/nexus/repos/keys/epel10.asc
    curl --fail --silent --show-error --location https://download.docker.com/linux/rhel/gpg -o /srv/nexus/repos/keys/docker.asc
    curl --fail --silent --show-error --location https://pkgs.k8s.io/core:/stable:/v1.36/rpm/repodata/repomd.xml.key -o /srv/nexus/repos/keys/kubernetes.asc
    curl --fail --silent --show-error --location https://packages.gitlab.com/gitlab/gitlab-ce/gpgkey -o /srv/nexus/repos/keys/gitlab.asc
    for key in rocky10 epel10 docker kubernetes gitlab; do
        file=/srv/nexus/repos/keys/$key.fpr
        gpg --batch --show-keys --with-fingerprint "/srv/nexus/repos/keys/$key.asc"
        if [[ ! -e $file ]]; then
            read -r -p "$key 已从官方发布核实的完整指纹（多个用空格分隔）: " expected
            read -ra fingerprints <<< "$expected"
            for fingerprint in "${fingerprints[@]}"; do
                [[ $fingerprint =~ ^([0-9A-F]{40}|[0-9A-F]{64})$ ]] || die '指纹格式错误'
            done
            printf '%s\n' "${fingerprints[@]}" | sort -u > "$file"
        fi
    done
    ;;
  signing-key)
    expect_host nexus
    [[ -t 0 ]] || die '密钥创建/解锁需要交互终端'
    export GPG_TTY=$(tty)
    install -d -m 0700 /etc/cnpl/rpm-gnupg
    export GNUPGHOME=/etc/cnpl/rpm-gnupg
    if [[ -s /srv/nexus/repos/keys/cnpl-metadata.fpr ]]; then
        signer=$(cat /srv/nexus/repos/keys/cnpl-metadata.fpr)
        gpg --batch --list-secret-keys "$signer" >/dev/null || die '记录的签名私钥缺失'
    else
        if gpg --batch --list-secret-keys --with-colons 2>/dev/null | grep -q '^sec:'; then die '已有私钥但缺少本项目指纹记录，先人工核对'; fi
        gpg --full-generate-key
        gpg --list-secret-keys --with-colons
        read -r -p '本次 CNPL 元数据签名主钥完整指纹: ' signer
        [[ $signer =~ ^[0-9A-F]{40}$ ]] || die '指纹不合法'
        gpg --batch --list-secret-keys "$signer" >/dev/null
        printf '%s\n' "$signer" > /srv/nexus/repos/keys/cnpl-metadata.fpr
    fi
    gpg --armor --export "$signer" > /srv/nexus/repos/keys/cnpl-metadata.asc
    verify_keys /srv/nexus/repos/keys
    chmod 0644 /srv/nexus/repos/keys/*
    for key in "${keys[@]}"; do rpm --import "/srv/nexus/repos/keys/$key.asc"; done
    ;;
  mirror)
    expect_host nexus; source /etc/profile.d/cnpl-proxy.sh
    [[ -t 0 ]] || die '元数据签名需要人工解锁，请使用交互终端'
    export GPG_TTY=$(tty)
    batch=${2:?需要唯一批次名}; minimum=${3:?需要经容量评估的最小剩余 GiB}
    [[ $batch =~ ^[0-9]{8}T[0-9]{6}Z$ && $minimum =~ ^[1-9][0-9]*$ ]] || die '批次或空间参数不合法'
    capacity
    available=$(df -B1 --output=avail /srv/nexus | tail -n1 | xargs)
    required=$((RPM_BYTES+RPM_BYTES/5+minimum*1024*1024*1024))
    [[ $available -gt $required ]] || die '完整包集合、元数据余量与应用保留空间不足，停止并先调整预算，不删除在用快照'
    stage=/srv/nexus/repos/releases/$batch
    [[ ! -e $stage ]] || die '该快照已存在，不能覆盖或复用半成品'
    verify_keys /srv/nexus/repos/keys
    install -d -m 0755 "$stage"
    options=(); for repo in "${repos[@]}"; do options+=("--repoid=$repo"); done
    dnf -y --setopt=reposdir=/etc/cnpl/upstream-repos --setopt=proxy=http://192.168.9.10:7890 reposync "${options[@]}" --download-metadata --download-path="$stage" --gpgcheck
    signer=$(cat /srv/nexus/repos/keys/cnpl-metadata.fpr)
    for repo in "${repos[@]}"; do
        metadata=$stage/$repo/repodata/repomd.xml
        [[ -s $metadata ]] || die "缺少 $repo 元数据"
        [[ ! -e $metadata.asc ]] || mv "$metadata.asc" "$metadata.asc.upstream"
        GNUPGHOME=/etc/cnpl/rpm-gnupg gpg --local-user "$signer" --armor --detach-sign "$metadata"
        GNUPGHOME=/etc/cnpl/rpm-gnupg gpg --verify "$metadata.asc" "$metadata"
    done
    [[ ! -e /srv/nexus/repos/current || -L /srv/nexus/repos/current ]] || die 'current 不是本项目符号链接'
    [[ ! -e /srv/nexus/repos/current.next && ! -L /srv/nexus/repos/current.next ]] || die '遗留 current.next，先核对'
    ln -s "$stage" /srv/nexus/repos/current.next
    mv -Tf /srv/nexus/repos/current.next /srv/nexus/repos/current
    printf 'PASS 已发布完整签名快照 %s\n' "$batch"
    ;;
  serve)
    expect_host nexus
    [[ -L /srv/nexus/repos/current ]] || die '先完成镜像、签名与发布'
    put "$CNPL_ROOT/config/nginx.conf" /etc/nginx/nginx.conf
    put "$CNPL_ROOT/config/cnpl-rpm.conf" /etc/nginx/conf.d/cnpl-rpm.conf
    fcontext '/srv/nexus/repos(/.*)?' httpd_sys_content_t
    fcontext '/etc/cnpl/tls(/.*)?' cert_t
    restorecon -RF /srv/nexus/repos /etc/cnpl/tls
    vm_ipset
    rich_rule 'rule family="ipv4" source ipset="cnpl-vms" port port="443" protocol="tcp" accept'
    firewall-cmd --check-config; firewall-cmd --reload
    nginx -t; systemctl enable --now nginx
    [[ $CNPL_CHANGED != 1 ]] || systemctl reload nginx
    ;;
  client)
    keydir=$CNPL_INPUTS/rpm-keys
    verify_keys "$keydir"
    install -d -m 0755 /etc/pki/rpm-gpg/cnpl /etc/yum.repos.d/cnpl-disabled
    for key in "${keys[@]}"; do put "$keydir/$key.asc" "/etc/pki/rpm-gpg/cnpl/$key.asc"; rpm --import "$keydir/$key.asc"; done
    for file in /etc/yum.repos.d/*.repo; do
        [[ -e $file ]] || continue
        name=$(basename "$file"); [[ $name != cnpl-private.repo ]] || continue
        case $name in rocky*.repo|epel*.repo|cnpl-media.repo|docker-ce.repo|kubernetes.repo|gitlab-ce.repo) ;; *) die "未知源文件 $name，停止归档";; esac
        [[ ! -e /etc/yum.repos.d/cnpl-disabled/$name ]] || die '归档重名，先核对'
        mv "$file" /etc/yum.repos.d/cnpl-disabled/; CNPL_CHANGED=1
    done
    put "$CNPL_ROOT/config/cnpl-private.repo" /etc/yum.repos.d/cnpl-private.repo
    dnf -y --disablerepo='*' --enablerepo='cnpl-*' makecache
    private_install jq dnf-plugins-core 'dnf-command(versionlock)'
    ;;
  verify)
    for path in baseos appstream crb epel docker-ce-stable kubernetes gitlab-ce; do
        curl --fail --silent --show-error --noproxy '*' "https://rpm.svc.internal.egon.top/$path/repodata/repomd.xml" -o /dev/null
    done
    dnf -y --disablerepo='*' --enablerepo='cnpl-*' makecache
    printf 'PASS 七个内网 RPM 仓库 HTTPS 与签名元数据\n'
    ;;
  *) die '用法：05-rpm.sh upstream|keys|signing-key|capacity|mirror 批次 同步后预留GiB|serve|client|verify';;
esac
result
