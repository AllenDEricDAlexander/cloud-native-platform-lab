#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077
adm=$1 image=$2 fsid=$3 run=$4 certificate=$5 quota=$6
[[ $EUID == 0 && $(hostname -s) == storage01 && $(getenforce) == Enforcing ]] || exit 1
systemctl is-active --quiet firewalld || exit 1
[[ -f $certificate && ! -L $certificate && $(stat -c %u "$certificate") == 0 ]] || exit 1
[[ $(stat -c %a "$certificate") == 600 || $(stat -c %a "$certificate") == 400 ]] || exit 1
python3 - "$certificate" <<'CERTIFICATE'
import ssl, sys, time
cert = ssl._ssl._test_decode_cert(sys.argv[1])
assert ("DNS", "s3.svc.internal.egon.top") in cert.get("subjectAltName", ())
assert ssl.cert_time_to_seconds(cert["notBefore"]) <= time.time()
assert ssl.cert_time_to_seconds(cert["notAfter"]) > time.time() + 86400
print("PASS RGW certificate SAN and validity")
CERTIFICATE
private=/var/lib/cnpl03/$fsid
install -d -m 0700 "$private"
work=$(mktemp -d "$private/rgw.XXXXXX")
trap 'rm -rf -- "$work"' EXIT
c() { "$adm" --image "$image" shell --fsid "$fsid" -- ceph "$@"; }
rule=$(c osd crush rule dump "${9:-cnpl03-physical}" --format json | jq -er .rule_id)
c config set global osd_pool_default_size 3
c config set global osd_pool_default_min_size 2
c config set global osd_pool_default_crush_rule "$rule"
jq -n --arg id "cnpl03-$run" --arg host1 "${7:-storage01}" --arg host2 "${8:-storage02}" --rawfile certificate "$certificate" '{service_type:"rgw",service_id:$id,placement:{hosts:[$host1,$host2]},spec:{rgw_frontend_port:9443,ssl:true,rgw_frontend_ssl_certificate:$certificate,rgw_frontend_extra_args:[("ssl_private_key=config://rgw/cert/rgw."+$id)]}}' > "$work/rgw.json"
"$adm" --image "$image" shell --fsid "$fsid" --mount "$work:/inputs:ro" -- ceph orch apply -i /inputs/rgw.json
c orch redeploy "rgw.cnpl03-$run"
uid=cnpl03-$run
rados() { "$adm" --image "$image" shell --fsid "$fsid" -- radosgw-admin "$@"; }
if rados user list | jq -e --arg uid "$uid" 'index($uid)!=null' >/dev/null; then
    rados user info --uid "$uid" > "$private/$uid-s3.json"
else
    rados user create --uid "$uid" --display-name "$uid" --max-buckets 2 > "$private/$uid-s3.json"
fi
rados quota set --uid "$uid" --quota-scope user --max-size "$quota" >/dev/null
rados quota enable --uid "$uid" --quota-scope user >/dev/null
rados user info --uid "$uid" > "$private/$uid-s3.json"
python3 - "${7:-storage01}" "${8:-storage02}" <<'HTTPS'
import socket, ssl, sys, time
context = ssl.create_default_context()
for host in sys.argv[1:]:
    deadline = time.monotonic() + 180
    while True:
        try:
            with socket.create_connection((host, 9443), timeout=5) as connection:
                with context.wrap_socket(connection, server_hostname="s3.svc.internal.egon.top") as tls:
                    tls.sendall(b"GET / HTTP/1.1\r\nHost: s3.svc.internal.egon.top\r\nConnection: close\r\n\r\n")
                    response = tls.recv(1024).split(b"\r\n", 1)[0]
                    assert response.split()[1] in (b"200", b"403"), response
            print("PASS RGW trusted TLS:", host, response.decode())
            break
        except (OSError, AssertionError) as error:
            if time.monotonic() >= deadline:
                raise SystemExit("RGW HTTPS did not become ready: " + host + " " + str(error))
            time.sleep(5)
HTTPS
printf '受限 S3 身份已准备；凭据仅位于 storage01:%s/%s-s3.json\n' "$private" "$uid"
