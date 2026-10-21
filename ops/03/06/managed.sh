#!/usr/bin/env bash
# 被 06/run.sh source；必须明确给出另一集群和独立设备，不推断目标。
set -euo pipefail
main_inputs=$INPUTS
main_uid=$(required .kubernetes.cluster_uid)
main_fsid=$(required .ceph.fsid)
[[ $(required .managed.approved) == true ]] || die '独立 Rook 对照尚未批准'
managed_inputs=$(required .managed.inputs_file)
managed_devices=$(required .managed.devices_file)
[[ -f $managed_inputs && -f $managed_devices ]] || die '缺少独立对照台账'
INPUTS=$managed_inputs
[[ $(required .run_id) == "$RUN" ]] || die '对照配置必须沿用本批 run_id'
[[ $(required .kubernetes.cluster_uid) != "$main_uid" ]] || die '对照必须指定独立 Kubernetes 集群'
cluster_identity_gate
ruby -rjson -rdigest -e '
 d=JSON.parse(File.read(ARGV[0])).fetch("devices"); p=JSON.parse(File.read(ARGV[1])).fetch("devices");
 abort "需要三独立物理域和主机" unless d.map{|x|x["hypervisor"]}.compact.uniq.size==3 && d.map{|x|x["host"]}.uniq.size==3;
 d.each{|x| abort "未批准/未知对照盘" unless x["approved"]==true && x["contains_data"]==false && x["bytes"].is_a?(Integer) && x["bytes"]>0 && x["stable_id"].match?(%r{\A/dev/disk/by-id/[a-zA-Z0-9_.:+-]+\z}); abort "对照盘不得复用主盘" if p.any?{|v|v["stable_id"]==x["stable_id"]}; abort "缺少对照映射证据" unless File.file?(x["evidence_file"]) && Digest::SHA256.file(x["evidence_file"]).hexdigest==x["evidence_sha256"] }
' "$managed_devices" "$DEVICES"
namespace cnpl03-managed
case "$ACTION" in
    managed-preflight)
        export CNPL03_MANAGED_DEVICES=$managed_devices
        "${CNPL03_ANSIBLE:-$HOME/.venvs/cnpl-ansible/bin/ansible-playbook}" -i "$(required .managed.inventory_file)" "$P03/06/managed-preflight-playbook.yml" 2>&1 | tee "$ATTEMPT/managed-devices.txt"
        ;;
    managed-deploy)
        # 必须先重新核验空盘，再使用 scoped operator。
        export CNPL03_MANAGED_DEVICES=$managed_devices
        "${CNPL03_ANSIBLE:-$HOME/.venvs/cnpl-ansible/bin/ansible-playbook}" -i "$(required .managed.inventory_file)" "$P03/06/managed-preflight-playbook.yml"
        verify_file "$(required .rook.values_file)" "$(required .rook.values_sha256)"
        chart cnpl03-managed-rook rook cnpl03-managed "$(required .rook.values_file)"
        jq -n --arg image "$(image ceph)" --slurpfile devices "$managed_devices" '{apiVersion:"ceph.rook.io/v1",kind:"CephCluster",metadata:{name:"comparison"},spec:{cephVersion:{image:$image},dataDirHostPath:"/var/lib/cnpl03-managed",mon:{count:3,allowMultiplePerNode:false},mgr:{count:2,allowMultiplePerNode:false},dashboard:{enabled:false},storage:{useAllNodes:false,useAllDevices:false,nodes:($devices[0].devices|group_by(.host)|map({name:.[0].host,devices:map({name:.stable_id})}))}}}' > "$ATTEMPT/managed.json"
        apply "$ATTEMPT/managed.json" cnpl03-managed
        wait_json 900 '.status.ceph.health=="HEALTH_OK"' k -n cnpl03-managed get cephcluster comparison -o json
        live_fsid=$(k -n cnpl03-managed get cephcluster comparison -o jsonpath='{.status.ceph.fsid}')
        [[ -n $live_fsid && $live_fsid != "$main_fsid" ]] || die '两集群 FSID 未隔离'
        ;;
    managed-services)
        cat > "$ATTEMPT/managed-services.yaml" <<'SERVICES'
apiVersion: ceph.rook.io/v1
kind: CephBlockPool
metadata: {name: comparison}
spec:
  failureDomain: host
  replicated: {size: 3, requireSafeReplicaSize: true}
---
apiVersion: ceph.rook.io/v1
kind: CephFilesystem
metadata: {name: comparison}
spec:
  metadataPool: {replicated: {size: 3}}
  dataPools: [{replicated: {size: 3}}]
  metadataServer: {activeCount: 1, activeStandby: true}
---
apiVersion: ceph.rook.io/v1
kind: CephObjectStore
metadata: {name: comparison}
spec:
  metadataPool: {replicated: {size: 3}}
  dataPool: {replicated: {size: 3}}
  gateway: {port: 8080, instances: 2}
SERVICES
        apply "$ATTEMPT/managed-services.yaml" cnpl03-managed
        ;;
    managed-check)
        k -n cnpl03-managed get cephcluster,cephblockpool,cephfilesystem,cephobjectstore,pods -o json > "$ATTEMPT/managed-status.json"
        [[ $(k -n cnpl03-managed get cephcluster comparison -o jsonpath='{.status.ceph.health}') == HEALTH_OK ]] || die '对照尚未健康'
        [[ $(k -n cnpl03-managed get cephcluster comparison -o jsonpath='{.status.ceph.fsid}') != "$main_fsid" ]] || die 'FSID 未隔离'
        ;;
    managed-cleanup)
        [[ $(k -n cnpl03-managed get pvc -o json | jq '.items|length') == 0 ]] || die '仍有持久卷，先保存数据并按 UID 释放，不自动删卷'
        k get pv -o json | jq -e 'all(.items[];(.spec.csi.volumeAttributes.clusterID // "")!="cnpl03-managed")' >/dev/null || die '仍有对照集群的 PV，先核对和保护后端数据'
        k -n cnpl03-managed delete cephobjectstore,cephfilesystem,cephblockpool -l "cnpl.io/run=$RUN" --wait=true --timeout=300s
        k -n cnpl03-managed delete cephcluster comparison --wait=true --timeout=600s
        printf 'API 对照资源已删除。保留 Operator/CRD 和磁盘残留证据；不得自动擦盘或强摘 Finalizer。\n'
        ;;
esac
INPUTS=$main_inputs
ceph_ok
