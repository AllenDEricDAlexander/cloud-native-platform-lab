#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P03/validate.sh" 05 ;;
    deploy|static|write|recreate|access|expand|snapshot|snapshot-policy|clone|reclaim|migrate|stateful|check|cleanup) ;;
    *) die '用法：05/run.sh validate|deploy|static|write|recreate|access|expand|snapshot|snapshot-policy|clone|reclaim|migrate|stateful|check|cleanup' ;;
esac
start 05 "$action"
cluster_gate; ceph_ok
ns=cnpl03-05
namespace "$ns"
probe=$(image probe)
yaml_json "$P03/05/workloads.yaml" | jq --arg image "$probe" --arg rbd "$SC_RBD" --arg fs "$SC_FS" '.items|=map(if .kind=="PersistentVolumeClaim" then .spec.storageClassName=(if .metadata.name=="shared" then $fs else $rbd end) elif .kind=="Pod" then .spec.containers[0].image=$image elif .kind=="StatefulSet" then .spec.template.spec.containers[0].image=$image | .spec.volumeClaimTemplates[0].spec.storageClassName=$rbd else . end)' > "$ATTEMPT/workloads.json"
subset() { jq --argjson names "$1" '.items|=map(select(.metadata.name as $name|$names|index($name)!=null))' "$ATTEMPT/workloads.json" > "$ATTEMPT/subset.json"; apply "$ATTEMPT/subset.json" "$ns"; }
ready() { k -n "$ns" wait --for=condition=Ready "pod/$1" --timeout=240s; }
owned_delete() {
    local kind=$1 name=$2 object
    object=$(k -n "$ns" get "$kind" "$name" -o json)
    jq -e --arg run "$RUN" '.metadata.labels["cnpl.io/run"]==$run' <<< "$object" >/dev/null || die '删除对象归属不符'
    k -n "$ns" delete "$kind" "$name" --wait=true --timeout=180s
}
backend() { remote storage01 "$P03/05/backend-host.sh" "$(required .ceph.cephadm)" "$(image ceph)" "$(required .ceph.fsid)" "$RBD_POOL" "$@"; }
check_data() {
    local expected actual
    expected=$(k -n "$ns" get cm checksums -o json)
    for pod in rbd-writer fs-a fs-b; do
        ready "$pod"
        actual=$(k -n "$ns" exec "$pod" -- sha256sum /data/sequence | awk '{print $1}')
        key=rbd; [[ $pod == rbd-writer ]] || key=shared
        [[ $actual == "$(jq -er --arg key "$key" '.data[$key]' <<< "$expected")" ]] || die "数据校验不符：$pod"
    done
}
restored_pod() {
    local name=$1 claim=$2
    jq -n --arg name "$name" --arg claim "$claim" --arg image "$probe" '{apiVersion:"v1",kind:"Pod",metadata:{name:$name},spec:{securityContext:{runAsUser:1000,fsGroup:1000},containers:[{name:"probe",image:$image,command:["sh","-c","sleep 86400"],resources:{requests:{cpu:"10m",memory:"16Mi"},limits:{memory:"64Mi"}},volumeMounts:[{name:"data",mountPath:"/data"}]}],volumes:[{name:"data",persistentVolumeClaim:{claimName:$claim}}]}}' > "$ATTEMPT/$name.json"
    apply "$ATTEMPT/$name.json" "$ns"; ready "$name"
}
case "$action" in
    deploy) subset '["rbd","shared","exclusive","rbd-writer","fs-a","fs-b"]'; ready rbd-writer; ready fs-a; ready fs-b ;;
    static)
        backend static "static-$RUN"
        pv=cnpl03-$RUN-static
        jq -n --arg pv "$pv" --arg handle "static-$RUN" --arg driver "$ROOK_NS.rbd.csi.ceph.com" --arg pool "$RBD_POOL" --arg ns "$EXTERNAL_NS" '{apiVersion:"v1",kind:"List",items:[{apiVersion:"v1",kind:"PersistentVolume",metadata:{name:$pv},spec:{capacity:{storage:"1Gi"},accessModes:["ReadWriteOnce"],persistentVolumeReclaimPolicy:"Retain",storageClassName:"",csi:{driver:$driver,volumeHandle:$handle,fsType:"ext4",volumeAttributes:{clusterID:$ns,pool:$pool,staticVolume:"true",imageName:$handle,imageFeatures:"layering"},nodeStageSecretRef:{name:"csi-rbd-node",namespace:$ns}}}},{apiVersion:"v1",kind:"PersistentVolumeClaim",metadata:{name:"static"},spec:{volumeName:$pv,storageClassName:"",accessModes:["ReadWriteOnce"],resources:{requests:{storage:"1Gi"}}}},{apiVersion:"v1",kind:"PersistentVolumeClaim",metadata:{name:"pending-size"},spec:{volumeName:$pv,storageClassName:"",accessModes:["ReadWriteOnce"],resources:{requests:{storage:"100Ti"}}}}]}' > "$ATTEMPT/static.json"
        apply "$ATTEMPT/static.json" "$ns"
        restored_pod static-reader static
        k -n "$ns" exec static-reader -- sh -ceu 'printf static-probe > /data/static; sync; test "$(cat /data/static)" = static-probe'
        [[ $(k -n "$ns" get pvc pending-size -o jsonpath='{.status.phase}') == Pending ]] || die '不匹配 PVC 未保持 Pending'
        k -n "$ns" get events --field-selector involvedObject.name=pending-size -o json > "$ATTEMPT/pending-events.json"
        ;;
    write)
        for pod in rbd-writer fs-a; do
            ready "$pod"
            k -n "$ns" exec "$pod" -- sh -ceu 'tmp=$(mktemp /data/.sequence.XXXXXX); i=1; while [ "$i" -le 1000 ]; do printf "%s:%06d\n" "$1" "$i"; i=$((i+1)); done > "$tmp"; if [ -f /data/sequence ]; then cmp "$tmp" /data/sequence; rm "$tmp"; else mv "$tmp" /data/sequence; fi; sync' -- "$RUN"
        done
        rbd_hash=$(k -n "$ns" exec rbd-writer -- sha256sum /data/sequence | awk '{print $1}')
        fs_hash=$(k -n "$ns" exec fs-a -- sha256sum /data/sequence | awk '{print $1}')
        jq -n --arg rbd "$rbd_hash" --arg shared "$fs_hash" '{apiVersion:"v1",kind:"ConfigMap",metadata:{name:"checksums"},data:{rbd:$rbd,shared:$shared}}' > "$ATTEMPT/checksums.json"
        apply "$ATTEMPT/checksums.json" "$ns"; check_data
        ;;
    recreate)
        check_data
        for pod in rbd-writer fs-a fs-b; do owned_delete pod "$pod"; done
        subset '["rbd-writer","fs-a","fs-b"]'; check_data
        ;;
    access)
        check_data
        actual_node=$(k -n "$ns" get pod rbd-writer -o jsonpath='{.spec.nodeName}')
        jq --arg node "$actual_node" '.items=[.items[]|select(.kind=="Pod" and .metadata.name=="rbd-writer")|.metadata.name="rwo-same-node"|.spec.nodeSelector["kubernetes.io/hostname"]=$node]' "$ATTEMPT/workloads.json" > "$ATTEMPT/same.json"
        apply "$ATTEMPT/same.json" "$ns"; ready rwo-same-node
        k -n "$ns" exec rwo-same-node -- sha256sum /data/sequence > "$ATTEMPT/rwo-same-node.txt"
        other=worker01; [[ $actual_node != worker01 ]] || other=worker02
        jq --arg node "$other" '.items[0].metadata.name="rwo-other-node"|.items[0].spec.nodeSelector["kubernetes.io/hostname"]=$node' "$ATTEMPT/same.json" > "$ATTEMPT/other.json"
        apply "$ATTEMPT/other.json" "$ns"
        sleep 20
        [[ $(k -n "$ns" get pod rwo-other-node -o jsonpath='{.status.phase}') == Pending ]] || die 'RWO 跨节点负向用例未保持 Pending'
        k -n "$ns" get events --field-selector involvedObject.name=rwo-other-node -o json > "$ATTEMPT/rwo-events.json"
        jq -e 'any(.items[]; (.message // ""|test("Multi-Attach|already.*attached|exclusive";"i")))' "$ATTEMPT/rwo-events.json" >/dev/null || die 'Pending 原因不是预期的卷访问限制'
        owned_delete pod rwo-other-node; owned_delete pod rwo-same-node
        jq '.items=[.items[]|select(.kind=="Pod" and .metadata.name=="rbd-writer")|.metadata.name="exclusive-a"|.spec.volumes[0].persistentVolumeClaim.claimName="exclusive"]' "$ATTEMPT/workloads.json" > "$ATTEMPT/exclusive.json"
        apply "$ATTEMPT/exclusive.json" "$ns"; ready exclusive-a
        jq '.items[0].metadata.name="exclusive-b"' "$ATTEMPT/exclusive.json" > "$ATTEMPT/exclusive-b.json"
        apply "$ATTEMPT/exclusive-b.json" "$ns"; sleep 15
        k -n "$ns" get events --field-selector involvedObject.name=exclusive-b -o json > "$ATTEMPT/rwop-events.json"
        jq -e 'any(.items[];(.message // ""|test("ReadWriteOncePod|already in use";"i")))' "$ATTEMPT/rwop-events.json" >/dev/null || die '未观察到 RWOP 独占约束'
        owned_delete pod exclusive-b; owned_delete pod exclusive-a
        ;;
    expand)
        check_data
        k -n "$ns" patch pvc rbd --type=merge -p '{"spec":{"resources":{"requests":{"storage":"2Gi"}}}}'
        wait_json 600 '.status.capacity.storage=="2Gi"' k -n "$ns" get pvc rbd -o json
        pv=$(k -n "$ns" get pvc rbd -o jsonpath='{.spec.volumeName}')
        [[ $(k get pv "$pv" -o jsonpath='{.spec.capacity.storage}') == 2Gi ]] || die 'PV 未扩容'
        capacity=$(k -n "$ns" exec rbd-writer -- sh -c 'df -Pk /data | awk "NR==2 {print \$2}"')
        [[ $capacity -gt 1800000 ]] || die '应用文件系统未扩容'
        check_data
        ;;
    snapshot|clone)
        check_data
        if [[ $action == snapshot ]]; then
            jq -n --arg class "cnpl03-$RUN-rbd" '{apiVersion:"snapshot.storage.k8s.io/v1",kind:"VolumeSnapshot",metadata:{name:"rbd-copy"},spec:{volumeSnapshotClassName:$class,source:{persistentVolumeClaimName:"rbd"}}}' > "$ATTEMPT/snapshot.json"
            apply "$ATTEMPT/snapshot.json" "$ns"
            wait_json 600 '.status.readyToUse==true' k -n "$ns" get volumesnapshot rbd-copy -o json
            kind=VolumeSnapshot; source=rbd-copy; group=snapshot.storage.k8s.io
        else kind=PersistentVolumeClaim; source=rbd; group=''; fi
        jq -n --arg class "$SC_RBD" --arg name "$action-restore" --arg kind "$kind" --arg source "$source" --arg group "$group" '{apiVersion:"v1",kind:"PersistentVolumeClaim",metadata:{name:$name},spec:{storageClassName:$class,accessModes:["ReadWriteOnce"],resources:{requests:{storage:"2Gi"}},dataSource:{apiGroup:$group,kind:$kind,name:$source}}}' > "$ATTEMPT/restore.json"
        apply "$ATTEMPT/restore.json" "$ns"; restored_pod "$action-reader" "$action-restore"
        expected=$(k -n "$ns" get cm checksums -o jsonpath='{.data.rbd}')
        [[ $(k -n "$ns" exec "$action-reader" -- sha256sum /data/sequence | awk '{print $1}') == "$expected" ]] || die '恢复/克隆数据不符'
        ;;
    snapshot-policy)
        check_data; backup_gate
        for policy in Delete Retain; do
            name=policy-$(tr '[:upper:]' '[:lower:]' <<< "$policy")
            k get volumesnapshotclass "cnpl03-$RUN-rbd" -o json | jq --arg name "cnpl03-$RUN-$name" --arg policy "$policy" 'del(.metadata.uid,.metadata.resourceVersion,.metadata.creationTimestamp,.metadata.managedFields)|.metadata.name=$name|.deletionPolicy=$policy' > "$ATTEMPT/$name-class.json"
            apply "$ATTEMPT/$name-class.json" ''
            backend state unused > "$ATTEMPT/$name-before.json"
            jq -n --arg name "$name" --arg class "cnpl03-$RUN-$name" '{apiVersion:"snapshot.storage.k8s.io/v1",kind:"VolumeSnapshot",metadata:{name:$name},spec:{volumeSnapshotClassName:$class,source:{persistentVolumeClaimName:"rbd"}}}' > "$ATTEMPT/$name.json"
            apply "$ATTEMPT/$name.json" "$ns"
            wait_json 600 '.status.readyToUse==true' k -n "$ns" get volumesnapshot "$name" -o json
            content=$(k -n "$ns" get volumesnapshot "$name" -o jsonpath='{.status.boundVolumeSnapshotContentName}')
            k get volumesnapshotcontent "$content" -o json > "$ATTEMPT/$name-content.json"
            backend state unused > "$ATTEMPT/$name-created.json"
            if cmp -s "$ATTEMPT/$name-before.json" "$ATTEMPT/$name-created.json"; then die '未观察到后端快照对象，不能确认回收策略'; fi
            owned_delete volumesnapshot "$name"
            if [[ $policy == Delete ]]; then
                k wait --for=delete "volumesnapshotcontent/$content" --timeout=300s
                end=$((SECONDS+300))
                while :; do
                    backend state unused > "$ATTEMPT/$name-after.json"
                    cmp -s "$ATTEMPT/$name-before.json" "$ATTEMPT/$name-after.json" && break
                    ((SECONDS<end)) || die '后端未回到快照前状态；存在残留或并发变化，停止调查'
                    sleep 5
                done
            else
                k get volumesnapshotcontent "$content" -o json > "$ATTEMPT/$name-retained.json"
                backend state unused > "$ATTEMPT/$name-after.json"
                cmp "$ATTEMPT/$name-created.json" "$ATTEMPT/$name-after.json"
            fi
        done
        ;;
    reclaim)
        backup_gate
        for policy in Delete Retain; do
            name=reclaim-$(tr '[:upper:]' '[:lower:]' <<< "$policy")
            k get sc "$SC_RBD" -o json | jq --arg name "$SC_RBD-$name" --arg policy "$policy" 'del(.metadata.uid,.metadata.resourceVersion,.metadata.creationTimestamp,.metadata.managedFields)|.metadata.name=$name|.metadata.annotations["storageclass.kubernetes.io/is-default-class"]="false"|.reclaimPolicy=$policy' > "$ATTEMPT/$name-sc.json"
            apply "$ATTEMPT/$name-sc.json" ''
            jq -n --arg name "$name" --arg class "$SC_RBD-$name" '{apiVersion:"v1",kind:"PersistentVolumeClaim",metadata:{name:$name},spec:{storageClassName:$class,accessModes:["ReadWriteOnce"],resources:{requests:{storage:"1Gi"}}}}' > "$ATTEMPT/$name.json"
            apply "$ATTEMPT/$name.json" "$ns"; restored_pod "$name-writer" "$name"
            k -n "$ns" exec "$name-writer" -- sh -ceu 'printf reclaim > /data/probe; sync'
            pvc=$(k -n "$ns" get pvc "$name" -o json); pv=$(jq -r .spec.volumeName <<< "$pvc")
            k get pv "$pv" -o json > "$ATTEMPT/$name-pv.json"
            backend_image=$(backend find-pv "$pv"); printf '%s\n' "$backend_image" > "$ATTEMPT/$name-backend.txt"
            owned_delete pod "$name-writer"; owned_delete pvc "$name"
            if [[ $policy == Delete ]]; then
                k wait --for=delete "pv/$pv" --timeout=300s
                end=$((SECONDS+300)); while ! backend absent "$backend_image"; do ((SECONDS<end)) || die 'Delete 策略后端仍存在'; sleep 5; done
            else
                wait_json 180 '.status.phase=="Released"' k get pv "$pv" -o json
                backend exists "$backend_image" || die 'Retain 后端意外消失'
            fi
        done
        ;;
    migrate)
        check_data
        old=$(k -n "$ns" get pod rbd-writer -o jsonpath='{.spec.nodeName}')
        target=worker01; [[ $old != worker01 ]] || target=worker02
        owned_delete pod rbd-writer
        pv=$(k -n "$ns" get pvc rbd -o jsonpath='{.spec.volumeName}')
        wait_json 180 "all(.items[]; .spec.source.persistentVolumeName!=\"$pv\" or .status.attached!=true)" k get volumeattachments -o json
        jq --arg node "$target" '.items=[.items[]|select(.kind=="Pod" and .metadata.name=="rbd-writer")|.spec.nodeSelector["kubernetes.io/hostname"]=$node]' "$ATTEMPT/workloads.json" > "$ATTEMPT/migrate.json"
        apply "$ATTEMPT/migrate.json" "$ns"; check_data
        [[ $(k -n "$ns" get pod rbd-writer -o jsonpath='{.spec.nodeName}') == "$target" ]] || die '未迁移至目标节点'
        ;;
    stateful)
        subset '["ordinal"]'
        k -n "$ns" rollout status statefulset/ordinal --timeout=300s
        for ordinal in 0 1; do k -n "$ns" exec "ordinal-$ordinal" -- cat /data/identity | grep -Fx "ordinal-$ordinal"; done
        k -n "$ns" scale statefulset ordinal --replicas=1
        k -n "$ns" wait --for=delete pod/ordinal-1 --timeout=180s
        k -n "$ns" get pvc data-ordinal-1 -o json > "$ATTEMPT/retained-ordinal.json"
        owned_delete statefulset ordinal
        subset '["ordinal"]'; k -n "$ns" rollout status statefulset/ordinal --timeout=300s
        for ordinal in 0 1; do k -n "$ns" exec "ordinal-$ordinal" -- cat /data/identity | grep -Fx "ordinal-$ordinal"; done
        ;;
    check)
        check_data
        k -n "$ns" get pvc,pods,volumesnapshots -o wide > "$ATTEMPT/lifecycle.txt"
        k get pv -o json > "$ATTEMPT/pvs.json"
        ;;
    cleanup)
        # 只停工作负载，保留 PVC、快照、PV、后端与校验账本。
        k -n "$ns" delete pod,statefulset -l "cnpl.io/run=$RUN" --wait=true --timeout=180s
        k -n "$ns" get pvc,volumesnapshots -o json > "$ATTEMPT/retained-data.json"
        ;;
esac
