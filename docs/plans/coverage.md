# V3.0 技术覆盖与实施位置

本索引用于确认已讨论的技术方向都有实施位置，不代表已部署或已通过测试。一个方向可跨阶段建设，以下链接优先指向专题步骤，必要时回访相关前置。

[返回七阶段目录](README.md) · [全部步骤索引](step-index.md)

## 基础设施、域名与供应系统

### ESXi 与 Rocky Linux 模板

实施位置：[00.04.03 制作 Rocky Linux 10 虚拟机模板](00-preparation/README.md#000403-制作-rocky-linux-10-虚拟机模板)。

### OpenWrt 旁路由

实施位置：[00.05.01 准备 OpenWrt 虚拟机](00-preparation/README.md#000501-准备-openwrt-虚拟机)；[02.06.04 实验 Cilium Egress Gateway 联动 OpenWrt](02-networking/README.md#020604-实验-cilium-egress-gateway-联动-openwrt)。

### VPN、WireGuard 与出口代理

实施位置：[00.06.01 建立 VPN 隧道与凭据管理](00-preparation/README.md#000601-建立-vpn-隧道与凭据管理)；[06.14.04 执行仓库、DNS 和 VPN 故障](06-advanced-security-dr/README.md#061404-执行仓库dns-和-vpn-故障)；[00.06.02 部署受控的显式 HTTP/HTTPS 代理](00-preparation/README.md#000602-部署受控的显式-httphttps-代理)；[00.06.04 设计代理绕行清单](00-preparation/README.md#000604-设计代理绕行清单)。

### egon.local、egon.top 与 .local 兼容

实施位置：[00.07.02 处理 macOS 的 .local 解析路径](00-preparation/README.md#000702-处理-macos-的-local-解析路径)；[00.03.03 建立公网发布白名单](00-preparation/README.md#000303-建立公网发布白名单)；[00.03.04 确定内部 DNS 与集群 DNS 的职责](00-preparation/README.md#000304-确定内部-dns-与集群-dns-的职责)。

### 内部 CA、证书与信任链

实施位置：[00.07.02 处理 macOS 的 .local 解析路径](00-preparation/README.md#000702-处理-macos-的-local-解析路径)；[00.08.02 分发各语言和系统的 CA 信任](00-preparation/README.md#000802-分发各语言和系统的-ca-信任)；[00.08.01 建立内部 PKI 信任链](00-preparation/README.md#000801-建立内部-pki-信任链)。

### Harbor 与镜像缓存

实施位置：[00.09.02 部署 Harbor 与项目权限](00-preparation/README.md#000902-部署-harbor-与项目权限)；[05.03.05 接入 GitLab、Jenkins、Harbor 与 Nexus](05-observability/README.md#050305-接入-gitlabjenkinsharbor-与-nexus)；[00.09.03 建立上游代理缓存和引导镜像库](00-preparation/README.md#000903-建立上游代理缓存和引导镜像库)。

### Nexus 与多语言依赖

实施位置：[00.09.04 部署 Nexus 和语言依赖代理](00-preparation/README.md#000904-部署-nexus-和语言依赖代理)；[05.03.05 接入 GitLab、Jenkins、Harbor 与 Nexus](05-observability/README.md#050305-接入-gitlabjenkinsharbor-与-nexus)；[04.02.02 配置各语言依赖代理](04-devops-platform/README.md#040202-配置各语言依赖代理)。

### 离线部署与物料

实施位置：[00.02.03 建立软件来源和离线物料清单](00-preparation/README.md#000203-建立软件来源和离线物料清单)；[04.02.05 验证离线构建与制品保留](04-devops-platform/README.md#040205-验证离线构建与制品保留)；[00.10.04 执行指定物料的断网验收](00-preparation/README.md#001004-执行指定物料的断网验收)。

### 资源与故障域

实施位置：[03.01.01 复核 OSD 设备与物理故障域](03-ceph-middleware/README.md#030101-复核-osd-设备与物理故障域)；[03.01.03 明确三故障域的恢复限制](03-ceph-middleware/README.md#030103-明确三故障域的恢复限制)；[00.01.03 制定内存和磁盘预算](00-preparation/README.md#000103-制定内存和磁盘预算)。

## Kubernetes 核心与调度

### kubeadm 与 stacked etcd 高可用

实施位置：[00.04.05 分散控制平面和存储节点](00-preparation/README.md#000405-分散控制平面和存储节点)；[01.02.03 初始化第一个控制平面](01-kubernetes/README.md#010203-初始化第一个控制平面)；[01.03.03 建立 etcd 与控制平面备份](01-kubernetes/README.md#010303-建立-etcd-与控制平面备份)。

### containerd 与 CRI

实施位置：[01.01.04 部署和验证 containerd](01-kubernetes/README.md#010104-部署和验证-containerd)；[01.01.03 配置内核、主机防火墙和 SELinux](01-kubernetes/README.md#010103-配置内核主机防火墙和-selinux)。

### Pod 生命周期、Init 与 Sidecar

实施位置：[01.04.02 观察 Pod、容器状态和重启](01-kubernetes/README.md#010402-观察-pod容器状态和重启)；[01.04.03 实施 Init Container 与 Sidecar](01-kubernetes/README.md#010403-实施-init-container-与-sidecar)；[01.04.04 验证临时容器与故障诊断](01-kubernetes/README.md#010404-验证临时容器与故障诊断)。

### Startup Probe

实施位置：[01.05.01 验证 Startup Probe 的启动保护](01-kubernetes/README.md#010501-验证-startup-probe-的启动保护)。

### Liveness Probe

实施位置：[01.05.02 验证 Liveness Probe 的自愈边界](01-kubernetes/README.md#010502-验证-liveness-probe-的自愈边界)。

### Readiness 与 EndpointSlice

实施位置：[01.05.03 验证 Readiness 与 EndpointSlice](01-kubernetes/README.md#010503-验证-readiness-与-endpointslice)。

### PreStop 与优雅停止

实施位置：[01.05.04 实现 PreStop 与应用优雅终止](01-kubernetes/README.md#010504-实现-prestop-与应用优雅终止)。

### RC 与 ReplicaSet

实施位置：[01.06.01 比较 RC 与 ReplicaSet](01-kubernetes/README.md#010601-比较-rc-与-replicaset)。

### Deployment 与滚动更新

实施位置：[01.06.02 建立 Deployment 与版本记录](01-kubernetes/README.md#010602-建立-deployment-与版本记录)；[01.06.04 比较 RollingUpdate 与 Recreate](01-kubernetes/README.md#010604-比较-rollingupdate-与-recreate)。

### StatefulSet 与持久化

实施位置：[01.07.01 建立 StatefulSet 稳定身份](01-kubernetes/README.md#010701-建立-statefulset-稳定身份)；[01.07.02 比较 StatefulSet 更新与扩缩策略](01-kubernetes/README.md#010702-比较-statefulset-更新与扩缩策略)。

### DaemonSet 更新回滚

实施位置：[01.07.03 部署 DaemonSet 并验证节点覆盖](01-kubernetes/README.md#010703-部署-daemonset-并验证节点覆盖)；[01.07.04 实施 DaemonSet 更新和回滚](01-kubernetes/README.md#010704-实施-daemonset-更新和回滚)。

### 级联、非级联与 Finalizer

实施位置：[01.08.01 比较 Foreground 与 Background 删除](01-kubernetes/README.md#010801-比较-foreground-与-background-删除)；[01.08.02 实施 Orphan 非级联删除](01-kubernetes/README.md#010802-实施-orphan-非级联删除)；[01.08.03 观察 Finalizer 与删除保护](01-kubernetes/README.md#010803-观察-finalizer-与删除保护)；[03.09.02 实现调谐、幂等与 Finalizer](03-ceph-middleware/README.md#030902-实现调谐幂等与-finalizer)。

### Job、CronJob 与批任务

实施位置：[01.09.02 部署 CronJob 并处理时间语义](01-kubernetes/README.md#010902-部署-cronjob-并处理时间语义)；[01.09.01 部署批处理 Job](01-kubernetes/README.md#010901-部署批处理-job)。

### ConfigMap 与 Secret

实施位置：[01.10.01 比较 ConfigMap 注入与刷新](01-kubernetes/README.md#011001-比较-configmap-注入与刷新)；[01.10.02 管理 Secret 和容器拉取凭据](01-kubernetes/README.md#011002-管理-secret-和容器拉取凭据)。

### Service 与 Headless

实施位置：[02.02.01 验证 ClusterIP 与端点选择](02-networking/README.md#020201-验证-clusterip-与端点选择)；[02.02.04 验证 Headless 与无 Selector Service](02-networking/README.md#020204-验证-headless-与无-selector-service)；[02.02.05 验证 ExternalName 和 DNS 限制](02-networking/README.md#020205-验证-externalname-和-dns-限制)。

### Taint 与 Toleration

实施位置：[02.07.03 验证 Taint 与 Toleration](02-networking/README.md#020703-验证-taint-与-toleration)。

### Affinity 与反亲和

实施位置：[02.07.02 验证 NodeSelector 与 Node Affinity](02-networking/README.md#020702-验证-nodeselector-与-node-affinity)；[02.07.04 验证 Pod Affinity 与 Anti-Affinity](02-networking/README.md#020704-验证-pod-affinity-与-anti-affinity)。

### Topology Spread

实施位置：[02.07.05 验证 Topology Spread Constraints](02-networking/README.md#020705-验证-topology-spread-constraints)。

### QoS、Eviction 与 Requests/Limits

实施位置：[02.08.02 比较 Guaranteed、Burstable 与 BestEffort](02-networking/README.md#020802-比较-guaranteedburstable-与-besteffort)；[02.08.01 设置 Requests、Limits、LimitRange 与 Quota](02-networking/README.md#020801-设置-requestslimitslimitrange-与-quota)；[05.08.06 分析 Requests、实际用量与效率](05-observability/README.md#050806-分析-requests实际用量与效率)；[02.08.03 验证 CPU 限流和临时存储耗尽](02-networking/README.md#020803-验证-cpu-限流和临时存储耗尽)。

### PDB、Quota 与 PriorityClass

实施位置：[02.08.05 验证 PDB 与节点维护](02-networking/README.md#020805-验证-pdb-与节点维护)；[06.05.06 结合 PDB、优先级与伸缩做压力实验](06-advanced-security-dr/README.md#060506-结合-pdb优先级与伸缩做压力实验)；[02.08.04 验证 PriorityClass 与抢占](02-networking/README.md#020804-验证-priorityclass-与抢占)；[02.08.01 设置 Requests、Limits、LimitRange 与 Quota](02-networking/README.md#020801-设置-requestslimitslimitrange-与-quota)。

### HPA、VPA 与 KEDA

实施位置：[01.09.04 实施 CPU 与内存 HPA 基础实验](01-kubernetes/README.md#010904-实施-cpu-与内存-hpa-基础实验)；[04.07.04 验证 HPA 与 GitOps 字段所有权](04-devops-platform/README.md#040704-验证-hpa-与-gitops-字段所有权)；[06.05.02 部署 VPA 并验证资源建议](06-advanced-security-dr/README.md#060502-部署-vpa-并验证资源建议)；[06.05.03 使用 KEDA 扩缩 Kafka 消费者](06-advanced-security-dr/README.md#060503-使用-keda-扩缩-kafka-消费者)；[06.05.04 使用 KEDA 扩缩 RabbitMQ Worker](06-advanced-security-dr/README.md#060504-使用-keda-扩缩-rabbitmq-worker)。

### ServiceAccount 与 RBAC

实施位置：[01.10.03 建立最小 ServiceAccount 与 RBAC](01-kubernetes/README.md#011003-建立最小-serviceaccount-与-rbac)；[06.01.04 轮换 ServiceAccount 和机器人凭据](06-advanced-security-dr/README.md#060104-轮换-serviceaccount-和机器人凭据)。

### kubeadm 升级与 Memory QoS

实施位置：[06.15.03 升级首个控制平面](06-advanced-security-dr/README.md#061503-升级首个控制平面)；[06.15.04 逐台升级其余控制平面](06-advanced-security-dr/README.md#061504-逐台升级其余控制平面)；[06.15.07 验证 Memory QoS 与目标版本新增能力](06-advanced-security-dr/README.md#061507-验证-memory-qos-与目标版本新增能力)。

## 网络、网关与服务治理

### Cilium、Hubble 与 eBPF

实施位置：[01.02.05 安装 Cilium 基础 CNI](01-kubernetes/README.md#010205-安装-cilium-基础-cni)；[02.06.02 比较 Kubernetes 与 Cilium 网络策略](02-networking/README.md#020602-比较-kubernetes-与-cilium-网络策略)；[02.01.03 启用 Hubble 基础观测](02-networking/README.md#020103-启用-hubble-基础观测)；[02.09.01 比较 kube-proxy 与 eBPF 替代](02-networking/README.md#020901-比较-kube-proxy-与-ebpf-替代)。

### MetalLB 与 Cilium L2/BGP

实施位置：[02.03.01 部署 MetalLB L2 主方案](02-networking/README.md#020301-部署-metallb-l2-主方案)；[02.09.03 实验 Cilium LB IPAM 与 L2 Announcements](02-networking/README.md#020903-实验-cilium-lb-ipam-与-l2-announcements)；[02.09.04 实验 Cilium BGP Control Plane](02-networking/README.md#020904-实验-cilium-bgp-control-plane)。

### Ingress 与 Gateway API

实施位置：[02.04.06 部署传统 Ingress 对比](02-networking/README.md#020406-部署传统-ingress-对比)；[02.04.01 锁定 Gateway API 与实现兼容性](02-networking/README.md#020401-锁定-gateway-api-与实现兼容性)。

### HTTP、HTTPS、gRPC、TCP、UDP

实施位置：[02.04.03 配置内部 HTTP 与 HTTPS 路由](02-networking/README.md#020403-配置内部-http-与-https-路由)；[02.04.05 配置 gRPC、TCP 与 UDP 实验](02-networking/README.md#020405-配置-grpctcp-与-udp-实验)。

### cert-manager 与公网发布

实施位置：[02.05.01 部署 cert-manager 与内部签发器](02-networking/README.md#020501-部署-cert-manager-与内部签发器)；[02.05.03 按白名单发布 egon.top 应用](02-networking/README.md#020503-按白名单发布-egontop-应用)。

### NetworkPolicy 与出口治理

实施位置：[02.06.01 实施 Namespace 默认拒绝策略](02-networking/README.md#020601-实施-namespace-默认拒绝策略)；[02.06.02 比较 Kubernetes 与 Cilium 网络策略](02-networking/README.md#020602-比较-kubernetes-与-cilium-网络策略)；[02.06.04 实验 Cilium Egress Gateway 联动 OpenWrt](02-networking/README.md#020604-实验-cilium-egress-gateway-联动-openwrt)。

### Istio Sidecar/Ambient

实施位置：[02.10.01 部署 Sidecar 模式服务网格](02-networking/README.md#021001-部署-sidecar-模式服务网格)；[02.10.02 部署 Ambient 模式并按需增加 waypoint](02-networking/README.md#021002-部署-ambient-模式并按需增加-waypoint)。

### SPIFFE/SPIRE

实施位置：[02.10.04 部署 SPIFFE/SPIRE 身份对比](02-networking/README.md#021004-部署-spiffespire-身份对比)；[06.03.06 回访 SPIFFE/SPIRE 与跨服务信任](06-advanced-security-dr/README.md#060306-回访-spiffespire-与跨服务信任)。

### 多集群 Cluster Mesh 与 MCS

实施位置：[06.10.02 部署 Cilium Cluster Mesh](06-advanced-security-dr/README.md#061002-部署-cilium-cluster-mesh)；[06.10.03 验证 MCS API 与服务导入导出](06-advanced-security-dr/README.md#061003-验证-mcs-api-与服务导入导出)。

## Ceph、数据服务与 Operator

### cephadm 与独立 Ceph

实施位置：[00.01.04 固定主方案与对比实验的管理权](00-preparation/README.md#000104-固定主方案与对比实验的管理权)；[03.01.04 保护宿主机和 Ceph 资源](03-ceph-middleware/README.md#030104-保护宿主机和-ceph-资源)；[03.02.02 引导首个 Ceph 管理节点](03-ceph-middleware/README.md#030202-引导首个-ceph-管理节点)。

### MON、MGR、OSD 与 CRUSH

实施位置：[03.02.03 扩展为三个 MON 与两个 MGR](03-ceph-middleware/README.md#030203-扩展为三个-mon-与两个-mgr)；[03.02.04 按明确设备清单创建 OSD](03-ceph-middleware/README.md#030204-按明确设备清单创建-osd)；[03.02.05 配置 CRUSH、池与基础监控](03-ceph-middleware/README.md#030205-配置-crush池与基础监控)。

### RBD、CephFS、MDS 与 RGW

实施位置：[03.03.01 建立 RBD 块存储池](03-ceph-middleware/README.md#030301-建立-rbd-块存储池)；[03.03.02 建立 CephFS 与 MDS 主备](03-ceph-middleware/README.md#030302-建立-cephfs-与-mds-主备)；[03.03.03 建立 RGW 对象存储入口](03-ceph-middleware/README.md#030303-建立-rgw-对象存储入口)。

### Rook External 与内部模式

实施位置：[03.04.02 部署 Rook External 控制与 CSI](03-ceph-middleware/README.md#030402-部署-rook-external-控制与-csi)；[03.06.04 准备 Rook 自管理独立实验资源](03-ceph-middleware/README.md#030604-准备-rook-自管理独立实验资源)；[03.06.05 实验 CephCluster 与存储 CRD](03-ceph-middleware/README.md#030605-实验-cephcluster-与存储-crd)。

### PV、PVC 与 StorageClass

实施位置：[03.05.01 比较静态 PV 与动态供应](03-ceph-middleware/README.md#030501-比较静态-pv-与动态供应)；[03.04.04 建立 StorageClass 与默认策略](03-ceph-middleware/README.md#030404-建立-storageclass-与默认策略)；[03.05.06 回访 StatefulSet 持久化实验](03-ceph-middleware/README.md#030506-回访-statefulset-持久化实验)。

### Snapshot、Clone 与回收

实施位置：[03.05.03 部署快照控制链并还原测试数据](03-ceph-middleware/README.md#030503-部署快照控制链并还原测试数据)；[03.05.04 验证克隆、回收与保留策略](03-ceph-middleware/README.md#030504-验证克隆回收与保留策略)；[03.05.02 验证卷扩容与文件系统变化](03-ceph-middleware/README.md#030502-验证卷扩容与文件系统变化)。

### Ceph 故障与数据恢复

实施位置：[03.06.01 演练单 OSD 和存储 VM 故障](03-ceph-middleware/README.md#030601-演练单-osd-和存储-vm-故障)；[03.06.02 演练计划维护和安全下线](03-ceph-middleware/README.md#030602-演练计划维护和安全下线)。

### PostgreSQL、CloudNativePG 与 PITR

实施位置：[03.07.01 部署单实例 PostgreSQL 基准](03-ceph-middleware/README.md#030701-部署单实例-postgresql-基准)；[05.03.03 接入 PostgreSQL 与 Redis](05-observability/README.md#050303-接入-postgresql-与-redis)；[03.07.02 使用 CloudNativePG 建立高可用](03-ceph-middleware/README.md#030702-使用-cloudnativepg-建立高可用)；[03.07.03 实施 WAL 归档、备份与 PITR](03-ceph-middleware/README.md#030703-实施-wal-归档备份与-pitr)。

### Redis、Sentinel、Cluster 与 Valkey

实施位置：[03.08.01 部署 Redis 并验证持久化](03-ceph-middleware/README.md#030801-部署-redis-并验证持久化)；[03.08.02 比较 Sentinel、Redis Cluster 与 Valkey](03-ceph-middleware/README.md#030802-比较-sentinelredis-cluster-与-valkey)。

### Kafka、Strimzi 与 KRaft

实施位置：[03.08.03 使用 Strimzi 部署 Kafka KRaft](03-ceph-middleware/README.md#030803-使用-strimzi-部署-kafka-kraft)；[03.08.04 验证 Kafka 数据与消费者生命周期](03-ceph-middleware/README.md#030804-验证-kafka-数据与消费者生命周期)。

### RabbitMQ 与 Quorum Queue

实施位置：[03.08.05 使用 RabbitMQ Operator 建立消息集群](03-ceph-middleware/README.md#030805-使用-rabbitmq-operator-建立消息集群)；[03.08.06 测试 RabbitMQ 故障与队列积压](03-ceph-middleware/README.md#030806-测试-rabbitmq-故障与队列积压)。

### NATS 与 JetStream

实施位置：[03.08.07 部署 NATS 与 JetStream](03-ceph-middleware/README.md#030807-部署-nats-与-jetstream)。

### MySQL Operator

实施位置：[03.07.05 增加 MySQL Operator 对照](03-ceph-middleware/README.md#030705-增加-mysql-operator-对照)。

### 自研 CRD/Operator、Kubebuilder/Fabric8/kube-rs

实施位置：[03.09.01 设计自定义 DemoApp API](03-ceph-middleware/README.md#030901-设计自定义-demoapp-api)；[03.09.02 实现调谐、幂等与 Finalizer](03-ceph-middleware/README.md#030902-实现调谐幂等与-finalizer)；[03.09.03 验证 CRD 版本与控制器权限](03-ceph-middleware/README.md#030903-验证-crd-版本与控制器权限)。

## DevOps、IaC 与平台工程

### GitLab CI 与动态 Runner

实施位置：[04.03.02 建立公共 GitLab CI 模板](04-devops-platform/README.md#040302-建立公共-gitlab-ci-模板)；[04.03.05 验证 GitLab CI 故障恢复](04-devops-platform/README.md#040305-验证-gitlab-ci-故障恢复)；[04.03.01 部署 Runner 管理器和 Kubernetes Executor](04-devops-platform/README.md#040301-部署-runner-管理器和-kubernetes-executor)。

### Jenkins、动态 Agent、共享库与 JCasC

实施位置：[04.04.01 部署 Jenkins Controller 与持久化](04-devops-platform/README.md#040401-部署-jenkins-controller-与持久化)；[04.04.02 配置动态 Kubernetes Agent](04-devops-platform/README.md#040402-配置动态-kubernetes-agent)；[04.04.03 建立 Jenkins Configuration as Code 与共享库](04-devops-platform/README.md#040403-建立-jenkins-configuration-as-code-与共享库)。

### BuildKit 与构建缓存

实施位置：[04.02.03 部署隔离的 BuildKit 构建能力](04-devops-platform/README.md#040203-部署隔离的-buildkit-构建能力)；[04.02.04 划分四类缓存并防止污染](04-devops-platform/README.md#040204-划分四类缓存并防止污染)。

### Java 双 CI

实施位置：[04.05.01 完成 Java 与 Spring Boot 服务](04-devops-platform/README.md#040501-完成-java-与-spring-boot-服务)。

### Rust 双 CI

实施位置：[04.05.02 完成 Rust 服务与原生制品](04-devops-platform/README.md#040502-完成-rust-服务与原生制品)。

### C 双 CI

实施位置：[04.05.03 完成 C 服务或计算 Worker](04-devops-platform/README.md#040503-完成-c-服务或计算-worker)。

### C++ 双 CI

实施位置：[04.05.04 完成 C++ 服务与依赖缓存](04-devops-platform/README.md#040504-完成-c-服务与依赖缓存)。

### C#/.NET 双 CI

实施位置：[04.05.05 完成 C# 与现代 .NET 服务](04-devops-platform/README.md#040505-完成-c-与现代-net-服务)。

### JS/TS 双 CI

实施位置：[04.05.06 完成 JS/TS 前后端交付](04-devops-platform/README.md#040506-完成-jsts-前后端交付)。

### Python 双 CI

实施位置：[04.05.07 完成 Python 服务和任务程序](04-devops-platform/README.md#040507-完成-python-服务和任务程序)。

### 十四种组合验收

实施位置：[04.05.08 执行十四种构建发布组合验收](04-devops-platform/README.md#040508-执行十四种构建发布组合验收)。

### 双 CI 的 OpenTofu/Ansible IaC

实施位置：[04.06.03 实现 GitLab CI 的 IaC 流程](04-devops-platform/README.md#040603-实现-gitlab-ci-的-iac-流程)；[04.06.04 实现 Jenkins 的 IaC 流程](04-devops-platform/README.md#040604-实现-jenkins-的-iac-流程)；[04.06.05 实现 Ansible 幂等、分批和漂移修复](04-devops-platform/README.md#040605-实现-ansible-幂等分批和漂移修复)。

### State 锁与集群外恢复执行器

实施位置：[04.06.02 建立远端 State、锁和备份](04-devops-platform/README.md#040602-建立远端-state锁和备份)；[04.06.06 建立集群外恢复执行器](04-devops-platform/README.md#040606-建立集群外恢复执行器)。

### Helm 与 Kustomize

实施位置：[04.07.01 制作 Helm Chart 与多环境覆盖](04-devops-platform/README.md#040701-制作-helm-chart-与多环境覆盖)。

### Argo CD、ApplicationSet 与 Flux

实施位置：[04.07.02 部署 Argo CD 与最小权限项目](04-devops-platform/README.md#040702-部署-argo-cd-与最小权限项目)；[04.09.04 划分 Argo CD、Crossplane 与 Operator 所有权](04-devops-platform/README.md#040904-划分-argo-cdcrossplane-与-operator-所有权)；[04.07.05 建立 ApplicationSet 与通知](04-devops-platform/README.md#040705-建立-applicationset-与通知)；[06.10.01 接入多集群 Argo CD/ApplicationSet](06-advanced-security-dr/README.md#061001-接入多集群-argo-cdapplicationset)；[04.10.02 实验 Flux GitOps](04-devops-platform/README.md#041002-实验-flux-gitops)。

### Argo Rollouts、Canary 与 Blue/Green

实施位置：[04.08.01 部署 Argo Rollouts 并验证路由适配](04-devops-platform/README.md#040801-部署-argo-rollouts-并验证路由适配)；[05.07.03 将指标接入 Argo Rollouts](05-observability/README.md#050703-将指标接入-argo-rollouts)；[04.08.02 实现 Canary 与 Blue/Green](04-devops-platform/README.md#040802-实现-canary-与-bluegreen)。

### Trivy、SBOM、Cosign 与供应链

实施位置：[04.08.04 建立 SBOM、扫描和来源证明](04-devops-platform/README.md#040804-建立-sbom扫描和来源证明)；[04.08.05 使用 Cosign 签名并保留可信材料](04-devops-platform/README.md#040805-使用-cosign-签名并保留可信材料)；[04.08.06 接入准入校验与拒绝发布实验](04-devops-platform/README.md#040806-接入准入校验与拒绝发布实验)。

### Backstage、Software Templates 与 TechDocs

实施位置：[04.09.01 部署 Backstage 并建立服务目录](04-devops-platform/README.md#040901-部署-backstage-并建立服务目录)；[04.09.02 实现 Software Templates 与双 CI 选择](04-devops-platform/README.md#040902-实现-software-templates-与双-ci-选择)；[04.09.06 完善 TechDocs、API 目录与权限](04-devops-platform/README.md#040906-完善-techdocsapi-目录与权限)。

### Crossplane 与平台 API

实施位置：[04.09.03 部署 Crossplane 与版本化平台 API](04-devops-platform/README.md#040903-部署-crossplane-与版本化平台-api)；[04.09.04 划分 Argo CD、Crossplane 与 Operator 所有权](04-devops-platform/README.md#040904-划分-argo-cdcrossplane-与-operator-所有权)；[04.09.05 完成开发者自助服务端到端交付](04-devops-platform/README.md#040905-完成开发者自助服务端到端交付)。

### Tekton 与 Dragonfly

实施位置：[04.10.01 实验 Tekton 原生流水线](04-devops-platform/README.md#041001-实验-tekton-原生流水线)；[06.08.03 比较 Workflow、Tekton 与应用 CI](06-advanced-security-dr/README.md#060803-比较-workflowtekton-与应用-ci)；[04.10.03 实验 Dragonfly P2P 分发](04-devops-platform/README.md#041003-实验-dragonfly-p2p-分发)。

## 可观测性、性能与成本

### Prometheus、Grafana 与 Alertmanager

实施位置：[01.09.03 建立资源指标入口](01-kubernetes/README.md#010903-建立资源指标入口)；[05.02.01 部署指标平台与持久化](05-observability/README.md#050201-部署指标平台与持久化)；[05.02.04 建立 Grafana 数据源和基础面板](05-observability/README.md#050204-建立-grafana-数据源和基础面板)；[05.02.05 建立 Alertmanager 分组与路由](05-observability/README.md#050205-建立-alertmanager-分组与路由)。

### Elasticsearch、Logstash、Kibana 与 ECK

实施位置：[05.05.01 部署 ECK 与小规模 Elasticsearch](05-observability/README.md#050501-部署-eck-与小规模-elasticsearch)；[05.05.03 建立 Logstash 解析与缓冲链路](05-observability/README.md#050503-建立-logstash-解析与缓冲链路)；[05.05.05 建立 Kibana 查询与故障案例](05-observability/README.md#050505-建立-kibana-查询与故障案例)。

### Fluent Bit、Loki 与 Alloy 路线

实施位置：[05.05.02 部署 Fluent Bit 节点日志采集](05-observability/README.md#050502-部署-fluent-bit-节点日志采集)；[05.06.01 部署 Loki 并规划对象存储](05-observability/README.md#050601-部署-loki-并规划对象存储)；[05.06.02 控制 Loki 标签与查询模式](05-observability/README.md#050602-控制-loki-标签与查询模式)。

### OpenTelemetry Collector 与多语言插桩

实施位置：[05.04.01 部署 Collector 采集与汇聚层](05-observability/README.md#050401-部署-collector-采集与汇聚层)；[05.04.02 接入多语言 SDK 与自动插桩](05-observability/README.md#050402-接入多语言-sdk-与自动插桩)。

### Tempo 与跨语言追踪

实施位置：[05.06.03 部署 Tempo 并关联日志与指标](05-observability/README.md#050603-部署-tempo-并关联日志与指标)；[05.04.03 贯通同步和异步上下文](05-observability/README.md#050403-贯通同步和异步上下文)。

### Pyroscope 持续 Profiling

实施位置：[05.06.04 接入 Pyroscope 持续性能剖析](05-observability/README.md#050604-接入-pyroscope-持续性能剖析)。

### SLO、错误预算与发布分析

实施位置：[05.07.01 为参考业务定义 SLI 与 SLO](05-observability/README.md#050701-为参考业务定义-sli-与-slo)；[05.07.02 建立错误预算和燃尽告警](05-observability/README.md#050702-建立错误预算和燃尽告警)；[05.07.03 将指标接入 Argo Rollouts](05-observability/README.md#050703-将指标接入-argo-rollouts)。

### k6、Locust 与容量

实施位置：[05.08.01 建立 k6/Locust 压测基准](05-observability/README.md#050801-建立-k6locust-压测基准)；[05.08.04 评估 Ceph 与应用的共享瓶颈](05-observability/README.md#050804-评估-ceph-与应用的共享瓶颈)。

### OpenCost 与资源效率

实施位置：[05.08.05 部署 OpenCost 与自建成本模型](05-observability/README.md#050805-部署-opencost-与自建成本模型)；[05.08.06 分析 Requests、实际用量与效率](05-observability/README.md#050806-分析-requests实际用量与效率)。

### 独立探测与观测后端故障

实施位置：[05.01.04 部署集群外可达性探测](05-observability/README.md#050104-部署集群外可达性探测)；[05.02.06 验证观测组件自身故障](05-observability/README.md#050206-验证观测组件自身故障)。

## 安全、弹性与高级工作负载

### Keycloak/OIDC 与身份治理

实施位置：[06.01.02 部署 Keycloak 与 OIDC 集成](06-advanced-security-dr/README.md#060102-部署-keycloak-与-oidc-集成)；[06.01.03 为 Kubernetes API 建立 OIDC 授权](06-advanced-security-dr/README.md#060103-为-kubernetes-api-建立-oidc-授权)。

### PSA、SecurityContext、Seccomp 与 SELinux

实施位置：[06.02.01 实施 Pod Security Admission 基线](06-advanced-security-dr/README.md#060201-实施-pod-security-admission-基线)；[06.02.02 验证 SecurityContext、Seccomp 和 SELinux](06-advanced-security-dr/README.md#060202-验证-securitycontextseccomp-和-selinux)。

### Kyverno 与准入恢复

实施位置：[06.02.03 完善 Kyverno 策略治理](06-advanced-security-dr/README.md#060203-完善-kyverno-策略治理)；[06.02.04 演练供应链和准入恢复](06-advanced-security-dr/README.md#060204-演练供应链和准入恢复)。

### SOPS/age、External Secrets 与 Vault

实施位置：[06.03.01 使用 SOPS 与 age 管理 GitOps 敏感配置](06-advanced-security-dr/README.md#060301-使用-sops-与-age-管理-gitops-敏感配置)；[06.03.02 部署 External Secrets 与秘密后端对照](06-advanced-security-dr/README.md#060302-部署-external-secrets-与秘密后端对照)；[06.03.03 验证 Vault 解封、备份与故障](06-advanced-security-dr/README.md#060303-验证-vault-解封备份与故障)。

### 静态加密轮换与审计

实施位置：[06.03.04 轮换 Kubernetes 数据加密密钥](06-advanced-security-dr/README.md#060304-轮换-kubernetes-数据加密密钥)；[06.03.05 建立 API 与平台审计链路](06-advanced-security-dr/README.md#060305-建立-api-与平台审计链路)。

### Falco 与 Tetragon

实施位置：[06.04.01 部署 Falco 并建立检测基准](06-advanced-security-dr/README.md#060401-部署-falco-并建立检测基准)；[06.04.02 部署 Tetragon 对照](06-advanced-security-dr/README.md#060402-部署-tetragon-对照)。

### Knative Serving/Eventing 与缩零

实施位置：[06.06.01 部署 Knative Serving 基础](06-advanced-security-dr/README.md#060601-部署-knative-serving-基础)；[06.06.03 部署 Knative Eventing](06-advanced-security-dr/README.md#060603-部署-knative-eventing)；[06.05.05 比较三种缩容到零方式](06-advanced-security-dr/README.md#060505-比较三种缩容到零方式)。

### Dapr 与 Workflow

实施位置：[06.07.01 部署 Dapr 控制面与组件](06-advanced-security-dr/README.md#060701-部署-dapr-控制面与组件)；[06.07.02 对比原生 SDK 与 Dapr 调用](06-advanced-security-dr/README.md#060702-对比原生-sdk-与-dapr-调用)。

### Argo Workflows 与 Argo Events

实施位置：[06.08.01 部署 Argo Workflows 与受控制品存储](06-advanced-security-dr/README.md#060801-部署-argo-workflows-与受控制品存储)；[06.08.02 部署 Argo Events 触发链路](06-advanced-security-dr/README.md#060802-部署-argo-events-触发链路)。

### Kueue 与批处理准入

实施位置：[06.08.04 部署 Kueue 队列准入](06-advanced-security-dr/README.md#060804-部署-kueue-队列准入)；[06.13.04 联合 Kueue 管理训练和批任务](06-advanced-security-dr/README.md#061304-联合-kueue-管理训练和批任务)。

### Cluster API/CAPV 与临时集群

实施位置：[06.09.02 部署 CAPI 管理组件与 CAPV](06-advanced-security-dr/README.md#060902-部署-capi-管理组件与-capv)；[06.09.04 测试 Machine 扩容、修复与升级](06-advanced-security-dr/README.md#060904-测试-machine-扩容修复与升级)。

### KubeVirt/CDI 与迁移

实施位置：[06.11.02 部署 KubeVirt 与虚拟机资源](06-advanced-security-dr/README.md#061102-部署-kubevirt-与虚拟机资源)；[06.11.03 接入 CDI 与 Ceph 磁盘](06-advanced-security-dr/README.md#061103-接入-cdi-与-ceph-磁盘)；[06.11.04 验证网络、迁移与存储限制](06-advanced-security-dr/README.md#061104-验证网络迁移与存储限制)。

### GPU Operator、Device Plugin 与 DRA

实施位置：[06.12.03 部署 GPU Operator 或受控驱动链](06-advanced-security-dr/README.md#061203-部署-gpu-operator-或受控驱动链)；[06.12.04 比较 Device Plugin 与 DRA](06-advanced-security-dr/README.md#061204-比较-device-plugin-与-dra)。

### KServe、Kubeflow 与 CPU 实验

实施位置：[06.13.01 部署 KServe 的 CPU 模型服务](06-advanced-security-dr/README.md#061301-部署-kserve-的-cpu-模型服务)；[06.13.03 部署 Kubeflow 必要模块](06-advanced-security-dr/README.md#061303-部署-kubeflow-必要模块)。

### vLLM、llm-d 与 GPU 性能

实施位置：[06.13.02 部署适配硬件的 vLLM 推理样例](06-advanced-security-dr/README.md#061302-部署适配硬件的-vllm-推理样例)；[06.13.05 研究 llm-d 与分布式推理](06-advanced-security-dr/README.md#061305-研究-llm-d-与分布式推理)。

### Chaos Mesh 与故障注入

实施位置：[06.14.02 部署 Chaos Mesh 并限制权限](06-advanced-security-dr/README.md#061402-部署-chaos-mesh-并限制权限)；[06.14.03 执行网络、Pod 和压力故障](06-advanced-security-dr/README.md#061403-执行网络pod-和压力故障)。

## 升级、备份与复现

### Kubernetes、CNI、CSI 与 Ceph 升级

实施位置：[06.15.01 准备升级兼容矩阵与隔离预演](06-advanced-security-dr/README.md#061501-准备升级兼容矩阵与隔离预演)；[06.15.05 分批升级 Worker 与存储共置节点](06-advanced-security-dr/README.md#061505-分批升级-worker-与存储共置节点)；[06.15.08 单独验证系统和 Ceph 滚动升级](06-advanced-security-dr/README.md#061508-单独验证系统和-ceph-滚动升级)。

### Velero 与实际数据搬运

实施位置：[06.16.02 部署 Velero 与适用的数据移动方案](06-advanced-security-dr/README.md#061602-部署-velero-与适用的数据移动方案)。

### 数据库一致性与独立备份

实施位置：[06.16.03 协调数据库与文件备份一致性](06-advanced-security-dr/README.md#061603-协调数据库与文件备份一致性)；[06.16.04 测试备份介质和密钥丢失边界](06-advanced-security-dr/README.md#061604-测试备份介质和密钥丢失边界)。

### etcd 恢复与全新集群恢复分离

实施位置：[06.17.01 选择两条不同的集群恢复路线](06-advanced-security-dr/README.md#061701-选择两条不同的集群恢复路线)。

### 基础服务恢复与数据校验

实施位置：[06.17.02 从集群外恢复基础服务](06-advanced-security-dr/README.md#061702-从集群外恢复基础服务)；[06.17.04 校验业务数据与服务恢复](06-advanced-security-dr/README.md#061704-校验业务数据与服务恢复)。

### 冷启动、有序停机与清理

实施位置：[06.06.02 实验 Revision、灰度与冷启动](06-advanced-security-dr/README.md#060602-实验-revision灰度与冷启动)；[06.17.05 执行冷启动与有序停机演练](06-advanced-security-dr/README.md#061705-执行冷启动与有序停机演练)；[06.17.06 清理扩展模块并核对资源台账](06-advanced-security-dr/README.md#061706-清理扩展模块并核对资源台账)。

### 完整复制验收与文档沉淀

实施位置：[06.17.07 完成 V3.0 文档和复制验收](06-advanced-security-dr/README.md#061707-完成-v30-文档和复制验收)。
