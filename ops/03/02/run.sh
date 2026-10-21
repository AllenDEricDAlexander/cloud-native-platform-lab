#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P03/validate.sh" 02 ;;
    prepare|bootstrap|hosts|osd-plan|osd-apply|baseline|mgr-failover|backup) ;;
    *) die '用法：02/run.sh validate|prepare|bootstrap|hosts|osd-plan|osd-apply|baseline|mgr-failover|backup' ;;
esac
start 02 "$action"
backup_gate
ceph_image=$(image ceph)
adm=$(required .ceph.cephadm); fsid=$(required .ceph.fsid)
[[ $fsid =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || die '先生成并登记固定 FSID'
export ANSIBLE_CONFIG="$REPO/ops/00-preparation/ansible/ansible.cfg"
ansible=${CNPL03_ANSIBLE:-$HOME/.venvs/cnpl-ansible/bin/ansible-playbook}
case "$action" in
    prepare)
        export CNPL03_CEPH_IMAGE=$ceph_image
        "$ansible" "$P03/02/prepare-playbook.yml" 2>&1 | tee "$ATTEMPT/prepare.txt"
        ;;
    bootstrap)
        remote storage01 "$P03/02/bootstrap-host.sh" "$adm" "$ceph_image" "$fsid" "$(host_value storage01 ip)" | tee "$ATTEMPT/bootstrap.txt"
        ;;
    hosts)
        ceph cephadm get-pub-key > "$ATTEMPT/ceph.pub"
        export CNPL03_CEPH_PUBLIC_KEY=$ATTEMPT/ceph.pub
        "$ansible" "$P03/02/enroll-playbook.yml" 2>&1 | tee "$ATTEMPT/enroll.txt"
        for host in storage02 storage03; do
            existing=$(ceph orch host ls --format json)
            if jq -e --arg h "$host" 'any(.[];.hostname==$h)' <<< "$existing" >/dev/null; then
                jq -e --arg h "$host" --arg ip "$(host_value "$host" ip)" 'any(.[];.hostname==$h and .addr==$ip)' <<< "$existing" >/dev/null || die '已纳管主机地址不符'
            else ceph orch host add "$host" "$(host_value "$host" ip)"; fi
        done
        ceph orch apply mon --placement='3 storage01 storage02 storage03'
        ceph orch apply mgr --placement='2 storage01 storage02'
        ceph config set mgr mgr/cephadm/autotune_memory_target_ratio 0.2
        ceph config set osd osd_memory_target_autotune false
        ceph config set osd osd_memory_target "$(required .ceph.osd_memory_target)"
        wait_json 600 '.monmap.num_mons==3 and (.quorum|length)==3 and .mgrmap.available==true' ceph status --format json
        ;;
    osd-plan|osd-apply)
        ruby "$P03/lib/review.rb" devices "$DEVICES" > "$ATTEMPT/budget.json"
        for host in storage01 storage02 storage03; do
            count=$(jq --arg host "$host" '[.devices[]|select(.host==$host)]|length' "$DEVICES")
            jq -en --argjson count "$count" --argjson target "$(required .ceph.osd_memory_target)" --argjson budget "$(required .ceph.service_memory_budget)" '$count*$target+2147483648 <= $budget' >/dev/null || die 'Ceph 内存预算不足，先调整主机与 kubelet 预留'
            while IFS=$'\t' read -r disk bytes; do
                remote "$host" "$P03/01/device-check.sh" "$disk" "$bytes" > "$ATTEMPT/$host-device-$RANDOM.txt"
            done < <(jq -r --arg host "$host" '.devices[]|select(.host==$host)|[.stable_id,.bytes]|@tsv' "$DEVICES")
            jq --arg host "$host" --arg id "cnpl03-$RUN-$host" '{service_type:"osd",service_id:$id,placement:{hosts:[$host]},spec:{data_devices:{paths:[.devices[]|select(.host==$host)|.stable_id]}}}' "$DEVICES" > "$ATTEMPT/$host-osd.json"
            # spec 通过管道传给 cephadm；不把盘符拼进 shell 命令。
            remote storage01 "$P03/02/osd-host.sh" "$adm" "$ceph_image" "$fsid" "$action" "$(jq -c . "$ATTEMPT/$host-osd.json")" | tee "$ATTEMPT/$host-osd.txt"
            if [[ $action == osd-apply ]]; then
                wait_json 600 "[.[]|select(.daemon_type==\"osd\" and .hostname==\"$host\" and .status_desc==\"running\")]|length==$count" ceph orch ps --format json --refresh
            fi
        done
        if [[ $action == osd-apply ]]; then wait_json 900 '.health.status=="HEALTH_OK"' ceph status --format json; ceph_ok; fi
        ;;
    baseline)
        ceph_ok
        ruby "$P03/lib/review.rb" devices "$DEVICES" > "$ATTEMPT/budget.json"
        for host in storage01 storage02 storage03; do
            domain=$(host_value "$host" actual_hypervisor)
            [[ $domain =~ ^esxi0[1-3]$ ]] || die '未知物理故障域'
            tree=$(ceph osd crush tree --format json)
            if ! jq -e --arg name "$domain" 'any(.nodes[];.name==$name and .type=="rack")' <<< "$tree" >/dev/null; then ceph osd crush add-bucket "$domain" rack; fi
            ceph osd crush move "$domain" root=default
            ceph osd crush move "$host" "rack=$domain"
        done
        ceph osd crush rule create-replicated cnpl03-physical default rack
        ceph osd tree --format json > "$ATTEMPT/osd-tree.json"
        ceph orch ps --format json > "$ATTEMPT/daemons.json"
        ceph df --format json > "$ATTEMPT/capacity.json"
        ceph_ok
        ;;
    mgr-failover)
        ceph_ok
        before=$(ceph mgr dump --format json)
        [[ $(jq '.standbys|length' <<< "$before") -ge 1 ]] || die '缺少备用 MGR'
        old=$(jq -r .active_name <<< "$before"); ceph mgr fail "$old"
        wait_json 180 ".active_name != \"$old\" and .available==true" ceph mgr dump --format json
        ceph_ok
        ;;
    backup)
        ceph_ok
        remote storage01 "$P03/02/backup-host.sh" "$adm" "$ceph_image" "$fsid" "$(required .backup.repository)" "$(required .backup.password_file)" | tee "$ATTEMPT/backup.txt"
        ;;
esac
