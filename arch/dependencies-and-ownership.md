# V3.0 依赖顺序、控制权与启停约定

本文件用于执行前核对依赖，不增加第八个建设阶段。

## 1. 主线依赖

### 1.1 从空环境开始

先用已校验种子建立 ESXi/iDRAC 管理和本地工具，再有局域网与 DNS/CA、GitLab/Harbor/Nexus；00 实际完成十节点 Linux/CRI 初始化及重启复验，01 复验后才建立 Kubernetes。Ceph 由 Rocky 存储主机上的 cephadm 独立管理，Kubernetes 通过 Rook External/CSI 消费卷，通过 RGW 端点消费对象存储。业务和有状态平台必须等到存储、证书与网络实际通过验证。

### 1.2 必须提前做的最低能力

备份、权限、时间同步、证书信任和恢复入口从 00 开始。01 开始保护 etcd 和加密密钥。03 开始数据备份。05 提供完整观测，但在此之前也要保存系统状态和故障记录。06 负责完整验证，不是第一次建立安全和备份。

### 1.3 合理回访而不是卡住主线

01 的 StatefulSet 身份实验在 03 增加持久化验证；02 完成基础网格/身份，04–06 扩展联动；04 用最小真实指标源独立验收自动发布，05 完善 SLO；06 的 GPU/KubeVirt/第二集群与 02 的 BGP 在前置满足时开展。不能为了等一块 GPU 而停止全部基础建设；但可交接不代表未做的高级实验已经通过，阶段完整完成仍需关闭这些条目。

## 2. 一项资源一个主控制者

### 2.1 VM、主机和存储

OpenTofu 与 Ansible 分别负责已约定的资源和配置。两套 CI 调用同一模块时使用同一受控状态与锁，不能并发写同一对象。Ceph 的外部主集群归 cephadm，内部 Rook 对照使用不同设备、身份和资源。Kubernetes Drain 不自动停止宿主机上的 Ceph 守护进程。

### 2.2 应用与平台 API

Argo CD 管理应用声明和顶层平台请求。Crossplane 管理它生成的组合资源，数据库 Operator 管理其子对象。Flux 在独立空间对照，不与 Argo CD 管理同一对象。HPA 管理的 replicas 字段需要与 GitOps 协调，不能每次同步重置。

### 2.3 VIP 与流量

API VIP 归 kube-vip，业务 VIP 主线归 MetalLB，Cilium L2/BGP 对照有独立池与选择器。网关、网格、Knative 和 Rollouts 的各层行为必须实际适配，不同时引入多套不清楚职责的入口。

## 3. 资源配置档

### 3.1 基础常驻档

保持网络、DNS、仓库、主 K8s、外部 Ceph/CSI、入口、GitOps、最低监控与备份。仅运行少量代表性业务和轻量数据服务，给节点维护、镜像拉取和存储恢复保留资源。

### 3.2 数据与交付实验档

为 PostgreSQL、Redis、Kafka、RabbitMQ、NATS、双 CI、Backstage、Crossplane 逐一分配预算。高可用实验按序开展；结束后按官方支持的方式停机、降配或重建，而不是一概将多数派有状态系统缩零。

### 3.3 大型扩展档

ELK/Loki 对照、多集群、KubeVirt、Kubeflow、GPU 与 llm-d 需要独立容量审查。每次只启用当前专题，确定结束后的清理顺序。已纳入范围不等于要求全部同时在线。

## 4. 故障与恢复次序

### 4.1 管理面故障

用集群外工具恢复 DNS、证书、源码和必要镜像，随后恢复所选路线需要的 Ceph、Kubernetes 与平台。恢复不能先要求故障集群的 Runner、Jenkins 或 Secret 服务正常。

### 4.2 存储和数据库故障

先确认旧写入者被隔离、存储保护和数据一致性，再重挂卷或切换写主。副本、Snapshot、外部备份和数据库 PITR 是不同保护层，不互相替代。

### 4.3 两种集群重建路线

完整 etcd 恢复需要匹配版本、身份和加密材料；全新集群加 GitOps/数据恢复需要重新关联资源与后端。不要同时导入相互矛盾的控制面状态、旧 PV 和新生成的资源。

## 5. 自举、控制权与按需模块补充

### 基础设施自举顺序

先用校验过的种子物料准备集群外管理工具；管理入口与基础网络先于 DNS/PKI，DNS/PKI 先于 GitLab/Harbor/Nexus，随后在 00 完成 Linux/CRI 与软件供应，01 再建立 Kubernetes。Ceph 主机可独立管理；Rook External 与 CSI 在 K8s 建成后接入。平台 API、网格、安全、观测等按各阶段逐步加入。

GitLab、Harbor、Nexus 和恢复工具在集群外且不依赖该 K8s/Ceph 才能启动。Jenkins Controller 可使用集群内 Ceph PVC，但不被要求在集群损坏时自救；集群外的受控恢复执行器负责这条路径。

### 资源所有权

OpenTofu 负责已划定的虚拟机与虚拟硬件；Ansible 负责主机配置；kubeadm 管理主集群生命周期；cephadm 管理外部 Ceph；Rook External/CSI 消费外部存储。Rook 内部 Ceph 使用另一批盘。

Argo CD 是主 GitOps。Crossplane 生成的资源由其管理，Argo CD 只管理顶层请求；数据库 Operator 再管理自身子资源。GitLab CI/Jenkins 通过同一 State 的锁交替管理 IaC，不并发 Apply 同一对象。Flux、Tekton、CAPI、MetalLB/Cilium 对照均有独立范围。

### 常驻与按需模块

基础网络、DNS、仓库、主 K8s、外部 Ceph、CSI、主要网关、最低 GitOps/监控/备份为常驻起点。数据库、双 CI、门户、日志和追踪按当时实验负载决定运行规格。

ELK 与 Loki、两套网格、Falco 与 Tetragon、第二集群、KubeVirt、Kubeflow 和分布式推理不要求同时常驻。按需不等于无备份直接缩到零：有状态多数派和持久数据按各系统流程停机、恢复或从已验证备份重建。

## 架构决策记录

保存实施中已经明确的取舍，不预填未经确认的决策。改变 CNI、VIP 控制者、存储主方案、资源预算或安全例外时，在本节追加状态、背景/约束、备选项、选择理由、控制权、代价、验证依据和关联步骤；先按现有计划实现，不为每个普通配置项新增记录。决策按 `0001-<主题>` 起递增编号，与步骤编号分开维护。
