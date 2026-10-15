# 操作与执行记录

[项目入口](../README.md) · [总体架构](../arch/README.md) · [七阶段计划](../plan/README.md)

本目录保存具体操作、部署配置、脚本、实验用例和实际结果。手册中的命令示例是实施参考，尚未执行的内容不代表已经验证；实际参数、前置条件和结果以台账、版本锁及对应批次记录为准。

## 阶段操作入口

| 阶段 | 计划 | 操作手册 |
| --- | --- | --- |
| 00 基础准备 | [任务与验收](../plan/00-preparation.md) | [操作与检查](00-preparation/README.md) |
| 01 Kubernetes | [任务与验收](../plan/01-kubernetes.md) | [操作与检查](01-kubernetes/README.md) |
| 02 网络治理 | [任务与验收](../plan/02-networking.md) | [操作与检查](02-networking/README.md) |
| 03 Ceph 与中间件 | [任务与验收](../plan/03-ceph-middleware.md) | [操作与检查](03-ceph-middleware/README.md) |
| 04 交付平台 | [任务与验收](../plan/04-devops-platform.md) | [操作与检查](04-devops-platform/README.md) |
| 05 可观测性 | [任务与验收](../plan/05-observability.md) | [操作与检查](05-observability/README.md) |
| 06 安全、进阶与恢复 | [任务与验收](../plan/06-advanced-security-dr.md) | [操作与检查](06-advanced-security-dr/README.md) |

## 共用输入与文件规则

- [资产与参数台账](inventory/README.md)：保存主机、网络、资源的计划与实际参数，不直接充当 Ansible Inventory 或 OpenTofu 输入。
- [版本与物料](versions.lock.yaml)：保存准确版本、镜像/包校验、来源、兼容性与验证记录；`null` 表示待锁定，不能据此部署。
- [执行记录模板](templates/execution-record.md)和[阶段验收模板](templates/phase-acceptance.md)：关联稳定步骤编号，按实际结果填写。

文档中的配置、脚本、样例和测试路径均从仓库根目录起算；它们是实施交付位置，文件产生时才创建相应子目录。各阶段可复用前面阶段已经交付的模块，不复制同一对象的多份配置或重复实现主机初始化。跨阶段共用配置在下表指定的位置维护，GitOps 仅引用上游配置并保存环境差异与发布版本。

## 配置脚本与实验文件归属

### 集群外基础设施

| 目录 | 阶段 | 负责内容 |
| --- | --- | --- |
| `ops/00-preparation/opentofu/` | 00/04 | VM、模板引用、虚拟硬件与受控 State；不重复配置客体 OS |
| `ops/00-preparation/ansible/` | 00/01/03 | Linux、containerd/CRI、基础服务与主机自动化；kubeadm/cephadm 复用这里的执行入口 |
| `ops/00-preparation/openwrt/` | 00/02 | 旁路由、VPN、显式代理、策略路由和恢复配置 |
| `ops/00-preparation/dns/` | 00 | 内部 zone、BIND 服务配置与客户端分域解析 |
| `ops/00-preparation/pki/` | 00/02/06 | 公开信任链、签发/轮换说明和模板；不保存私钥 |
| `ops/00-preparation/registry/` | 00/04 | 集群外 GitLab/Harbor/Nexus、生态缓存、离线物料同步与预热 |
| `ops/03-ceph-middleware/cephadm/` | 03/06 | 外部 Ceph 主机、设备/OSD 与服务规格及恢复入口 |

### Kubernetes 平台配置

| 目录 | 阶段 | 负责内容 |
| --- | --- | --- |
| `ops/01-kubernetes/bootstrap/` | 01 | kubeadm/kubelet、kube-vip 与 Cilium 基础配置；主机 Linux/CRI 复用 `ops/00-preparation/ansible/` |
| `ops/01-kubernetes/core-resources/` | 01/02/06 | 控制器、生命周期、配置、身份、调度与伸缩的可复用 YAML |
| `ops/02-networking/networking/` | 02 | Service、DNS、Cilium、MetalLB、Gateway/Ingress、TLS、策略与网格 |
| `ops/03-ceph-middleware/storage/` | 03 | Rook External/CSI、StorageClass/PVC/Snapshot，不管理外部 OSD 生命周期 |
| `ops/03-ceph-middleware/middleware/` | 03 | 数据库、消息 Operator 与 CR |
| `ops/04-devops-platform/metrics/`、`ops/05-observability/observability/` | 04/05 | 04 最小真实灰度指标源；05 完整指标/日志/追踪/剖析/成本 |
| `ops/06-advanced-security-dr/security/` | 01/04/06 | RBAC、PSA、准入、身份、运行时与秘密声明 |
| `ops/03-ceph-middleware/operators/` | 03 | 自研 Operator 源码/CRD/RBAC/部署与 API 说明 |
| `ops/06-advanced-security-dr/multicluster/` | 06C | CAPI/CAPV、集群连接、Cluster Mesh 与多集群声明 |

### GitOps 期望状态

| 目录 | 阶段 | 负责内容 |
| --- | --- | --- |
| `ops/04-devops-platform/gitops/bootstrap/` | 04 | 主 Argo CD 的受控引导；引导后明确资源所有权移交 |
| `ops/04-devops-platform/gitops/platform/` | 04 | 引用各阶段可复用配置与平台工程配置的 Application/ApplicationSet |
| `ops/04-devops-platform/gitops/environments/dev/` | 04 | 开发实验的 Namespace、参数和固定制品版本 |
| `ops/04-devops-platform/gitops/environments/staging/` | 04 | 预发布验证和晋级配置 |
| `ops/04-devops-platform/gitops/environments/prod-like/` | 04 | 拟生产配置与受控晋级，不代表真实生产环境 |

### 构建与基础设施流水线

| 目录 | 阶段 | 负责内容 |
| --- | --- | --- |
| `ops/04-devops-platform/ci/gitlab/` | 04 | GitLab CI 模板、语言流水线、Runner 与 IaC 流程 |
| `ops/04-devops-platform/ci/jenkins/` | 04 | Shared Library、Jenkinsfile、Agent 与 IaC 流程 |
| `ops/04-devops-platform/ci/tekton/` | 04 | 隔离的原生流水线对照 |
| `ops/04-devops-platform/ci/builders/` | 00/04 | 七语言工具链、CA 和依赖客户端镜像定义 |
| `ops/04-devops-platform/ci/shared/` | 04 | 两套 CI 共用的构建/测试/制品/供应链/发布契约 |

### 开发者平台工程

| 目录 | 阶段 | 负责内容 |
| --- | --- | --- |
| `ops/04-devops-platform/backstage/` | 04 | 门户配置、目录集成、Software Templates 与任务动作 |
| `ops/04-devops-platform/crossplane/` | 04 | 平台 API、Composition、Provider 引用和资源权限 |
| `ops/04-devops-platform/service-templates/` | 04 | 七类语言应用、CI、部署和文档的可复用模板 |

### 可复现实验场景

| 目录 | 阶段 | 负责内容 |
| --- | --- | --- |
| `ops/01-kubernetes/examples/` | 01 | Pod、控制器、生命周期、探针、删除传播等场景 |
| `ops/02-networking/examples/` | 02 | 数据面、Hubble、L2/BGP、策略与出口对照 |
| `ops/03-ceph-middleware/examples/` | 03 | 外部/自管理 Ceph、卷生命周期和故障对照 |
| `ops/04-devops-platform/examples/` | 04 | 七语言示例、双 CI、GitOps 与供应链实验 |
| `ops/05-observability/examples/` | 05 | 遥测关联、故障定位、性能与成本场景 |
| `ops/06-advanced-security-dr/serverless/` | 06B | Knative、Dapr、Argo、NATS 事件场景 |
| `ops/06-advanced-security-dr/multicluster/examples/` | 06C | 第二集群、跨集群隔离与流量故障切换 |
| `ops/06-advanced-security-dr/kubevirt/` | 06D | VM/CDI、嵌套虚拟化与迁移 |
| `ops/06-advanced-security-dr/ai-gpu/` | 06D | Kueue、DRA、GPU、模型服务和训练 |

### 验收用例

| 目录 | 阶段 | 负责内容 |
| --- | --- | --- |
| `ops/<阶段目录>/tests/smoke/` | 00–06 | 主机/CRI/基础服务和阶段交接的最小检查 |
| `ops/<阶段目录>/tests/integration/` | 01–06 | 控制器、网络、CSI、应用与自助服务完整链路 |
| `ops/<阶段目录>/tests/performance/` | 05/06 | 固定输入下的负载、吞吐/延迟/资源与成本 |
| `ops/<阶段目录>/tests/failover/` | 00–06 | VPN、控制平面、OSD、消息和节点等受控单故障 |
| `ops/<阶段目录>/tests/disaster-recovery/` | 03/06E | 独立备份、原状态/新集群恢复与 RTO/RPO |
| `ops/<阶段目录>/tests/security/` | 01/04/06A | 认证/授权、策略、供应链、轮换与检测正反用例 |

### 跨模块操作入口

配置检查、物料同步/预热、主机 smoke、备份索引与恢复编排等入口随实际交付放到 `ops/<阶段目录>/scripts/`，复用已交付的 Playbook 和模块，不重复实现第二套部署逻辑。脚本需明确输入、只读/变更模式、作用域、错误退出码、重试/幂等和清理；凭据来自受控引用，不输出到日志。

每个实现或实验说明须包含输入、版本、操作、检查、失败恢复和清理。测试用例放 `ops/<阶段目录>/tests/`，真实输出归对应阶段的 `records/`。`prod-like` 是拟生产实验环境，不代表真实生产承诺。

## 执行与验收记录

已开始 00 阶段，当前记录见 [2026-10-14 批次](00-preparation/records/2026-10-14/README.md)。母机安装、公共配置重启与运行时二进制安装已有用户回传证据，整体阶段尚未验收通过。

执行时按 `ops/<阶段目录>/records/<执行批次>/` 建目录，关联稳定步骤编号；保存命令/退出码、版本、对象/请求状态、数据校验、恢复和清理结果。历史脚本和原始输出保留原文，记录文档中的仓库链接随结构更新；失败尝试和当时的参数建议不能被后续成功结果覆盖。

00 必须有十节点 Linux/CRI/重启/幂等矩阵，04 有七语言 × 两套 CI 的 14 组矩阵，06 有 A–E 专题与实际 RTO/RPO。计划目标和静态文档检查不能代替运行证据。秘密和二进制备份放受控外部位置，只保留安全引用；不要提交私钥、Token、完整 kubeconfig、State、原始数据库备份或敏感日志。

## 操作手册与故障处理

已验证的稳定操作提炼回对应阶段操作手册，注明适用版本、前置、输入、操作、检查、失败停止/恢复、数据保护、清理以及对应记录。优先覆盖 DNS/CA/仓库、节点 Linux/CRI、etcd、Ceph/数据库、升级和完整集群恢复；未经运行验证的示例保留待验证说明。

实际故障在对应批次记录中保存症状、时间线、影响、诊断命令、观察证据、已排除原因、根因可信度、修复和恢复验证，关联原计划步骤和实际版本。未证实的推测不能写成已找到根因；可重复的修复操作再提炼回阶段手册。
