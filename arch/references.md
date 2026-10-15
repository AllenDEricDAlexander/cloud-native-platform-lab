# 官方资料与版本复核入口

资料维护日期：2026-10-13。本文件保留官方资料入口。本轮复核了 kubeadm 高可用/安装/升级、运行时与 containerd 配置、Rocky 10 CPU 前置、Cilium 兼容/L2、Rook External 和 Velero 数据搬运，以及原版本候选页面；其余条目保留为实施前复核入口。后续执行应切换到锁定版本的文档，不无条件照用 latest、main 或 stable。

以下资料支持技术语义与能力边界；本项目的 IP、资源预算、步骤顺序和验收目标是针对本实验室的工程设计，不是厂商对该硬件的认证。未逐项锁定的高级模块在执行时仍需复核。

## R01

[RFC 9499 — DNS Terminology](https://datatracker.ietf.org/doc/html/rfc9499)

内部 DNS、权威区、转发与分视图的语义。用于核对 internal.egon.top 的内部解析职责及客户端查询路径。

## K01

[Kubernetes 1.36 发布信息](https://kubernetes.io/releases/1.36/)

编写日页面列出 1.36.5；仅作为当前文档的候选起点，不替代执行日版本复核。

## K02

[kubeadm 配置 API](https://kubernetes.io/docs/reference/config-api/kubeadm-config.v1beta4/)

核对 API 入口、集群网络、networking.dnsDomain 和控制平面配置字段；Service DNS 默认域为 cluster.local。

## K03

[kubeadm 升级官方流程](https://kubernetes.io/docs/tasks/administer-cluster/kubeadm/kubeadm-upgrade/)

控制平面及 Worker 的顺序、版本约束和升级验证。具体过程以目标版本文档为准。

## K04

[Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)

Pod/容器状态、终止、重启和生命周期行为的核对入口。

## K05

[Liveness, Readiness, and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/)

三类探针的职责、执行条件与当前 API 行为。

## K06

[Garbage Collection](https://kubernetes.io/docs/concepts/architecture/garbage-collection/)

Foreground、Background、Orphan 及资源所有权语义。

## K07

[DNS for Services and Pods](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/)

Service/Pod DNS、Headless 与集群域配置的核对入口；本方案保留 cluster.local，例如 kubernetes.default.svc.cluster.local。

## N01

[Cilium Kubernetes Compatibility](https://docs.cilium.io/en/stable/network/kubernetes/compatibility/)

编写日明确测试列表覆盖到 Kubernetes 1.36；不以未列出等同必然不可用，也不未经测试就上主线。

## N02

[Cilium L2 Announcements](https://docs.cilium.io/en/stable/network/l2-announcements/)

L2 宣告前提、Beta 标记与限制；与 MetalLB 的独立实验边界。

## N03

[Gateway API 官方入口](https://gateway-api.sigs.k8s.io/)

核对 API 版本、Channel、路由类型和控制器实现报告；不能用 CRD 已安装代替数据面验证。

## S01

[Ceph Tentacle 发布与安全说明](https://docs.ceph.com/en/latest/releases/tentacle/)

编写日页面列出 20.2.4 及安全升级事项。执行前使用对应稳定版本文档，复核补丁与升级要求。

## S02

[cephadm 部署新集群](https://docs.ceph.com/en/latest/cephadm/install/)

核对宿主机依赖、初始化和服务管理；latest 页面可能属于开发文档，应切换实际使用版本。

## S03

[Rook 前置条件](https://rook.io/docs/rook/latest-release/Getting-Started/Prerequisites/prerequisites/)

核对 Kubernetes 支持范围、设备要求、内核和卷客户端条件。

## S04

[Rook External Storage Cluster](https://rook.io/docs/rook/latest-release/CRDs/Cluster/external-cluster/external-cluster/)

区分由外部 Ceph 提供存储与在 Kubernetes 内管理 Ceph 守护进程。

## D01

[GitLab Runner Kubernetes Executor](https://docs.gitlab.com/runner/executors/kubernetes/)

动态 Job Pod、资源、权限及执行器约束的官方核对入口。

## D02

[Jenkins Kubernetes Plugin](https://plugins.jenkins.io/kubernetes/)

动态 Agent、模板与插件版本要求。

## D03

[Harbor Proxy Cache](https://goharbor.io/docs/main/administration/configure-proxy-cache/)

上游缓存项目与访问路径，不代表任意镜像地址都能透明重写。

## D04

[Backstage Software Templates](https://backstage.io/docs/features/software-templates/)

服务模板、仓库生成与任务执行能力的核对入口。

## D05

[Crossplane Compositions](https://docs.crossplane.io/latest/composition/compositions/)

组合资源、函数与当前版本行为；DevApplication/DevDatabase 是本项目拟设计 API。

## D06

[Argo CD 文档](https://argo-cd.readthedocs.io/en/stable/)

主 GitOps 的声明式交付、同步和权限核对入口。

## D07

[Argo Rollouts 文档](https://argo-rollouts.readthedocs.io/en/stable/)

渐进发布、分析与实际流量管理适配。

## O01

[OpenTelemetry Collector](https://opentelemetry.io/docs/collector/)

统一遥测接收、处理、导出和运行设计的官方入口。

## O02

[Elastic Cloud on Kubernetes](https://www.elastic.co/docs/deploy-manage/deploy/cloud-on-k8s)

ECK 的产品、版本和实际授权能力核对。

## A01

[Cluster API Concepts](https://cluster-api.sigs.k8s.io/user/concepts.html)

管理集群、工作负载集群与机器生命周期的边界。

## A02

[KubeVirt Live Migration](https://kubevirt.io/user-guide/compute/live_migration/)

迁移前置与存储、网络、CPU 等条件。

## A03

[Velero CSI Snapshot Data Movement](https://velero.io/docs/main/csi-snapshot-data-movement/)

区分快照引用和实际数据搬运；备份必须能够脱离原存储恢复。

## A04

[KEDA 文档](https://keda.sh/docs/latest/)

当前 Scaler、认证、缩零与工作负载支持，执行时切换锁定版本。

## A05

[Kyverno 文档](https://kyverno.io/docs/introduction/)

策略、准入与运行边界的核对入口。

## A06

[Knative 文档](https://knative.dev/docs/)

Serving、Eventing、网络依赖与 Serverless 实验。

## A07

[Dapr 文档](https://docs.dapr.io/)

服务调用、状态、发布订阅和 Workflow 的组件支持。

## A08

[KServe 文档](https://kserve.github.io/website/)

模型服务、部署模式与依赖检查。

## A09

[NVIDIA GPU Operator Platform Support](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/platform-support.html)

核对 GPU、操作系统、驱动与部署方式；不能保证任意 Rocky/GPU 组合直接支持。

## A10

[vLLM GPU Installation](https://docs.vllm.ai/en/latest/getting_started/installation/gpu/)

模型框架硬件和软件前置；老架构 GPU 必须单独核对。

## K08

[Container Runtimes](https://kubernetes.io/docs/setup/production-environment/container-runtimes/)

运行时、cgroup 与 CRI 前置。项目将系统/CRI 安装配置安排在 00，01 仅复验并创建集群；阶段划分是本项目设计。

## K09

[Installing kubeadm](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/)

Swap、包仓库、系统前置和 SELinux 示例的核对入口；自定义 Enforcing 方案仍需验证具体策略，不能假定任意 Rocky/containerd 组合都受支持。

## K10

[containerd CRI configuration](https://github.com/containerd/containerd/blob/main/docs/cri/config.md)

2.x 的配置 v3、runtime/images 插件路径、SystemdCgroup、pinned sandbox image 和 registry 配置；实施时对应锁定 tag 复核。

## K11

[cri-tools crictl](https://github.com/kubernetes-sigs/cri-tools/blob/master/docs/crictl.md)

CRI socket、镜像和 sandbox/container 操作。00 的 host-network smoke 只验证 CRI，不能替代 01 的 CNI/Pod 网络验收。

## K12

[Creating Highly Available Clusters with kubeadm](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/high-availability/)

三控制平面、负载均衡入口及 join/健康检查前置；实际 kube-vip 引导需按其锁定版本确认凭据顺序。

## R02

[Rocky Linux 10 Release Notes](https://docs.rockylinux.org/latest/releases/release_notes/10_0/)

x86_64 平台的 x86-64-v3 要求；客体实际可见 CPU 能力/EVC 必须现场检查，不能只凭物理 CPU 名称判断。

## 版本基线与复核约定

本次核对的 Kubernetes 候选起点为 1.36.5，Cilium 1.20 系列的官方测试范围覆盖 1.36。升级路线以相邻次版本为原则，具体执行时重新核对维护期、补丁和全部关键插件。[发布依据](references.md#k01)；[兼容依据](references.md#n01)。

Ceph Tentacle 在编写日官方页面已列出 20.2.4 及安全修复，不应只满足早期最低版本；Rook/CSI 的精确版本根据执行日矩阵确定。ops/versions.lock.yaml 已建立草案结构；执行前逐项填入 OS、包、Chart、镜像 Digest、API Channel、核对日期与实际验证证据。当前未锁定字段不能用于部署。[Ceph 依据](references.md#s01)；[Rook 依据](references.md#s03)。
