#!/usr/bin/env bash
# admin -> 单台已完成指纹核验与 ssh-copy-id 的 Rocky；只分发公开代码和公开输入。
source "$(dirname "$0")/../lib/common.sh"
[[ $(role) == admin && $(id -un) == ops ]] || die '在 admin 的 ops 会话执行'
host=${1:?需要当前已创建的 Rocky 主机名}
case $host in admin|openwrt) die '本入口只分发至其他 Rocky';; esac
ip=$(host_ip "$host")
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "ops@$ip" 'mkdir -p /home/ops/.local/share/cnpl-bundle /home/ops/.local/share/cnpl-inputs'
rsync -a --safe-links "$CNPL_ROOT/scripts" "$CNPL_ROOT/config" "$CNPL_ROOT/inputs" "$CNPL_ROOT/ansible" "ops@$ip:/home/ops/.local/share/cnpl-bundle/"
inputs=/srv/cnpl/inputs
for file in cnpl-root.crt chrony-server.conf ntp-upstream-ip.txt; do
    [[ ! -s $inputs/$file ]] || scp "$inputs/$file" "ops@$ip:/home/ops/.local/share/cnpl-inputs/"
done
if [[ -d $inputs/rpm-keys ]]; then rsync -a --safe-links "$inputs/rpm-keys" "ops@$ip:/home/ops/.local/share/cnpl-inputs/"; fi
if [[ -f $inputs/disks/$host.json ]]; then scp "$inputs/disks/$host.json" "ops@$ip:/home/ops/.local/share/cnpl-inputs/data-disk.json"; fi
printf 'PASS 已分发 %s 的公开材料，尚未运行远端安装\n' "$host"
