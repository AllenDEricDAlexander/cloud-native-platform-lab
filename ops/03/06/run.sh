#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P03/validate.sh" 06 ;;
    osd-stop|osd-out|recover|csi|csi-node|quota|maintenance-plan|vm-observe|vm-reboot|managed-preflight|managed-deploy|managed-services|managed-check|managed-cleanup) ;;
    *) die '用法：06/run.sh validate|osd-stop|osd-out|recover|csi|csi-node|quota|maintenance-plan|vm-observe|vm-reboot|managed-{preflight,deploy,services,check,cleanup}' ;;
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
if [[ $action != maintenance-plan ]]; then
    pointer=$P03/05/records/$RUN/latest-backup.json
    verify_file "$(jq -er .file "$pointer")" "$(jq -er .sha256 "$pointer")"
    jq -e --arg run "$RUN" --arg uid "$(required .kubernetes.cluster_uid)" --arg fsid "$(required .ceph.fsid)" '.run==$run and .cluster_uid==$uid and .fsid==$fsid and .data_file_restore_verified==true' "$(jq -er .file "$pointer")" >/dev/null || die '缺少本批 PVC 数据的独立读回证据'
    k -n cnpl03-05 get pvc rbd shared -o json > "$ATTEMPT/claims.json"
    jq -en --slurpfile receipt "$(jq -er .file "$pointer")" --slurpfile live "$ATTEMPT/claims.json" '($receipt[0].claims|sort_by(.name))==([$live[0].items[]|{name:.metadata.name,uid:.metadata.uid,volume:.spec.volumeName}]|sort_by(.name))' >/dev/null || die '数据备份的 PVC 身份已变化'
fi
io_check() {
    local expected actual
    expected=$(k -n cnpl03-05 get cm checksums -o jsonpath='{.data.rbd}')
    actual=$(k -n cnpl03-05 exec rbd-writer -- sh -ceu 'printf "%s\n" "$(date +%s)" >> /data/fault-sequence; sync; sha256sum /data/sequence' | awk '{print $1}')
    [[ -n $expected && $actual == "$expected" ]] || die '故障窗口业务数据校验失败'
}
case "$action" in
    vm-reboot) source "$P03/06/vm-reboot.sh" ;;
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
        wait_json 90 "any(.osds[];.osd==$id and .up==0)" ceph osd dump --format json
        ceph osd dump --format json > "$ATTEMPT/osd-injected.json"
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
        driver=$ROOK_NS.rbd.csi.ceph.com
        owned=$(k -n "$ROOK_NS" get driver "$driver" -o json)
        jq -e '.metadata.annotations["meta.helm.sh/release-name"]=="cnpl03-ceph-csi"' <<< "$owned" >/dev/null || die 'CSI Driver 不属于本 release'
        deployment=$(k -n "$ROOK_NS" get deploy "$driver-ctrlplugin" -o json)
        jq -e --arg uid "$(jq -r .metadata.uid <<< "$owned")" 'any(.metadata.ownerReferences[]?;.uid==$uid and .kind=="Driver") and .status.availableReplicas>=2' <<< "$deployment" >/dev/null || die 'CSI controller 归属或健康副本不符'
        replicas=$(k -n "$ROOK_NS" get rs -o json | jq -c --arg uid "$(jq -r .metadata.uid <<< "$deployment")" '[.items[]|select(any(.metadata.ownerReferences[]?;.uid==$uid))|.metadata.uid]')
        pod=$(k -n "$ROOK_NS" get pods -o json | jq -er --argjson replicas "$replicas" '[.items[]|select(.status.phase=="Running" and any(.metadata.ownerReferences[]?;.uid as $uid|$replicas|index($uid)!=null))]|sort_by(.metadata.name)|.[0].metadata.name')
        k -n "$ROOK_NS" get pod "$pod" -o json > "$ATTEMPT/controller-before.json"
        k -n "$ROOK_NS" delete pod "$pod" --wait=true --timeout=120s
        io_check
        k -n "$ROOK_NS" rollout status "deployment/$driver-ctrlplugin" --timeout=300s
        printf '本轮验证 controller Pod 重建与已有挂载；新卷供应另跑 04 smoke，并保留是否实际捕获中断的事件。\n'
        ;;
    csi-node)
        io_check
        # 用户态 NBD 的插件重建先选没有活动 PVC 的节点，避免杀掉已有映射进程。
        node=$(host_value cp01 fqdn)
        k get pods -A --field-selector "spec.nodeName=$node" -o json | jq -e 'all(.items[].spec.volumes[]?;has("persistentVolumeClaim")|not)' >/dev/null || die '目标节点存在活动 PVC，不能执行空闲节点插件用例'
        driver=$ROOK_NS.rbd.csi.ceph.com
        owned=$(k -n "$ROOK_NS" get driver "$driver" -o json)
        jq -e '.metadata.annotations["meta.helm.sh/release-name"]=="cnpl03-ceph-csi"' <<< "$owned" >/dev/null || die 'CSI Driver 不属于本 release'
        ds=$(k -n "$ROOK_NS" get ds "$driver-nodeplugin" -o json)
        jq -e --arg uid "$(jq -r .metadata.uid <<< "$owned")" 'any(.metadata.ownerReferences[]?;.uid==$uid and .kind=="Driver")' <<< "$ds" >/dev/null || die 'CSI DaemonSet 归属不符'
        uid=$(jq -r .metadata.uid <<< "$ds")
        pod=$(k -n "$ROOK_NS" get pods -o json | jq -er --arg node "$node" --arg uid "$uid" '[.items[]|select(.spec.nodeName==$node and any(.metadata.ownerReferences[]?;.uid==$uid))]|if length==1 then .[0].metadata.name else error("节点插件不是唯一对象") end')
        k -n "$ROOK_NS" get pod "$pod" -o json > "$ATTEMPT/node-plugin-before.json"
        k -n "$ROOK_NS" delete pod "$pod" --wait=true --timeout=120s
        io_check
        k -n "$ROOK_NS" rollout status "daemonset/$driver-nodeplugin" --timeout=300s
        jq -n --arg node "$node" --arg image "$(image probe)" '{apiVersion:"v1",kind:"Pod",metadata:{name:"csi-recovery-cp01"},spec:{nodeSelector:{"kubernetes.io/hostname":$node},tolerations:[{operator:"Exists",effect:"NoSchedule"}],containers:[{name:"probe",image:$image,command:["sh","-ceu","test \"$(cat /data/probe)\" = phase03; sleep 3600"],resources:{requests:{cpu:"10m",memory:"16Mi"},limits:{memory:"64Mi"}},volumeMounts:[{name:"data",mountPath:"/data"}]}],volumes:[{name:"data",persistentVolumeClaim:{claimName:"probe-rbd-cp01"}}]}}' > "$ATTEMPT/csi-recovery.json"
        apply "$ATTEMPT/csi-recovery.json" cnpl03-04
        k -n cnpl03-04 wait --for=condition=Ready pod/csi-recovery-cp01 --timeout=180s
        k -n cnpl03-04 exec csi-recovery-cp01 -- cat /data/probe | grep -Fx phase03
        k -n cnpl03-04 get pod csi-recovery-cp01 -o json > "$ATTEMPT/remounted.json"
        k -n cnpl03-04 delete pod csi-recovery-cp01 --wait=true --timeout=120s
        k -n cnpl03-05 get events -o json > "$ATTEMPT/volume-events.json"
        printf 'PASS 空闲节点插件重建后重新挂载并读回；未注入活动用户态映射进程崩溃。\n'
        ;;
    quota)
        remote storage01 "$P03/06/quota-host.sh" "$(required .ceph.cephadm)" "$(image ceph)" "$(required .ceph.fsid)" "$RUN" "$CRUSH_RULE" | tee "$ATTEMPT/quota.txt"
        ;;
    maintenance-plan)
        ceph osd dump --format json > "$ATTEMPT/flags-before.json"
        k get nodes -o json > "$ATTEMPT/nodes-before.json"
        printf '%s\n' '维护顺序：确认备份/多数派/ok-to-stop → 保存原标志和调度状态 → drain 选定 storage Worker → cephadm host maintenance → 经批准的客户机内重启 → exit maintenance → 恢复原调度状态 → PG/哈希/标志复核。'
        printf '%s\n' 'noout/恢复限速如需修改，先记录原值、配置独立的到期撤销任务。三域失一域不能恢复完整三副本。此入口只出计划，不改变标志。'
        ;;
    vm-observe)
        [[ $(required .fault.approved) == true ]] || die 'VM 故障窗口未批准'
        printf '按已审核计划在选定客户机内操作；本入口仅有界观测，不调用虚拟化接口。\n'
        end=$((SECONDS+60))
        while ((SECONDS<end)); do
            io_check
            ceph status --format json > "$ATTEMPT/vm-$SECONDS.json"
            sleep 3
        done
        ;;
esac
