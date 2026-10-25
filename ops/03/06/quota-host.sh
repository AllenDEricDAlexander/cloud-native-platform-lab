#!/usr/bin/env bash
set -euo pipefail
set +x
adm=$1 image=$2 fsid=$3 run=$4 rule=$5
[[ $EUID == 0 && $(hostname -s) == storage01 && $run =~ ^[a-z][a-z0-9-]{2,19}$ ]] || exit 1
[[ $rule == cnpl03-host || $rule == cnpl03-physical ]] || exit 1
"$adm" --image "$image" shell --fsid "$fsid" -- bash -s -- "$run" "$rule" <<'QUOTA'
set -euo pipefail
run=$1 rule=$2 pool=cnpl03-$1-quota
if ceph osd pool ls --format json | jq -e --arg pool "$pool" 'index($pool)!=null' >/dev/null; then
    [[ $(ceph osd pool application get "$pool" rados cnpl.run) == "$run" ]] || exit 1
    ceph df --format json | jq -e --arg pool "$pool" 'any(.pools[];.name==$pool and .stats.objects==0)' >/dev/null || { echo '本批配额池仍有对象，保留现场' >&2; exit 1; }
else
    ceph osd pool create "$pool" 8 8 replicated "$rule"
    ceph osd pool set "$pool" size 3
    ceph osd pool set "$pool" min_size 2
    ceph osd pool application enable "$pool" rados
    ceph osd pool application set "$pool" rados cnpl.run "$run"
fi
ceph osd pool set-quota "$pool" max_bytes 16777216
# full-try 请求必须返回 ENOSPC；普通 rados put 在满池可能等待，超时不能判定为拒绝。
python3 - "$pool" <<'PY'
import errno, json, subprocess, sys, time
import rados
pool = sys.argv[1]
cluster = rados.Rados(conffile='/etc/ceph/ceph.conf')
cluster.conf_set('rados_osd_op_timeout', '10')
cluster.connect()
io = cluster.open_ioctx(pool)
io.set_osdmap_full_try()
names = []
try:
    payload = b'x' * 1048576
    denied = False
    denied_code = None
    for i in range(1, 18):
        name = 'cnpl-quota-%02d' % i
        try:
            io.write_full(name, payload)
            names.append(name)
        except rados.Error as error:
            if error.errno not in (errno.ENOSPC, errno.EDQUOT):
                raise
            denied = True
            denied_code = error.errno
            break
    deadline = time.monotonic() + 120
    while not denied and time.monotonic() < deadline:
        health = json.loads(subprocess.check_output(['ceph', 'health', 'detail', '--format', 'json']))
        details = health.get('checks', {}).get('POOL_FULL', {}).get('detail', [])
        if any(pool in item.get('message', '') for item in details):
            try:
                io.write_full('cnpl-quota-denied', payload)
                names.append('cnpl-quota-denied')
            except rados.Error as error:
                if error.errno not in (errno.ENOSPC, errno.EDQUOT):
                    raise
                denied = True
                denied_code = error.errno
            break
        time.sleep(3)
    if not denied:
        raise RuntimeError('bounded quota test did not observe ENOSPC')
    print(json.dumps({'pool': pool, 'bytes_written': len(names)*1048576, 'errno': errno.errorcode[denied_code], 'actual_osd_full_injected': False}))
finally:
    for name in names:
        io.remove_object(name)
    io.close()
    cluster.shutdown()
PY
ceph osd pool stats "$pool"
printf 'PASS 专用池配额返回 EDQUOT/ENOSPC，并已清理本次对象；未注入真实 OSD nearfull/full。\n'
QUOTA
