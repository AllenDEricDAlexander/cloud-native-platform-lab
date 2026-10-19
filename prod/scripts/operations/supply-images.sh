#!/usr/bin/env bash
source "$(dirname "$0")/../lib/common.sh"
[[ $(role) == admin && $(id -un) == ops ]] || die '在 admin 的 ops 会话执行'
need skopeo; need jq
umask 077
directory=$HOME/.local/share/cnpl/secrets
install -d -m 0700 "$directory"
for access in publisher reader; do
    file=$directory/harbor-$access.json
    [[ -s $file ]] || die '先从 Harbor 受控分发本次机器人凭据'
    name=$(jq -er '.name' "$file")
    jq -er '.secret' "$file" | skopeo login --authfile "$directory/harbor-$access-auth.json" --username "$name" --password-stdin harbor.k8s.internal.egon.top >/dev/null
    chmod 0600 "$directory/harbor-$access-auth.json"
done
record=/srv/cnpl/inputs/bootstrap-images.json
if [[ ! -e $record ]]; then
    pause=$(skopeo inspect --override-os linux --override-arch amd64 --format '{{.Digest}}' docker://registry.k8s.io/pause:3.10.2)
    busybox=$(skopeo inspect --override-os linux --override-arch amd64 --format '{{.Digest}}' docker://registry.k8s.io/e2e-test-images/busybox:1.38.0-1)
    [[ $pause =~ ^sha256:[0-9a-f]{64}$ && $busybox =~ ^sha256:[0-9a-f]{64}$ ]] || die '上游未返回有效摘要'
    read -r -p '官方 curlimages/curl 已选定的固定版本号: ' curl_version
    [[ $curl_version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die '必须是实际存在的固定版本号'
    curl_digest=$(skopeo inspect --override-os linux --override-arch amd64 --format '{{.Digest}}' "docker://docker.io/curlimages/curl:$curl_version")
    [[ $curl_digest =~ ^sha256:[0-9a-f]{64}$ ]] || die 'curl 镜像摘要不合法'
    jq -n --arg pause "$pause" --arg busybox "$busybox" --arg curl "$curl_digest" --arg version "$curl_version" '{pause:$pause,busybox:$busybox,curl:$curl,curl_version:$version}' > "$record"
fi
for name in pause busybox curl; do
    digest=$(jq -er --arg name "$name" '.[$name]' "$record")
    [[ $digest =~ ^sha256:[0-9a-f]{64}$ ]] || die '登记摘要不合法'
    case $name in pause) source=registry.k8s.io/pause; tag=3.10.2;; busybox) source=registry.k8s.io/e2e-test-images/busybox; tag=1.38.0-1;; curl) source=docker.io/curlimages/curl; tag=$(jq -er .curl_version "$record"); [[ $tag =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die 'curl 版本锁不正确';; esac
    skopeo inspect --override-os linux --override-arch amd64 "docker://$source@$digest" | jq -e '.Architecture=="amd64" and .Os=="linux"' >/dev/null || die '源镜像不包含所需 linux/amd64 平台'
    skopeo copy --all --preserve-digests --dest-authfile "$directory/harbor-publisher-auth.json" "docker://$source@$digest" "docker://harbor.k8s.internal.egon.top/bootstrap/$name:$tag"
    actual=$(skopeo inspect --authfile "$directory/harbor-reader-auth.json" --format '{{.Digest}}' "docker://harbor.k8s.internal.egon.top/bootstrap/$name:$tag")
    [[ $actual == "$digest" ]] || die '目标摘要与已登记源摘要不同'
done
work=$(mktemp -d); trap 'rm -rf -- "$work"' EXIT
digest=$(jq -r .busybox "$record")
if skopeo copy --all --src-authfile "$directory/harbor-reader-auth.json" --dest-authfile "$directory/harbor-reader-auth.json" "docker://harbor.k8s.internal.egon.top/bootstrap/busybox@$digest" "docker://harbor.k8s.internal.egon.top/bootstrap/busybox:reader-denied-$(date +%s)" > "$work/denied" 2>&1; then die '只读机器人错误地获得推送权限'; fi
grep -Eiq 'denied|unauthorized|requested access' "$work/denied" || die '推送失败原因不是权限拒绝，不能算通过'
code=$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' https://harbor.k8s.internal.egon.top/v2/business/private-probe/manifests/latest)
[[ $code == 401 || $code == 403 ]] || die '业务私有项目匿名路径未拒绝'
printf 'PASS 引导/诊断镜像摘要一致、只读推送拒绝、私有项目匿名拒绝\n'
