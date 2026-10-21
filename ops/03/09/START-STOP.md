# 数据平台启停与恢复顺序

启动：基础 VM/DNS/时间/CA/仓库 → cephadm MON 多数派/MGR/OSD → PG 健康与容量 → RBD/CephFS/MDS/RGW → Rook External/CSI/快照控制链 → 对应 Operator → 数据库与消息多数派/复制 → 业务客户端。每层先运行对应 check，再继续下层。

停止前先明确只暂停单套实验，还是维护存储/主机。停止业务写入和新任务；保存 Kafka group offset/ISR、Rabbit confirm/ack/积压、NATS consumer/stream sequence、数据库最新事务/WAL/备份。需要清空积压时先验证消费者幂等及处理结果，不把清队列当作备份。

数据库：先生成并校验独立备份/WAL，记录当前主备角色和复制位置，再按选定 Operator 的维护/关停规程逐成员操作。源卷与恢复目标独立。大版本升级使用 07 的新目标迁移，不用应用回滚覆盖数据结构。

消息：Kafka 保存 ISR/多数派与位点后按该 Strimzi/Kafka 版本滚动维护；Rabbit Quorum Queue 和 NATS JetStream 保留多数派及明确的安全停止路线。不能把任意三副本 StatefulSet 全部 scale=0 视为通用安全暂停。Redis Sentinel 与 Cluster 的主备/分片分别处理，保存 AOF/RDB 与发现信息。

只有所有卷消费者已停写、挂载已正常解除，才维护 CSI/存储 VM；先处理 kubelet 的调度/Drain，再处理 Ceph 服务，两层不能相互替代。停止 Ceph 前确认独立备份、MON 多数派、PG 以及单域损失风险。按 06 保存原 noout/恢复限速/调度状态，必要变更先配独立到期恢复任务；vSphere 电源动作由用户在控制台执行。

恢复：按启动顺序逐层启动，先复核原 FSID/集群 UID/设备，再验证哈希、已确认事务和消息 ID、消费位点、原标志及调度状态。原域尚未恢复时只记降级可用，不能报告完整三副本保护。数据需要恢复时按明确时间点新建目标，核对 RPO/RTO、TLS/权限/连接入口后，由用户切换业务。

交接材料：每项配置与版本 SHA、实际后端/UID 映射、正常/负向/故障数据校验、独立备份恢复、未完成项、受限连接信息及秘密外部位置。Phase 04 只消费这些已验证的服务；脚本已交付的状态不提升成服务已就绪。
