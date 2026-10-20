#!/usr/bin/env bash
source "$(dirname "$0")/../lib/common.sh"
root
base=/etc/cnpl/pki
case "${1:-}" in
  init)
    expect_host admin
    if [[ -e $base/root/root.key || -e $base/root/root.crt || -e $base/intermediate/ca.key || -e $base/intermediate/ca.crt ]]; then
        for file in root/root.key root/root.crt intermediate/ca.key intermediate/ca.crt; do [[ -s $base/$file ]] || die 'CA 状态不完整，停止而不重新生成'; done
        openssl verify -CAfile "$base/root/root.crt" "$base/intermediate/ca.crt"
    else
        umask 077; install -d -m 0700 "$base/root" "$base/intermediate" "$base/issued"
        openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -aes-256-cbc -out "$base/root/root.key"
        openssl req -new -x509 -sha256 -days 3650 -key "$base/root/root.key" -subj '/CN=CNPL Root CA' -addext 'basicConstraints=critical,CA:TRUE,pathlen:1' -addext 'keyUsage=critical,keyCertSign,cRLSign' -out "$base/root/root.crt"
        openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -aes-256-cbc -out "$base/intermediate/ca.key"
        openssl req -new -key "$base/intermediate/ca.key" -subj '/CN=CNPL Intermediate CA' -out "$base/intermediate/ca.csr"
        cat > "$base/intermediate/extensions.cnf" <<'EOF'
basicConstraints=critical,CA:TRUE,pathlen:0
keyUsage=critical,keyCertSign,cRLSign
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
nameConstraints=critical,permitted;DNS:.internal.egon.top
EOF
        openssl x509 -req -sha256 -days 1825 -in "$base/intermediate/ca.csr" -CA "$base/root/root.crt" -CAkey "$base/root/root.key" -set_serial "0x$(openssl rand -hex 16)" -extfile "$base/intermediate/extensions.cnf" -out "$base/intermediate/ca.crt"
        openssl verify -CAfile "$base/root/root.crt" "$base/intermediate/ca.crt"
    fi
    install -d -o ops -g ops -m 0750 /srv/cnpl/inputs
    install -m 0644 "$base/root/root.crt" /srv/cnpl/inputs/cnpl-root.crt
    put "$base/root/root.crt" /etc/pki/ca-trust/source/anchors/cnpl-root.crt
    update-ca-trust
    ;;
  issue|stage)
    expect_host admin; service=${2:?需要 nexus/harbor/gitlab}
    case $service in nexus) fqdn=nexus.svc.internal.egon.top; san='DNS:nexus.svc.internal.egon.top,DNS:rpm.svc.internal.egon.top';; harbor) fqdn=harbor.k8s.internal.egon.top; san=DNS:$fqdn;; gitlab) fqdn=gitlab.svc.internal.egon.top; san=DNS:$fqdn;; *) die '未知服务';; esac
    issued=$base/issued/$service
    if [[ $1 == issue ]]; then
        if [[ -e $issued/tls.key || -e $issued/tls.crt || -e $issued/fullchain.crt ]]; then
            [[ -s $issued/tls.key && -s $issued/tls.crt && -s $issued/fullchain.crt ]] || die '签发状态不完整，停止'
        else
            install -d -m 0700 "$issued"; umask 077
            openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$issued/tls.key"
            openssl req -new -key "$issued/tls.key" -subj "/CN=$fqdn" -out "$issued/tls.csr"
            printf 'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=%s\n' "$san" > "$issued/extensions.cnf"
            openssl x509 -req -sha256 -days 365 -in "$issued/tls.csr" -CA "$base/intermediate/ca.crt" -CAkey "$base/intermediate/ca.key" -set_serial "0x$(openssl rand -hex 16)" -extfile "$issued/extensions.cnf" -out "$issued/tls.crt"
            cat "$issued/tls.crt" "$base/intermediate/ca.crt" > "$issued/fullchain.crt"
        fi
    fi
    openssl verify -CAfile "$base/root/root.crt" -untrusted "$base/intermediate/ca.crt" -verify_hostname "$fqdn" "$issued/tls.crt"
    openssl x509 -in "$issued/tls.crt" -checkend 2592000 -noout || die '证书不足 30 天，先走续期维护'
    diff <(openssl pkey -in "$issued/tls.key" -pubout 2>/dev/null) <(openssl x509 -in "$issued/tls.crt" -pubkey -noout)
    if [[ $1 == stage ]]; then
        install -d -o root -g ops -m 0750 /srv/cnpl-transfer
        install -d -o ops -g ops -m 0700 "/srv/cnpl-transfer/$service"
        install -o ops -g ops -m 0600 "$issued/tls.key" "$issued/fullchain.crt" "/srv/cnpl-transfer/$service/"
    fi
    ;;
  trust)
    put "$CNPL_INPUTS/cnpl-root.crt" /etc/pki/ca-trust/source/anchors/cnpl-root.crt
    update-ca-trust
    ;;
  install-leaf)
    service=$(role); case $service in nexus|harbor|gitlab) ;; *) die '该角色无服务叶证书';; esac
    install -d -m 0700 /etc/cnpl/tls
    put /home/ops/.local/share/cnpl-tls/fullchain.crt /etc/cnpl/tls/fullchain.crt
    put /home/ops/.local/share/cnpl-tls/tls.key /etc/cnpl/tls/tls.key 0600
    restorecon -RF /etc/cnpl/tls
    ;;
  unstage)
    expect_host admin; service=${2:?需要服务名}
    case $service in nexus|harbor|gitlab) rm -f "/srv/cnpl-transfer/$service/tls.key" "/srv/cnpl-transfer/$service/fullchain.crt";; *) die '未知服务';; esac
    ;;
  *) die '用法：04-pki.sh init|issue 服务|stage 服务|trust|install-leaf|unstage 服务';;
esac
result
