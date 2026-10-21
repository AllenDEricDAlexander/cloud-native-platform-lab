# 06.16 分层备份、真实数据搬运与抽样恢复

覆盖 06.16.01–04。`run.sh validate|render <location|backup|restore>|inventory-check|install|location|backup|check|restore|restore-check|cleanup-plan`。先按 inventory.json 填基础服务、身份、控制平面、存储、业务五层的 RPO/频率/加密/保留/版本/恢复依赖与实际备份索引；仓库只保留引用，原始 PKI/State/数据库/etcd 备份在外部加密保存。

真正独立目的地必须位于主 Ceph 和三台 ESXi 故障域之外，并已有抽样可读恢复证据；现有 esxi01 的 backup VM 不满足。inventory-check 要求每层 outside_primary_ceph/outside_three_esxi/sample_restore_verified 与完整字段，材料 SHA 仍由现场人员确认真实性，不能自填 true 就宣称容灾通过。

按 Kubernetes/CSI/Snapshot/Velero/插件/数据移动器兼容矩阵安装本地完整包，开启所选 node-agent/CSI data mover 的支持方式，镜像与权限逐项复核。location 引用已有私有凭据、HTTPS/CA 和本批 bucket prefix；在两个集群接同一目的地时只允许源写、恢复目标只读，先验证实际权限。共享 BSL 已由其他主体管理则跳过 location，不接管。

backup 只选一个明确普通业务 Namespace，不包含所有集群对象。必须选择 `data_movement=csi` 的 snapshotMoveData，或 filesystem 的 defaultVolumesToFsBackup；单纯 Snapshot 元数据不允许。check 要求 Backup Completed、零 errors、实际 DataUpload/PodVolumeBackup 非空且全部 Completed，再在目的地检查对象/数据字节与索引。PartiallyFailed、缺失搬运对象或源端快照存在均不能通过。

数据库与消息使用 03 的原生一致性备份/WAL/逻辑导出与业务 ID 账本；写入持续时要记录冻结/归档边界、确认事务和恢复点，不能普通拷贝 PostgreSQL/Kafka/RabbitMQ 文件代替一致性方案。文件/对象另存 SHA 与版本清单。

restore 只能选已登记隔离 recovery 目标且 UID 与源不同，要求同名备份已同步到 Completed，恢复到不存在的新 Namespace；先安装匹配 CRD/Operator/StorageClass/恢复身份和 CSI 数据搬运组件。按 17 核对 PV VolumeHandle、Ceph FSID/身份/后端及 StorageClass 映射，不混用原卷和新卷。恢复完成 CR/Pod/PVC 只是中间状态，必须隔离源存储后读取文件/对象和原生数据库/消息回执，证明数据确实来自独立备份。

分别在副本上模拟介质不可达、数据损坏、缺 CA/age/签名/etcd/数据库解密材料；预期拒绝后恢复受控材料并再次还原。不能破坏唯一密钥。清理先保留保留期内备份和恢复数据，再逐条处理本批 Restore/Backup/Snapshot/临时空间；不删除共享 bucket、BSL、原存储或未知 Finalizer。本轮所有备份和恢复均未访问内网。
