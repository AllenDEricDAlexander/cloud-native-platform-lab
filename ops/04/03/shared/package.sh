#!/usr/bin/env bash
# 此入口仅由保护分支/固定发布任务调用；MR 不获得该任务的凭据。
set -euo pipefail
set +x
root=$(cd "$(dirname "$0")/../.." && pwd)
source "$root/02/client.sh"
: "${LANGUAGE:?}" "${SOURCE_REVISION:?}" "${CI_FLAVOR:?}" "${PIPELINE_URL:?}" "${BUILDER_IMAGE:?}" "${RUNTIME_IMAGE:?}" "${IMAGE_REPOSITORY:?}" "${SOURCE_DIR:?}" "${REGISTRY_CACHE:?}"
[[ $SOURCE_REVISION =~ ^[a-f0-9]{40}$ && $CI_FLAVOR =~ ^(gitlab|jenkins|tekton)$ ]] || exit 2
[[ $RUNTIME_IMAGE =~ ^harbor\.k8s\.internal\.egon\.top/.+@sha256:[a-f0-9]{64}$ && $BUILDER_IMAGE =~ ^harbor\.k8s\.internal\.egon\.top/.+@sha256:[a-f0-9]{64}$ ]] || exit 2
[[ $IMAGE_REPOSITORY =~ ^harbor\.k8s\.internal\.egon\.top/[a-z0-9_/-]+$ ]] || exit 2
[[ $(git rev-parse HEAD) == "$SOURCE_REVISION" ]] || { echo '检出提交与制品身份不符' >&2; exit 1; }
[[ -s $SOURCE_DIR/dist/native.tar && -s $SOURCE_DIR/dist/tests.json ]] || { echo '缺少本 CI 的原生制品/测试结果' >&2; exit 1; }
mkdir -p release
attempt=${CI_JOB_ID:-${BUILD_NUMBER:-${BUILD_ATTEMPT_ID:-}}}
[[ $attempt =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$ ]] || { echo '缺少安全的流水线尝试标识' >&2; exit 2; }
tag=$IMAGE_REPOSITORY:$CI_FLAVOR-$SOURCE_REVISION-$attempt
cache=$(cache_key "$LANGUAGE" "$BUILDER_IMAGE" "$SOURCE_DIR/dependencies.lock" trusted)
buildctl_tls build --frontend dockerfile.v0 --local "context=$SOURCE_DIR" --local "dockerfile=$SOURCE_DIR" --opt filename=Containerfile --opt platform=linux/amd64 --opt "build-arg:RUNTIME_IMAGE=$RUNTIME_IMAGE" --import-cache "type=registry,ref=$REGISTRY_CACHE:$cache" --export-cache "type=registry,ref=$REGISTRY_CACHE:$cache,mode=max" --metadata-file release/build.json --output "type=image,name=$tag,push=true"
digest=$(jq -er '.["containerimage.digest"]|select(test("^sha256:[a-f0-9]{64}$"))' release/build.json)
native_sha=$(shasum -a 256 "$SOURCE_DIR/dist/native.tar" | awk '{print $1}')
jq -n --arg lang "$LANGUAGE" --arg ci "$CI_FLAVOR" --arg rev "$SOURCE_REVISION" --arg attempt "$attempt" --arg url "$PIPELINE_URL" --arg builder "$BUILDER_IMAGE" --arg image "$IMAGE_REPOSITORY@$digest" --arg native "$native_sha" --slurpfile tests "$SOURCE_DIR/dist/tests.json" '{language:$lang,ci:$ci,source_revision:$rev,build_attempt_id:$attempt,pipeline_url:$url,builder_image:$builder,image:$image,native_artifact_sha256:$native,tests:$tests[0],runtime_accepted:false}' > release/release.json
bash "$root/03/shared/publish-native.sh"
