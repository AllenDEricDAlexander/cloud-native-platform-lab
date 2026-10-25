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
        repository_file=$(get '.ceph.repository_file // empty' || true)
        if [[ -n $repository_file ]]; then private_file "$repository_file"; fi
        gpg_file=$(get '.ceph.gpg_file // empty' || true)
        if [[ -n $gpg_file ]]; then verify_file "$gpg_file" "$(required .ceph.gpg_sha256)"; fi
        rpm_bundle=$(get '.ceph.rpm_bundle // empty' || true)
        if [[ -n $rpm_bundle ]]; then
            verify_file "$rpm_bundle" "$(required .ceph.rpm_bundle_sha256)"
            [[ $(material ceph | jq -er .sha256) == "$(required .ceph.rpm_bundle_sha256)" ]] || die 'RPM 物料包与主版本锁不符'
        fi
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
            ceph_hostname=$(ceph_host "$host")
            existing=$(ceph orch host ls --format json)
            if jq -e --arg h "$ceph_hostname" 'any(.[];.hostname==$h)' <<< "$existing" >/dev/null; then
                jq -e --arg h "$ceph_hostname" --arg ip "$(host_value "$host" ip)" 'any(.[];.hostname==$h and .addr==$ip)' <<< "$existing" >/dev/null || die '已纳管主机地址不符'
            else ceph orch host add "$ceph_hostname" "$(host_value "$host" ip)"; fi
        done
        ceph orch apply mon --placement="3 $(ceph_host storage01) $(ceph_host storage02) $(ceph_host storage03)"
        ceph orch apply mgr --placement="2 $(ceph_host storage01) $(ceph_host storage02)"
        ceph config set mgr mgr/cephadm/autotune_memory_target_ratio 0.2
        ceph config set osd osd_memory_target_autotune false
        ceph config set osd osd_memory_target "$(required .ceph.osd_memory_target)"
        wait_json 600 '.monmap.num_mons==3 and (.quorum|length)==3 and .mgrmap.available==true' ceph status --format json
        ;;
    osd-plan|osd-apply)
        ruby "$P03/lib/review.rb" devices "$DEVICES" > "$ATTEMPT/budget.json"
        reserved=$(ruby -ryaml -e 'v=YAML.load_file(ARGV[0]).fetch("node_reservations").fetch("ceph_reserved_on_storage_nodes").fetch("memory");abort "无法解析 Ceph 预留" unless v.match?(/\A\d+Gi\z/);puts v.to_i*1024**3' "$REPO/ops/inventory/resources.yaml")
        [[ $(required .ceph.service_memory_budget) -le $reserved ]] || die 'Ceph 预算超过主台账预留，先核对 kubelet/主机实际配置'
        for host in storage01 storage02 storage03; do
            ceph_hostname=$(ceph_host "$host")
            count=$(jq --arg host "$host" '[.devices[]|select(.host==$host)]|length' "$DEVICES")
            jq -en --argjson count "$count" --argjson target "$(required .ceph.osd_memory_target)" --argjson budget "$(required .ceph.service_memory_budget)" '$count*$target+2147483648 <= $budget' >/dev/null || die 'Ceph 内存预算不足，先调整主机与 kubelet 预留'
            expected_devices=()
            while IFS=$'\t' read -r disk bytes; do
                checked=$(remote "$host" "$P03/01/device-check.sh" "$disk" "$bytes" json)
                printf '%s\n' "$checked" > "$ATTEMPT/$host-device-$RANDOM.json"
                expected_devices+=("$(jq -er .target <<< "$checked")")
            done < <(jq -r --arg host "$host" '.devices[]|select(.host==$host)|[.stable_id,.bytes]|@tsv' "$DEVICES")
            expected_paths=$(printf '%s\n' "${expected_devices[@]}" | jq -Rsc 'split("\n")|map(select(length>0))')
            jq --arg host "$host" --arg ceph_host "$ceph_hostname" --arg id "cnpl03-$RUN-$host" '{service_type:"osd",service_id:$id,placement:{hosts:[$ceph_host]},spec:{data_devices:{paths:[.devices[]|select(.host==$host)|.stable_id]}}}' "$DEVICES" > "$ATTEMPT/$host-osd.json"
            # spec 通过管道传给 cephadm；不把盘符拼进 shell 命令。
            remote storage01 "$P03/02/osd-host.sh" "$adm" "$ceph_image" "$fsid" "$action" "$(jq -c . "$ATTEMPT/$host-osd.json")" "$expected_paths" | tee "$ATTEMPT/$host-osd.txt"
            if [[ $action == osd-apply ]]; then
                wait_json 600 "[.[]|select(.daemon_type==\"osd\" and .hostname==\"$ceph_hostname\" and .status_desc==\"running\")]|length==$count" ceph orch ps --format json --refresh
            fi
        done
        if [[ $action == osd-apply ]]; then wait_json 900 '.health.status=="HEALTH_OK"' ceph status --format json; ceph_ok; fi
        ;;
    baseline)
        ceph_ok
        ruby "$P03/lib/review.rb" devices "$DEVICES" > "$ATTEMPT/budget.json"
        failure_domain=$(get '.ceph.failure_domain // "rack"')
        if [[ $failure_domain == rack ]]; then
            for host in storage01 storage02 storage03; do
                domain=$(host_value "$host" actual_hypervisor)
                [[ $domain =~ ^esxi0[1-3]$ ]] || die '未知物理故障域'
                tree=$(ceph osd crush tree --format json)
                if ! jq -e --arg name "$domain" 'any(.nodes[];.name==$name and .type=="rack")' <<< "$tree" >/dev/null; then ceph osd crush add-bucket "$domain" rack; fi
                ceph osd crush move "$domain" root=default
                ceph osd crush move "$(ceph_host "$host")" "rack=$domain"
            done
        fi
        rules=$(ceph osd crush rule dump --format json)
        if jq -e --arg name "$CRUSH_RULE" 'any(.[];.rule_name==$name)' <<< "$rules" >/dev/null; then
            jq -e --arg name "$CRUSH_RULE" --arg domain "$failure_domain" '.[]|select(.rule_name==$name)|any(.steps[];.op=="chooseleaf_firstn" and .type==$domain) and any(.steps[];.op=="take" and .item_name=="default")' <<< "$rules" >/dev/null || die '已有 CRUSH 规则与选择的故障域不符'
        else
            ceph osd crush rule create-replicated "$CRUSH_RULE" default "$failure_domain"
        fi
        ceph config set global osd_pool_default_size 3
        ceph config set global osd_pool_default_min_size 2
        ceph osd tree --format json > "$ATTEMPT/osd-tree.json"
        ceph orch ps --format json > "$ATTEMPT/daemons.json"
        ceph df --format json > "$ATTEMPT/capacity.json"
        ceph_ok
        ;;
    mgr-failover)
        ceph_ok
        before=$(ceph mgr dump --format json)
        printf '%s\n' "$before" > "$ATTEMPT/mgr-before.json"
        [[ $(jq '.standbys|length' <<< "$before") -ge 1 ]] || die '缺少备用 MGR'
        old=$(jq -r .active_name <<< "$before"); ceph mgr fail "$old"
        wait_json 180 ".active_name != \"$old\" and .available==true" ceph mgr dump --format json
        ceph mgr dump --format json > "$ATTEMPT/mgr-after.json"
        ceph_ok
        ;;
    backup)
        ceph_ok
        if [[ $(get '.backup.mode // "remote"') == mac ]]; then
            source "$P03/02/backup-mac.sh"
        else
            remote storage01 "$P03/02/backup-host.sh" "$adm" "$ceph_image" "$fsid" "$(required .backup.repository)" "$(required .backup.password_file)" | tee "$ATTEMPT/backup.txt"
        fi
        ;;
esac
