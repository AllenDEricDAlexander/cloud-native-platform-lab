#!/usr/bin/env bash
source "$(dirname "$0")/../lib/common.sh"
root; expect_host harbor; need jq
cd /opt/cnpl-harbor
umask 077
work=$(mktemp -d); trap 'rm -rf -- "$work"' EXIT
compose=(docker compose -f docker-compose.yml -f compose.cnpl.yml)
case "${1:-}" in
  configure)
    [[ -s harbor.yml.tmpl && -s prepare ]] || die '先取得并校验官方安装物料'
    if [[ -e /data/database && ! -s /etc/cnpl/secrets/harbor-admin.password ]]; then die '已有 Harbor 数据但缺少原秘密，停止初始化'; fi
    secret_hex /etc/cnpl/secrets/harbor-admin.password
    secret_hex /etc/cnpl/secrets/harbor-db.password
    ! cmp -s /etc/cnpl/secrets/harbor-admin.password /etc/cnpl/secrets/harbor-db.password || die 'Harbor 管理与数据库口令必须不同'
    [[ -s /etc/pki/ca-trust/source/anchors/cnpl-root.crt ]] || die '缺少内部公开根 CA'
    ! grep -q '^storage_service:' harbor.yml.tmpl || die '官方存储配置结构变化，先核对，避免重复定义'
    # 原样保留官方完整配置，精确修改本平台需要的字段；密码从文件读取。
    awk '
      BEGIN {getline admin < "/etc/cnpl/secrets/harbor-admin.password"; getline db < "/etc/cnpl/secrets/harbor-db.password"}
      /^hostname:/ {$0="hostname: harbor.k8s.internal.egon.top"}
      /^  certificate:/ {$0="  certificate: /etc/cnpl/tls/fullchain.crt"}
      /^  private_key:/ {$0="  private_key: /etc/cnpl/tls/tls.key"}
      /^harbor_admin_password:/ {$0="harbor_admin_password: \"" admin "\""}
      /^  password: root123$/ {$0="  password: \"" db "\""}
      /^data_volume:/ {$0="data_volume: /data"}
      /^  http_proxy:/ {$0="  http_proxy: http://192.168.9.10:7890"}
      /^  https_proxy:/ {$0="  https_proxy: http://192.168.9.10:7890"}
      /^  no_proxy:/ {$0="  no_proxy: 127.0.0.1,localhost,.internal.egon.top,.cluster.local,192.168.9.0/24,10.244.0.0/16,192.168.20.0/24"}
      {print}
      END {print "\nstorage_service:\n  ca_bundle: /etc/pki/ca-trust/source/anchors/cnpl-root.crt"}
    ' harbor.yml.tmpl > "$work/harbor.yml"
    grep -Fxq '    - trivy' "$work/harbor.yml" || die '官方代理组件字段变化，先核对，不编造组件名'
    grep -Fxq '  insecure: false' "$work/harbor.yml" || die '扫描器 TLS 验证未开启'
    put "$work/harbor.yml" /opt/cnpl-harbor/harbor.yml 0600
    fcontext '/data(/.*)?' container_file_t
    fcontext '/opt/cnpl-harbor(/.*)?' container_file_t
    restorecon -RF /data /opt/cnpl-harbor
    sha256sum harbor.yml /etc/cnpl/tls/fullchain.crt /etc/cnpl/tls/tls.key /etc/pki/ca-trust/source/anchors/cnpl-root.crt | awk '{print $1}' > "$work/config.sha256"
    if [[ ! -e .cnpl-prepared.sha256 ]] || ! cmp -s "$work/config.sha256" .cnpl-prepared.sha256; then
        ./prepare --with-trivy > "$work/prepare.log" 2>&1 || die '官方 prepare 失败；保留本机服务日志核对，不输出私密配置'
        restorecon -RF /data /opt/cnpl-harbor
        chmod 0600 docker-compose.yml
        put "$work/config.sha256" /opt/cnpl-harbor/.cnpl-prepared.sha256 0600
        CNPL_CHANGED=1
    fi
    ;;
  images)
    "${compose[@]}" config --quiet
    if [[ ! -s compose.images.yml ]]; then
        "${compose[@]}" pull
        "${compose[@]}" config --format json > "$work/compose.json"
        overlay='{"services":{}}'; manifest='{}'
        while IFS=$'\t' read -r name tag; do
            repository=${tag%:*}; repository=${repository#docker.io/}
            digests=$(docker image inspect "$tag" --format '{{json .RepoDigests}}')
            digest=$(jq -er --arg repository "$repository" '[.[]|select((split("@")[0]|sub("^docker.io/";""))==$repository)]|if length==1 then .[0] else error("no unique digest") end' <<< "$digests")
            image_id=$(docker image inspect "$tag" --format '{{.Id}}')
            [[ $digest =~ @sha256:[0-9a-f]{64}$ && $image_id =~ ^sha256:[0-9a-f]{64}$ ]] || die '官方镜像未提供有效摘要/ID'
            overlay=$(jq --arg name "$name" --arg image "$digest" '.services[$name]={image:$image}' <<< "$overlay")
            manifest=$(jq --arg name "$name" --arg tag "$tag" --arg digest "$digest" --arg id "$image_id" '.[$name]={tag:$tag,digest:$digest,image_id:$id}' <<< "$manifest")
        done < <(jq -r '.services|to_entries[]|[.key,.value.image]|@tsv' "$work/compose.json")
        [[ $(jq '.services|length' <<< "$overlay") -ge 8 ]] || die '官方组件镜像清单不完整'
        printf '%s\n' "$manifest" > /data/bootstrap-images.json
        printf '%s\n' "$overlay" > compose.images.yml
        CNPL_CHANGED=1
    fi
    "${compose[@]}" -f compose.images.yml config --quiet
    ;;
  seed)
    [[ -s /data/bootstrap-images.json ]] || die '先固定组件摘要'
    install -d -m 0700 /data/bootstrap-seed
    archive=/data/bootstrap-seed/harbor-v2.15.4.docker.tar
    if [[ ! -f $archive ]]; then
        mapfile -t images < <(jq -r '.[].tag' /data/bootstrap-images.json)
        docker save -o "$archive.new" "${images[@]}"
        mv "$archive.new" "$archive"
        sha256sum "$archive" > "$archive.sha256"
        CNPL_CHANGED=1
    fi
    sha256sum -c "$archive.sha256"
    ;;
  restore-images)
    # 仅生成离线 Image ID overlay；不停止或启动在用服务。
    sha256sum -c /data/bootstrap-seed/harbor-v2.15.4.docker.tar.sha256
    docker load -i /data/bootstrap-seed/harbor-v2.15.4.docker.tar > /dev/null
    overlay='{"services":{}}'
    while IFS=$'\t' read -r name tag expected; do
        actual=$(docker image inspect "$tag" --format '{{.Id}}')
        [[ $actual == "$expected" ]] || die '恢复镜像与原始 Image ID 不符'
        overlay=$(jq --arg name "$name" --arg image "$actual" '.services[$name]={image:$image,pull_policy:"never"}' <<< "$overlay")
    done < <(jq -r 'to_entries[]|[.key,.value.tag,.value.image_id]|@tsv' /data/bootstrap-images.json)
    printf '%s\n' "$overlay" > compose.restore-images.yml
    ;;
  verify)
    curl --fail --silent --show-error https://harbor.k8s.internal.egon.top/api/v2.0/health -o "$work/health.json"
    jq -e '.status=="healthy" and ([.components[].status]|all(.=="healthy"))' "$work/health.json" >/dev/null
    code=$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' https://harbor.k8s.internal.egon.top/v2/)
    [[ $code == 401 ]] || die '未登录 registry 返回值异常'
    "${compose[@]}" -f compose.images.yml ps --format json > "$work/ps.json"
    printf 'PASS Harbor health、registry 认证与 Compose 状态\n'
    ;;
  *) die '用法：harbor.sh configure|images|seed|restore-images|verify';;
esac
result
