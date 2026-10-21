#!/usr/bin/env bash
# 仅受保护发布任务运行；私钥/口令从CI文件凭据读取，口令通过stdin传给Cosign。
set -euo pipefail
set +x
umask 077
: "${TRIVY_CACHE_DIR:?}" "${TRIVY_DB_METADATA:?}" "${COSIGN_KEY_FILE:?}" "${COSIGN_PASSWORD_FILE:?}" "${COSIGN_PUBLIC_KEY:?}" "${COSIGN_PUBLIC_KEY_SHA256:?}"
image=$(jq -er .image release/release.json)
[[ $image =~ ^harbor\.k8s\.internal\.egon\.top/.+@sha256:[a-f0-9]{64}$ ]] || exit 2
for file in "$COSIGN_KEY_FILE" "$COSIGN_PASSWORD_FILE"; do
    ruby -e 's=File.stat(ARGV[0]);abort "签名材料权限不符" unless s.file? && s.uid==Process.uid && [0400,0600].include?(s.mode & 0777)' "$file"
done
[[ $(shasum -a 256 "$COSIGN_PUBLIC_KEY" | awk '{print $1}') == "$COSIGN_PUBLIC_KEY_SHA256" ]] || exit 1
ruby -rjson -rtime -e 'm=JSON.parse(File.read(ARGV[0]));age=Time.now-Time.parse(m.fetch("UpdatedAt"));limit=Integer(ARGV[1]);abort "Trivy DB时间未来/过期" unless age>=0 && age<=limit*3600' "$TRIVY_DB_METADATA" "${TRIVY_DB_MAX_AGE_HOURS:-72}"
trivy image --cache-dir "$TRIVY_CACHE_DIR" --skip-db-update --skip-java-db-update --offline-scan --format cyclonedx --output release/sbom.json "$image"
trivy image --cache-dir "$TRIVY_CACHE_DIR" --skip-db-update --skip-java-db-update --offline-scan --severity HIGH,CRITICAL --exit-code 1 --format json --output release/vulnerabilities.json "$image"
jq --arg time "$(date -u +%FT%TZ)" '{buildDefinition:{buildType:"https://internal.egon.top/cnpl/dual-ci/v1",externalParameters:{source_revision:.source_revision,language:.language,ci:.ci},resolvedDependencies:[{uri:.builder_image}]},runDetails:{builder:{id:.pipeline_url},metadata:{finishedOn:$time}}}' release/release.json > release/provenance.json
password_stream() { ruby -e 's=File.binread(ARGV[0]);STDOUT.write(s.sub(/\r?\n\z/,""))' "$COSIGN_PASSWORD_FILE"; }
# Sigstore的非TTY密码读取支持stdin；清除可能覆盖stdin的环境值。
password_stream | env -u COSIGN_PASSWORD cosign sign --yes --key "$COSIGN_KEY_FILE" --tlog-upload=false "$image"
password_stream | env -u COSIGN_PASSWORD cosign attest --yes --key "$COSIGN_KEY_FILE" --tlog-upload=false --type slsaprovenance --predicate release/provenance.json "$image"
cosign verify --key "$COSIGN_PUBLIC_KEY" --insecure-ignore-tlog=true "$image" > release/signature.json
cosign verify-attestation --key "$COSIGN_PUBLIC_KEY" --insecure-ignore-tlog=true --type slsaprovenance "$image" > release/attestation.json
native=$(jq -r .native_artifact_sha256 release/release.json)
jq --arg sbom "$(shasum -a 256 release/sbom.json | awk '{print $1}')" --arg provenance "$(shasum -a 256 release/provenance.json | awk '{print $1}')" --arg scanned "$(date -u +%FT%TZ)" --slurpfile db "$TRIVY_DB_METADATA" '. + {sbom_sha256:$sbom,provenance_sha256:$provenance,signature_verified:true,scanned_at:$scanned,trivy_db:$db[0]}' release/release.json > release/signed.json
mv release/signed.json release/release.json
