# Cloud Native Platform Lab

在三台 ESXi 上建设可重复部署、可独立恢复、支持指定物料离线安装与构建的云原生实验平台。正式建设固定为 00–06 七个阶段；06A–06E 是第 06 阶段内部专题。

当前交付为规划文档、目录骨架和待核实台账。所有部署、实验和验收均未执行；空目录不表示组件已实现，`versions.lock.yaml` 的草案也不是可直接使用的版本锁。

## 从这里开始

1. 阅读 [总体架构](docs/architecture/overview.md)，确认组件部署位置与控制权。
2. 按 [七阶段总体计划](docs/plans/README.md) 查看实施顺序、交付物与验收。
3. 从 [Phase 00](docs/plans/00-preparation/README.md) 开始，依次完成 VM、基础服务、Linux 初始化和 CRI；服务器操作细节见 [节点初始化实施手册](docs/plans/00-preparation/node-bootstrap.md)。
4. 通过阶段验收后再进入下一阶段；按 [执行记录模板](docs/templates/execution-record.md) 保存证据，用 [全部步骤索引](docs/plans/step-index.md) 和 [技术覆盖索引](docs/plans/coverage.md) 定位原有步骤。

## 仓库结构

```text
cloud-native-platform-lab/
├── README.md
├── versions.lock.yaml
├── docs/
│   ├── architecture/
│   │   ├── overview.md
│   │   ├── physical-topology.md
│   │   ├── network-topology.md
│   │   ├── ip-address-plan.md
│   │   ├── storage-architecture.md
│   │   ├── security-architecture.md
│   │   └── resource-capacity.md
│   ├── adr/
│   ├── plans/
│   │   ├── 00-preparation/
│   │   ├── 01-kubernetes/
│   │   ├── 02-networking/
│   │   ├── 03-ceph-middleware/
│   │   ├── 04-devops-platform/
│   │   ├── 05-observability/
│   │   └── 06-advanced-security-dr/
│   ├── runbooks/
│   ├── troubleshooting/
│   ├── reference/
│   └── templates/
├── inventory/
│   ├── hosts.yaml
│   ├── networks.yaml
│   └── resources.yaml
├── infrastructure/
│   ├── opentofu/
│   ├── ansible/
│   ├── openwrt/
│   ├── dns/
│   ├── pki/
│   ├── registry/
│   └── cephadm/
├── kubernetes/
│   ├── bootstrap/
│   ├── core-resources/
│   ├── networking/
│   ├── storage/
│   ├── middleware/
│   ├── observability/
│   ├── security/
│   ├── operators/
│   └── multicluster/
├── gitops/
│   ├── bootstrap/
│   ├── platform/
│   └── environments/
│       ├── dev/
│       ├── staging/
│       └── prod-like/
├── ci/
│   ├── gitlab/
│   ├── jenkins/
│   ├── tekton/
│   ├── builders/
│   └── shared/
├── platform-engineering/
│   ├── backstage/
│   ├── crossplane/
│   └── service-templates/
├── labs/
│   ├── kubernetes-core/
│   ├── cilium-ebpf/
│   ├── ceph-rook/
│   ├── devsecops/
│   ├── observability/
│   ├── serverless/
│   ├── multi-cluster/
│   ├── kubevirt/
│   └── ai-gpu/
├── tests/
│   ├── smoke/
│   ├── integration/
│   ├── performance/
│   ├── failover/
│   ├── disaster-recovery/
│   └── security/
├── scripts/
└── reports/
```

保留 `V3.0-DOCUMENTS.md`、原架构基线和步骤索引作为兼容入口。各实施目录目前用说明文件或 `.gitkeep` 保留；阶段执行时才新增真实模块、配置和脚本。

## 各类文件负责什么

| 位置 | 保存内容 | 边界 |
| --- | --- | --- |
| `docs/architecture/`、`docs/adr/` | 架构、约束和决策理由 | 地址与硬件明细引用 inventory，避免独立维护另一份部署参数 |
| `docs/plans/` | 待执行任务、操作顺序、验收和恢复要求 | 不把计划文字当作执行结果 |
| `inventory/` | 主机、地址、放置和容量台账 | 当前为设计值，现场核实后才可转换为 Ansible/OpenTofu 输入 |
| `versions.lock.yaml` | 准确版本、镜像/包校验、来源、兼容性与验证记录 | `null` 表示待锁定，禁止据此部署 |
| `infrastructure/` | VM、Linux、CRI、基础仓库、DNS/PKI、外部 Ceph | 可由集群外管理机执行，不依赖业务集群 |
| `kubernetes/` | 可复用平台配置、Chart values、CRD/CR 与核心实验资源 | 不保存同一对象的多份环境副本 |
| `gitops/` | Argo CD 引导、平台应用引用、环境差异与发布版本 | 引用上游配置；`prod-like` 是拟生产实验环境，不是生产承诺 |
| `ci/` | 双 CI 模板、Builder、Tekton 对照及共用构建契约 | 构建制品并更新 GitOps，避免直接抢写集群对象 |
| `platform-engineering/` | Backstage、Crossplane 和七类语言服务模板 | 门户模板、平台 API 与交付流水线分别维护 |
| `labs/` | 可复现实验场景、参数、样例应用与清理说明 | 七套语言样例归 `labs/devsecops/`，不新增平行应用根目录 |
| `tests/` | 正常、故障、性能、容灾和安全验收用例 | 测试实现与实际测试结果分开 |
| `scripts/` | 跨模块检查、同步、备份和恢复入口 | 复用 Playbook/模块，不再实现一套主机配置逻辑 |
| `docs/runbooks/`、`docs/troubleshooting/` | 验证后的操作规程、故障诊断案例 | 规划中的命令先保留在 Plan，实测后提炼为 Runbook |
| `reports/` | 带步骤号和执行时间的脱敏证据、验收与比较报告 | 不提交私钥、Token、备份数据包或 IaC State |

## 阶段交付主线

| 阶段 | 必须形成的能力 |
| --- | --- |
| [00 基础准备](docs/plans/00-preparation/README.md) | 基础服务独立运行；十台 Rocky 完成 Linux/CRI 初始化、重启复验和离线检查，具备入群条件 |
| [01 Kubernetes](docs/plans/01-kubernetes/README.md) | kubeadm 三控制平面、十节点 Ready、etcd/API 故障实验及全部核心资源生命周期实验 |
| [02 网络治理](docs/plans/02-networking/README.md) | 入口、DNS/TLS、隔离、调度与网格实验有实际请求和拒绝证据 |
| [03 存储与中间件](docs/plans/03-ceph-middleware/README.md) | 外部 Ceph、CSI、数据库/消息服务、独立备份及自研 Operator |
| [04 交付平台](docs/plans/04-devops-platform/README.md) | 七类语言 × 双 CI 的 14 组构建部署；双 IaC、自动灰度回滚、自助服务 |
| [05 可观测性](docs/plans/05-observability/README.md) | Metrics/Logs/Traces/Profiles 关联、告警、SLO、性能和成本证据 |
| [06 进阶与恢复](docs/plans/06-advanced-security-dr/README.md) | 五个专题分别验收，完成升级、容灾重建和 RTO/RPO 实测 |

本次规划调整不启动虚拟机、应用或集群。实际实施时先补齐硬件、地址、软件版本和独立备份条件；硬件不满足的模块保留阻塞项，不删除范围，也不计为已通过。
