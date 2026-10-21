#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077
adm=$1 image=$2 fsid=$3 mon_ip=$4
[[ $EUID == 0 && $(hostname -s) == storage01 ]] || exit 1
[[ $(getenforce) == Enforcing ]] || exit 1
systemctl is-active --quiet firewalld containerd chronyd || exit 1
[[ $fsid =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || exit 1
if [[ -d /var/lib/ceph/$fsid ]]; then
    "$adm" --image "$image" shell --fsid "$fsid" -- ceph fsid | grep -Fx "$fsid"
    exit 0
fi
[[ ! -e /etc/ceph/ceph.conf ]] || { echo '已有 Ceph 配置，禁止重新引导' >&2; exit 1; }
if [[ -d /var/lib/ceph ]]; then
    [[ -z $(find /var/lib/ceph -mindepth 1 -maxdepth 1 -type d -name '*-*-*-*-*' -print) ]] || exit 1
fi
"$adm" --image "$image" bootstrap --fsid "$fsid" --mon-ip "$mon_ip" --skip-dashboard --skip-monitoring-stack --skip-firewalld --log-to-file
"$adm" --image "$image" shell --fsid "$fsid" -- ceph fsid | grep -Fx "$fsid"
