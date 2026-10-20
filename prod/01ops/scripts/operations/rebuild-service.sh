#!/usr/bin/env bash
# 仅用于 Web 人工重建后的替代 VM；拒绝在原生产实例执行数据回填。
source "$(dirname "$0")/../lib/common.sh"
root; need jq
mode=${1:?需要 rpm-source 或 application}; target=${2:?需要已校验的独立恢复目录}
[[ ${CNPL_REBUILD_CONFIRMED:-} == yes && $target =~ ^/srv/cnpl-restore-check/[A-Za-z0-9_.-]+$ ]] || die '先确认隔离/停服与替代 VM，指定正式恢复目录'
host=$(role)
case $host in nexus|harbor|gitlab) ;; *) die '本入口只恢复三个私服';; esac
[[ $(cat "$target/etc/cnpl/backup/source-role") == "$host" ]] || die '备份角色不符'
source_id=$(cat "$target/etc/cnpl/backup/source-machine-id") || die '缺少原始主机身份'
[[ $source_id =~ ^[0-9a-f]{32}$ && $source_id != "$(cat /etc/machine-id)" ]] || die '拒绝在原生产 VM 上恢复覆盖或使用未知来源'
for file in tls/tls.key tls/fullchain.crt; do [[ -s $target/etc/cnpl/$file ]] || die '缺少配套服务秘密/证书'; done
restore_private() {
    install -d -m 0700 /etc/cnpl/tls /etc/cnpl/secrets
    cp -a "$target/etc/cnpl/tls/." /etc/cnpl/tls/
    cp -a "$target/etc/cnpl/secrets/." /etc/cnpl/secrets/
    restorecon -RF /etc/cnpl/tls /etc/cnpl/secrets
}
empty_directory() { [[ ! -e $1 || -z $(find "$1" -mindepth 1 -maxdepth 1 -print -quit) ]] || die "恢复目标 $1 不是空目录"; }
if [[ $mode == rpm-source ]]; then
    [[ $host == nexus ]] || die '只有 nexus 恢复 DNF 源'
    mountpoint -q /srv/nexus || die '先在 Web 准备并挂载替代 VM 数据盘'
    empty_directory /srv/nexus/repos
    empty_directory /srv/nexus/data
    ! systemctl is-active --quiet cnpl-nexus || die '替代 VM 上已有运行的 Nexus'
    current=$(cat "$target/srv/nexus/backup/rpm-current.txt")
    [[ $current =~ ^/srv/nexus/repos/releases/[0-9]{8}T[0-9]{6}Z$ ]] || die 'RPM 快照记录不合法'
    restore_private
    for directory in rpm-gnupg upstream-repos; do
      [[ ! -d $target/etc/cnpl/$directory ]] || cp -a "$target/etc/cnpl/$directory" /etc/cnpl/
    done
    install -d -m 0755 /srv/nexus/repos/releases
    cp -a "$target/srv/nexus/repos/keys" /srv/nexus/repos/
    cp -a "$target$current" /srv/nexus/repos/releases/
    ln -s "$current" /srv/nexus/repos/current
    put "$target/etc/nginx/nginx.conf" /etc/nginx/nginx.conf
    put "$target/etc/nginx/conf.d/cnpl-rpm.conf" /etc/nginx/conf.d/cnpl-rpm.conf
    bash "$CNPL_ROOT/scripts/bootstrap/05-rpm.sh" serve
    printf 'PASS DNF 源恢复；先按第五章验证签名，再安装同版本 PG/Docker\n'
    exit
fi
[[ $mode == application ]] || die '未知模式'
case $host in
  harbor)
    ! systemctl is-active --quiet cnpl-harbor || die '替代 VM 上 Harbor 仍在运行'
    mountpoint -q /data || die '数据盘未挂载'
    empty_directory /data; empty_directory /opt/cnpl-harbor
    restore_private
    cp -a "$target/data/." /data/
    install -d -m 0700 /opt/cnpl-harbor
    cp -a "$target/opt/cnpl-harbor/." /opt/cnpl-harbor/
    fcontext '/data(/.*)?' container_file_t
    fcontext '/opt/cnpl-harbor(/.*)?' container_file_t
    restorecon -RF /data /opt/cnpl-harbor
    install -m 0750 "$CNPL_ROOT/ansible/files/harbor-firewall.sh" /usr/local/sbin/cnpl-harbor-firewall
    put "$target/etc/systemd/system/cnpl-harbor-firewall.service" /etc/systemd/system/cnpl-harbor-firewall.service
    bash "$CNPL_ROOT/scripts/operations/harbor.sh" restore-images
    sed 's/compose.images.yml/compose.restore-images.yml/g' "$target/etc/systemd/system/cnpl-harbor.service" > /etc/systemd/system/cnpl-harbor.service
    systemctl daemon-reload
    systemctl enable --now cnpl-harbor-firewall cnpl-harbor
    bash "$CNPL_ROOT/scripts/operations/harbor.sh" verify
    ;;
  nexus)
    ! systemctl is-active --quiet cnpl-nexus || die '替代 VM 上 Nexus 仍在运行'
    empty_directory /srv/nexus/data
    count=$(sudo -u postgres psql -XAt -d nexus -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='nexus'")
    [[ $count == 0 ]] || die '目标数据库已有应用表，拒绝覆盖'
    [[ $(jq -r .postgresql_major "$target/srv/nexus/backup/metadata.json") == "$(cat /srv/nexus/postgres/PG_VERSION)" ]] || die 'PG major 不符'
    restore_private
    install -d -o postgres -g postgres -m 0700 /srv/nexus/backup
    cp -a "$target/srv/nexus/backup/." /srv/nexus/backup/
    chown postgres:postgres /srv/nexus/backup/nexus.dump
    password=$(cat /etc/cnpl/secrets/nexus-db.password)
    [[ $password =~ ^[0-9a-f]{64}$ ]] || die '原数据库秘密格式异常'
    printf "ALTER ROLE nexus PASSWORD '%s';\n" "$password" | sudo -u postgres psql -X -v ON_ERROR_STOP=1 >/dev/null; unset password
    sudo -u postgres pg_restore --exit-on-error --clean --if-exists --no-owner --no-privileges --role=nexus -d nexus /srv/nexus/backup/nexus.dump
    install -d -o 200 -g 200 -m 0750 /srv/nexus/data
    cp -a "$target/srv/nexus/data/." /srv/nexus/data/
    install -d -m 0700 /opt/cnpl-nexus
    cp -a "$target/opt/cnpl-nexus/." /opt/cnpl-nexus/
    sha256sum -c /srv/nexus/backup/nexus-image.tar.sha256
    docker load -i /srv/nexus/backup/nexus-image.tar > /dev/null
    id=$(jq -er .id /srv/nexus/backup/nexus-image.json)
    [[ $(docker image inspect "$id" --format '{{.Id}}') == "$id" ]] || die '恢复镜像 ID 不符'
    jq -n --arg image "$id" '{services:{nexus:{image:$image,pull_policy:"never"}}}' > /opt/cnpl-nexus/compose.restore.yml
    sed 's/docker compose /docker compose -f compose.yml -f compose.restore.yml /g' "$target/etc/systemd/system/cnpl-nexus.service" > /etc/systemd/system/cnpl-nexus.service
    put "$target/etc/nginx/conf.d/cnpl-nexus.conf" /etc/nginx/conf.d/cnpl-nexus.conf
    setsebool -P httpd_can_network_connect 1
    nginx -t; systemctl reload nginx
    systemctl daemon-reload; systemctl enable --now cnpl-nexus
    ;;
  gitlab)
    expected=$(cat "$target/etc/cnpl/backup/source-rpm.nevra")
    [[ $(rpm -q --qf '%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}' gitlab-ce) == "$expected" ]] || die 'GitLab RPM 必须与备份精确一致'
    [[ $(gitlab-rails runner 'puts Project.count') == 0 ]] || die '目标 GitLab 已有项目，拒绝恢复覆盖'
    gitlab-ctl stop
    restore_private
    cp -a "$target/etc/gitlab/." /etc/gitlab/
    install -d -o git -g git -m 0700 /var/opt/gitlab/backups
    cp -a "$target/var/opt/gitlab/backups/." /var/opt/gitlab/backups/
    chown -R git:git /var/opt/gitlab/backups
    restorecon -RF /etc/gitlab /var/opt/gitlab
    gitlab-ctl reconfigure
    gitlab-ctl stop puma; gitlab-ctl stop sidekiq
    find /var/opt/gitlab/backups -maxdepth 1 -name '*_gitlab_backup.tar' -printf '%f\n'
    read -r -p '选择本次成对归档的 BACKUP ID（不含 _gitlab_backup.tar）: ' backup
    [[ $backup =~ ^[A-Za-z0-9_.-]+$ && -s /var/opt/gitlab/backups/${backup}_gitlab_backup.tar ]] || die '归档选择无效'
    GITLAB_ASSUME_YES=1 gitlab-backup restore BACKUP="$backup"
    gitlab-ctl restart
    gitlab-rake gitlab:check SANITIZE=true
    ;;
esac
printf 'PASS 数据回填与启动步骤；继续从 admin 复验真实制品/Git/权限和网络路径\n'
