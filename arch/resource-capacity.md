# 资源容量与启用条件

数值是沿用的起步预算，不是现场测量。[resources.yaml](../ops/inventory/resources.yaml) 保存规格和待确认容量，[hosts.yaml](../ops/inventory/hosts.yaml) 保存计划放置。

## 1. 节点与集群外预算

| 角色 | 台数 | 单台 vCPU / 内存 | 合计 vCPU / 内存 |
| --- | --- | --- | --- |
| cp | 3 | 4 / 8 GiB | 12 / 24 GiB |
| infra | 2 | 6 / 12 GiB | 12 / 24 GiB |
| storage | 3 | 8 / 16 GiB | 24 / 48 GiB |
| worker | 2 | 8 / 16 GiB | 16 / 32 GiB |
| 十节点合计 | 10 | — | 64 / 128 GiB |

OpenWrt、DNS、Harbor、GitLab、Nexus、管理机另计约 40 GiB。三宿主机规划总内存 256 GiB，减去上述 168 GiB 仅剩 88 GiB 的账面差额，仍未扣 ESXi、vCenter、既有 VM、第二 DNS、Ceph 恢复和维护余量，不能直接当成可分配内存。

原定十台各 8 vCPU/16 GiB 的扩展目标为 80 vCPU/160 GiB；连同基础服务为 200 GiB，是否启用取决于逐宿主机核算。物理 CPU 核数未知，不预先证明 vCPU 超分比合理。

## 2. 必须实际配置的资源

00 划分系统、containerd、构建缓存和候选数据盘，配置挂载、日志轮转与空间阈值；01 将 00 的角色预留写入 kubelet，并核对 Node Allocatable。storage 节点需为 OS 和 cephadm 保留 CPU/内存，不能把整台 16 GiB 许诺给 Pod。

三台 ESXi 的节点内存分别为 52、36、40 GiB；再分配基础 VM 时必须逐台计算。API 高可用不等于具备 ESXi 级 N+1 接管能力。

## 3. 实验运行档

| 运行档 | 保留能力 | 启用前条件 |
| --- | --- | --- |
| 基础常驻 | DNS/CA 信任、仓库、主 K8s、外部 Ceph/CSI、网关、最低 GitOps/监控/备份 | 主机与磁盘有维护余量 |
| 数据与交付 | 数据库、消息、双 CI、Backstage、Crossplane | CI 并发限制、磁盘/Pod/Service 配额与数据备份 |
| 观测对照 | ELK/Loki、Tempo、Pyroscope、压测 | 分别限定数据量、Retention、采样和资源上限 |
| 高级实验 | 第二集群、KubeVirt、Kubeflow、GPU、llm-d | 真实硬件/驱动/许可证、可用容量及独立恢复条件 |

按需运行表示错峰实验和按各产品流程停机/恢复，不表示删除原定实验，也不表示多数派数据库可以任意缩到零。每次实验记录开始、峰值、结束资源量与残留对象。

## 4. 启用与阻塞判断

先检查各 ESXi 内存/CPU/Datastore、节点 Allocatable/PVC、Ceph 水位、Service 地址余量，再决定启用规模。实际阈值在 00 的资产核验后填写，未知容量不写成零或无限。

GPU 型号、显存、直通、嵌套虚拟化、BGP 上游与第二集群资源均未实测；缺失条件写为阻塞并保留步骤。基础主线可以交接，但整体阶段完成仍要求关闭其未完成项。

## 5. 虚拟机规格与磁盘预算

控制平面三台，每台 4 vCPU、8GB；Infra 两台，每台 6 vCPU、12GB；Storage/Ceph 三台，每台 8 vCPU、16GB；Compute 两台，每台 8 vCPU、16GB。合计 64 vCPU、128GB。后续可按资源扩大到用户原定十台各 8 vCPU/16GB 的目标。

OS、containerd、临时构建和 OSD 数据盘分开规划。十台各 1TB 是虚拟磁盘配置目标，不代表十台都立即占满物理存储，也不代表 Ceph 有 10TB 可用空间。业务持久化主要通过 CSI 申请，不随意散落到各节点本地目录。
