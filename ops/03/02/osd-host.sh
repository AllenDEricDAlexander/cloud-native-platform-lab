#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077
adm=$1 image=$2 fsid=$3 action=$4 spec=$5
[[ $EUID == 0 && $(hostname -s) == storage01 && $(getenforce) == Enforcing ]] || exit 1
systemctl is-active --quiet firewalld || exit 1
jq -e '.service_type=="osd" and (.placement.hosts|length)==1 and (.placement.hosts[0]|IN("storage01","storage02","storage03")) and (.spec.data_devices.paths|length)>0 and all(.spec.data_devices.paths[];test("^/dev/disk/by-id/")) and (.spec.data_devices.all // false)==false' <<< "$spec" >/dev/null || exit 1
work=$(mktemp /var/tmp/cnpl03-osd.XXXXXX)
trap 'rm -f -- "$work"' EXIT
printf '%s\n' "$spec" > "$work"
"$adm" --image "$image" shell --fsid "$fsid" --mount "$work:/osd.json:ro" -- ceph orch apply -i /osd.json --dry-run
if [[ $action == osd-apply ]]; then
    "$adm" --image "$image" shell --fsid "$fsid" --mount "$work:/osd.json:ro" -- ceph orch apply -i /osd.json
fi
