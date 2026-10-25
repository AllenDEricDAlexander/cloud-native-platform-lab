#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P03/validate.sh" 04 ;;
    export|operator|connect|network|classes|snapshot|smoke|default|check) ;;
    *) die '用法：04/run.sh validate|export|operator|connect|network|classes|snapshot|smoke|default|check' ;;
esac
start 04 "$action"
backup_gate; ceph_ok; cluster_gate
namespace cnpl03-04
case "$action" in
    export)
        material rook >/dev/null
        remote storage01 "$P03/04/export-host.sh" "$(required .ceph.cephadm)" "$(image ceph)" "$(required .ceph.fsid)" "$(required .rook.export_script_file)" "$(required .rook.export_script_sha256)" "$(get '.rook.export_arguments|tojson')" "$RUN" "$RBD_POOL" "$CEPH_FS" | tee "$ATTEMPT/export-location.txt"
        ;;
    operator)
        material ceph_csi >/dev/null
        values=$(required .rook.values_file); verify_file "$values" "$(required .rook.values_sha256)"
        # values 必须包含 operator-values.yaml 的安全设置及本版本所有 CSI 镜像 Digest。
        chart cnpl03-rook rook "$ROOK_NS" "$values"
        # Rook 1.21 的 CSI Driver/OperatorConfig/RBAC 由独立驱动 Chart 声明。
        component_chart cnpl03-ceph-csi ceph_csi "$ROOK_NS"
        ;;
    connect)
        keytype=$(required .ceph.cephx_key_type)
        [[ $keytype == aes || $keytype == aes256k ]] || die '必须明确选择 CephX 密钥类型'
        connection=$(required .rook.connection_file); private_file "$connection"
        verify_file "$connection" "$(required .rook.connection_sha256)"
        ruby "$P03/04/connection-check.rb" "$connection" "$(required .ceph.fsid)"
        namespace "$EXTERNAL_NS"
        apply "$P03/04/external-rbac.yaml" "$EXTERNAL_NS"
        # Rook 会接管并刷新 MON 地址；重试时保留属于本 CephCluster UID 的动态端点。
        live_cluster=$(k -n "$EXTERNAL_NS" get cephcluster external --ignore-not-found -o json)
        live_endpoints=$(k -n "$EXTERNAL_NS" get cm rook-ceph-mon-endpoints --ignore-not-found -o json)
        if [[ -n $live_cluster && -n $live_endpoints ]]; then
            jq -e --arg run "$RUN" '.metadata.labels["cnpl.io/run"]==$run' <<< "$live_cluster" >/dev/null || die '外部 CephCluster 归属不符'
            if jq -e --arg uid "$(jq -r .metadata.uid <<< "$live_cluster")" 'any(.metadata.ownerReferences[]?;.kind=="CephCluster" and .uid==$uid)' <<< "$live_endpoints" >/dev/null; then
                private_temp
                jq '.items|=map(select(.metadata.name!="rook-ceph-mon-endpoints"))' "$connection" > "$PRIVATE_TEMP_ROOT/connection.json"
                connection=$PRIVATE_TEMP_ROOT/connection.json
            fi
        fi
        apply "$connection" "$EXTERNAL_NS" >/dev/null
        jq -n --arg image "$(image ceph)" --arg keytype "$keytype" '{apiVersion:"ceph.rook.io/v1",kind:"CephCluster",metadata:{name:"external",namespace:"cnpl03-external"},spec:{external:{enable:true},dataDirHostPath:"/var/lib/rook",cephVersion:{image:$image},crashCollector:{disable:true},monitoring:{enabled:false},csi:{skipUserCreation:true},security:{cephx:{csi:{keyType:$keytype}}}}}' > "$ATTEMPT/external.json"
        apply "$ATTEMPT/external.json" "$EXTERNAL_NS"
        wait_json 600 '.status.phase=="Connected" or .status.state=="Connected"' k -n "$EXTERNAL_NS" get cephcluster external -o json
        ;;
    network)
        export ANSIBLE_CONFIG="$REPO/ops/00-preparation/ansible/ansible.cfg"
        "${CNPL03_ANSIBLE:-$HOME/.venvs/cnpl-ansible/bin/ansible-playbook}" "$P03/04/network-playbook.yml" 2>&1 | tee "$ATTEMPT/mon-network.txt"
        ;;
    classes)
        jq -n --arg rbd "$SC_RBD" --arg fs "$SC_FS" --arg pool "$RBD_POOL" --arg cephfs "$CEPH_FS" --arg prefix "$ROOK_NS" --arg ns "$EXTERNAL_NS" '
          def sc($name;$driver;$parameters): {apiVersion:"storage.k8s.io/v1",kind:"StorageClass",metadata:{name:$name,annotations:{"storageclass.kubernetes.io/is-default-class":"false"}},provisioner:($prefix+"."+$driver+".csi.ceph.com"),parameters:($parameters+{clusterID:$ns,"csi.storage.k8s.io/provisioner-secret-namespace":$ns,"csi.storage.k8s.io/node-stage-secret-namespace":$ns,"csi.storage.k8s.io/controller-expand-secret-namespace":$ns}),reclaimPolicy:"Retain",allowVolumeExpansion:true,volumeBindingMode:"Immediate"};
          {apiVersion:"v1",kind:"List",items:[sc($rbd;"rbd";{pool:$pool,imageFeatures:"layering","csi.storage.k8s.io/fstype":"ext4","csi.storage.k8s.io/provisioner-secret-name":"csi-rbd-provisioner","csi.storage.k8s.io/controller-expand-secret-name":"csi-rbd-provisioner","csi.storage.k8s.io/node-stage-secret-name":"csi-rbd-node"}),sc($fs;"cephfs";{fsName:$cephfs,pool:($cephfs+"-data"),"csi.storage.k8s.io/provisioner-secret-name":"csi-cephfs-provisioner","csi.storage.k8s.io/controller-expand-secret-name":"csi-cephfs-provisioner","csi.storage.k8s.io/node-stage-secret-name":"csi-cephfs-node"})]}' > "$ATTEMPT/classes.json"
        jq --arg rbd "$(get '.ceph.rbd_mounter // "krbd"')" --arg fs "$(get '.ceph.cephfs_mounter // "kernel"')" '.items[0].parameters.mounter=$rbd | .items[1].parameters.mounter=$fs' "$ATTEMPT/classes.json" > "$ATTEMPT/classes-mounters.json"
        apply "$ATTEMPT/classes-mounters.json" ''
        ;;
    snapshot)
        info=$(material snapshot_controller)
        manifest=$(jq -er .file <<< "$info"); verify_file "$manifest" "$(jq -er .sha256 <<< "$info")"
        ruby "$P03/lib/review.rb" images "$manifest"
        namespace cnpl03-snapshot
        apply "$manifest" cnpl03-snapshot
        for crd in volumesnapshots.snapshot.storage.k8s.io volumesnapshotcontents.snapshot.storage.k8s.io volumesnapshotclasses.snapshot.storage.k8s.io; do k wait --for=condition=Established "crd/$crd" --timeout=120s; done
        jq -n --arg name "cnpl03-$RUN-rbd" --arg driver "$ROOK_NS.rbd.csi.ceph.com" --arg ns "$EXTERNAL_NS" '{apiVersion:"snapshot.storage.k8s.io/v1",kind:"VolumeSnapshotClass",metadata:{name:$name},driver:$driver,deletionPolicy:"Retain",parameters:{clusterID:$ns,"csi.storage.k8s.io/snapshotter-secret-name":"csi-rbd-provisioner","csi.storage.k8s.io/snapshotter-secret-namespace":$ns}}' > "$ATTEMPT/snapshotclass.json"
        apply "$ATTEMPT/snapshotclass.json" ''
        ;;
    smoke)
        for driver in rbd cephfs; do
            class=$SC_RBD; access=ReadWriteOnce
            if [[ $driver == cephfs ]]; then class=$SC_FS; access=ReadWriteMany; fi
            for host in $(ruby -ryaml -e 'puts YAML.load_file(ARGV[0]).fetch("kubernetes_nodes").map{|h|h["id"]}' "$REPO/ops/inventory/hosts.yaml"); do
                node=$(host_value "$host" fqdn)
                name=probe-$driver-$host
                jq -n --arg name "$name" --arg class "$class" --arg access "$access" --arg node "$node" --arg image "$(image probe)" '{apiVersion:"v1",kind:"List",items:[{apiVersion:"v1",kind:"PersistentVolumeClaim",metadata:{name:$name},spec:{storageClassName:$class,accessModes:[$access],resources:{requests:{storage:"1Gi"}}}},{apiVersion:"v1",kind:"Pod",metadata:{name:$name},spec:{nodeSelector:{"kubernetes.io/hostname":$node},tolerations:[{operator:"Exists",effect:"NoSchedule"}],restartPolicy:"Never",containers:[{name:"probe",image:$image,command:["sh","-ceu","test -f /data/probe || printf phase03 > /data/probe; sync; test \"$(cat /data/probe)\" = phase03; sleep 3600"],resources:{requests:{cpu:"10m",memory:"16Mi"},limits:{memory:"64Mi"}},volumeMounts:[{name:"data",mountPath:"/data"}]}],volumes:[{name:"data",persistentVolumeClaim:{claimName:$name}}]}}]}' > "$ATTEMPT/$name.json"
                apply "$ATTEMPT/$name.json" cnpl03-04
                k -n cnpl03-04 wait --for=condition=Ready "pod/$name" --timeout=180s
                k -n cnpl03-04 exec "$name" -- cat /data/probe | grep -Fx phase03
                k -n cnpl03-04 get pvc "$name" -o json > "$ATTEMPT/$name-pvc.json"
                k -n cnpl03-04 delete pod "$name" --wait=true --timeout=120s
            done
        done
        ;;
    default)
        current=$(k get sc -o json)
        jq -e --arg name "$SC_RBD" 'all(.items[]; .metadata.name==$name or (.metadata.annotations["storageclass.kubernetes.io/is-default-class"] // "false")!="true")' <<< "$current" >/dev/null || die '已有其他默认 StorageClass，停止而不修改'
        jq -e --arg name "$SC_RBD" --arg run "$RUN" 'any(.items[];.metadata.name==$name and .metadata.labels["cnpl.io/run"]==$run)' <<< "$current" >/dev/null || die 'StorageClass 归属不符'
        k annotate sc "$SC_RBD" storageclass.kubernetes.io/is-default-class=true --overwrite
        ;;
    check)
        k -n "$ROOK_NS" get deploy,ds,pods -o wide > "$ATTEMPT/csi.txt"
        k get csidrivers -o json > "$ATTEMPT/drivers.json"
        jq -e --arg rbd "$ROOK_NS.rbd.csi.ceph.com" --arg fs "$ROOK_NS.cephfs.csi.ceph.com" 'any(.items[];.metadata.name==$rbd) and any(.items[];.metadata.name==$fs)' "$ATTEMPT/drivers.json" >/dev/null
        k -n "$EXTERNAL_NS" get pods -o json | jq -e 'all(.items[]; (.metadata.labels.app // "" | test("rook-ceph-(mon|osd|mgr|mds|rgw)$"))|not)' >/dev/null || die '外部消费空间出现 Ceph 守护进程'
        k get storageclasses -o json > "$ATTEMPT/classes.json"
        ;;
esac
