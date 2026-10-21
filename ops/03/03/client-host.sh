#!/usr/bin/env bash
# 仅对本次新建的测试 RBD/子卷映射、格式化和挂载；不接收任意设备名。
set -euo pipefail
set +x
umask 077
adm=$1 image=$2 fsid=$3 run=$4 pool=$5 fs=$6 action=$7
[[ $EUID == 0 && $(hostname -s) == storage01 && $(getenforce) == Enforcing ]] || exit 1
systemctl is-active --quiet firewalld || exit 1
"$adm" --image "$image" shell --fsid "$fsid" -- bash -s -- "$run" "$pool" "$fs" "$action" <<'CLIENT'
set -euo pipefail
set +x
umask 077
run=$1 pool=$2 fs=$3 action=$4
[[ $run =~ ^[a-z][a-z0-9-]{2,19}$ && $pool == "cnpl03-$run-rbd" && $fs == "cnpl03-$run-fs" ]] || exit 1
client=cnpl03-$run-probe
work=$(mktemp -d)
mapped=''; created=false; authorized=false; subvolume=false
cleanup() {
    rc=$?; trap - EXIT
    if mountpoint -q "$work/a"; then umount "$work/a" || rc=1; fi
    if mountpoint -q "$work/b"; then umount "$work/b" || rc=1; fi
    if [[ -n $mapped ]]; then rbd device unmap "$mapped" || rc=1; fi
    if [[ $created == true && $rc == 0 ]]; then rbd rm "$pool/probe-$run" || rc=1; fi
    if [[ $subvolume == true && $rc == 0 ]]; then ceph fs subvolume rm "$fs" "probe-$run" || rc=1; fi
    if [[ $authorized == true && $rc == 0 ]]; then ceph auth del "client.$client" || rc=1; fi
    rm -rf -- "$work"
    exit "$rc"
}
trap cleanup EXIT
mkdir "$work/a" "$work/b"
if ceph auth ls --format json | jq -e --arg name "client.$client" 'any(.auth_dump[];.entity==$name)' >/dev/null; then echo '已有测试身份，先调查原失败批次' >&2; exit 1; fi
if [[ $action == rbd-test ]]; then
    if rbd ls --pool "$pool" --format json | jq -e --arg name "probe-$run" 'index($name)!=null' >/dev/null; then exit 1; fi
    ceph auth get-or-create "client.$client" mon 'profile rbd' osd "profile rbd pool=$pool" > "$work/client.keyring"
    authorized=true
    rbd --id "$client" --keyring "$work/client.keyring" create "$pool/probe-$run" --size 32M --image-feature layering
    created=true
    mapped=$(rbd --id "$client" --keyring "$work/client.keyring" device map "$pool/probe-$run")
    [[ -b $mapped && $mapped == /dev/rbd* ]] || exit 1
    rbd device list --format json | jq -e --arg pool "$pool" --arg name "probe-$run" --arg device "$mapped" 'any(.[];.pool==$pool and (.name // .image)==$name and .device==$device)' >/dev/null || exit 1
    mkfs.ext4 -q "$mapped"
    mount "$mapped" "$work/a"
    printf '%s\n' "$run:sequence:000001" > "$work/a/probe"
    sync
    checksum=$(sha256sum "$work/a/probe" | awk '{print $1}')
    umount "$work/a"; mount "$mapped" "$work/a"
    [[ $(sha256sum "$work/a/probe" | awk '{print $1}') == "$checksum" ]] || exit 1
    if rbd --id "$client" --keyring "$work/client.keyring" ls --pool "$fs-data" 2> "$work/denied"; then exit 1; fi
    grep -Eqi 'permission denied|operation not permitted' "$work/denied" || exit 1
else
    if ceph fs subvolume ls "$fs" --format json | jq -e --arg name "probe-$run" 'any(.[];.name==$name)' >/dev/null; then exit 1; fi
    ceph fs subvolume create "$fs" "probe-$run" --size 33554432
    subvolume=true
    path=$(ceph fs subvolume getpath "$fs" "probe-$run")
    ceph fs authorize "$fs" "client.$client" "$path" rw > "$work/client.keyring"
    authorized=true
    ceph auth get-key "client.$client" > "$work/secret"
    mons=$(ceph mon dump --format json | jq -r '[.mons[].public_addrs.addrvec[]|select(.type=="v2")|.addr|sub("/.*$";"")]|join(",")')
    for mount_dir in a b; do mount -t ceph "$mons:$path" "$work/$mount_dir" -o "name=$client,secretfile=$work/secret,fs=$fs"; done
    printf '%s\n' "$run:sequence:000001" > "$work/a/probe"
    sync; cmp "$work/a/probe" "$work/b/probe"
    chmod 0600 "$work/a/probe"
    [[ $(stat -c %a "$work/b/probe") == 600 ]] || exit 1
fi
printf 'PASS %s 重挂载/共享读写及校验\n' "$action"
CLIENT
