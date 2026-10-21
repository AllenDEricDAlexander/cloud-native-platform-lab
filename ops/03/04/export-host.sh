#!/usr/bin/env bash
# 运行事先核验 SHA 的官方 exporter；秘密只留远端 root 私有目录。
set -euo pipefail
set +x
umask 077
adm=$1 image=$2 fsid=$3 exporter=$4 expected=$5 arguments=$6 run=$7 pool=$8 fs=$9
[[ $EUID == 0 && $(hostname -s) == storage01 && -f $exporter && ! -L $exporter ]] || exit 1
[[ $(sha256sum "$exporter" | awk '{print $1}') == "$expected" ]] || exit 1
mapfile -t args < <(jq -er '.[]' <<< "$arguments")
jq -e --arg pool "$pool" --arg fs "$fs" 'index("--restricted-auth-permission")!=null and index("true")!=null and index("--rbd-data-pool-name")!=null and index($pool)!=null and index("--cephfs-filesystem-name")!=null and index($fs)!=null and index("cnpl03-external")!=null' <<< "$arguments" >/dev/null || exit 1
private=/var/lib/cnpl03/$fsid
install -d -m 0700 "$private"
out=$(mktemp "$private/external-$run.XXXXXX")
"$adm" --image "$image" shell --fsid "$fsid" --mount "$exporter:/inputs/exporter.py:ro" -- python3 /inputs/exporter.py "${args[@]}" > "$out"
[[ -s $out ]] || exit 1
printf '导出完成，仅保存于 storage01:%s；按同版本 importer 契约转换并受控传递。\n' "$out"
