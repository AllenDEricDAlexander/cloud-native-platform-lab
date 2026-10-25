#!/usr/bin/env bash
set -euo pipefail
set +x
adm=$1 image=$2 fsid=$3 pool=$4 action=$5 value=$6
[[ $EUID == 0 && $(hostname -s) == storage01 && $pool == cnpl03-*-rbd ]] || exit 1
"$adm" --image "$image" shell --fsid "$fsid" -- bash -s -- "$pool" "$action" "$value" <<'BACKEND'
set -euo pipefail
pool=$1 action=$2 value=$3
owner=${pool#cnpl03-}; owner=${owner%-rbd}
r() { rbd "$@"; }
case "$action" in
    find-pv)
        # CSI 可关闭 image metadata；通过其双向 journal 关联核验，不能由 PV 名猜镜像名。
        [[ $value =~ ^pvc-[0-9a-f-]{36}$ ]] || exit 1
        work=$(mktemp -d); trap 'rm -rf -- "$work"' EXIT
        rados -p "$pool" getomapval csi.volumes.default "csi.volume.$value" "$work/uuid" >/dev/null
        uuid=$(cat "$work/uuid"); [[ $uuid =~ ^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$ ]] || exit 1
        rados -p "$pool" getomapval "csi.volume.$uuid" csi.volname "$work/pv" >/dev/null
        [[ $(cat "$work/pv") == "$value" ]] || exit 1
        rados -p "$pool" getomapval "csi.volume.$uuid" csi.imagename "$work/image" >/dev/null
        name=$(cat "$work/image"); [[ $name == "csi-vol-$uuid" ]] || exit 1
        r info "$pool/$name" --format json >/dev/null
        printf '%s\n' "$name"
        ;;
    exists) r ls --pool "$pool" --format json | jq -e --arg name "$value" 'index($name)!=null' >/dev/null ;;
    absent) r ls --pool "$pool" --format json | jq -e --arg name "$value" 'index($name)==null' >/dev/null ;;
    snapshots) r snap ls "$pool/$value" --format json ;;
    state)
        result='[]'
        while IFS= read -r name; do
            snaps=$(r snap ls "$pool/$name" --format json)
            result=$(jq -c --arg name "$name" --argjson snaps "$snaps" '.+[{image:$name,snapshots:($snaps|sort_by(.id))}]' <<< "$result")
        done < <(r ls --pool "$pool" --format json | jq -r '.[]' | sort)
        jq -S . <<< "$result"
        ;;
    static)
        [[ $value =~ ^static-[a-z0-9-]+$ ]] || exit 1
        if r ls --pool "$pool" --format json | jq -e --arg name "$value" 'index($name)!=null' >/dev/null; then
            [[ $(r image-meta get "$pool/$value" cnpl.run) == "$owner" ]] || exit 1
        else
            r create "$pool/$value" --size 1G --image-feature layering
            r image-meta set "$pool/$value" cnpl.run "$owner"
        fi
        ;;
    *) exit 2 ;;
esac
BACKEND
