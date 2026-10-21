# 06.17 两条重建路线、RTO/RPO、冷启动与交接

覆盖 06.17.01–07。`run.sh validate|plan|check|report <时间线JSON>|handoff|cleanup-plan`。每个批次只选 `recovery.route=etcd-restore` 或 `fresh-cluster`，要求独立备份、隔离目标和来源/版本/密钥/存储映射证据；不在唯一原副本做不可恢复实验。plan 只输出路线与依赖，不启动 VM/服务。

恢复从集群外开始，依 dependencies.json：物理管理/BMC/vSphere→管理工具、DNS/CA/时间/Harbor/Nexus/源码→Linux/CRI、选定 Ceph 恢复能力→所选 Kubernetes 路线/VIP/CNI/DNS→CSI/CRD/Operator/身份与数据→GitOps/应用/观测。无需依赖尚未恢复的 Jenkins/集群内 Runner，源 Ceph 未恢复也不能成为基础仓库恢复前置。复用 00 的 `ansible/playbooks/{dns,harbor,nexus,gitlab,restore-drill,bootstrap-nodes}.yml`，但使用独立恢复 Inventory/目标限制/受控参数，不能拿原台账直接覆盖。

**原 etcd 状态路线。** 先 fence 所有旧写入者，保存每个旧 etcd 目录、静态 Pod、PKI、EncryptionConfiguration 和历史备份钥。三个成员使用同一已校验快照、各自 member/peerURL、新成员列表和新数据目录；锁定 etcdutl 二进制 SHA/版本支持 bump-revision/mark-compacted。`etcd-restore-host.sh` 由用户在隔离目标节点显式执行，检查身份/权限/旧服务停止，并还原到不存在的新目录；不停止旧服务、不改静态 Pod、不启动 etcd。revision_bump 必须根据最大写速率/离线时长计算，并在回执中明确 revision_bump_sufficient，没有通用默认值。切换前复核 SELinux 精确标签、挂载、成员/URL/PKI/加密与 watch/cache 行为，再按版本支持流程逐台恢复，不让旧集群重新写入。

**全新集群路线。** 不导入旧 etcd 状态。用独立恢复 Inventory 复用 00 Linux/CRI、01 的 init-cp01/join-control-plane/join-workers/install-cilium 配置入口，重新登记 kube-system UID、身份和网络。先恢复必要 CRD/Operator/Secret/StorageClass，再选择 16 的 Velero/原生数据库恢复和 04 的 GitOps（prune 关闭），审查 PV VolumeHandle、Ceph FSID/用户/池、Secret 和路由映射。不把旧 PV 对象直接绑定新后端，不把两条路线组合重复导入同一对象。

外部 Ceph 保留则先验证 FSID/quorum/数据/CSI连接；原存储丢失则准备独立新存储，再搬回真实数据。etcd 快照没有 PVC/数据库/对象内容。控制面恢复之后两条路线都要验证原生数据库事务/消息确认、文件/对象 SHA、七语言服务和观测。check 要求独立恢复 API 端点、明确 recovery UID、节点就绪、业务回执 checks 全部为 true 且零丢失/重复，并运行时间线检查。原 etcd 路线应保留源对象 UID 且要求旧写入者已 fence；新集群路线 UID 必须不同。它只核对提交的真实材料，不能自动替代业务测试。

timeline.json 填含时区的真实里程碑：故障开始、恢复开始、基础就绪、业务验证完成、源最后确认写入、最新恢复数据。report 拒绝倒置时间/负数，RTO=业务验证−故障开始，RPO=源最后确认−最新恢复数据，按约定目标判定，不默认填零；结果仍不自动提升阶段验收。两条路线分别生成报告，不能合并出一个没有来源的最优值。

冷启动先在独立新 VM 小规模复现同一依赖图，按 readiness 放行下游；ESXi 自动开 VM 不等于服务就绪。安全停机先关入口/停写、排空队列/工作流并做原生一致性备份，再反向退出应用/平台/Kubernetes/存储/基础服务/物理层，每层保存停止条件与真实回执。发生电力故障后先检查一致性和数据保护再放行业务，不让未就绪 Ceph 的无限重试耗尽资源。

清理扩展模块前先保护模型/VM/消息/备份，依次退出故障 CR、工作负载、队列/Claim、控制器、临时 VM/盘/VIP/DNS/权限；以对象 UID、VM UUID 和归属台账核对，不做全局 prune/强拆 Finalizer。handoff 仅审查 83 步文件索引；06A–E、七阶段、未满足硬件/版本、实测报告、冷启动及新建 VM 复制验收逐项留 pending，全部真实闭环后再人工验收。本轮没有执行重建或启动任何服务。
