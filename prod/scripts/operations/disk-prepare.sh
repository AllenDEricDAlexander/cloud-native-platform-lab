#!/usr/bin/env bash
source "$(dirname "$0")/../lib/common.sh"
root; need jq
file=${2:?需要该主机的正式磁盘 JSON}
[[ -f $file && ! -L $file ]] || die '磁盘输入不存在或是符号链接'
disk=$(jq -er '.disk' "$file"); uuid=$(jq -er '.uuid' "$file")
size=$(jq -er '.size_bytes' "$file"); mount=$(jq -er '.mount' "$file")
read -r planned_size planned_mount < <(awk -v host="$(role)" '$1==host {print $2" "$3}' "$CNPL_ROOT/inputs/data-disks.tsv")
[[ $planned_size =~ ^[1-9][0-9]*$ && $planned_mount == /* ]] || die '该角色没有正式服务数据盘配置'
[[ $(jq -er .host "$file") == "$(role)" && $size == "$planned_size" && $mount == "$planned_mount" ]] || die '磁盘输入与当前 VM 角色不符'
state=$(bash "$CNPL_ROOT/ansible/files/disk-state.sh" "$disk" "$size" "$uuid" "$mount")
if [[ ${1:-} == inspect ]]; then printf '%s\n' "$state"; exit; fi
[[ ${1:-} == apply ]] || die '用法：disk-prepare.sh inspect|apply 正式磁盘JSON'
[[ $(findmnt -nr -M "$mount" -o UUID || true) == '' || $(findmnt -nr -M "$mount" -o UUID) == "$uuid" ]] || die '挂载点已被其他卷使用'
if ! mountpoint -q "$mount" && [[ -d $mount ]]; then [[ -z $(find "$mount" -mindepth 1 -maxdepth 1 -print -quit) ]] || die '未挂载目录已有数据，停止'; fi
if jq -e '.raw' <<< "$state" >/dev/null; then
    jq -e '.initialize == true' "$file" >/dev/null || die '未批准初始化空盘'
    parted --script "$disk" mklabel gpt mkpart primary xfs 1MiB 100%
    udevadm settle
    [[ -b ${disk}-part1 ]] || die '稳定分区路径未出现'
    mkfs.xfs -m "uuid=$uuid" "${disk}-part1"
    CNPL_CHANGED=1
fi
bash "$CNPL_ROOT/ansible/files/disk-state.sh" "$disk" "$size" "$uuid" "$mount" | jq -e '.reusable' >/dev/null
install -d -m 0755 "$mount"
entry="UUID=$uuid $mount xfs defaults,nodev,nosuid 0 0"
if ! grep -Fxq "$entry" /etc/fstab; then
    [[ -z $(awk -v point="$mount" '$1!~/^#/ && $2==point {print}' /etc/fstab) ]] || die 'fstab 已有不同挂载记录，先核对'
    cp -a /etc/fstab "/etc/fstab.cnpl-$(date -u +%Y%m%dT%H%M%S)-$$"
    printf '%s\n' "$entry" >> /etc/fstab; CNPL_CHANGED=1
fi
findmnt --verify
if ! mountpoint -q "$mount"; then mount "$mount"; CNPL_CHANGED=1; fi
findmnt -nr -M "$mount" -o UUID,FSTYPE,OPTIONS
result
