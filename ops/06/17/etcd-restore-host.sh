#!/usr/bin/env bash
# 仅在隔离且旧写入者已 fence 的恢复节点离线还原到新目录，不切换静态 Pod。
set -euo pipefail
set +x
umask 077
[[ $# -eq 13 ]] || { printf '用法：node ip receipt receipt_sha snapshot snapshot_sha etcdutl_sha member peer_url initial_cluster new_data_dir token revision_bump\n' >&2; exit 2; }
node=$1 ip_expected=$2 receipt=$3 receipt_sha=$4 snapshot=$5 snapshot_sha=$6 tool_sha=$7 member=$8 peer=$9
shift 9
initial=$1 destination=$2 token=$3 bump=$4
[[ $bump =~ ^[1-9][0-9]{0,15}$ ]]
[[ $(hostname -f) == "$node" ]]
ip -j addr | python3 -c 'import json,sys;assert any(a.get("local")==sys.argv[1] for i in json.load(sys.stdin) for a in i.get("addr_info",[]))' "$ip_expected"
[[ $(getenforce) == Enforcing ]]
for value in "$receipt_sha" "$snapshot_sha" "$tool_sha"; do [[ $value =~ ^[0-9a-f]{64}$ ]]; done
printf '%s  %s\n' "$receipt_sha" "$receipt" | sha256sum -c -
printf '%s  %s\n' "$snapshot_sha" "$snapshot" | sha256sum -c -
tool=$(command -v etcdutl)
printf '%s  %s\n' "$tool_sha" "$tool" | sha256sum -c -
python3 - "$receipt" "$node" "$snapshot" "$bump" <<'PY'
import json, os, stat, sys
d = json.load(open(sys.argv[1]))
assert d['node'] == sys.argv[2] and d['isolated'] is True and d['old_writers_fenced'] is True
assert d['recovery_route'] == 'etcd-restore' and d['historical_keys_restored'] is True
assert d['revision_bump'] == int(sys.argv[4]) and d['revision_bump_sufficient'] is True
for path in sys.argv[1], sys.argv[3]:
    s = os.stat(path)
    assert not os.path.islink(path) and stat.S_ISREG(s.st_mode) and s.st_uid == os.getuid() and stat.S_IMODE(s.st_mode) in (0o400, 0o600)
PY
[[ $member =~ ^[a-z0-9-]+$ && $token =~ ^cnpl06-[a-z0-9-]+$ && $peer =~ ^https://[a-z0-9.-]+:2380$ ]]
[[ $destination =~ ^/var/lib/etcd-restore-cnpl06-[a-z0-9-]+$ && ! -e $destination && ! -L $destination ]]
if pgrep -x etcd >/dev/null || [[ -n $(ss -Hlnpt '( sport = :2379 or sport = :2380 )') ]]; then printf '本节点仍有 etcd 服务，禁止覆盖/混入旧集群。\n' >&2; exit 1; fi
etcdutl snapshot status "$snapshot" -w json
# bump/mark-compacted 必须由锁定 etcd 版本支持；不省略哈希校验、不覆盖旧目录。
etcdutl snapshot restore "$snapshot" --name "$member" --data-dir "$destination" --initial-cluster "$initial" --initial-advertise-peer-urls "$peer" --initial-cluster-token "$token" --bump-revision "$bump" --mark-compacted
printf '新目录已还原；按审批规程核对 SELinux 标签、PKI/加密配置和成员映射后再切换静态 Pod。尚未启动 etcd。\n'
