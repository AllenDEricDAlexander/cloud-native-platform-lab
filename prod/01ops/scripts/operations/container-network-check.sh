#!/usr/bin/env bash
source "$(dirname "$0")/../lib/common.sh"
root; expect_host harbor; need jq
file=/etc/cnpl/inputs/bootstrap-images.json
busybox=$(jq -er '.busybox' "$file"); curl_digest=$(jq -er '.curl' "$file")
[[ $busybox =~ ^sha256:[0-9a-f]{64}$ && $curl_digest =~ ^sha256:[0-9a-f]{64}$ ]] || die '缺少真实私服诊断镜像摘要'
busybox=harbor.k8s.internal.egon.top/bootstrap/busybox@$busybox
curl_image=harbor.k8s.internal.egon.top/bootstrap/curl@$curl_digest
cd /opt/cnpl-harbor
core=$(docker compose -f docker-compose.yml -f compose.cnpl.yml ps -q core)
[[ $core =~ ^[0-9a-f]{64}$ ]] || die 'Harbor core 容器不唯一或未运行'
network=$(docker inspect "$core" --format '{{range $name, $value := .NetworkSettings.Networks}}{{$name}}{{end}}')
[[ $network =~ ^[A-Za-z0-9_.-]+$ ]] || die '无法唯一确认 Harbor 真实网络'
docker pull "$busybox" >/dev/null
docker pull "$curl_image" >/dev/null
work=$(mktemp -d); names=(); prefix=cnpl-net-$(openssl rand -hex 6)
cleanup() {
    original=$?; trap - EXIT; set +e
    cleanup_rc=0
    for name in "${names[@]}"; do
        if docker container inspect "$name" >/dev/null 2>&1; then docker rm -f "$name" >/dev/null || cleanup_rc=1; fi
    done
    rm -rf -- "$work"
    [[ $original == 0 && $cleanup_rc == 0 ]] || exit 1
}
trap cleanup EXIT
options=(--rm --network "$network" --cap-drop ALL --security-opt no-new-privileges --read-only --tmpfs /tmp:rw,noexec,nosuid,nodev,size=16m --dns 192.168.9.11 --dns 192.168.9.17)
for dns in 192.168.9.11 192.168.9.17; do
    name=$prefix-dns-${dns##*.}; names+=("$name")
    timeout 20 docker run "${options[@]}" --name "$name" "$busybox" nslookup harbor.k8s.internal.egon.top "$dns" > "$work/dns"
    grep -q '192.168.9.12' "$work/dns" || die '容器 UDP DNS 返回错误'
done
curl_run() {
    local suffix=$1; shift
    names+=("$prefix-$suffix")
    timeout 20 docker run "${options[@]}" --name "$prefix-$suffix" --mount type=bind,src=/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem,dst=/cnpl-ca.pem,readonly "$curl_image" --cacert /cnpl-ca.pem --silent --show-error --connect-timeout 3 --max-time 8 "$@"
}
for dns in 192.168.9.11 192.168.9.17; do
    # telnet 只验证 TCP 53 建连；没有发送 DNS 帧时有界等待超时是预期，必须已成功建立连接。
    set +e
    curl_run "tcp-${dns##*.}" --noproxy '*' --output /dev/null --write-out '%{num_connects} %{remote_ip}' "telnet://$dns:53" > "$work/tcp" 2> "$work/tcp-error"
    status=$?
    set -e
    [[ ( $status == 0 || $status == 28 || $status == 52 || $status == 56 ) && $(cat "$work/tcp") == "1 $dns" ]] || die '容器 TCP DNS 无法建连'
done
curl_run https --noproxy '*' --output /dev/null --write-out '%{http_code}' https://harbor.k8s.internal.egon.top/v2/ > "$work/https"
[[ $(cat "$work/https") == 401 ]] || die '容器内网 HTTPS/认证异常'
curl_run proxy --proxy http://192.168.9.10:7890 --output /dev/null --write-out '%{http_code} %{remote_ip}' https://www.google.com/generate_204 > "$work/proxy"
[[ $(cat "$work/proxy") == '204 192.168.9.10' ]] || die '容器经 OpenWrt 出网失败'
set +e
curl_run denied --noproxy '*' --output /dev/null --write-out '%{num_connects}' telnet://1.1.1.1:443 > "$work/denied" 2> "$work/denied-error"
status=$?
set -e
[[ ( $status == 7 || $status == 28 ) && $(cat "$work/denied") == 0 ]] || die '容器公网新连接未被拒绝，或诊断本身失败'
printf 'PASS 实际 Harbor 网络内 UDP/TCP DNS、可信 HTTPS、代理与直接公网拒绝\n'
