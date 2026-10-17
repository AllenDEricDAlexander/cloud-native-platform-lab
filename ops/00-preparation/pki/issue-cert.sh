#!/usr/bin/env bash
# 用中间 CA 签发服务端证书（00.08.01）：每个服务单独私钥，SAN 写实际访问名称。
# 输出在 ${CNPL_PKI_DIR:-~/cnpl-pki}/intermediate/issued/<名称>/：server.key、server.crt、fullchain.crt。
# 用法：bash ops/00-preparation/pki/issue-cert.sh harbor.k8s.internal.egon.top [192.168.9.12]
set -euo pipefail
# 数组展开写成 ${arr[@]+"${arr[@]}"}：macOS 自带 bash 3.2 在 set -u 下展开空数组会报 unbound variable。
umask 077
NAME=${1:?用法：issue-cert.sh <FQDN> [IP]}
IP=${2:-}
PKI=${CNPL_PKI_DIR:-$HOME/cnpl-pki}
CA=$PKI/intermediate
OUT=$CA/issued/$NAME
pass_in=(); [ -n "${CNPL_PKI_PASS:-}" ] && pass_in=(-passin env:CNPL_PKI_PASS)
[ -e "$OUT/server.crt" ] && { echo "已存在 $OUT/server.crt，不覆盖" >&2; exit 1; }
mkdir -p "$OUT"
SAN="DNS:${NAME}"; [ -n "$IP" ] && SAN="${SAN},IP:${IP}"
cat > "$OUT/ext.cnf" <<CNF
basicConstraints = critical, CA:false
keyUsage = critical, digitalSignature
extendedKeyUsage = serverAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid
subjectAltName = ${SAN}
CNF
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$OUT/server.key"
openssl req -new -sha256 -key "$OUT/server.key" -subj "/O=cloud-native-platform-lab/CN=${NAME}" -out "$OUT/server.csr"
echo "== 用中间 CA 签发 ${NAME}（825 天，需要中间 CA 口令）"
openssl x509 -req -sha256 -days 825 -in "$OUT/server.csr" -CA "$CA/intermediate.crt" -CAkey "$CA/intermediate.key" \
  ${pass_in[@]+"${pass_in[@]}"} -CAcreateserial -extfile "$OUT/ext.cnf" -out "$OUT/server.crt"
cat "$OUT/server.crt" "$CA/intermediate.crt" > "$OUT/fullchain.crt"
openssl verify -CAfile "$PKI/root/root.crt" -untrusted "$CA/intermediate.crt" "$OUT/server.crt"
openssl x509 -in "$OUT/server.crt" -noout -subject -enddate -ext subjectAltName
