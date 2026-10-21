#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077
adm=$1 image=$2 fsid=$3 run=$4 certificate=$5 quota=$6
[[ $EUID == 0 && $(hostname -s) == storage01 && $(getenforce) == Enforcing ]] || exit 1
systemctl is-active --quiet firewalld || exit 1
[[ -f $certificate && ! -L $certificate && $(stat -c %u "$certificate") == 0 ]] || exit 1
[[ $(stat -c %a "$certificate") == 600 || $(stat -c %a "$certificate") == 400 ]] || exit 1
openssl x509 -in "$certificate" -noout -checkend 86400
openssl x509 -in "$certificate" -noout -checkhost s3.svc.internal.egon.top
private=/var/lib/cnpl03/$fsid
install -d -m 0700 "$private"
work=$(mktemp -d "$private/rgw.XXXXXX")
trap 'rm -rf -- "$work"' EXIT
c() { "$adm" --image "$image" shell --fsid "$fsid" -- ceph "$@"; }
rule=$(c osd crush rule dump cnpl03-physical --format json | jq -er .rule_id)
c config set global osd_pool_default_size 3
c config set global osd_pool_default_min_size 2
c config set global osd_pool_default_crush_rule "$rule"
jq -n --arg id "cnpl03-$run" --rawfile certificate "$certificate" '{service_type:"rgw",service_id:$id,placement:{hosts:["storage01","storage02"]},spec:{rgw_frontend_port:9443,ssl:true,rgw_frontend_ssl_certificate:$certificate}}' > "$work/rgw.json"
"$adm" --image "$image" shell --fsid "$fsid" --mount "$work:/inputs:ro" -- ceph orch apply -i /inputs/rgw.json
uid=cnpl03-$run
rados() { "$adm" --image "$image" shell --fsid "$fsid" -- radosgw-admin "$@"; }
if rados user list | jq -e --arg uid "$uid" 'index($uid)!=null' >/dev/null; then
    rados user info --uid "$uid" > "$private/$uid-s3.json"
else
    rados user create --uid "$uid" --display-name "$uid" --max-buckets 2 > "$private/$uid-s3.json"
fi
rados quota set --uid "$uid" --quota-scope user --max-size "$quota"
rados quota enable --uid "$uid" --quota-scope user
printf '受限 S3 身份已准备；凭据仅位于 storage01:%s/%s-s3.json\n' "$private" "$uid"
