#!/usr/bin/env bash
source "$(dirname "$0")/../lib/common.sh"
source "$(dirname "$0")/../lib/http.sh"
root; expect_host nexus; need jq
umask 077
work=$(mktemp -d); trap 'rm -rf -- "$work"' EXIT
secrets=/etc/cnpl/secrets
base=https://nexus.svc.internal.egon.top/service/rest/v1
HTTP_NETRC=$secrets/nexus-admin.netrc
ensure_object() {
    local get=$1 create=$2 desired=$3
    http GET "$base/$get" '' "$work/response.json"
    if [[ $HTTP_CODE == 404 ]]; then
        http POST "$base/$create" "$desired" "$work/response.json"; http_ok; CNPL_CHANGED=1
    else
        http_ok
        jq -e --slurpfile wanted "$desired" 'def canonical: if (.proxy.remoteUrl?|type)=="string" then .proxy.remoteUrl |= sub("/+$";"") else . end; canonical | contains($wanted[0]|canonical)' "$work/response.json" >/dev/null || die "已有 $get 与正式配置不符，先审查，不覆盖"
    fi
}
case "${1:-}" in
  init)
    secret_hex "$secrets/nexus-admin.password"
    password=$(cat "$secrets/nexus-admin.password")
    printf 'machine nexus.svc.internal.egon.top\nlogin admin\npassword %s\n' "$password" > "$work/final.netrc"
    HTTP_NETRC=$work/final.netrc
    http GET "$base/security/users?userId=admin" '' "$work/check.json"
    if [[ $HTTP_CODE != 200 ]]; then
        [[ -s /srv/nexus/data/admin.password ]] || die '正式管理员认证失败，且初始口令不存在，不能重置现有账号'
        initial=$(cat /srv/nexus/data/admin.password)
        [[ $initial =~ ^[A-Za-z0-9-]+$ ]] || die '初始口令格式异常'
        printf 'machine nexus.svc.internal.egon.top\nlogin admin\npassword %s\n' "$initial" > "$work/initial.netrc"
        status=$(curl --silent --show-error --netrc-file "$work/initial.netrc" --request PUT --header 'Content-Type: text/plain' --data-binary "@$secrets/nexus-admin.password" --output "$work/change.json" --write-out '%{http_code}' "$base/security/users/admin/change-password")
        [[ $status == 204 ]] || die '管理员初始化失败'
        CNPL_CHANGED=1
    fi
    HTTP_NETRC=$work/final.netrc
    http GET "$base/security/users?userId=admin" '' "$work/check.json"; http_ok
    jq -e 'any(.[];.userId=="admin" and (.roles|index("nx-admin"))!=null)' "$work/check.json" >/dev/null || die '管理员权限或响应内容不符合要求'
    put "$work/final.netrc" "$secrets/nexus-admin.netrc" 0600
    unset password initial
    ;;
  proxy)
    http GET "$base/http" '' "$work/response.json"; http_ok
    if ! jq -e --slurpfile wanted "$CNPL_ROOT/config/nexus-http.json" 'contains($wanted[0])' "$work/response.json" >/dev/null; then
        http PUT "$base/http" "$CNPL_ROOT/config/nexus-http.json" "$work/response.json"; http_ok; CNPL_CHANGED=1
    fi
    ;;
  repositories)
    cp "$CNPL_ROOT/config/nexus-maven-proxy.json" "$work/maven-central.json"
    ensure_object repositories/maven/proxy/maven-central repositories/maven/proxy "$work/maven-central.json"
    for specification in 'npm npm-proxy https://registry.npmjs.org' 'pypi pypi-proxy https://pypi.org/'; do
        read -r format name url <<< "$specification"
        jq --arg name "$name" --arg url "$url" 'del(.maven)|.name=$name|.proxy.remoteUrl=$url' "$work/maven-central.json" > "$work/$name.json"
        ensure_object "repositories/$format/proxy/$name" "repositories/$format/proxy" "$work/$name.json"
    done
    for specification in 'maven-releases RELEASE ALLOW_ONCE' 'maven-snapshots SNAPSHOT ALLOW'; do
        read -r name policy write <<< "$specification"
        jq -n --arg name "$name" --arg policy "$policy" --arg write "$write" '{name:$name,online:true,storage:{blobStoreName:"default",strictContentTypeValidation:true,writePolicy:$write},maven:{versionPolicy:$policy,layoutPolicy:"STRICT",contentDisposition:"INLINE"}}' > "$work/$name.json"
        ensure_object "repositories/maven/hosted/$name" repositories/maven/hosted "$work/$name.json"
    done
    printf '%s\n' '{"name":"maven-public","online":true,"storage":{"blobStoreName":"default","strictContentTypeValidation":true},"group":{"memberNames":["maven-releases","maven-snapshots","maven-central"]}}' > "$work/maven-public.json"
    ensure_object repositories/maven/group/maven-public repositories/maven/group "$work/maven-public.json"
    ;;
  permissions)
    http GET "$base/security/anonymous" '' "$work/anonymous.json"; http_ok
    if jq -e '.enabled' "$work/anonymous.json" >/dev/null; then
        jq '.enabled=false' "$work/anonymous.json" > "$work/disabled.json"
        http PUT "$base/security/anonymous" "$work/disabled.json" "$work/response.json"; http_ok; CNPL_CHANGED=1
    fi
    for account in cnpl-reader cnpl-publisher; do
        if [[ $account == cnpl-reader ]]; then
            privileges='["nx-repository-view-maven2-maven-public-browse","nx-repository-view-maven2-maven-public-read","nx-repository-view-npm-npm-proxy-browse","nx-repository-view-npm-npm-proxy-read","nx-repository-view-pypi-pypi-proxy-browse","nx-repository-view-pypi-pypi-proxy-read"]'
        else
            privileges=$(jq -nc '["maven-releases","maven-snapshots"] as $repos|["browse","read","add","edit"] as $actions|[$repos[] as $r|$actions[] as $a|"nx-repository-view-maven2-\($r)-\($a)"]')
        fi
        jq -n --arg id "$account" --argjson privileges "$privileges" '{id:$id,name:$id,description:"Scoped preparation access",privileges:$privileges,roles:[]}' > "$work/role.json"
        ensure_object "security/roles/$account" security/roles "$work/role.json"
        http GET "$base/security/roles/$account" '' "$work/role-current.json"; http_ok
        jq -e --argjson privileges "$privileges" '(.privileges|sort)==($privileges|sort) and .roles==[]' "$work/role-current.json" >/dev/null || die '角色有额外权限'
        file=$secrets/$account-user.json
        http GET "$base/security/users?userId=$account" '' "$work/users.json"; http_ok
        jq --arg id "$account" '[.[]|select(.userId==$id)]' "$work/users.json" > "$work/matching-users.json"
        count=$(jq length "$work/matching-users.json")
        if [[ $count == 0 ]]; then
            if [[ ! -e $file ]]; then
                secret_hex "$secrets/$account.password"
                jq -n --arg id "$account" --rawfile password "$secrets/$account.password" '{userId:$id,firstName:"CNPL",lastName:$id,emailAddress:($id+"@internal.egon.top"),password:$password,status:"active",roles:[$id]}' > "$file"
            fi
            http POST "$base/security/users" "$file" "$work/user.json"; http_ok; CNPL_CHANGED=1
        else
            [[ $count == 1 ]] || die '用户查询结果不唯一'
            jq '.[0]' "$work/matching-users.json" > "$work/user.json"
            [[ -s $file ]] || die '已有账号缺少本次受控凭据，停止而不重置'
            jq -e --arg id "$account" '.roles==[$id] and .status=="active"' "$work/user.json" >/dev/null || die '账号权限或状态不符'
        fi
        jq -r '"machine nexus.svc.internal.egon.top\nlogin "+.userId+"\npassword "+.password+"\n"' "$file" > "$work/$account.netrc"
        put "$work/$account.netrc" "$secrets/nexus-${account#cnpl-}.netrc" 0600
    done
    ;;
  verify)
    curl --fail --silent --show-error https://nexus.svc.internal.egon.top/service/rest/v1/status -o /dev/null
    for entry in 'maven-public/org/slf4j/slf4j-api/2.0.16/slf4j-api-2.0.16.pom' 'npm-proxy/is-number' 'pypi-proxy/simple/idna/'; do
        curl --fail --silent --show-error --netrc-file "$secrets/nexus-reader.netrc" "https://nexus.svc.internal.egon.top/repository/$entry" -o "$work/artifact"
        [[ -s $work/artifact ]] || die '私服返回空制品'
    done
    curl --fail --silent --show-error --netrc-file "$secrets/nexus-reader.netrc" https://nexus.svc.internal.egon.top/repository/npm-proxy/is-number -o "$work/npm.json"
    jq -e '.versions["7.0.0"]' "$work/npm.json" >/dev/null
    curl --fail --silent --show-error --netrc-file "$secrets/nexus-reader.netrc" https://nexus.svc.internal.egon.top/repository/pypi-proxy/simple/idna/ -o "$work/pypi.html"
    grep -q 'idna-3.10' "$work/pypi.html"
    probe=preparation-probe-$(date -u +%Y%m%d%H%M%S)-$(openssl rand -hex 4)
    url=https://nexus.svc.internal.egon.top/repository/maven-releases/top/egon/cnpl/$probe/0.0.1/$probe-0.0.1.pom
    printf '<project><modelVersion>4.0.0</modelVersion><groupId>top.egon.cnpl</groupId><artifactId>%s</artifactId><version>0.0.1</version></project>\n' "$probe" > "$work/probe.pom"
    code=$(curl --silent --show-error --netrc-file "$secrets/nexus-reader.netrc" --upload-file "$work/probe.pom" --output "$work/denied" --write-out '%{http_code}' "$url")
    [[ $code == 403 ]] || die '只读上传未被准确拒绝'
    code=$(curl --silent --show-error --netrc-file "$secrets/nexus-publisher.netrc" --upload-file "$work/probe.pom" --output "$work/upload" --write-out '%{http_code}' "$url")
    [[ $code == 200 || $code == 201 ]] || die '发布账号上传失败'
    curl --fail --silent --show-error --netrc-file "$secrets/nexus-reader.netrc" "${url/maven-releases/maven-public}" -o "$work/read.pom"
    cmp "$work/probe.pom" "$work/read.pom"
    code=$(curl --silent --show-error --netrc-file "$secrets/nexus-publisher.netrc" --upload-file "$work/probe.pom" --output "$work/repeated" --write-out '%{http_code}' "$url")
    [[ $code == 400 || $code == 403 || $code == 409 ]] || die 'releases 允许重复发布'
    code=$(curl --silent --show-error --output "$work/anonymous" --write-out '%{http_code}' https://nexus.svc.internal.egon.top/repository/maven-public/org/slf4j/slf4j-api/2.0.16/slf4j-api-2.0.16.pom)
    [[ $code == 401 || $code == 403 ]] || die '匿名读取未被拒绝'
    printf 'PASS Nexus 真实读取、发布、ALLOW_ONCE、只读与匿名拒绝；探针=%s\n' "$probe"
    ;;
  *) die '用法：nexus-api.sh init|proxy|repositories|permissions|verify';;
esac
result
