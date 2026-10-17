#!/usr/bin/env bash
# 内部 CA（00.08.01）：在管理端生成根 CA 与中间 CA。
#
# 私钥只写在仓库之外的 ${CNPL_PKI_DIR:-~/cnpl-pki}，以 AES-256 加密，运行时提示输入口令；
# 仓库只保存公开证书（ops/00-preparation/pki/public/），由 Ansible 分发信任。
# 根 CA 只用于签发中间 CA，日常签发用中间 CA；中间 CA 带名称约束，只能为 internal.egon.top 及其子域、
# 192.168.9.0/24 签发证书，误签外部域名会被客户端拒绝。
# 已存在的 CA 不覆盖。用法：bash ops/00-preparation/pki/create-ca.sh
set -euo pipefail
# 数组展开写成 ${arr[@]+"${arr[@]}"}：macOS 自带 bash 3.2 在 set -u 下展开空数组会报 unbound variable。
umask 077
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
PKI=${CNPL_PKI_DIR:-$HOME/cnpl-pki}
PUB=$REPO/ops/00-preparation/pki/public
# 测试时可用 CNPL_PKI_PASS 提供口令；正常使用不要设置，交由 openssl 提示输入。
pass_out=(); pass_in=()
if [ -n "${CNPL_PKI_PASS:-}" ]; then pass_out=(-pass env:CNPL_PKI_PASS); pass_in=(-passin env:CNPL_PKI_PASS); fi

mkdir -p "$PKI"/{root,intermediate/issued} "$PUB"
if [ -e "$PKI/root/root.key" ]; then echo "已存在 $PKI/root/root.key，不覆盖" >&2; exit 1; fi

cat > "$PKI/root/root.cnf" <<'CNF'
[req]
distinguished_name = dn
prompt = no
[dn]
O = cloud-native-platform-lab
CN = CNPL Lab Root CA 2026
[v3_root]
basicConstraints = critical, CA:true, pathlen:1
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash
[v3_intermediate]
basicConstraints = critical, CA:true, pathlen:0
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always
nameConstraints = critical, permitted;DNS:internal.egon.top, permitted;DNS:.internal.egon.top, permitted;IP:192.168.9.0/255.255.255.0
CNF

echo "== 根 CA 私钥（ECDSA P-384，请设置并牢记根 CA 口令）"
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-384 -aes-256-cbc ${pass_out[@]+"${pass_out[@]}"} -out "$PKI/root/root.key"
echo "== 根 CA 证书（10 年）"
openssl req -new -x509 -sha384 -days 3650 -key "$PKI/root/root.key" ${pass_in[@]+"${pass_in[@]}"} \
  -config "$PKI/root/root.cnf" -extensions v3_root -out "$PKI/root/root.crt"

echo "== 中间 CA 私钥（ECDSA P-384，请设置中间 CA 口令，可与根 CA 不同）"
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-384 -aes-256-cbc ${pass_out[@]+"${pass_out[@]}"} -out "$PKI/intermediate/intermediate.key"
openssl req -new -sha384 -key "$PKI/intermediate/intermediate.key" ${pass_in[@]+"${pass_in[@]}"} \
  -subj "/O=cloud-native-platform-lab/CN=CNPL Lab Issuing CA 2026" -out "$PKI/intermediate/intermediate.csr"
echo "== 用根 CA 签发中间 CA（5 年，需要根 CA 口令）"
openssl x509 -req -sha384 -days 1825 -in "$PKI/intermediate/intermediate.csr" \
  -CA "$PKI/root/root.crt" -CAkey "$PKI/root/root.key" ${pass_in[@]+"${pass_in[@]}"} -CAcreateserial \
  -extfile "$PKI/root/root.cnf" -extensions v3_intermediate -out "$PKI/intermediate/intermediate.crt"

openssl verify -CAfile "$PKI/root/root.crt" "$PKI/intermediate/intermediate.crt"
umask 022
cp "$PKI/root/root.crt" "$PUB/cnpl-lab-root-ca.crt"
cp "$PKI/intermediate/intermediate.crt" "$PUB/cnpl-lab-issuing-ca.crt"
echo "== 完成。私钥在 ${PKI}（勿提交、请另行加密备份），公开证书已写入 ${PUB}："
for c in "$PUB"/*.crt; do openssl x509 -in "$c" -noout -subject -enddate -fingerprint -sha256; done
