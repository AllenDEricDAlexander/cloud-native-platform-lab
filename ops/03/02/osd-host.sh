#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077
preview_matches() {
    jq -e --arg host "$1" --arg service "$2" --argjson expected "$3" '
        [.[]|select(.service_type=="osd")] as $groups |
        ($groups|length)==1 and $groups[0].service_name==$service and
        ($groups[0].data|keys)==[$host] and
        all($groups[0].data[$host][]; .host==$host and (.error // false)==false and ((.notes // [])|length)==0) and
        ([$groups[0].data[$host][]|.data[]?|.data]|sort)==($expected|sort)
    ' >/dev/null
}
if [[ ${1:-} == --check-preview ]]; then shift; preview_matches "$@"; exit; fi
adm=$1 image=$2 fsid=$3 action=$4 spec=$5 expected=$6
[[ $EUID == 0 && $(hostname -s) == storage01 && $(getenforce) == Enforcing ]] || exit 1
systemctl is-active --quiet firewalld || exit 1
jq -e '.service_type=="osd" and (.placement.hosts|length)==1 and (.placement.hosts[0]|test("^storage0[123](\\.k8s\\.internal\\.egon\\.top)?$")) and (.spec.data_devices.paths|length)>0 and all(.spec.data_devices.paths[];test("^/dev/disk/by-id/[a-zA-Z0-9_.:+-]+$") and (test("-part[0-9]+$")|not)) and (.spec.data_devices.all // false)==false' <<< "$spec" >/dev/null || exit 1
count=$(jq '.spec.data_devices.paths|length' <<< "$spec")
jq -en --argjson expected "$expected" --argjson count "$count" '$expected|type=="array" and length==$count and (unique|length)==$count and all(.[];test("^/dev/(sd[a-z]+|vd[a-z]+|nvme[0-9]+n[0-9]+)$"))' >/dev/null || exit 1
work=$(mktemp /var/tmp/cnpl03-osd.XXXXXX)
trap 'rm -f -- "$work"' EXIT
printf '%s\n' "$spec" > "$work"
host=$(jq -r '.placement.hosts[0]' <<< "$spec")
service=osd.$(jq -r .service_id <<< "$spec")
deadline=$((SECONDS + 180)); ready=false
while ((SECONDS < deadline)); do
    preview=$("$adm" --image "$image" shell --fsid "$fsid" --mount "$work:/osd.json:ro" -- ceph orch apply -i /osd.json --dry-run --format json)
    printf '%s\n' "$preview"
    if jq -e '..|strings|select(startswith("Preview data is being generated"))' <<< "$preview" >/dev/null; then sleep 5; continue; fi
    preview_matches "$host" "$service" "$expected" <<< "$preview" || { echo 'OSD 预览与本次检查的主机/设备不符，停止' >&2; exit 1; }
    ready=true; break
done
[[ $ready == true ]] || { echo 'OSD 预览生成超时，未执行 apply' >&2; exit 1; }
if [[ $action == osd-apply ]]; then
    "$adm" --image "$image" shell --fsid "$fsid" --mount "$work:/osd.json:ro" -- ceph orch apply -i /osd.json
fi
