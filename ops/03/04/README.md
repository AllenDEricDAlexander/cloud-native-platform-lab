# 03.04 Rook External 与 CSI

覆盖 03.04.01–05。离线 `bash ops/03/04/run.sh validate`；现场 export → operator → connect → network → classes → snapshot → smoke → default → check。

锁定 rook、ceph_csi、snapshot_controller、probe。将匹配 Rook 版本的官方 create-external-cluster-resources.py 预置到 storage01；本仓库不编写 Python。先审阅其 `--help` 和实际参数，把文件路径/SHA、export_arguments 登记到输入。导出参数必须指定本批 RBD 池、CephFS、cnpl03-external 和 restricted-auth-permission；输出只写远端 root 私有文件，绝不 source 未审查的 shell。

以同版本官方 import 流程的结果制作受控 connection_file，格式为 `{fsid,apiVersion:"v1",kind:"List",items:[...]}`。items 包含 cnpl03-external 内 rook-ceph-mon Secret、rook-ceph-mon-endpoints ConfigMap、csi-rbd-node/provisioner 与 csi-cephfs-node/provisioner Secret，可加 rook-ceph-csi-config。保持官方字段和实际 caps，不得用 client.admin；rook-ceph-mon 使用 ceph-username/ceph-secret，admin-secret 必须为空。文件权限 0600，另锁 SHA。导入脚本只检查结构/无管理员身份，现场仍需用 `ceph auth get <受限身份>` 审计池/文件系统 caps，输出受控保存。

operator-values.yaml 给出外部消费的配置基线；本批实际为 Rook 1.21.0 加独立 ceph-csi-drivers Chart 1.1.0、Ceph-CSI 3.18.1。仓库外 values_file 限定 watch namespace 及全部内网 Digest，并登记 values_sha256。脚本渲染后扫描镜像，拒绝未锁镜像；已有他方 CRD 拒绝接管，不能让两个 Operator 重复供应同一驱动。导入还包含独立 External RBAC、CSI Secret 类型/别名；ClientProfile 和 StorageClass/快照类的 clusterID 均为 `cnpl03-external`。

CephX 类型必须显式填写，本批为 `aes256k`，RBD/文件挂载为 `rbd-nbd` / `fuse`。用户态映射进程计入节点插件内存；实际 OOM 后已将 RBD 节点插件调整为 request 256Mi/limit 2Gi，CephFS 为 128Mi/1Gi。Driver/DaemonSet 使用 `OnDelete`，后续配置更新须先安排消费者正常停写、卸载和逐节点维护，不能自动滚动杀掉活动 NBD/FUSE 进程。现有 Pod 通过 resize 子资源原位增加限制，保留 UID/映射。

network 从十节点检查所选客户端及三 MON 端口；它不能证明 OSD 数据路径。smoke 分别为十节点申请 RBD/CephFS PVC，逐节点挂载写读，本批 20 项已通过。smoke PVC 默认 Retain，20Gi 预算需提前计入；探针 Pod 已正常删除，PVC 保留。classes 初始不抢默认类；default 只在无其他默认类且归属匹配时将本批 RBD 设置为唯一默认。

snapshot_controller 物料 file 必须是审查过的完整 CRD/RBAC/Controller 安装清单，包含内网 Digest 和正确的 ServiceAccount/ClusterRoleBinding namespace。快照类初始 Retain，不把快照等同独立备份。External CephCluster 只能消费，check 检查消费 namespace 内没有新 MON/OSD/MGR/MDS/RGW。

Pending/挂载失败分别检查事件、CSI Secret、caps、内核、消费者到 MON/OSD/MDS 的实际源地址。保留 PVC 和后端数据；不回退为全局管理员身份，不自动卸载 CSI/CRD，不部署第二套主 Ceph。
