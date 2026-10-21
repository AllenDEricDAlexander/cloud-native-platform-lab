#!/usr/bin/env bash
# Linux 只读检查；不清签名、不分区、不格式化。03.02 创建 OSD 前再次执行。
set -euo pipefail
set +x
device=${1:?稳定 ID 必填}; bytes=${2:?精确字节数必填}
[[ $device =~ ^/dev/disk/by-id/[a-zA-Z0-9_.:+-]+$ && $device != *-part[0-9]* ]] || exit 1
[[ $bytes =~ ^[1-9][0-9]*$ && -b $device && -L $device ]] || exit 1
target=$(readlink -f -- "$device")
[[ $(lsblk -bdno TYPE "$target") == disk ]] || exit 1
[[ $(blockdev --getsize64 "$target") == "$bytes" ]] || exit 1
tree=$(lsblk -bJ -o PATH,TYPE,FSTYPE,UUID,MOUNTPOINTS "$target")
jq -e '.blockdevices|length==1 and all(.[]; .type=="disk" and (.fstype==null or .fstype=="") and (.uuid==null or .uuid=="") and ((.children // [])|length==0) and all(.mountpoints[]?; .==null))' <<< "$tree" >/dev/null || exit 1
[[ -z $(wipefs --no-act --noheadings --output TYPE "$target") ]] || exit 1
if pvs --noheadings -o pv_name | awk '{$1=$1; print}' | grep -Fxq "$target"; then exit 1; fi
# device-mapper、挂载和 holder 不能只靠 FSTYPE 判定。
[[ -z $(find "/sys/class/block/$(basename "$target")/holders" -mindepth 1 -maxdepth 1 -print) ]] || exit 1
if findmnt -rn -S "$target" >/dev/null; then exit 1; fi
printf 'PASS 空整盘 %s bytes=%s\n' "$device" "$bytes"
