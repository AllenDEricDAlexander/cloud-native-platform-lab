# Cloud Native Platform Lab

在三台 ESXi 上建设可重复部署、可独立恢复、支持指定物料离线安装与构建的云原生实验平台。建设分为 00–06 七个阶段，06A–06E 是第 06 阶段内部专题。

## 1. 目标与边界

- **一套主集群**：十台 Rocky Linux 10 虚拟机（3 控制平面、2 基础设施、3 存储、2 工作节点），kubeadm 部署，Cilium 网络，外部 Ceph 存储。
- **集群外基础服务**：内部 DNS、内部 CA、Harbor、GitLab、Nexus、OpenWrt 显式代理与备份，不依赖 Kubernetes 或 Ceph，集群故障时仍可用于恢复。
- **可复现**：所有配置以台账、版本锁和自动化（Ansible 等）表达；每一步留存真实运行证据。
- **安全基线不让步**：SELinux 保持 Enforcing，firewalld 保持启用，规则按来源限定；私钥、口令与订阅地址不进仓库。

## 2. 阶段与进度

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| [00](plan/00-preparation.md) | 虚拟机、Linux 与 CRI、网络与代理、DNS、CA、仓库、备份、离线物料 | 主线可交接（[阶段验收](ops/00-preparation/records/2026-10-14/acceptance.md)）：十台节点与 DNS、CA、代理、Harbor、GitLab、Nexus、备份就绪，断网验收通过；未完成项在后续阶段跟踪 |
| [01](plan/01-kubernetes.md) | kubeadm 初始化、控制平面高可用、Cilium | [基础集群、完整备份与单 VM HA 通过](ops/01-kubernetes/records/2026-10-17-restart/README.md)；[01.03–01.10 核心实验验收与清理通过，已生成 02 交接](ops/01-kubernetes/records/core-07-10/runs/10-20261018T132014Z/README.md)；.15 分发待交付 |
| [02](plan/02-networking.md) | 服务网络、MetalLB、Gateway、网络策略 | [02.01 网络基准](ops/02-networking/records/02.01-20261018T142346Z/README.md)、[02.02.01 ClusterIP](ops/02-networking/records/02.02.01-fixed-20261018T152113Z/README.md)验收及清理通过；按统一批次准备剩余 02.02 内容 |
| [03](plan/03-ceph-middleware.md) | Ceph、Rook CSI、中间件 | 未开始 |
| [04](plan/04-devops-platform.md) | CI/CD、GitOps、平台工程 | 未开始 |
| [05](plan/05-observability.md) | 指标、日志、追踪、成本 | 未开始 |
| [06](plan/06-advanced-security-dr.md) | 安全、多集群、Serverless、虚拟化、灾备 | 未开始 |

逐项状态与证据见 [Phase 00 执行批次](ops/00-preparation/records/2026-10-14/README.md)与 [Phase 01 当前批次](ops/01-kubernetes/records/2026-10-17-restart/README.md)。阶段按顺序推进，上一阶段验收后再进入下一阶段；本阶段的问题在本阶段修复，不推到后续阶段。

## 3. 环境概况

台账是主机、网络与资源参数的唯一来源：**目标**（Phase 00 完成时应有的全部设备、虚拟机与服务）见 [阶段目标状态](plan/00-preparation.md#阶段完成时的目标状态)，**实际**见 [台账速览](ops/inventory/README.md)。

| 项目 | 概况 | 详细 |
| --- | --- | --- |
| 物理机 | 3 台 Dell R730/R730xd，ESXi 8，vCenter 纳管；合计 256 GiB 内存 | [台账速览](ops/inventory/README.md) |
| 网络 | 单一实验网 192.168.9.0/24，网关 .1；内部域名 internal.egon.top 下分 mgmt / k8s / svc 三层 | [网络台账](ops/inventory/networks.yaml) |
| 虚拟机 | 十台节点 .101–.110；基础服务 .10–.16（OpenWrt、DNS、Harbor、GitLab、Nexus、备份） | [主机台账](ops/inventory/hosts.yaml) |
| 版本 | 每个组件的精确版本、来源与校验值 | [版本锁](ops/versions.lock.yaml) |
| 管理端 | 一台 Mac：Ansible 控制端、内部 CA 私钥、种子物料 | [Phase 00 操作流程](ops/00-preparation/README.md) 步骤 0 |

## 4. 怎么读、怎么做

| 目录 | 回答的问题 | 内容 |
| --- | --- | --- |
| [arch/](arch/README.md) | 为什么这样设计 | 总体架构、拓扑、组件职责、技术约束与参考资料 |
| [plan/](plan/README.md) | 要做什么、做到什么程度算完成 | 七阶段任务、稳定步骤编号、交付物与验收标准；[步骤索引](plan/step-index.md)、[覆盖索引](plan/coverage.md) |
| [ops/](ops/README.md) | 具体怎么做 | 每个阶段一份可以照着执行的操作流程，以及台账、版本锁、配置、脚本和测试 |
| `ops/<阶段>/records/` | 实际做了什么、结果如何 | 按发生顺序的执行记录与原始证据，包括失败与修正 |

- **了解项目**：架构 → 阶段计划。
- **动手操作**：打开对应阶段的操作流程（当前是 [Phase 02 / 02.02.01](ops/02-networking/examples/service-clusterip/README.md)），按步骤执行，输出保存到该阶段的 records。
- **查看进度或排查问题**：看执行记录；遇到过的问题和处理方法都在其中。

## 5. 共同约定

- 数值以台账与版本锁为准；文档与它们不一致时，修正文档。
- 操作从管理端执行，输出用 `tee` 保存为证据；每个剧本可以重复运行。
- 失败时保留证据、查明原因再修复，不通过关闭 SELinux、停止防火墙或跳过校验来绕过。
- 秘密只放在仓库之外的受控位置；提交前检查证据中没有私钥、口令和订阅信息。
- 未经运行验证的内容标为待验证，计划与清单不能代替运行证据。

根目录只保留本入口和 arch、plan、ops 三个目录。
