#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P03/validate.sh" 03 ;;
    pools|rgw|rbd-test|cephfs-test|mds-failover|s3-test|independent-copy|check) ;;
    *) die '用法：03/run.sh validate|pools|rgw|rbd-test|cephfs-test|mds-failover|s3-test|independent-copy|check' ;;
esac
start 03 "$action"
backup_gate; ceph_ok
pool() {
    local name=$1 app=$2 owner pool_id
    if ! ceph osd pool ls --format json | jq -e --arg name "$name" 'index($name)!=null' >/dev/null; then
        ceph osd pool create "$name" 8 8 replicated "$CRUSH_RULE"
        pool_id=$(ceph osd pool ls detail --format json | jq -er --arg name "$name" '.[]|select(.pool_name==$name)|.pool_id // .pool')
        ceph config-key set "cnpl03/owner/$name" "$(jq -cn --arg run "$RUN" --argjson id "$pool_id" '{run:$run,id:$id}')"
    fi
    owner=$(ceph config-key get "cnpl03/owner/$name") || die '已有池缺少本批归属，停止'
    pool_id=$(ceph osd pool ls detail --format json | jq -er --arg name "$name" '.[]|select(.pool_name==$name)|.pool_id // .pool')
    jq -e --arg run "$RUN" --argjson id "$pool_id" '.run==$run and .id==$id' <<< "$owner" >/dev/null || die '池归属或 ID 不符'
    ceph osd pool set "$name" size 3
    ceph osd pool set "$name" min_size 2
    ceph osd pool set "$name" pg_autoscale_mode on
    ceph osd pool set-quota "$name" max_bytes "$(required .ceph.pool_quota_bytes)"
    ceph osd pool application enable "$name" "$app"
}
case "$action" in
    pools)
        ruby "$P03/lib/review.rb" devices "$DEVICES" > "$ATTEMPT/budget.json"
        quota=$(required .ceph.pool_quota_bytes)
        jq -en --argjson quota "$quota" --argjson budget "$(jq .recommended_max_bytes "$ATTEMPT/budget.json")" '$quota>0 and $quota*3 <= $budget' >/dev/null || die '三个池的合计配额超出安全预算'
        pool "$RBD_POOL" rbd
        ceph osd pool application set "$RBD_POOL" rbd cnpl_run "$RUN"
        remote storage01 "$P03/lib/exec-host.sh" storage01 "$(required .ceph.cephadm)" --image "$(image ceph)" shell --fsid "$(required .ceph.fsid)" -- rbd pool init "$RBD_POOL"
        pool "$CEPH_FS-meta" cephfs; pool "$CEPH_FS-data" cephfs
        if ! ceph fs ls --format json | jq -e --arg fs "$CEPH_FS" 'any(.[];.name==$fs)' >/dev/null; then ceph fs new "$CEPH_FS" "$CEPH_FS-meta" "$CEPH_FS-data"; fi
        ceph fs set "$CEPH_FS" max_mds 1
        ceph fs set "$CEPH_FS" standby_count_wanted 1
        ceph orch apply mds "$CEPH_FS" --placement="2 $(ceph_host storage01) $(ceph_host storage02)"
        wait_json 600 "any(.filesystems[]; .mdsmap.fs_name==\"$CEPH_FS\" and any(.mdsmap.info[]; .state==\"up:active\")) and any(.standbys[]?;.name|startswith(\"$CEPH_FS.\"))" ceph fs dump --format json
        wait_json 600 '.health.status=="HEALTH_OK"' ceph status --format json
        ;;
    rgw)
        remote storage01 "$P03/03/rgw-host.sh" "$(required .ceph.cephadm)" "$(image ceph)" "$(required .ceph.fsid)" "$RUN" "$(required .ceph.rgw_certificate_file)" "$(get '.ceph.rgw_quota_bytes // .ceph.pool_quota_bytes')" "$(ceph_host storage01)" "$(ceph_host storage02)" "$CRUSH_RULE" | tee "$ATTEMPT/rgw.txt"
        ;;
    rbd-test|cephfs-test)
        remote storage01 "$P03/03/client-host.sh" "$(required .ceph.cephadm)" "$(image ceph)" "$(required .ceph.fsid)" "$RUN" "$RBD_POOL" "$CEPH_FS" "$action" "$(get '.ceph.rbd_mounter // "krbd"')" "$(get '.ceph.cephfs_mounter // "kernel"')" | tee "$ATTEMPT/$action.txt"
        ;;
    mds-failover)
        ceph fs dump --format json > "$ATTEMPT/mds-before.json"
        old=$(ceph fs dump --format json | jq -er --arg fs "$CEPH_FS" '.filesystems[]|select(.mdsmap.fs_name==$fs)|.mdsmap.info[]|select(.state=="up:active")|.name')
        ceph mds fail "$old"
        wait_json 300 "any(.filesystems[];.mdsmap.fs_name==\"$CEPH_FS\" and any(.mdsmap.info[];.state==\"up:active\" and .name!=\"$old\")) and any(.standbys[]?;.name|startswith(\"$CEPH_FS.\"))" ceph fs dump --format json
        wait_json 300 '.health.status=="HEALTH_OK"' ceph status --format json
        ceph fs dump --format json > "$ATTEMPT/mds-after.json"
        remote storage01 "$P03/03/client-host.sh" "$(required .ceph.cephadm)" "$(image ceph)" "$(required .ceph.fsid)" "$RUN" "$RBD_POOL" "$CEPH_FS" cephfs-test "$(get '.ceph.rbd_mounter // "krbd"')" "$(get '.ceph.cephfs_mounter // "kernel"')" | tee "$ATTEMPT/after-mds.txt"
        ;;
    s3-test|independent-copy)
        need aws
        credentials=$(required .ceph.aws_credentials_file); private_file "$credentials"
        export AWS_SHARED_CREDENTIALS_FILE=$credentials AWS_CA_BUNDLE
        AWS_CA_BUNDLE=$(required .ceph.ca_file)
        profile=$(required .ceph.rgw_profile); endpoint=$(required .ceph.rgw_endpoint)
        [[ $endpoint == https://s3.svc.internal.egon.top:* || $endpoint == https://s3.svc.internal.egon.top ]] || die 'RGW 端点必须使用规划的 TLS 域名'
        bucket=cnpl03-$RUN
        printf '%s\n' "$RUN:sequence:000001" > "$ATTEMPT/payload.txt"
        aws_s3() { aws --profile "$profile" --endpoint-url "$endpoint" "$@"; }
        # 测试桶首次创建，已有同名桶只在所有者校验后继续。
        if ! aws_s3 s3api head-bucket --bucket "$bucket" 2> "$ATTEMPT/head-bucket.txt"; then
            grep -Eq '404|Not Found|NoSuchBucket' "$ATTEMPT/head-bucket.txt" || die '桶访问失败，不能据此判定桶不存在'
            aws_s3 s3api create-bucket --bucket "$bucket"
        fi
        aws_s3 s3api put-object --bucket "$bucket" --key "$RUN/payload.txt" --body "$ATTEMPT/payload.txt" > "$ATTEMPT/put.json"
        aws_s3 s3api get-object --bucket "$bucket" --key "$RUN/payload.txt" "$ATTEMPT/restored.txt" > "$ATTEMPT/get.json"
        cmp "$ATTEMPT/payload.txt" "$ATTEMPT/restored.txt"
        aws_s3 s3api list-objects-v2 --bucket "$bucket" --prefix "$RUN/" > "$ATTEMPT/list.json"
        jq -e --arg key "$RUN/payload.txt" 'any(.Contents[];.Key==$key)' "$ATTEMPT/list.json" >/dev/null
        code=$(curl --silent --show-error --cacert "$AWS_CA_BUNDLE" --output /dev/null --write-out '%{http_code}' "$endpoint/$bucket/$RUN/payload.txt")
        [[ $code == 403 ]] || die '匿名读取未按预期返回 403'
        if [[ $action == independent-copy && $(get '.backup.mode // "remote"') == mac ]]; then
            source "$P03/03/s3-backup-mac.sh"
        elif [[ $action == independent-copy ]]; then
            target=$(required .backup.s3_endpoint)
            [[ $target == https://* && $target != "$endpoint" ]] || die '独立对象备份不能使用原 RGW 端点'
            aws --profile "$profile-independent" --endpoint-url "$target" s3 cp "$ATTEMPT/payload.txt" "$(required .backup.s3_destination)/$RUN/payload.txt"
            aws --profile "$profile-independent" --endpoint-url "$target" s3 cp "$(required .backup.s3_destination)/$RUN/payload.txt" "$ATTEMPT/independent.txt"
            cmp "$ATTEMPT/payload.txt" "$ATTEMPT/independent.txt"
        fi
        aws_s3 s3api delete-object --bucket "$bucket" --key "$RUN/payload.txt" > "$ATTEMPT/delete.json"
        if aws_s3 s3api head-object --bucket "$bucket" --key "$RUN/payload.txt" 2> "$ATTEMPT/head-object.txt"; then die '删除后对象仍存在'; fi
        grep -Eq '404|Not Found|NoSuchKey' "$ATTEMPT/head-object.txt" || die '删除后错误不符合预期'
        ;;
    check)
        ceph osd pool ls detail --format json > "$ATTEMPT/pools.json"
        ceph fs status "$CEPH_FS" --format json > "$ATTEMPT/filesystem.json"
        ceph orch ps --format json > "$ATTEMPT/services.json"
        jq -e --arg pool "$RBD_POOL" '.[]|select(.pool_name==$pool)|.size==3 and .min_size==2' "$ATTEMPT/pools.json" >/dev/null
        ;;
esac
ceph_ok
