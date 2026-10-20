#!/usr/bin/env bash
# 只读整盘检查；无分区/格式化命令，也不依赖 jq 或自定义 Python。
set -euo pipefail
export LC_ALL=C
fail() { printf '磁盘预检失败：%s\n' "$*" >&2; exit 1; }
[[ $# == 3 || $# == 4 ]] || fail '需要 by-id、字节容量、UUID 和可选挂载点'
disk=$1 size=$2 expected=$3 mount=${4:-/var/lib/containerd}
[[ $disk =~ ^/dev/disk/by-id/[A-Za-z0-9_.:+-]+$ && ! $disk =~ -part[0-9]+$ ]] || fail '必须指定整盘 by-id'
[[ $size =~ ^[0-9]+$ && $size -gt 0 ]] || fail '非法容量'
[[ $expected == - || $expected =~ ^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$ ]] || fail '非法 UUID'
case $mount in /var/lib/containerd|/srv/nexus|/data|/var/opt/gitlab|/srv/build|/srv/backup) ;; *) fail '不允许的挂载点';; esac
[[ -b $disk ]] || fail '设备不存在或不是块设备'
real=$(readlink -f "$disk")
[[ $real =~ ^/dev/[A-Za-z0-9_./-]+$ ]] || fail '异常的实际设备路径'
[[ $(lsblk -bdn -o SIZE "$real" | xargs) == "$size" ]] || fail '整盘容量不符'
mapfile -t types < <(lsblk -nr -o TYPE "$real")
[[ ${types[0]:-} == disk ]] || fail '对象不是整盘'
signatures=$(wipefs --no-act --noheadings --output TYPE "$real")
mounted=$(lsblk -nr -o MOUNTPOINTS "$real" | sed '/^[[:space:]]*$/d')
raw=false reusable=false is_mounted=false
if [[ ${#types[@]} == 1 && -z $signatures && -z $mounted && -z $(lsblk -dn -o FSTYPE,UUID "$real" | xargs) ]]; then
    raw=true
elif [[ ${#types[@]} == 2 && ${types[1]} == part && $expected != - ]]; then
    mapfile -t devices < <(lsblk -nrp -o PATH "$real")
    part=${devices[1]}
    [[ $(lsblk -dn -o FSTYPE "$part" | xargs) == xfs ]] || fail '已有分区不是 XFS'
    [[ $(lsblk -dn -o UUID "$part" | xargs) == "$expected" ]] || fail '已有文件系统 UUID 与记录不符'
    if [[ -n $mounted ]]; then
        while IFS= read -r target; do [[ $target == "$mount" ]] || fail '设备已被其他挂载点使用'; done <<< "$mounted"
        is_mounted=true
    fi
    reusable=true
else
    fail '设备有未知签名/分区/使用者，停止处理'
fi
printf '{"raw":%s,"reusable":%s,"mounted":%s,"by_id":"%s","path":"%s","partition":"%s-part1","uuid":"%s"}\n' "$raw" "$reusable" "$is_mounted" "$disk" "$real" "$disk" "$expected"
