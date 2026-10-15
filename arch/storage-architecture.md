# 存储与备份架构

## 1. 物理到业务的数据路径

主方案不使用 vSAN。三台 storage VM 从各自 ESXi 的已核实磁盘获得 OSD 设备，cephadm 管理 MON/MGR/OSD/MDS/RGW；Rook External 导入连接与受限凭据，Ceph CSI 为 Kubernetes 供应卷。Rook External 不接管外部守护进程生命周期。[Rook 官方说明](https://rook.io/docs/rook/latest-release/CRDs/Cluster/external-cluster/external-cluster/)

| 数据类型 | 规划方式 | 检查重点 |
| --- | --- | --- |
| VM OS / containerd / 构建临时数据 | 分开预算的本地磁盘或挂载点 | 文件系统、容量、权限与重启后的挂载 |
| Ceph OSD | 专用且确认可使用的设备 | 稳定设备 ID、物理来源、无文件系统/现有数据 |
| RBD | Ceph 块池 → CSI → StorageClass/PVC | 挂载模式、扩容、重挂载、回收策略 |
| CephFS | 文件系统及 MDS → CSI → RWX PVC | 多 Pod 读写、权限、MDS 故障 |
| RGW | 对象桶及受限 S3 身份 | Endpoint、对象校验、配额、恢复，不当作 PVC |
| 独立备份 | 三台 ESXi 和当前 Ceph 故障域以外的介质 | 实际数据、密钥、可读取性、隔离恢复 |

十节点“各 1 TB”是原目标规格，不能换算成 Ceph 可用容量；当前 OSD 数量、大小和介质未知，台账留空。禁止根据 `/dev/sdb` 名称猜测设备并格式化。

## 2. 建设顺序

00 只配置已确认的系统/运行时盘、准备 cephadm 所需主机能力并保护候选 OSD，实际 OSD 初始化在 03。03 先核实盘位映射与故障域，再 bootstrap、加入主机、声明 OSD、建立池/文件系统/对象服务，最后导入 Rook External/CSI。

Kubernetes、Ceph 节点 OS、基础仓库不能依赖由自身供应的唯一 Ceph 卷启动。storage VM 同时运行 kubelet 不改变这个约束。

Rook 自管理实验使用隔离盘与身份；不与 cephadm 共用 OSD、FSID、MON 或管理凭据。实验结束先保护数据再卸载，不把删除 CR 等同于安全销毁所有存储。

## 3. 故障域与数据服务

三副本策略需按实际物理放置配置并检查 CRUSH；单 OSD、单 storage VM 和整台 ESXi 故障分别记录。三故障域失去一个后可用性、写入条件、重建余量取决于池参数和剩余空间，不预先承诺恢复到完整三副本。

PostgreSQL/CloudNativePG、Redis、Kafka/Strimzi、RabbitMQ Operator、NATS/JetStream 为明确建设项，MySQL/ECK 为扩展实验。每套服务需要独立连接凭据、持久化、失败重试与恢复测试；自研 Operator 从小型 DemoApp 调谐和 Finalizer 开始。

## 4. 备份与恢复验收

00 恢复基础服务；01 备份 etcd、PKI、审计/加密配置；03 做数据库原生备份、对象/文件备份；06E 用 Velero 和实际数据搬运验证集群级恢复。快照引用不能证明数据已经离开原存储，数据库还需协调应用一致性。[Velero 数据搬运说明](https://velero.io/docs/main/csi-snapshot-data-movement/)

每次恢复都记录备份时间点、日志/WAL/消息覆盖范围、校验方式、RTO/RPO 和清理。选择“原 etcd 状态恢复”或“新集群 + GitOps + 数据恢复”中的明确路线，避免混用两套对象身份。唯一备份和解密密钥不能一起丢在同一故障域。
