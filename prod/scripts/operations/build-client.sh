#!/usr/bin/env bash
source "$(dirname "$0")/../lib/common.sh"
[[ $(role) == build01 ]] || die '只用于 build01'
case "${1:-}" in
  configure)
    root; need jq
    secret=/etc/cnpl/secrets/nexus-reader.json
    jq -e '.userId=="cnpl-reader" and (.password|test("^[0-9a-f]{64}$"))' "$secret" >/dev/null || die '只允许本次生成的 reader 凭据'
    directory=/home/ops/.config/cnpl
    install -d -o ops -g ops -m 0700 "$directory"
    work=$(mktemp -d); trap 'rm -rf -- "$work"' EXIT; chmod 0700 "$work"
    password=$(jq -er .password "$secret")
    printf '<settings><mirrors><mirror><id>cnpl</id><mirrorOf>*</mirrorOf><url>https://nexus.svc.internal.egon.top/repository/maven-public/</url></mirror></mirrors><servers><server><id>cnpl</id><username>cnpl-reader</username><password>%s</password></server></servers></settings>\n' "$password" > "$work/maven-settings.xml"
    auth=$(printf 'cnpl-reader:%s' "$password" | base64 -w0)
    printf 'registry=https://nexus.svc.internal.egon.top/repository/npm-proxy/\n//nexus.svc.internal.egon.top/repository/npm-proxy/:_auth=%s\nstrict-ssl=true\ncafile=/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem\nignore-scripts=true\n' "$auth" > "$work/npmrc"
    printf 'machine nexus.svc.internal.egon.top\nlogin cnpl-reader\npassword %s\n' "$password" > "$work/nexus.netrc"
    unset password auth
    printf '[global]\nindex-url = https://nexus.svc.internal.egon.top/repository/pypi-proxy/simple/\ncert = /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem\ndisable-pip-version-check = true\n' > "$work/pip.conf"
    for file in maven-settings.xml npmrc nexus.netrc pip.conf; do
        put "$work/$file" "$directory/$file" 0600
        chown ops:ops "$directory/$file"
    done
    ;;
  verify)
    [[ $(id -un) == ops ]] || die '在 build01 的 ops 会话执行真实客户端验收'
    directory=$HOME/.config/cnpl
    work=$(mktemp -d /srv/build/work/acceptance.XXXXXX)
    export NPM_CONFIG_USERCONFIG=$directory/npmrc
    export PIP_CONFIG_FILE=$directory/pip.conf
    export NETRC=$directory/nexus.netrc
    export NODE_EXTRA_CA_CERTS=/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem
    mvn -s "$directory/maven-settings.xml" -Dmaven.repo.local="$work/maven-cache" org.apache.maven.plugins:maven-dependency-plugin:3.8.1:get -Dartifact=org.slf4j:slf4j-api:2.0.16 -Dtransitive=false
    npm --cache "$work/npm-cache" pack is-number@7.0.0 --ignore-scripts --pack-destination "$work"
    python3 -m pip download --no-deps --no-cache-dir --dest "$work" idna==3.10
    # python3 -m pip 是 RPM 提供的客户端，未编写或执行自定义 Python 脚本。
    [[ -s $work/maven-cache/org/slf4j/slf4j-api/2.0.16/slf4j-api-2.0.16.jar ]] || die 'Maven 未取得真实 JAR'
    [[ -s $work/is-number-7.0.0.tgz ]] || die 'npm 未取得固定版本'
    compgen -G "$work/idna-3.10-*.whl" >/dev/null || die 'pip 未取得固定版本 wheel'
    find "$work" -maxdepth 1 -type f -exec sha256sum {} +
    printf 'PASS 三类包客户端，使用独立空缓存从 Nexus 获取；记录=%s\n' "$work"
    ;;
  *) die '用法：build-client.sh configure|verify';;
esac
result
