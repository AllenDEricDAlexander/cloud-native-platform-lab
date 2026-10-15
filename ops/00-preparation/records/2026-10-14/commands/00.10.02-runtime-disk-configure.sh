#!/usr/bin/env bash
set -euo pipefail
# One-time initialization for the user-confirmed rocky10-base /dev/sdb.
install -d -m 0700 /root/lab-evidence/phase00
(
set -euxo pipefail
trap 'LAB_STEP_RC=$?; printf "step_exit=%s\n" "$LAB_STEP_RC"' EXIT
date -Is
dnf install -y parted xfsprogs
test "$(hostnamectl --static)" = rocky10-base
test "$(systemctl is-enabled containerd || true)" = masked
test "$(blockdev --getsize64 /dev/sdb)" -eq 107374182400
test "$(lsblk -nrpo NAME /dev/sdb | wc -l)" -eq 1
LAB_DISK_SIGNATURES=$(wipefs --no-act --noheadings --output TYPE /dev/sdb)
test -z "$LAB_DISK_SIGNATURES"
test -z "$(lsblk -nro MOUNTPOINTS /dev/sdb | tr -d '[:space:]')"
test ! -L /var/lib/containerd
mkdir -p /var/lib/containerd
if mountpoint -q /var/lib/containerd; then exit 1; fi
test -z "$(find /var/lib/containerd -mindepth 1 -maxdepth 1 -print -quit)"
test -z "$(awk '$0 !~ /^[[:space:]]*#/ && $2 == "/var/lib/containerd" {print}' /etc/fstab)"

parted -s -a optimal /dev/sdb mklabel gpt mkpart containerd xfs 1MiB 100%
partprobe /dev/sdb
udevadm settle
mkfs.xfs -L containerd /dev/sdb1

LAB_CONTAINERD_UUID=$(blkid -s UUID -o value /dev/sdb1)
test -n "$LAB_CONTAINERD_UUID"
cp -a /etc/fstab "/etc/fstab.phase00.$(date +%Y%m%d%H%M%S).bak"
printf 'UUID=%s /var/lib/containerd xfs defaults,nodev,nosuid 0 0\n' "$LAB_CONTAINERD_UUID" >> /etc/fstab
systemctl daemon-reload
mount /var/lib/containerd
test "$(findmnt -rn -M /var/lib/containerd -o UUID)" = "$LAB_CONTAINERD_UUID"
chmod 0700 /var/lib/containerd
restorecon -RFv /var/lib/containerd
findmnt --verify --verbose
findmnt -M /var/lib/containerd
xfs_info /var/lib/containerd
ls -Zd /var/lib/containerd
blkid /dev/sdb1
getenforce
firewall-cmd --state
) 2>&1 | tee -a /root/lab-evidence/phase00/00.10.02-runtime-disk-configure.txt
