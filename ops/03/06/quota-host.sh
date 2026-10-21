#!/usr/bin/env bash
set -euo pipefail
set +x
adm=$1 image=$2 fsid=$3 run=$4
[[ $EUID == 0 && $(hostname -s) == storage01 ]] || exit 1
"$adm" --image "$image" shell --fsid "$fsid" -- bash -s -- "$run" <<'QUOTA'
set -euo pipefail
umask 077
run=$1; pool=cnpl03-$run-quota
work=$(mktemp -d); trap 'rm -rf -- "$work"' EXIT
if ceph osd pool ls --format json | jq -e --arg pool "$pool" 'index($pool)!=null' >/dev/null; then echo '配额用例池已存在，先处理原批次' >&2; exit 1; fi
ceph osd pool create "$pool" 8 8 replicated cnpl03-physical
ceph osd pool set "$pool" size 3
ceph osd pool set "$pool" min_size 2
ceph osd pool application enable "$pool" rados
ceph osd pool set-quota "$pool" max_bytes 16777216
dd if=/dev/zero of="$work/payload" bs=1M count=1 status=none
denied=false; written=0
# 总量不超过 24MiB，不能靠填满真实 OSD/Datastore 验证水位。
for i in $(seq 1 24); do
    if timeout 10 rados -p "$pool" put "probe-$i" "$work/payload" 2> "$work/error"; then written=$i; sleep 2
    else
        if grep -Eqi 'quota|no space|full' "$work/error"; then denied=true; break; fi
        cat "$work/error" >&2; exit 1
    fi
done
ceph health detail
ceph osd pool stats "$pool"
for i in $(seq 1 "$written"); do rados -p "$pool" rm "probe-$i"; done
[[ $denied == true ]] || { echo '有界写入内未观察到配额拒绝，不能判定通过' >&2; exit 1; }
printf 'PASS 专用池配额拒绝；真实 nearfull/full 水位未注入。\n'
QUOTA
