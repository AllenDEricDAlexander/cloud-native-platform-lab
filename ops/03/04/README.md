# 03.04 Rook External 与 CSI

覆盖 03.04.01–05。离线 `bash ops/03/04/run.sh validate`；现场 export → operator → connect → network → classes → snapshot → smoke → default → check。

锁定 rook、ceph_csi、snapshot_controller、probe。将匹配 Rook 版本的官方 create-external-cluster-resources.py 预置到 storage01；本仓库不编写 Python。先审阅其 `--help` 和实际参数，把文件路径/SHA、export_arguments 登记到输入。导出参数必须指定本批 RBD 池、CephFS、cnpl03-external 和 restricted-auth-permission；输出只写远端 root 私有文件，绝不 source 未审查的 shell。

以同版本官方 import 流程的结果制作受控 connection_file，格式为 `{fsid,apiVersion:"v1",kind:"List",items:[...]}`。items 包含 cnpl03-external 内 rook-ceph-mon Secret、rook-ceph-mon-endpoints ConfigMap、csi-rbd-node/provisioner 与 csi-cephfs-node/provisioner Secret，可加 rook-ceph-csi-config。保持官方字段和实际 caps，不得用 client.admin；rook-ceph-mon 使用 ceph-username/ceph-secret，admin-secret 必须为空。文件权限 0600，另锁 SHA。导入脚本只检查结构/无管理员身份，现场仍需用 `ceph auth get <受限身份>` 审计池/文件系统 caps，输出受控保存。

operator-values.yaml 给出外部消费的配置基线；在仓库外 values_file 中按选定 Chart 合并该基线、限定 watch namespace（仅外部集群及显式管理空间）及所有 operator/CSI/sidecar 内网 Digest，并登记 values_sha256。脚本渲染后扫描镜像，拒绝未锁镜像；已有他方 CRD 拒绝接管，不能让两个 Operator 重复供应同一驱动。Chart/API 参数未联网核对，materials.compatibility_file 为执行门槛。

network 从十节点检查内核客户端与三 MON 端口；它不能证明 OSD 数据路径。smoke 才分别为十节点申请 RBD/CephFS PVC，逐节点挂载写读。smoke PVC 默认 Retain，20Gi 预算需提前计入，测试后按 05 的后端留存规程清理，不能只删 namespace 当作后端清理。classes 初始不抢默认类；default 只在无其他默认类且归属匹配时将本批 RBD 设置为唯一默认。

snapshot_controller 物料 file 必须是审查过的完整 CRD/RBAC/Controller 安装清单，包含内网 Digest 和正确的 ServiceAccount/ClusterRoleBinding namespace。快照类初始 Retain，不把快照等同独立备份。External CephCluster 只能消费，check 检查消费 namespace 内没有新 MON/OSD/MGR/MDS/RGW。

Pending/挂载失败分别检查事件、CSI Secret、caps、内核、消费者到 MON/OSD/MDS 的实际源地址。保留 PVC 和后端数据；不回退为全局管理员身份，不自动卸载 CSI/CRD，不部署第二套主 Ceph。
