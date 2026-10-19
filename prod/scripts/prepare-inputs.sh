#!/usr/bin/env bash
# 在 admin 逐阶段生成正式输入；不包含样例值，不修改远端主机。
source "$(dirname "$0")/lib/common.sh"
[[ $(role) == admin ]] || die '仅在 admin 执行'
CNPL_INPUTS=${CNPL_INPUTS_ADMIN:-/srv/cnpl/inputs}
install -d -m 0750 "$CNPL_INPUTS"
choose_package() {
    local package=$1 pick
    mapfile -t candidates < <(dnf -y -q --showduplicates --disablerepo='*' --enablerepo='cnpl-*' repoquery --archlist=x86_64,noarch --qf '%{name}-%{epoch}:%{version}-%{release}.%{arch}' "$package" | sort -u)
    [[ ${#candidates[@]} -gt 0 ]] || die "私服没有 $package"
    printf '可选 %s：\n' "$package" >&2
    printf '  %s\n' "${candidates[@]}" >&2
    read -r -p '粘贴其中一个完整 NEVRA: ' pick
    printf '%s\n' "${candidates[@]}" | grep -Fxq "$pick" || die '选择值不在私服查询结果中'
    [[ $pick =~ ^[A-Za-z0-9_.+-]+-[0-9]+:[A-Za-z0-9_.+~]+-[A-Za-z0-9_.+~]+\.(x86_64|noarch)$ ]] || die 'NEVRA 格式不正确'
    SELECTED=$pick
}
record_disk() {
    local host=$1 bytes=$2 mount=$3 disk uuid answer osd='[]'
    read -r -p "$host 的 $mount 整盘 by-id: " disk
    [[ $disk =~ ^/dev/disk/by-id/[A-Za-z0-9_.:+-]+$ && ! $disk =~ -part[0-9]+$ ]] || die '必须是整盘稳定 ID'
    read -r -p '已有 XFS 填实际 UUID；新空盘直接回车生成一次: ' uuid
    answer=false
    if [[ -z $uuid ]]; then
        uuid=$(cat /proc/sys/kernel/random/uuid)
        read -r -p "已人工核对 $host 的新空盘，允许初始化请输入 $host: " answer
        [[ $answer == "$host" ]] || die '未确认新盘'
        answer=true
    fi
    [[ $uuid =~ ^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$ ]] || die 'UUID 不合法'
    if [[ $host == storage0[123] ]]; then
        read -r -p "$host 的 1 TiB 原始 OSD 整盘 by-id: " osd
        [[ $osd =~ ^/dev/disk/by-id/[A-Za-z0-9_.:+-]+$ && $osd != "$disk" && ! $osd =~ -part[0-9]+$ ]] || die 'OSD ID 不合法'
        osd=$(jq -nc --arg disk "$osd" '[$disk]')
    fi
    DISK_JSON=$(jq -nc --arg host "$host" --arg disk "$disk" --arg uuid "$uuid" --arg mount "$mount" --argjson size "$bytes" --argjson init "$answer" --argjson osd "$osd" '{host:$host,disk:$disk,runtime_disk:$disk,uuid:$uuid,runtime_uuid:$uuid,mount:$mount,size_bytes:$size,initialize:$init,osd_disks:$osd}')
}
case "${1:-}" in
  base)
    for file in hosts.ini ansible.cfg data-disks.tsv; do
        if [[ -e $CNPL_INPUTS/$file ]]; then cmp -s "$CNPL_ROOT/inputs/$file" "$CNPL_INPUTS/$file" || die "$file 已存在且不同，先人工核对";
        else install -m 0640 "$CNPL_ROOT/inputs/$file" "$CNPL_INPUTS/$file"; fi
    done
    ;;
  packages|admin-packages)
    need jq
    if [[ $1 == admin-packages ]]; then
        file=$CNPL_INPUTS/admin-tools.lock.json
        names=(ansible-core helm kubectl restic)
    else
        file=$CNPL_INPUTS/packages.lock.json
        names=(docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin container-selinux iptables-nft postgresql-server postgresql-contrib gitlab-ce)
    fi
    [[ ! -e $file ]] || die '正式版本锁已存在，按维护流程审查更新，不覆盖'
    json='{}'
    for package in "${names[@]}"; do
        choose_package "$package"
        json=$(jq --arg name "$package" --arg version "$SELECTED" '.+{($name):$version}' <<< "$json")
    done
    printf '%s\n' "$json" > "$file"; chmod 0640 "$file"
    ;;
  disk)
    need jq; host=${2:?需要角色名}; host_ip "$host" >/dev/null
    read -r size mount < <(awk -v host="$host" '$1==host {print $2" "$3}' "$CNPL_ROOT/inputs/data-disks.tsv")
    [[ $size =~ ^[1-9][0-9]*$ && $mount == /* ]] || die '该服务角色没有正式数据盘配置'
    install -d -m 0750 "$CNPL_INPUTS/disks"
    [[ ! -e $CNPL_INPUTS/disks/$host.json ]] || die '本机磁盘记录已存在，先核对，不重新生成 UUID'
    record_disk "$host" "$size" "$mount"
    printf '%s\n' "$DISK_JSON" > "$CNPL_INPUTS/disks/$host.json"
    ;;
  harbor)
    need jq; file=$CNPL_INPUTS/harbor.lock.json
    [[ ! -e $file ]] || die 'Harbor 安装物料锁已存在'
    read -r -p '官方 v2.15.4 online installer 已核实的 SHA-256: ' sha
    [[ $sha =~ ^[0-9a-f]{64}$ ]] || die '摘要必须为 64 位小写十六进制'
    jq -n --arg hash "$sha" '{version:"2.15.4",sha256:$hash}' > "$file"
    ;;
  nodes)
    need jq; need skopeo; file=$CNPL_INPUTS/k8s-bootstrap.yml
    [[ ! -e $file ]] || die '十节点正式输入已存在，不能重建 UUID 或覆盖版本'
    packages='{}'; nodes='{}'
    for package in containerd.io container-selinux kubeadm kubelet kubectl cri-tools kubernetes-cni; do
        choose_package "$package"; packages=$(jq --arg name "$package" --arg version "$SELECTED" '.+{($name):$version}' <<< "$packages")
    done
    pause=$(skopeo inspect --format '{{.Digest}}' docker://harbor.k8s.internal.egon.top/bootstrap/pause:3.10.2)
    busybox=$(skopeo inspect --format '{{.Digest}}' docker://harbor.k8s.internal.egon.top/bootstrap/busybox:1.38.0-1)
    [[ $pause =~ ^sha256:[0-9a-f]{64}$ && $busybox =~ ^sha256:[0-9a-f]{64}$ ]] || die 'Harbor 未提供有效摘要'
    for host in cp01 cp02 cp03 infra01 infra02 storage01 storage02 storage03 worker01 worker02; do
        record_disk "$host" 107374182400 /var/lib/containerd
        nodes=$(jq --arg name "$host" --argjson value "$DISK_JSON" '.+{($name):$value}' <<< "$nodes")
    done
    # JSON 是有效的 YAML；直接由 Ansible -e @文件读取，无模板和自定义 Python。
    jq -n --argjson packages "$packages" --argjson nodes "$nodes" --arg pause "harbor.k8s.internal.egon.top/bootstrap/pause@$pause" --arg smoke "harbor.k8s.internal.egon.top/bootstrap/busybox@$busybox" '{cnpl_runtime_packages:$packages,cnpl_nodes:$nodes,cnpl_pause_image:$pause,cnpl_smoke_image:$smoke}' > "$file"
    chmod 0640 "$file"
    ;;
  ntp-addresses)
    need dig
    dig +short ntp.aliyun.com A
    dig +short time.nju.edu.cn A
    file=$CNPL_INPUTS/ntp-upstream-ip.txt
    [[ ! -e $file ]] || die '已登记 NTP 上游地址，先审查更新，不覆盖'
    read -r -p '填写两台时间服务实际选用、已验证的上游 IPv4（空格分隔）: ' addresses
    read -ra entries <<< "$addresses"
    [[ ${#entries[@]} -ge 2 ]] || die '至少记录两个独立地址'
        for ip in "${entries[@]}"; do valid_ipv4 "$ip" || die '非法 IPv4 地址'; done
    unique=$(printf '%s\n' "${entries[@]}" | sort -u)
    [[ $(printf '%s\n' "$unique" | wc -l) -ge 2 ]] || die '上游 IP 必须至少两个且不重复'
    printf '%s\n' "$unique" > "$file"
    {
      while read -r ip; do printf 'server %s iburst\n' "$ip"; done < "$file"
      printf 'driftfile /var/lib/chrony/drift\nmakestep 1.0 3\nrtcsync\nallow 192.168.9.0/24\nlogdir /var/log/chrony\n'
    } > "$CNPL_INPUTS/chrony-server.conf"
    ;;
  *) die '用法：prepare-inputs.sh base|admin-packages|packages|disk 主机|harbor|nodes|ntp-addresses';;
esac
printf 'PASS 正式输入已保存，后续使用同一文件\n'
