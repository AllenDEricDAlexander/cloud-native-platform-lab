#!/usr/bin/env bash
# 在 storage01 将恢复必需材料写入独立 restic 仓库；不输出 keyring。
set -euo pipefail
set +x
umask 077
adm=$1 image=$2 fsid=$3 repository=$4 password_file=$5
[[ $EUID == 0 && $(hostname -s) == storage01 && -f $password_file && ! -L $password_file ]] || exit 1
[[ $(stat -c '%a' "$password_file") == 600 || $(stat -c '%a' "$password_file") == 400 ]] || exit 1
[[ $(stat -c '%u' "$password_file") == 0 ]] || exit 1
work=$(mktemp -d /var/tmp/cnpl03-recovery.XXXXXX)
trap 'rm -rf -- "$work"' EXIT
c() { "$adm" --image "$image" shell --fsid "$fsid" -- ceph "$@"; }
[[ $(c fsid) == "$fsid" ]] || exit 1
c mon dump --format json > "$work/mon.json"
c osd getcrushmap -o - > "$work/crush.bin"
c osd pool ls detail --format json > "$work/pools.json"
c orch ls --export > "$work/services.yaml"
c orch host ls --format json > "$work/hosts.json"
c config dump --format json > "$work/config.json"
c config generate-minimal-conf > "$work/ceph.conf"
c auth export > "$work/ceph.keyring"
restic --repo "$repository" --password-file "$password_file" backup --tag "cnpl03-$fsid" "$work" /etc/ceph
restic --repo "$repository" --password-file "$password_file" check
printf 'PASS 已写入加密仓库并完成 restic check；恢复读取另行演练。\n'
