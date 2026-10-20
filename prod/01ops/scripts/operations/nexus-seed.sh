#!/usr/bin/env bash
source "$(dirname "$0")/../lib/common.sh"
root; expect_host nexus; need jq
directory=/srv/nexus/backup
install -d -o postgres -g postgres -m 0700 "$directory"
image=$(awk '$1=="image:"{print $2}' /opt/cnpl-nexus/compose.yml)
[[ $image =~ ^docker.io/sonatype/nexus3@sha256:[0-9a-f]{64}$ ]] || die 'Nexus 镜像没有固定官方摘要'
id=$(docker image inspect "$image" --format '{{.Id}}')
[[ $id =~ ^sha256:[0-9a-f]{64}$ ]] || die 'Nexus 镜像不存在'
if [[ ! -e $directory/nexus-image.tar ]]; then
    docker save -o "$directory/nexus-image.tar.new" "$id"
    mv "$directory/nexus-image.tar.new" "$directory/nexus-image.tar"
    sha256sum "$directory/nexus-image.tar" > "$directory/nexus-image.tar.sha256"
    jq -n --arg image "$image" --arg id "$id" '{image:$image,id:$id}' > "$directory/nexus-image.json"
    chmod 0600 "$directory"/nexus-image.*
    CNPL_CHANGED=1
fi
[[ $(jq -r .id "$directory/nexus-image.json") == "$id" ]] || die '镜像版本变化，先安排新版本恢复种子维护'
sha256sum -c "$directory/nexus-image.tar.sha256"
result
