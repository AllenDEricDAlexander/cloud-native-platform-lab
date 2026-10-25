#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P03/validate.sh" 07 ;;
    backup-target) exec bash "$P03/07/backup-s3.sh" prepare ;;
    backup-target-check) exec bash "$P03/07/backup-s3.sh" check ;;
    credentials|backup-credentials|baseline|baseline-test|baseline-restart|operator|ha|ha-test|archiving|backup|pitr-before|pitr-after|pitr|failover|dump|restore-dump|minor-upgrade|major-migrate|mysql|mysql-test|mysql-check|check) ;;
    *) die '用法：07/run.sh validate|backup-target|backup-target-check|credentials|backup-credentials|baseline|baseline-test|baseline-restart|operator|ha|ha-test|archiving|backup|pitr-before|pitr-after|pitr|failover|dump|restore-dump|minor-upgrade|major-migrate|mysql|mysql-test|mysql-check|check' ;;
esac
start 07 "$action"
cluster_gate; ceph_ok; backup_gate
ns=cnpl03-07; namespace "$ns"
pg_image=$(image postgresql)
sql() { local host=$1; shift; k -n "$ns" exec -i pg-client -- psql -h "$host" -U app -d app -X -qAt -v ON_ERROR_STOP=1 "$@"; }
check_pg() {
    local expected actual
    expected=$(ruby -rdigest -e 'puts "1000|"+Digest::MD5.hexdigest((1..1000).map{|n|"cnpl03-#{n}"}.join(","))')
    actual=$(sql "$1" -c "SELECT count(*),md5(string_agg(payload,',' ORDER BY id)) FROM probe WHERE id<=1000")
    [[ $actual == "$expected" ]] || die '数据库已提交序号/哈希不符'
}
render_cluster() {
    local cnpg_image
    cnpg_image=${UPGRADE_IMAGE:-$(image postgresql_cnpg)}
    yaml_json "$P03/07/cluster.yaml" | jq --arg image "$cnpg_image" --arg class "$SC_RBD" '.items[0].spec.imageName=$image|.items[0].spec.storage.storageClass=$class|.items[0].spec.walStorage.storageClass=$class' > "$ATTEMPT/cluster.json"
}
ha_ready() { wait_json 900 '.status.readyInstances==3 and .status.instances==3 and .status.phase=="Cluster in healthy state"' k -n "$ns" get cluster cnpl03-pg -o json; }
case "$action" in
    credentials)
        private_file "$(required .postgres.password_file)"; private_file "$(required .postgres.app_password_file)"
        work=$(mktemp -d); CLEANUP_DIRECTORY=$work
        printf postgres > "$work/super-username"; printf app > "$work/app-username"
        ruby -e 'ARGV.each_slice(2){|s,d|p=File.read(s);abort "password must be one nonempty line of 16-256 characters" unless p.match?(/\A[^\r\n\x00]{16,256}\n?\z/);File.write(d,p.delete_suffix("\n"))}' "$(required .postgres.password_file)" "$work/super-password" "$(required .postgres.app_password_file)" "$work/app-password"
        escaped=$(sed 's/\\/\\\\/g;s/:/\\:/g' "$work/app-password")
        [[ $escaped != *$'\n'* ]] || die 'pgpass 口令必须为单行'
        printf '*:5432:app:app:%s\n' "$escaped" > "$work/pgpass"
        secret_from_files "$ns" pg-superuser "username=$work/super-username" "password=$work/super-password"
        secret_from_files "$ns" pg-app "username=$work/app-username" "password=$work/app-password"
        secret_from_files "$ns" pg-client "pgpass=$work/pgpass"
        ;;
    backup-credentials)
        secret_from_files "$ns" "$(required .backup.s3_secret)" "ACCESS_KEY_ID=$(required .backup.s3_access_key_file)" "ACCESS_SECRET_KEY=$(required .backup.s3_secret_key_file)"
        secret_from_files "$ns" "$(required .backup.s3_ca_secret)" "ca.crt=$(required .backup.s3_ca_file)"
        ;;
    baseline)
        yaml_json "$P03/07/postgresql.yaml" | jq --arg image "$pg_image" --arg class "$SC_RBD" '.items|=map(if .kind=="Deployment" then .spec.template.spec.containers[0].image=$image elif .kind=="Pod" then .spec.containers[0].image=$image elif .kind=="PersistentVolumeClaim" then .spec.storageClassName=$class else . end)' > "$ATTEMPT/baseline.json"
        apply "$ATTEMPT/baseline.json" "$ns"
        k -n "$ns" rollout status deployment/baseline --timeout=300s
        k -n "$ns" wait --for=condition=Ready pod/pg-client --timeout=180s
        ;;
    baseline-test|ha-test)
        host=baseline; [[ $action != ha-test ]] || host=cnpl03-pg-rw
        sql "$host" < "$P03/07/transactions.psql" > "$ATTEMPT/transactions.txt"
        check_pg "$host"
        ;;
    baseline-restart)
        check_pg baseline
        k -n "$ns" rollout restart deployment/baseline
        k -n "$ns" rollout status deployment/baseline --timeout=300s
        check_pg baseline
        ;;
    operator) component_chart cnpl03-cnpg cloudnativepg "$ns" ;;
    ha)
        data_domains; render_cluster
        apply "$ATTEMPT/cluster.json" "$ns"; ha_ready
        ;;
    archiving)
        endpoint=$(required .backup.s3_endpoint)
        [[ $endpoint == https://* && $endpoint != "$(required .ceph.rgw_endpoint)" ]] || die 'WAL 归档必须使用独立 HTTPS 存储'
        component_manifest barman_plugin "$ns"
        source "$P03/lib/certificate-approval.sh"
        approve_certificate "$ns" barman-cloud-client
        approve_certificate "$ns" barman-cloud-server
        k -n "$ns" rollout status deployment/barman-cloud --timeout=180s
        backup_secret=$(required .backup.s3_secret)
        k -n "$ns" get secret "$backup_secret" >/dev/null
        ca_secret=$(required .backup.s3_ca_secret); k -n "$ns" get secret "$ca_secret" >/dev/null
        jq -n --arg endpoint "$endpoint" --arg destination "$(required .backup.s3_destination)" --arg secret "$backup_secret" --arg ca "$ca_secret" '{apiVersion:"barmancloud.cnpg.io/v1",kind:"ObjectStore",metadata:{name:"independent"},spec:{retentionPolicy:"7d",configuration:{destinationPath:$destination,endpointURL:$endpoint,endpointCA:{name:$ca,key:"ca.crt"},s3Credentials:{accessKeyId:{name:$secret,key:"ACCESS_KEY_ID"},secretAccessKey:{name:$secret,key:"ACCESS_SECRET_KEY"}},wal:{compression:"gzip"},data:{compression:"gzip"}}}}' > "$ATTEMPT/objectstore.json"
        apply "$ATTEMPT/objectstore.json" "$ns"
        k -n "$ns" patch cluster cnpl03-pg --type=merge -p '{"spec":{"plugins":[{"name":"barman-cloud.cloudnative-pg.io","isWALArchiver":true,"parameters":{"barmanObjectName":"independent"}}]}}'
        ;;
    backup)
        ha_ready
        name=backup-$(date -u +%Y%m%d%H%M%S)
        jq -n --arg name "$name" '{apiVersion:"postgresql.cnpg.io/v1",kind:"Backup",metadata:{name:$name},spec:{cluster:{name:"cnpl03-pg"},method:"plugin",pluginConfiguration:{name:"barman-cloud.cloudnative-pg.io"}}}' > "$ATTEMPT/backup.json"
        apply "$ATTEMPT/backup.json" "$ns"
        wait_json 900 '.status.phase=="completed"' k -n "$ns" get backup "$name" -o json
        k -n "$ns" get backup "$name" -o json > "$ATTEMPT/completed-backup.json"
        ;;
    pitr-before)
        sql cnpl03-pg-rw -c "INSERT INTO probe(id,payload) VALUES(1001,'before-target') ON CONFLICT DO NOTHING;"
        sql cnpl03-pg-rw -c 'SELECT clock_timestamp()' > "$ATTEMPT/pitr-target.txt"
        ;;
    pitr-after)
        sql cnpl03-pg-rw -c "INSERT INTO probe(id,payload) VALUES(1002,'after-target') ON CONFLICT DO NOTHING;"
        primary=$(k -n "$ns" get cluster cnpl03-pg -o jsonpath='{.status.currentPrimary}')
        closed_wal=$(k -n "$ns" exec "$primary" -c postgres -- psql -U postgres -d app -X -qAt -v ON_ERROR_STOP=1 -c 'SELECT pg_walfile_name(pg_current_wal_lsn())')
        [[ $closed_wal =~ ^[0-9A-F]{24}$ ]] || die '待归档 WAL 段名无效'
        k -n "$ns" exec "$primary" -c postgres -- psql -U postgres -d app -X -qAt -v ON_ERROR_STOP=1 -c 'SELECT pg_switch_wal()' > "$ATTEMPT/wal-switch.txt"
        end=$((SECONDS+300))
        until [[ $(k -n "$ns" exec "$primary" -c postgres -- psql -U postgres -d app -X -qAt -v ON_ERROR_STOP=1 -c "SELECT last_archived_wal >= '$closed_wal' FROM pg_stat_archiver") == t ]]; do
            ((SECONDS<end)) || die '目标后事务所在的 WAL 尚未确认归档'
            sleep 3
        done
        k -n "$ns" exec "$primary" -c postgres -- psql -U postgres -d app -X -qAt -v ON_ERROR_STOP=1 -c 'SELECT row_to_json(a) FROM pg_stat_archiver a' > "$ATTEMPT/archiver.json"
        ;;
    pitr)
        target=$(required .postgres.pitr_time)
        ruby -rtime -e 'Time.parse(ARGV[0]); abort "目标必须带时区" unless ARGV[0].match?(/(?:Z|[+-]\d\d(?::?\d\d)?)\z/)' "$target"
        render_cluster
        jq --arg target "$target" '.items[0].metadata.name="cnpl03-pitr"|.items[0].spec.bootstrap={recovery:{source:"origin",database:"app",owner:"app",secret:{name:"pg-app"},recoveryTarget:{targetTime:$target}}}|.items[0].spec.externalClusters=[{name:"origin",plugin:{name:"barman-cloud.cloudnative-pg.io",parameters:{barmanObjectName:"independent",serverName:"cnpl03-pg"}}}]' "$ATTEMPT/cluster.json" > "$ATTEMPT/pitr.json"
        apply "$ATTEMPT/pitr.json" "$ns"
        wait_json 1200 '.status.readyInstances==3' k -n "$ns" get cluster cnpl03-pitr -o json
        check_pg cnpl03-pitr-rw
        [[ $(sql cnpl03-pitr-rw -c 'SELECT count(*) FROM probe WHERE id=1001') == 1 ]] || die 'PITR 缺少目标前事务'
        [[ $(sql cnpl03-pitr-rw -c 'SELECT count(*) FROM probe WHERE id=1002') == 0 ]] || die 'PITR 错误包含目标后事务'
        ;;
    failover)
        ha_ready; check_pg cnpl03-pg-rw
        before=$(k -n "$ns" get cluster cnpl03-pg -o json)
        primary=$(jq -r .status.currentPrimary <<< "$before"); uid=$(jq -r .metadata.uid <<< "$before")
        k -n "$ns" get pod "$primary" -o json | jq -e --arg uid "$uid" 'any(.metadata.ownerReferences[]?;.uid==$uid)' >/dev/null || die '主 Pod 归属不符'
        (
            for i in $(seq 10001 10030); do
                if sql cnpl03-pg-rw -c "INSERT INTO probe(id,payload) VALUES($i,'failover-$i') ON CONFLICT DO NOTHING" >/dev/null 2>&1; then printf '%s\t%s\tack\n' "$(date +%s)" "$i"; else printf '%s\t%s\tfail\n' "$(date +%s)" "$i"; fi
                sleep 1
            done
        ) > "$ATTEMPT/writes.tsv" & writer_pid=$!
        P03_BACKGROUND_PID=$writer_pid
        sleep 3
        awk '$3=="ack" {found=1} END {exit !found}' "$ATTEMPT/writes.tsv" || die '故障前没有已确认的连续写入，停止'
        started=$(date +%s)
        k -n "$ns" delete pod "$primary" --wait=false
        wait_json 600 ".status.currentPrimary!=\"$primary\" and .status.readyInstances>=2" k -n "$ns" get cluster cnpl03-pg -o json
        end=$((SECONDS+180))
        until sql cnpl03-pg-rw -c "INSERT INTO probe(id,payload) VALUES(10031,'after-failover') ON CONFLICT DO NOTHING" >/dev/null 2>&1; do ((SECONDS<end)) || die '新主未恢复客户端写入'; sleep 1; done
        recovered=$(date +%s)
        wait "$writer_pid"; P03_BACKGROUND_PID=''
        printf '%s\t10031\tack\n' "$recovered" >> "$ATTEMPT/writes.tsv"
        for id in $(awk '$3=="ack" {print $2}' "$ATTEMPT/writes.tsv"); do [[ $(sql cnpl03-pg-rw -c "SELECT count(*) FROM probe WHERE id=$id") == 1 ]] || die '丢失已确认提交事务'; done
        jq -n --argjson seconds "$(($(date +%s)-started))" --argjson recovery "$((recovered-started))" '{observation_seconds:$seconds,observed_client_recovery_seconds:$recovery,acknowledged_transactions_lost:0,rto_scope:"从删除主 Pod 到观察到新主成功提交；不是物理主机/完整平台恢复时间"}' > "$ATTEMPT/failover.json"
        ha_ready; check_pg cnpl03-pg-rw
        ;;
    dump|restore-dump|major-migrate)
        directory=$(required .backup.local_restore_directory)
        [[ $directory == /* && -d $directory && ! -L $directory ]] || die '独立导出目录未准备'
        case "$directory" in "$REPO"/*) die '数据库备份不能写入仓库' ;; esac
        if [[ $action == dump || $action == major-migrate ]]; then
            saved=$(mktemp -d "$directory/cnpl03-$RUN.XXXXXX")
            k -n "$ns" exec pg-client -- pg_dump -h cnpl03-pg-rw -U app -d app -Fc --no-owner > "$saved/app.dump"
            sha "$saved/app.dump" > "$ATTEMPT/dump-sha256.txt"
            jq -n --arg path "$saved/app.dump" --arg sha "$(sha "$saved/app.dump")" --arg uid "$(required .kubernetes.cluster_uid)" --arg run "$RUN" '{path:$path,sha256:$sha,cluster_uid:$uid,run:$run}' > "$P03/07/records/$RUN/latest-dump.json"
        else
            receipt=$(cat "$P03/07/records/$RUN/latest-dump.json")
            jq -e --arg uid "$(required .kubernetes.cluster_uid)" --arg run "$RUN" '.cluster_uid==$uid and .run==$run' <<< "$receipt" >/dev/null || die '备份回执身份不符'
            verify_file "$(jq -er .path <<< "$receipt")" "$(jq -er .sha256 <<< "$receipt")"
            saved=$(dirname "$(jq -r .path <<< "$receipt")")
        fi
        if [[ $action != dump ]]; then
            render_cluster
            target=cnpl03-dump-restore
            if [[ $action == major-migrate ]]; then
                next=$(material postgresql_upgrade)
                [[ $(jq -r .version <<< "$next") == "$(required .postgres.upgrade_version)" ]] || die '升级目标未与输入明确选择一致'
                current_major=$(material postgresql_cnpg | jq -r '.version|split(".")[0]'); next_major=$(jq -r '.version|split(".")[0]' <<< "$next")
                [[ $next_major -gt $current_major ]] || die '大版本迁移要求目标 major 更高'
                UPGRADE_IMAGE=$(image postgresql_upgrade); render_cluster; target=cnpl03-upgrade
            fi
            jq --arg name "$target" '.items[0].metadata.name=$name' "$ATTEMPT/cluster.json" > "$ATTEMPT/new-cluster.json"
            [[ -z $(k -n "$ns" get cluster "$target" --ignore-not-found -o name) ]] || die '恢复必须使用全新目标，不能覆盖已有数据库'
            apply "$ATTEMPT/new-cluster.json" "$ns"
            wait_json 900 '.status.readyInstances==3' k -n "$ns" get cluster "$target" -o json
            sql "$target-rw" -c 'SELECT 1' >/dev/null
            k -n "$ns" exec -i pg-client -- pg_restore -h "$target-rw" -U app -d app --no-owner --exit-on-error < "$saved/app.dump"
            check_pg "$target-rw"
        fi
        ;;
    minor-upgrade)
        next=$(material postgresql_upgrade)
        [[ $(jq -r .version <<< "$next") == "$(required .postgres.upgrade_version)" ]] || die '升级目标未与输入明确选择一致'
        current_major=$(material postgresql_cnpg | jq -r '.version|split(".")[0]'); next_major=$(jq -r '.version|split(".")[0]' <<< "$next")
        [[ $next_major == "$current_major" ]] || die '此入口只允许同 major 升级'
        check_pg cnpl03-pg-rw
        patch=$(jq -cn --arg image "$(image postgresql_upgrade)" '{spec:{imageName:$image}}')
        k -n "$ns" patch cluster cnpl03-pg --type=merge -p "$patch"
        wait_json 900 "[.items[]|select(.metadata.labels[\"cnpg.io/cluster\"]==\"cnpl03-pg\")]|length==3 and all(.[];.spec.containers[0].image==\"$(image postgresql_upgrade)\")" k -n "$ns" get pods -o json
        ha_ready; check_pg cnpl03-pg-rw
        ;;
    mysql|mysql-test|mysql-check) source "$P03/07/mysql.sh" ;;
    check)
        check_pg baseline; check_pg cnpl03-pg-rw
        k -n "$ns" get cluster,backup,pvc,pods -o json > "$ATTEMPT/databases.json"
        ;;
esac
