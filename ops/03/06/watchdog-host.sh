#!/usr/bin/env bash
# 先安排独立于管理端连接的恢复任务，再允许注入故障；不擦除设备。
set -euo pipefail
set +x
umask 077
adm=$1 image=$2 fsid=$3 run=$4 osd=$5 seconds=$6 mode=$7
[[ $EUID == 0 && $(hostname -s) == storage01 && $(getenforce) == Enforcing ]] || exit 1
systemctl is-active --quiet firewalld || exit 1
[[ $osd =~ ^[0-9]+$ && $seconds =~ ^[0-9]+$ && $seconds -le 180 && $run =~ ^[a-z][a-z0-9-]{2,19}$ ]] || exit 1
unit=cnpl03-$run-osd-$osd
private=/var/lib/cnpl03/$fsid
install -d -m 0700 "$private"
script=$private/$unit.sh
if [[ $mode == arm ]]; then
    if systemctl is-active --quiet "$unit.timer"; then echo '已有待恢复任务，先执行 recover' >&2; exit 1; fi
    {
        printf '#!/usr/bin/env bash\nset -u\n'
        printf '%q ' "$adm" --image "$image" shell --fsid "$fsid" -- ceph orch daemon start "osd.$osd"; printf '\n'
        printf '%q ' "$adm" --image "$image" shell --fsid "$fsid" -- ceph osd in "$osd"; printf '\n'
    } > "$script"
    chmod 0700 "$script"
    systemd-run --unit "$unit" --on-active="${seconds}s" /bin/bash "$script"
    systemctl is-active --quiet "$unit.timer" || exit 1
    printf 'PASS watchdog 已安排，期限 %ss\n' "$seconds"
elif [[ $mode == disarm ]]; then
    systemctl stop "$unit.timer" || exit 1
    systemctl reset-failed "$unit.service" 2>/dev/null || true
    rm -f "$script"
else exit 2; fi
