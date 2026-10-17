# 七阶段总体实施计划

本计划回答「要做什么、做到什么程度算完成」：连接架构、阶段任务、交付物和验收，固定七个阶段，保留原 363 个稳定步骤编号。「具体怎么做」在 ops 下各阶段的操作流程；「实际做了什么」在各阶段的执行记录（当前为 [Phase 00 批次](../ops/00-preparation/records/2026-10-14/README.md)）。

[项目入口](../README.md) · [总体架构](../arch/README.md) · [步骤索引](step-index.md) · [覆盖索引](coverage.md)

## 执行与交接规则

00 → 01 → 02 主线 → 03 → 04 → 05 → 06。每阶段必须交付可复用配置/脚本、文档、测试入口和真实报告；仅有清单、安装界面或目录不算完成。

00 必须实际部署基础服务、创建十台服务器、配置 Linux 并安装验证 CRI。01 从节点基线复验开始，只负责 kubeadm/CNI/控制平面和资源实验。发现系统问题返回 00 的角色配置修复，不能把服务器初始化留给 01。

| 状态 | 判定 |
| --- | --- |
| 未执行 / 进行中 | 尚无全部运行证据，不计为通过 |
| 主线可交接 | 本阶段的交接用例已通过；条件实验仍逐项跟踪 |
| 阻塞 / 失败待修复 | 分别记录缺失前置或真实失败及恢复动作 |
| 阶段完整完成 | 该阶段全部要求、交付物与验收有证据，回访项已关闭 |

“主线可交接”不等于“阶段完整完成”。硬件受限模块不能静默删除或标成通过。阶段独立验收允许依赖先前阶段，但不能依赖尚未实施的后续阶段才能证明自己的基本成果。

| 容易形成的依赖 | 本轮安排 |
| --- | --- |
| 仓库依赖待建仓库中的自身物料 | 00 使用经校验的离线种子启动管理机与集群外仓库，随后转内网源 |
| CRI 到 01 才部署 | 安装、配置、运行、重启与幂等均纳入 00；01 复验 |
| 无 CNI 无法验收 CRI | 00 host-network sandbox 验证 RuntimeReady；01 验证 CNI 和普通 Pod 网络 |
| 04 自动回退等待 05 | 04 实施最小真实指标源并验收；05 扩展完整 SLO |
| 01 StatefulSet 与持久化 | 01 验证身份和控制器；03 独立验证真实 PVC 与恢复 |
| 02 网格等待未来统一身份/观测 | 02 验证基础 mTLS/授权；05/06 扩展追踪和信任联动 |
| 05 跨集群观测没有第二集群 | 05 完成标签/路由和主集群验证；06C 新集群接入后补实测，不提前声称跨集群已通过 |

## 每阶段要交什么

### Phase 00｜基础设施与服务器初始化

目标：独立于 Kubernetes 完成基础设施部署与恢复，十台 Rocky 节点具备入群条件。

[阶段正文与 43 个步骤](00-preparation.md) · [具体实施](../ops/00-preparation/README.md)

- **建设范围**：ESXi 模板/批量 VM、Rocky Linux 10、VMXNET3、Linux 基线与 containerd/runc/crictl、OpenWrt/VPN、IP/DNS/CA/NTP、Harbor/Nexus/GitLab、Ansible/OpenTofu、离线镜像和依赖。
- **实际顺序**：资产与版本核实 → 集群外管理工具/种子 → 模板和基础 VM → 网络/DNS/CA/仓库 → 十节点 Linux/CRI 初始化 → 重启/幂等/离线/备份验收。00.10.01 的工具准备在创建 VM 前执行，编号用于追溯而非强制逐号执行。
- **重点实验**：批量克隆唯一身份、VMXNET3、VPN 分流与断链、代理缓存、CRI 容器运行、重启保持配置、离线安装/构建、基础服务恢复。
- **交付物**：inventory 三份台账；OpenTofu 模块；Ansible Inventory/角色/Playbook；模板制作记录；OpenWrt/DNS/PKI/仓库配置；物料同步和预热入口；十节点 Linux/CRI 检查结果。
- **验收用例**：十台节点通过 node-readiness 和 host-network CRI smoke；关键服务不依赖 K8s/Ceph；VPN 故障下内网可用；干净客户端断网后完成指定物料的安装及七类最小构建；独立备份恢复一个基础服务。

交接要求：基础服务与十台服务器已实际就绪；OS/CRI 初始化不能延后到 01。

### Phase 01｜Kubernetes 高可用与核心资源

目标：理解并验证资源控制器、生命周期和控制平面高可用。

[阶段正文与 47 个步骤](01-kubernetes.md) · [具体实施](../ops/01-kubernetes/README.md)

- **建设范围**：复验 00 节点基线，配置 kubeadm/kubelet，建立三控制平面 stacked etcd、kube-vip、Cilium 基础 CNI，加入十节点。
- **核心资源**：Pod、RC、ReplicaSet、Deployment、StatefulSet、DaemonSet、Job/CronJob、三种 Probe、PreStop、ConfigMap/Secret、更新/扩缩容/回滚、级联删除和垃圾回收。
- **实际顺序**：只读入群检查 → kubeadm/kubelet 与 VIP 引导配置 → cp01 init → Cilium → cp02/03 join → 七 Worker join → DNS/HA/etcd 备份 → 核心资源实验。
- **交付物**：ops/01-kubernetes/bootstrap/ 初始化/Join/Cilium 基础配置；ops/01-kubernetes/core-resources/ YAML；ops/01-kubernetes/examples/ 场景；etcd 备份入口、测试和故障记录。
- **验收用例**：10 节点 Ready；单控制平面故障时 etcd Quorum 和 API 仍可用；Pod 异常、Readiness 端点摘除、DaemonSet 回滚、ReplicaSet 接管、StatefulSet 身份保持及全部基础实验通过。

交接要求：交接可用集群、核心实验集和恢复材料；持久化数据验收归 03，01 不宣称 PVC 数据恢复已通过。

### Phase 02｜网络、调度与服务治理

目标：完成应用通信、统一入口、调度隔离与服务治理。

[阶段正文与 45 个步骤](02-networking.md) · [具体实施](../ops/02-networking/README.md)

- **建设范围**：Service/CoreDNS/EndpointSlice、MetalLB、Ingress 对照、Envoy Gateway/Gateway API、Cilium NetworkPolicy/Hubble、cert-manager。
- **调度与进阶**：Taint/Toleration、Node/Pod Affinity、Topology Spread、QoS/Eviction/PDB、ResourceQuota/LimitRange/PriorityClass；Cilium kube-proxy replacement/L2/BGP/Egress Gateway、Istio Sidecar/Ambient、SPIFFE/SPIRE。
- **实际顺序**：固定通信基准 → Service/DNS → MetalLB 与入口 → TLS/网络策略 → 调度与资源治理 → 隔离数据面及网格对照 → 清理并复验主线。
- **交付物**：网络拓扑与地址台账；ops/02-networking/networking/ 的 Cilium values、Gateway/HTTPRoute、NetworkPolicy、TLS 和调度策略；ops/02-networking/examples/ 场景与 ops/02-networking/tests/integration/ 网络用例。
- **验收用例**：跨节点 Pod、域名、HTTPS/gRPC、允许/拒绝流量、节点约束和物理故障域分布通过；每种高级模式有前后对照与回退证据，缺少 BGP 前置则单独阻塞该项。

交接要求：主线通信先交接给 03；尚未完成的进阶项仍计入本阶段，不能因可交接而把全部范围标成完成。

### Phase 03｜Ceph、存储与中间件

目标：在不使用 vSAN 的条件下提供持久化与可恢复的数据服务。

[阶段正文与 48 个步骤](03-ceph-middleware.md) · [具体实施](../ops/03-ceph-middleware/README.md)

- **存储范围**：cephadm、MON/MGR/OSD/MDS/RGW、Rook External、Ceph CSI、StorageClass、RBD/CephFS、PV/PVC/VolumeSnapshot，以及隔离的 Rook 自管理对照。
- **数据与扩展**：PostgreSQL/CloudNativePG、Redis、Kafka/Strimzi、RabbitMQ Operator、NATS/JetStream；扩展 MySQL/ECK，开发一个有调谐/幂等/Finalizer 的 Kubernetes Operator。
- **实际顺序**：核实独立备份与设备映射 → cephadm/池/文件/对象 → Rook External/CSI → 卷生命周期 → 存储故障 → 数据库/消息与恢复 → 自研 Operator。
- **交付物**：ops/03-ceph-middleware/cephadm/；ops/03-ceph-middleware/storage/、middleware/、operators/；OSD 映射；StorageClass/PVC/Operator CR；数据库安装/恢复规程与故障报告。
- **验收用例**：PVC 动态供应、扩容和 Pod 重建保留数据；OSD 失效/重平衡、CSI 故障、数据库切换与独立备份恢复、Kafka Broker 失效和消息持久化均有数据校验。

交接要求：至少完成一次 OSD 故障与数据库独立恢复；其他列明数据服务及对照仍需逐项实验记录。

### Phase 04｜双 CI、GitOps 与平台工程

目标：建立可审计、支持七类语言的自动交付和研发自助平台。

[阶段正文与 55 个步骤](04-devops-platform.md) · [具体实施](../ops/04-devops-platform/README.md)

- **建设范围**：GitLab CI、Jenkins、BuildKit、Harbor/Nexus 缓存、Argo CD/Rollouts、Helm/Kustomize、双 IaC、SBOM/Trivy/Cosign/准入、Backstage/Crossplane/ApplicationSet、Tekton/Flux/Dragonfly。
- **语言范围**：Java、Rust、C、C++、C#、JS/TS、Python；两个 CI 各自构建、推送、部署并验收全部七类，同一 Digest 跨环境晋级。
- **实际顺序**：应用与制品契约 → Builder/缓存 → 两套 CI → 14 组交付 → 双 IaC → GitOps → 灰度/签名/拒绝发布 → 自助平台 → 隔离对照。
- **交付物**：ops/04-devops-platform/ci/gitlab/、jenkins/、builders/、shared/、tekton/；七语言 ops/04-devops-platform/examples/ 示例；ops/04-devops-platform/gitops/ 环境声明；Backstage Template、Crossplane Composition；IaC 与恢复执行器。
- **验收用例**：14 组“语言 × CI”完整构建部署记录；两套 IaC 均完成 Plan/受控 Apply/幂等/失败补偿；真实指标驱动灰度中止和回退；Backstage 创建并交付一个完整服务。

交接要求：本阶段部署最小真实指标源完成 Rollouts 验收，不依赖 05。05 负责全面观测和 SLO 扩展。

### Phase 05｜可观测性、性能与成本

目标：为多语言应用和跨集群组件建立完整遥测、故障定位与容量依据。

[阶段正文与 42 个步骤](05-observability.md) · [具体实施](../ops/05-observability/README.md)

- **建设范围**：Prometheus/Grafana/Alertmanager、ELK/Fluent Bit、OpenTelemetry Collector、Loki/Tempo/Pyroscope/OpenCost。
- **研究内容**：Metrics/Logs/Traces/Profiles、采样/高基数、日志解析与索引、Retention、SLI/SLO/错误预算、资源成本与容量。
- **实际顺序**：统一遥测标签/预算 → 指标/告警 → Ceph/中间件/基础设施采集 → OTel → ELK 与 Loki/Trace/Profile → SLO 发布分析 → 压测/成本对照。
- **交付物**：ops/05-observability/observability/ 配置、Dashboard、Kibana 查询、OTel 配置、告警与 SLO；ops/05-observability/examples/ 场景、ops/05-observability/tests/performance/ 用例及性能/成本报告。
- **验收用例**：跨语言同步/异步请求串联日志、指标和 Trace；Ceph I/O、Kafka Lag、Java Profiling 与压力案例可定位；ELK/Loki 同负载比较；SLO 驱动灰度分析和资源成本核算。

交接要求：保留最低监控和集群外探测，向 06 提供可复用故障指标；第二集群真实观测在 06C 接入后补充实测。

### Phase 06｜安全、进阶技术与升级容灾

目标：按五个内部专题验证平台可靠性和高级能力，完成完整重建。

[阶段正文与 83 个步骤](06-advanced-security-dr.md) · [具体实施](../ops/06-advanced-security-dr/README.md)

- **06A 安全与弹性**：RBAC/ServiceAccount/PSA、Kyverno/Trivy/Cosign、Keycloak、Falco/Tetragon、HPA/VPA/KEDA、Chaos Mesh。
- **06B Serverless 与事件平台**：Knative、Dapr、Argo Workflows/Events、NATS、事件驱动扩缩容和重放/幂等。
- **06C 多集群**：Cluster API Provider vSphere、Cilium Cluster Mesh、ApplicationSet/Flux、多集群隔离、流量故障切换和观测接入。
- **06D 高级计算**：KubeVirt、Kueue、DRA、Kubeflow、KServe、GPU Operator、vLLM、llm-d；先验证虚拟化、设备、驱动与容量。
- **06E 升级与容灾**：相邻 kubeadm 次版本升级、etcd/Ceph 恢复、Velero、独立数据备份、完整集群重建与 RTO/RPO。
- **交付与验收**：安全策略、故障注入用例、升级与恢复规程、跨集群测试、RTO/RPO 报告；完成一次安全可控升级和约定恢复测试，每个高级模块有可重复实验或明确阻塞记录。

交接要求：硬件缺失不伪装成功。五个专题分别报告状态，所有要求闭环后才标记第 06 阶段完整完成。

## 实施记录与最终验收

每个任务先确认输入和作用域，再写配置、执行、核对正常/失败路径、清理并归档。实际参数、命令、退出码、对象状态、请求/数据校验及回退记录使用 [执行记录模板](../ops/templates/execution-record.md)；阶段收尾使用 [阶段验收模板](../ops/templates/phase-acceptance.md)。

报告统一放 `ops/<阶段目录>/records/<执行批次>/`；已验证的稳定操作提炼回 `ops/<阶段目录>/README.md`，故障案例保留在对应批次记录中。高级实验保留资源、硬件、版本和未执行原因。完整项目完成要求七阶段的范围和证据都闭环，不用步骤数量或组件安装数量替代验收。

## 阶段回访与完成判定补充

### 阶段顺序与回访

00 创建基础服务与十台节点，完成 Linux/CRI 安装、配置、运行、重启和幂等验收；01 复验节点基线后建立核心集群；02 完成主网络和调度；03 提供持久存储和数据服务；04 建立双 CI 与平台工程；05 建立观测和 SLO；06 执行进阶、安全与恢复。

02 先完成基础网格身份，06 扩展信任；04 用最小真实指标源完成自动灰度/回退，05 扩展完整 SLO。01 的 StatefulSet 先验证稳定身份，03 才验证真实 PVC 持久化。基础备份与权限从 00/01 开始，06 不是第一次备份。BGP、GPU、嵌套虚拟化或第二集群条件不满足时标为阻塞而非删除范围。

### 完成判定与证据

每个步骤均写明实施内容、过程安排与完成判定。执行时记录实际版本、输入、状态、输出、异常、恢复和数据校验；步骤初始状态为未执行；后续仅依据对应批次证据更新，不覆盖历史记录。

“组件已安装”“功能已通过”“故障恢复已通过”“性能达到目标”是四种不同状态。只有通过对应测试才能提升状态。RTO/RPO、吞吐和资源成本均由实测或明确的估算模型得出，不能由本规划预先保证。
