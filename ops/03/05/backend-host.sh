#!/usr/bin/env bash
set -euo pipefail
set +x
adm=$1 image=$2 fsid=$3 pool=$4 action=$5 value=$6
[[ $EUID == 0 && $(hostname -s) == storage01 && $pool == cnpl03-*-rbd ]] || exit 1
r() { "$adm" --image "$image" shell --fsid "$fsid" -- rbd "$@"; }
case "$action" in
    find-pv)
        result='[]'
        while IFS= read -r name; do
            meta=$(r image-meta list "$pool/$name" --format json)
            if jq -e --arg pv "$value" '(.metadata // .)["csi.storage.k8s.io/pv/name"]==$pv' <<< "$meta" >/dev/null; then result=$(jq -c --arg name "$name" '.+[$name]' <<< "$result"); fi
        done < <(r ls --pool "$pool" --format json | jq -r '.[]')
        jq -e 'length==1' <<< "$result" >/dev/null || { echo '无法唯一关联 PV 与 RBD 元数据；停止而不推断 UUID' >&2; exit 1; }
        jq -r '.[0]' <<< "$result"
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
        if r ls --pool "$pool" --format json | jq -e --arg name "$value" 'index($name)!=null' >/dev/null; then
            [[ $(r image-meta get "$pool/$value" cnpl.run) == "${value#static-}" ]] || exit 1
        else
            r create "$pool/$value" --size 1G --image-feature layering
            r image-meta set "$pool/$value" cnpl.run "${value#static-}"
        fi
        ;;
    *) exit 2 ;;
esac
