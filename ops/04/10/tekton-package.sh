#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077
private=$(mktemp -d)
trap 'rm -rf -- "$private"' EXIT
cp /build-auth/cosign.key "$private/cosign.key"
cp /build-auth/cosign.password "$private/password"
cp /build-auth/config.json "$private/config.json"
cp /build-auth/nexus-curl.conf "$private/nexus-curl.conf"
chmod 600 "$private/"*
export DOCKER_CONFIG=$private COSIGN_KEY_FILE=$private/cosign.key COSIGN_PASSWORD_FILE=$private/password
export NEXUS_CURL_CONFIG=$private/nexus-curl.conf
export BUILDKIT_CA=/build-auth/ca.crt BUILDKIT_CERT=/build-auth/tls.crt BUILDKIT_KEY=/build-auth/tls.key
bash ops/04/03/shared/package.sh
bash ops/04/08/supply-chain.sh
