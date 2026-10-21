#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
source "$P04/02/client.sh"
language=${1:?指定语言}
[[ $language =~ ^(java|rust|c|cpp|csharp|jsts|python)$ ]] || die '未知语言'
start 02 build-builder
base=$(image "base_$language")
verify_file "$(required .build.ca_file)" "$(required .build.ca_sha256)"
private_file "$(required .build.client_key)"
export BUILDKIT_ADDR=$(required .build.endpoint) BUILDKIT_CA=$(required .build.ca_file) BUILDKIT_CERT=$(required .build.client_cert) BUILDKIT_KEY=$(required .build.client_key)
repository=$(required .build.builder_repository)
[[ $repository =~ ^harbor\.k8s\.internal\.egon\.top/[a-z0-9_/-]+$ ]] || die 'Builder 发布仓库无效'
private_temp
cp "$P04/02/builders/$language/Containerfile" "$PRIVATE_TEMP/Containerfile"
cp "$(required .build.ca_file)" "$PRIVATE_TEMP/lab-root-ca.crt"
cp -R "$P04/02/config" "$PRIVATE_TEMP/config"
ref=$repository/$language:$(git -C "$REPO" rev-parse HEAD)
buildctl_tls build --frontend dockerfile.v0 --local "context=$PRIVATE_TEMP" --local "dockerfile=$PRIVATE_TEMP" --opt filename=Containerfile --opt "build-arg:BASE_IMAGE=$base" --opt platform=linux/amd64 --metadata-file "$ATTEMPT/build-metadata.json" --output "type=image,name=$ref,push=true"
jq -e '.["containerimage.digest"]|test("^sha256:[a-f0-9]{64}$")' "$ATTEMPT/build-metadata.json" >/dev/null
printf '将实际 Digest 登记主版本锁与 materials 后，才可被 CI 引用。\n'
