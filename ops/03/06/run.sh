#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P03/validate.sh" 06 ;;
    osd-stop|osd-out|recover|csi|csi-node|quota|maintenance-plan|vm-observe|managed-preflight|managed-deploy|managed-services|managed-check|managed-cleanup) ;;
    *) die '用法：06/run.sh validate|osd-stop|osd-out|recover|csi|quota|maintenance-plan|vm-observe|managed-{preflight,deploy,services,check,cleanup}' ;;
esac
start 06 "$action"
backup_gate; cluster_identity_gate
recovery=$P03/06/records/$RUN/recovery.json
recover_osd() {
    local saved id
    [[ -f $recovery ]] || return 1
    saved=$(cat "$recovery") || return 1
    jq -e --arg run "$RUN" --arg fsid "$(required .ceph.fsid)" --arg uid "$(required .kubernetes.cluster_uid)" '.run==$run and .fsid==$fsid and .cluster_uid==$uid' <<< "$saved" >/dev/null || return 1
    id=$(jq -er .osd_id <<< "$saved") || return 1
    ceph orch daemon start "osd.$id" || return 1
    ceph osd in "$id" || return 1
    wait_json 900 '.health.status=="HEALTH_OK"' ceph status --format json || return 1
    remote storage01 "$P03/06/watchdog-host.sh" "$(required .ceph.cephadm)" "$(image ceph)" "$(required .ceph.fsid)" "$RUN" "$id" "$(required .fault.watchdog_seconds)" disarm || return 1
    cp "$recovery" "$ATTEMPT/recovered.json" || return 1
    rm -f "$recovery" || return 1
}
if [[ $action == recover ]]; then recover_osd; exit; fi
cluster_gate; ceph_ok
if [[ $action == managed-* ]]; then source "$P03/06/managed.sh"; exit; fi
io_check() {
    local expected actual
    expected=$(k -n cnpl03-05 get cm checksums -o jsonpath='{.data.rbd}')
    actual=$(k -n cnpl03-05 exec rbd-writer -- sh -ceu 'printf "%s\n" "$(date +%s)" >> /data/fault-sequence; sync; sha256sum /data/sequence' | awk '{print $1}')
    [[ -n $expected && $actual == "$expected" ]] || die '故障窗口业务数据校验失败'
}
case "$action" in
    osd-stop|osd-out)
        [[ $(required .fault.approved) == true ]] || die '单 OSD 故障未批准'
        [[ ! -e $recovery ]] || die '存在待恢复记录，先 recover'
        id=$(required .fault.osd_id); [[ $id =~ ^[0-9]+$ ]] || die 'OSD ID 非法'
        ceph osd dump --format json | jq -e --argjson id "$id" 'any(.osds[];.osd==$id and .up==1 and .in==1)' >/dev/null || die '目标 OSD 初始状态不符'
        ceph osd ok-to-stop "$id"
        io_check
        jq -n --arg run "$RUN" --arg fsid "$(required .ceph.fsid)" --arg uid "$(required .kubernetes.cluster_uid)" --argjson id "$id" '{run:$run,fsid:$fsid,cluster_uid:$uid,osd_id:$id}' > "$recovery"
        RECOVERY_FUNCTION=recover_osd
        remote storage01 "$P03/06/watchdog-host.sh" "$(required .ceph.cephadm)" "$(image ceph)" "$(required .ceph.fsid)" "$RUN" "$id" "$(required .fault.watchdog_seconds)" arm | tee "$ATTEMPT/watchdog.txt"
        ceph orch daemon stop "osd.$id"
        if [[ $action == osd-out ]]; then ceph osd out "$id"; fi
        end=$((SECONDS+$(required .fault.duration_seconds)))
        while ((SECONDS<end)); do
            io_check
            status=$(ceph status --format json)
            printf '%s\n' "$status" > "$ATTEMPT/health-$SECONDS.json"
            jq -e '.health.status!="HEALTH_ERR"' <<< "$status" >/dev/null || die '故障窗口触达 HEALTH_ERR，恢复'
            ceph df --format json | jq -e --argjson limit "$(required .ceph.max_used_percent)" '.stats.total_used_raw_ratio*100 < $limit' >/dev/null || die '触达容量阈值，恢复'
            sleep 3
        done
        recover_osd; RECOVERY_FUNCTION=''; io_check; ceph_ok
        ;;
    csi)
        io_check
        # 选择一个本 release 的 CSI provisioner Pod；不缩容整套驱动。
        pods=$(k -n "$ROOK_NS" get pods -o json)
        pod=$(jq -er '[.items[]|select(.metadata.labels.app=="csi-rbdplugin-provisioner")]|sort_by(.metadata.name)|.[0].metadata.name' <<< "$pods")
        [[ $(jq --arg pod "$pod" '[.items[]|select(.metadata.labels.app=="csi-rbdplugin-provisioner" and .status.phase=="Running")]|length' <<< "$pods") -ge 2 ]] || die '缺少健康的 CSI 副本，停止'
        k -n "$ROOK_NS" delete pod "$pod" --wait=true --timeout=120s
        io_check
        k -n "$ROOK_NS" rollout status deployment/csi-rbdplugin-provisioner --timeout=300s
        printf '本轮验证 controller Pod 重建与已有挂载；新卷供应另跑 04 smoke，并保留是否实际捕获中断的事件。\n'
        ;;
    csi-node)
        io_check
        node=$(k -n cnpl03-05 get pod rbd-writer -o jsonpath='{.spec.nodeName}')
        ds=$(k -n "$ROOK_NS" get ds csi-rbdplugin -o json)
        jq -e '.metadata.annotations["meta.helm.sh/release-name"]=="cnpl03-rook"' <<< "$ds" >/dev/null || die 'CSI DaemonSet 不属于本 release'
        uid=$(jq -r .metadata.uid <<< "$ds")
        pod=$(k -n "$ROOK_NS" get pods -o json | jq -er --arg node "$node" --arg uid "$uid" '[.items[]|select(.spec.nodeName==$node and any(.metadata.ownerReferences[]?;.uid==$uid))]|if length==1 then .[0].metadata.name else error("节点插件不是唯一对象") end')
        k -n "$ROOK_NS" get pod "$pod" -o json > "$ATTEMPT/node-plugin-before.json"
        k -n "$ROOK_NS" delete pod "$pod" --wait=true --timeout=120s
        io_check
        k -n "$ROOK_NS" rollout status daemonset/csi-rbdplugin --timeout=300s
        k -n cnpl03-05 get events -o json > "$ATTEMPT/volume-events.json"
        printf 'PASS 单节点插件重建与已有挂载；新挂载/供应窗口另跑 04 smoke，未捕获的中断不判定为故障已验证。\n'
        ;;
    quota)
        remote storage01 "$P03/06/quota-host.sh" "$(required .ceph.cephadm)" "$(image ceph)" "$(required .ceph.fsid)" "$RUN" | tee "$ATTEMPT/quota.txt"
        ;;
    maintenance-plan)
        ceph osd dump --format json > "$ATTEMPT/flags-before.json"
        k get nodes -o json > "$ATTEMPT/nodes-before.json"
        printf '%s\n' '维护顺序：确认备份/多数派/ok-to-stop → 保存原标志和调度状态 → drain 选定 storage Worker → cephadm host maintenance → vSphere 单 VM 重启 → exit maintenance → 恢复原调度状态 → PG/哈希/标志复核。'
        printf '%s\n' 'noout/恢复限速如需修改，先记录原值、配置独立的到期撤销任务。三域失一域不能恢复完整三副本。此入口只出计划，不改变标志。'
        ;;
    vm-observe)
        [[ $(required .fault.approved) == true ]] || die 'VM 故障窗口未批准'
        printf '请按已审核维护计划在 vSphere 控制台操作单台 VM；本入口仅有界观测，不控制电源。\n'
        end=$((SECONDS+60))
        while ((SECONDS<end)); do
            io_check
            ceph status --format json > "$ATTEMPT/vm-$SECONDS.json"
            sleep 3
        done
        ;;
esac
