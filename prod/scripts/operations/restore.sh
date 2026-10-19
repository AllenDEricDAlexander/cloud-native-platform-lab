#!/usr/bin/env bash
source "$(dirname "$0")/../lib/common.sh"
root; host=$(role)
case $host in admin|dns|dns02|nexus|harbor|gitlab) ;; *) die '未知恢复客户端';; esac
load_repo() { set -a; source /etc/cnpl/secrets/restic.env; set +a; }
restic_run() { restic -o "sftp.command=ssh -F /etc/cnpl/backup/ssh.conf cnpl-backup-$host -s sftp" "$@"; }
target_ok() { [[ $1 =~ ^/srv/cnpl-restore-check/[A-Za-z0-9_.-]+$ ]] || die '目标必须为 /srv/cnpl-restore-check/独立批次'; }
case "${1:-}" in
  list)
    load_repo; restic_run snapshots
    ;;
  extract)
    load_repo; snapshot=${2:?需要快照ID}; target=${3:?需要独立恢复目录}; target_ok "$target"
    [[ $snapshot =~ ^[0-9a-f]{8,64}$ && ! -e $target ]] || die '快照 ID 不合法或目标目录已存在'
    install -d -m 0700 "$target"
    restic_run restore "$snapshot" --target "$target"
    restic_run check
    printf 'PASS 快照提取与仓库校验；尚需执行角色功能恢复验收\n'
    ;;
  dns)
    [[ $host == dns ]] || die '本项在主 DNS 执行'
    target=${2:?需要已提取目录}; target_ok "$target"
    test -s "$target/var/named/cnpl-forward.zone" || die '缺少主区域备份'
    ! ss -H -lntu | awk '{print $5}' | grep -Eq '(^|:)1053$' || die '1053 已被使用'
    directory=$(mktemp -d /var/named/data/cnpl-restore.XXXXXX)
    chown root:named "$directory"; chmod 0750 "$directory"
    install -o root -g named -m 0640 "$target/var/named/cnpl-forward.zone" "$directory/forward.zone"
    configuration=/etc/named.cnpl-restore.$$.conf
    cat > "$configuration" <<EOF
options { directory "$directory"; listen-on { 127.0.0.1; }; listen-on-v6 { none; }; recursion no; dnssec-validation no; pid-file "/run/named/cnpl-restore.$$.pid"; session-keyfile "/run/named/cnpl-restore.$$.key"; };
controls { };
zone "internal.egon.top" IN { type primary; file "forward.zone"; };
EOF
    # 运行时文件放入 named 可写目录，测试端口和进程仅由本次验收拥有。
    chown named:named "$directory"
    fcontext '/etc/named\.cnpl-restore\..*\.conf' named_conf_t
    restorecon -RF "$directory" "$configuration"
    named-checkconf "$configuration"
    named-checkzone internal.egon.top "$directory/forward.zone"
    mapping=$(semanage port -l | awk '$2=="tcp" || $2=="udp" {for(i=3;i<=NF;i++){gsub(/,/,"",$i);if($i==1053)print $1" "$2}}')
    [[ -z $mapping || $(printf '%s\n' "$mapping" | grep -v '^dns_port_t ' || true) == '' ]] || die '1053 已属于其他 SELinux 类型'
    added_tcp=false; added_udp=false; pid=''
    cleanup() {
        original=$?; trap - EXIT; set +e
        cleanup_rc=0
        [[ -z $pid ]] || { kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null; }
        if [[ $added_tcp == true ]]; then semanage port -d -t dns_port_t -p tcp 1053 || cleanup_rc=1; fi
        if [[ $added_udp == true ]]; then semanage port -d -t dns_port_t -p udp 1053 || cleanup_rc=1; fi
        rm -f "$configuration" /run/named/cnpl-restore.$$.pid /run/named/cnpl-restore.$$.key; rm -rf -- "$directory"
        [[ $original == 0 ]] || exit "$original"
        exit "$cleanup_rc"
    }
    trap cleanup EXIT
    if ! grep -Fxq 'dns_port_t tcp' <<< "$mapping"; then semanage port -a -t dns_port_t -p tcp 1053; added_tcp=true; fi
    if ! grep -Fxq 'dns_port_t udp' <<< "$mapping"; then semanage port -a -t dns_port_t -p udp 1053; added_udp=true; fi
    named -g -u named -p 1053 -c "$configuration" > "$directory/restore.log" 2>&1 & pid=$!
    for attempt in $(seq 1 10); do
        if [[ $(dig @127.0.0.1 -p 1053 +short +time=1 +tries=1 harbor.k8s.internal.egon.top A) == 192.168.9.12 ]]; then printf 'PASS 恢复区域可启动独立 named 并返回正确地址\n'; exit 0; fi
        sleep 1
    done
    die '恢复 DNS 实例未返回期望结果'
    ;;
  nexus-db)
    [[ $host == nexus ]] || die '在 Nexus VM 执行数据库恢复验证'
    target=${2:?需要已提取目录}; target_ok "$target"
    [[ -s $target/srv/nexus/backup/nexus.dump && -s $target/srv/nexus/backup/metadata.json ]] || die '缺少成对的数据库与元数据'
    expected=$(jq -er .schema_tables "$target/srv/nexus/backup/metadata.json")
    [[ $expected =~ ^[0-9]+$ && $expected -gt 0 ]] || die '原库表数量不合法'
    [[ $(jq -r .postgresql_major "$target/srv/nexus/backup/metadata.json") == "$(cat /srv/nexus/postgres/PG_VERSION)" ]] || die '恢复测试数据库 major 不一致'
    database=cnpl_restore_$(date -u +%Y%m%d%H%M%S)_$$
    directory=/srv/nexus/backup/$database
    [[ ! -e $directory ]] || die '恢复测试目录已存在'
    install -d -o postgres -g postgres -m 0700 "$directory"
    install -o postgres -g postgres -m 0600 "$target/srv/nexus/backup/nexus.dump" "$directory/nexus.dump"
    created=false
    cleanup() {
        original=$?; trap - EXIT; set +e
        cleanup_rc=0
        if [[ $created == true ]]; then sudo -u postgres dropdb "$database" || cleanup_rc=1; fi
        rm -rf -- "$directory"
        [[ $original == 0 ]] || exit "$original"
        exit "$cleanup_rc"
    }
    trap cleanup EXIT
    sudo -u postgres createdb -O nexus "$database"; created=true
    sudo -u postgres pg_restore --exit-on-error --no-owner --no-privileges --role=nexus -d "$database" "$directory/nexus.dump"
    actual=$(sudo -u postgres psql -XAt -d "$database" -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='nexus'")
    [[ $actual == "$expected" ]] || die '恢复库表数量与备份时不符'
    printf 'PASS 独立数据库导入与 schema 数量校验，生产库未修改\n'
    ;;
  independent-copy)
    load_repo; medium=${2:?需要已挂载的独立介质路径}
    [[ ${CNPL_INDEPENDENT_MEDIA_CONFIRMED:-} == yes ]] || die '先人工确认介质独立于三台 ESXi'
    mountpoint -q "$medium" || die '不是实际挂载点'
    findmnt "$medium"
    destination=$medium/cnpl-$host
    password=/etc/cnpl/secrets/restic-independent.password
    if [[ -e $destination/config ]]; then [[ -s $password ]] || die '独立仓库存在但口令缺失';
    else [[ ! -e $destination || -z $(find "$destination" -mindepth 1 -maxdepth 1 -print -quit) ]] || die '目标非空且不是已知仓库'; secret_hex "$password"; restic -r "$destination" --password-file "$password" init; fi
    restic_run -r "$destination" --password-file "$password" copy --from-repo "$RESTIC_REPOSITORY" --from-password-file "$RESTIC_PASSWORD_FILE"
    restic -r "$destination" --password-file "$password" check
    restic -r "$destination" --password-file "$password" snapshots
    ;;
  independent-extract)
    medium=${2:?需要独立介质}; snapshot=${3:?需要独立快照ID}; target=${4:?需要新恢复目录}; target_ok "$target"
    mountpoint -q "$medium" || die '独立介质未挂载'
    [[ $snapshot =~ ^[0-9a-f]{8,64}$ && ! -e $target ]] || die '目标已存在或快照 ID 异常'
    install -d -m 0700 "$target"
    restic -r "$medium/cnpl-$host" --password-file /etc/cnpl/secrets/restic-independent.password restore "$snapshot" --target "$target"
    ;;
  *) die '用法：restore.sh list|extract 快照 目录|dns 目录|nexus-db 目录|independent-copy 挂载点|independent-extract 挂载点 快照 目录';;
esac
