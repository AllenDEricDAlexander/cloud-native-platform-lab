# 06.10 多集群交付、Cluster Mesh/MCS 与切换

覆盖 06.10.01–05。`run.sh validate|render <network|gitops|mcs>|apply|gitops|check|mesh-check|failover-plan|cleanup-plan`。先完成 09 第二集群，分别填写 kubeconfig/context/UID/节点基线；`multicluster.target` 每次明确选一个，不能由当前 kubectl context 猜测。cluster name/ID 必须唯一，Pod/Service 网段和 MTU/路由/防火墙/CA/身份共享条件先验。

Cluster Mesh 改动属于既有 Cilium 归属：使用 02 的已锁定 Helm/GitOps 配置分别 enable clustermesh-apiserver 和精确内网入口，两个集群均健康后用已锁定 Cilium CLI 的 connect 流程互联。先核对该版本 `cilium clustermesh --help`、监听端口/证书/Service 类型和目标 kubeconfig，不在本脚本盲目更新 Cilium。将兼容/连接/跨集群查询证据保存 mesh_evidence_file/SHA。mesh-check 仅检查真实对等状态，CRD 存在不能证明 Mesh。

两边各执行一次 apply，部署同一固定镜像并在响应中返回 CLUSTER_NAME；全局 Service 不复制数据库。现有同空间允许规则与跨集群 Cilium policy 一起评估，另用不同团队/同名服务/拒绝 Pod 验证边界，不能只看 allow。禁止跨集群读取 Secret/创建权限；分别用真实受限身份做拒绝测试。05 遥测必须携带 cluster/run 标签，跨集群 Grafana 查询可区分两边。

Argo CD 先在明确 target 中建立独立 AppProject 和两个受限集群凭据/名称，凭据从 03 私密流程导入；gitops 仅新建本批 ApplicationSet，锁完整 revision，禁止自动 prune 与删除既有应用。GitOps 管理的应用不与 apply 同时作用于相同对象：选独立目录/对象或完成可审计所有权移交。Flux 对照也只管理独立对象，不能与 Argo 同时接管。

MCS 子模式仅输出 ServiceExport；先核对选定 Cilium/控制器确实实现 MCS，CRD 和 ServiceExport 本身不等于支持。只有独立的实现兼容证据、ServiceImport/端口/Endpoint 和真实跨集群名称请求都通过后才验收。未经确认不 apply MCS，也不将 Cilium 全局 Service 宣称为同一 API。

failover-plan 只保存本批 Deployment 的 UID/resourceVersion 条件补丁，不执行故障。先准备本集群内有界恢复任务或独立管理端定时恢复，并确认它拥有仅该 Deployment 的 get/patch 权限；持续请求内网入口、设最多 30 秒和错误率停止阈值，再在对应目标执行 `kubectl -n <本批空间> patch deployment global-echo --type=json --patch-file <down.json>`。达到阈值或到期立即用 restore.json 恢复，等待 rollout；恢复补丁只在同一 UID 且仍为 0 副本时适用，期间有其他变更则停止人工核对。必须记录独立恢复就绪证据才能注入，Mac shell trap 不能作为唯一自动回退。

分别记录检测、路由切换、连接恢复、业务结果；有状态业务先证明复制/一致性再讨论 RPO。退出先恢复副本/连接、停止生成器和流量，保护数据，再撤本批全局 Service/策略/凭据；共享 Cilium/网关不卸载。所有跨集群行为仍待真实 VM 验收。
