#!/usr/bin/env bash
source "$(dirname "$0")/../lib/common.sh"
root; role=$(role)
case $role in admin|dns|dns02|nexus|harbor|gitlab) ;; *) die '该角色不是本期备份客户端';; esac
umask 077
load_repo() {
    [[ -s /etc/cnpl/secrets/restic.env ]] || die '先配置本机独立仓库'
    set -a; source /etc/cnpl/secrets/restic.env; set +a
    [[ $RESTIC_REPOSITORY == "sftp:cnpl-backup-$role:/repo" ]] || die '仓库与当前角色不符'
    [[ $RESTIC_PASSWORD_FILE == /etc/cnpl/secrets/restic.password ]] || die '密码文件路径不符'
}
restic_run() { restic -o "sftp.command=ssh -F /etc/cnpl/backup/ssh.conf cnpl-backup-$role -s sftp" "$@"; }
case "${1:-}" in
  key)
    install -d -m 0700 /etc/cnpl/secrets
    if [[ ! -e /etc/cnpl/secrets/backup.ssh ]]; then
        [[ ! -e /etc/cnpl/secrets/backup.ssh.pub ]] || die '已有公钥而私钥缺失，不能自动重建'
        ssh-keygen -q -t ed25519 -N '' -f /etc/cnpl/secrets/backup.ssh -C "cnpl-$role-backup"
        CNPL_CHANGED=1
    fi
    ssh-keygen -y -f /etc/cnpl/secrets/backup.ssh > /run/cnpl-backup-public.$$
    trap 'rm -f /run/cnpl-backup-public.$$' EXIT
    diff <(awk '{print $1" "$2}' /etc/cnpl/secrets/backup.ssh.pub) /run/cnpl-backup-public.$$
    chmod 0600 /etc/cnpl/secrets/backup.ssh
    ;;
  configure)
    [[ ${CNPL_EXISTING_REPOSITORY:-false} != true || -s /etc/cnpl/secrets/restic.password ]] || die '已有仓库但解密口令缺失，停止而不重新生成'
    secret_hex /etc/cnpl/secrets/restic.password
    install -d -m 0700 /etc/cnpl/backup
    put "$CNPL_INPUTS/backup-hostkey.pub" /etc/cnpl/backup/known_hosts 0600
    file=$(mktemp); trap 'rm -f "$file"' EXIT
    cat > "$file" <<EOF
Host cnpl-backup-$role
    HostName backup.mgmt.internal.egon.top
    User bk_$role
    IdentityFile /etc/cnpl/secrets/backup.ssh
    UserKnownHostsFile /etc/cnpl/backup/known_hosts
    IdentitiesOnly yes
    StrictHostKeyChecking yes
    BatchMode yes
    ForwardAgent no
    ClearAllForwardings yes
EOF
    put "$file" /etc/cnpl/backup/ssh.conf 0600
    printf 'RESTIC_REPOSITORY=sftp:cnpl-backup-%s:/repo\nRESTIC_PASSWORD_FILE=/etc/cnpl/secrets/restic.password\n' "$role" > "$file"
    put "$file" /etc/cnpl/secrets/restic.env 0600
    ;;
  init)
    load_repo
    if [[ ${CNPL_REPOSITORY_EMPTY:-false} == true ]]; then
        restic_run init; CNPL_CHANGED=1
    else
        restic_run cat config > /dev/null || die '已有仓库无法解密，停止而不重新初始化'
    fi
    ;;
  verify)
    load_repo
    work=$(mktemp -d); trap 'rm -rf -- "$work"' EXIT
    printf 'ls -la /repo\n' | sftp -q -F /etc/cnpl/backup/ssh.conf -b - "cnpl-backup-$role" > "$work/list"
    if printf 'get /etc/passwd %s\n' "$work/leak" | sftp -q -F /etc/cnpl/backup/ssh.conf -b - "cnpl-backup-$role" > "$work/denied" 2>&1; then die 'SFTP 越出受限目录'; fi
    restic_run check
    restic_run snapshots --json | jq -c '{snapshot_count:length}'
    ;;
  run)
    [[ ${CNPL_BACKUP_APPROVED:-} == yes ]] || die '先确认本次停服/备份窗口，再设 CNPL_BACKUP_APPROVED=yes'
    need flock
    exec 9> /run/cnpl-backup.lock; flock -n 9 || die '上一次备份仍在执行'
    load_repo
    install -d -m 0700 /var/lib/cnpl/backups
    stopped=''; work=$(mktemp -d)
    finish() {
        original=$?; trap - EXIT; set +e
        restart_rc=0
        if [[ -n $stopped ]]; then systemctl start "$stopped"; restart_rc=$?; fi
        rm -rf -- "$work"
        [[ $original == 0 && $restart_rc == 0 ]] || exit 1
    }
    trap finish EXIT
    install -d -m 0700 /etc/cnpl/backup
    printf '%s\n' "$role" > /etc/cnpl/backup/source-role
    cat /etc/machine-id > /etc/cnpl/backup/source-machine-id
    if [[ $role == gitlab ]]; then rpm -q --qf '%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}' gitlab-ce > /etc/cnpl/backup/source-rpm.nevra; fi
    case $role in
      harbor)
        systemctl is-active --quiet cnpl-harbor || die 'Harbor 原本未运行，先排查，不在备份后擅自拉起'
        stopped=cnpl-harbor; systemctl stop cnpl-harbor
        paths=(/data /opt/cnpl-harbor /etc/cnpl /etc/systemd/system/cnpl-harbor.service /etc/systemd/system/cnpl-harbor-firewall.service)
        ;;
      nexus)
        systemctl is-active --quiet cnpl-nexus || die 'Nexus 原本未运行'
        bash "$CNPL_ROOT/scripts/operations/nexus-seed.sh"
        stopped=cnpl-nexus; systemctl stop cnpl-nexus
        install -d -o postgres -g postgres -m 0700 /srv/nexus/backup
        sudo -u postgres pg_dump -Fc -d nexus -f /srv/nexus/backup/nexus.dump
        count=$(sudo -u postgres psql -XAt -d nexus -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='nexus'")
        jq -n --argjson count "$count" --arg version "$(cat /srv/nexus/postgres/PG_VERSION)" '{schema_tables:$count,postgresql_major:$version}' > /srv/nexus/backup/metadata.json
        snapshot=$(readlink -f /srv/nexus/repos/current)
        [[ $snapshot == /srv/nexus/repos/releases/* && -s $snapshot/baseos/repodata/repomd.xml ]] || die 'DNF current 不指向已交付快照'
        printf '%s\n' "$snapshot" > /srv/nexus/backup/rpm-current.txt
        paths=(/srv/nexus/data /srv/nexus/backup /srv/nexus/repos/keys "$snapshot" /opt/cnpl-nexus /etc/cnpl /etc/nginx /etc/systemd/system/cnpl-nexus.service /etc/systemd/system/postgresql.service.d)
        ;;
      gitlab)
        gitlab-backup create
        paths=(/var/opt/gitlab/backups /etc/gitlab /etc/cnpl /etc/systemd/system/gitlab-runsvdir.service.d)
        ;;
      dns|dns02) paths=(/etc/named.conf /var/named /etc/chrony.conf /etc/cnpl);;
      admin)
        [[ -s /etc/cnpl/secrets/openwrt-backup.ssh && -s /etc/cnpl/backup/openwrt-known_hosts ]] || die '先按 10.5 建立 OpenWrt 专用受限备份密钥'
        install -d -m 0700 /etc/cnpl/backup-inputs
        ssh -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/etc/cnpl/backup/openwrt-known_hosts -i /etc/cnpl/secrets/openwrt-backup.ssh root@192.168.9.10 backup > "$work/openwrt.tar.gz"
        tar -tzf "$work/openwrt.tar.gz" > /dev/null
        install -m 0600 "$work/openwrt.tar.gz" /etc/cnpl/backup-inputs/openwrt-config.tar.gz
        paths=(/etc/cnpl /home/ops/.ssh /home/ops/.local/share/cnpl/secrets /srv/cnpl/inputs /srv/cnpl/configuration /srv/cnpl/images/openwrt /srv/cnpl/images/mihomo)
        ;;
    esac
    restic_run backup --json --tag "$role" "${paths[@]}" > "$work/backup.jsonl"
    restic_run check
    if [[ -n $stopped ]]; then systemctl start "$stopped"; stopped=''; fi
    jq -s -e '[.[]|select(.message_type=="summary")]|last|select(.snapshot_id!=null)' "$work/backup.jsonl" > "$work/summary.json"
    install -m 0600 "$work/summary.json" /var/lib/cnpl/backups/last-success.json
    printf 'PASS 备份与仓库校验；角色=%s\n' "$role"
    ;;
  *) die '用法：backup.sh key|configure|init|verify|run';;
esac
result
