# 全部实施步骤索引

本索引保留 363 个稳定步骤编号，链接跳转到具体步骤。00 的 Linux/CRI 操作详见节点初始化手册；06 按 06A–06E 分组，原编号不变。

[返回七阶段目录](README.md) · [按技术主题查找](coverage.md)

## Phase 00｜基础设施、服务器初始化与软件供应准备

### 00.01 确认建设边界与资产

[00.01.01 登记三台物理宿主机与现有数据](00-preparation.md#000101-登记三台物理宿主机与现有数据)

[00.01.02 检查网络设备与 DHCP 可控程度](00-preparation.md#000102-检查网络设备与-dhcp-可控程度)

[00.01.03 制定内存和磁盘预算](00-preparation.md#000103-制定内存和磁盘预算)

[00.01.04 固定主方案与对比实验的管理权](00-preparation.md#000104-固定主方案与对比实验的管理权)

### 00.02 建立项目和软件版本基线

[00.02.01 建立项目目录与变更记录](00-preparation.md#000201-建立项目目录与变更记录)

[00.02.02 复核并锁定兼容版本](00-preparation.md#000202-复核并锁定兼容版本)

[00.02.03 建立软件来源和离线物料清单](00-preparation.md#000203-建立软件来源和离线物料清单)

### 00.03 规划网络、内部域名与公网域名

[00.03.01 固定节点、Pod、Service 与 VIP 地址](00-preparation.md#000301-固定节点podservice-与-vip-地址)

[00.03.02 确定域名层级和 Kubernetes 集群域](00-preparation.md#000302-确定域名层级和-kubernetes-集群域)

[00.03.03 建立公网发布白名单](00-preparation.md#000303-建立公网发布白名单)

[00.03.04 确定内部 DNS 与集群 DNS 的职责](00-preparation.md#000304-确定内部-dns-与集群-dns-的职责)

### 00.04 准备 ESXi 网络和虚拟机模板

[00.04.01 检查虚拟交换机和 Port Group](00-preparation.md#000401-检查虚拟交换机和-port-group)

[00.04.02 验证 VIP 的二层可达性](00-preparation.md#000402-验证-vip-的二层可达性)

[00.04.03 制作 Rocky Linux 10 虚拟机模板](00-preparation.md#000403-制作-rocky-linux-10-虚拟机模板)

[00.04.04 部署集群外管理与基础服务虚拟机](00-preparation.md#000404-部署集群外管理与基础服务虚拟机)

[00.04.05 分散控制平面和存储节点](00-preparation.md#000405-分散控制平面和存储节点)

### 00.05 在 ESXi 部署 OpenWrt 旁路由

[00.05.01 准备 OpenWrt 虚拟机](00-preparation.md#000501-准备-openwrt-虚拟机)

[00.05.02 接入现有局域网](00-preparation.md#000502-接入现有局域网)

[00.05.03 配置旁路由访问控制](00-preparation.md#000503-配置旁路由访问控制)

[00.05.04 保留双接口路由的升级路径](00-preparation.md#000504-保留双接口路由的升级路径)

### 00.06 接入 VPN、代理和出口分流

[00.06.01 建立 VPN 隧道与凭据管理](00-preparation.md#000601-建立-vpn-隧道与凭据管理)

[00.06.02 部署受控的显式 HTTP/HTTPS 代理](00-preparation.md#000602-部署受控的显式-httphttps-代理)

[00.06.03 建立分流与故障策略](00-preparation.md#000603-建立分流与故障策略)

[00.06.04 设计代理绕行清单](00-preparation.md#000604-设计代理绕行清单)

[00.06.05 演练网络出口故障](00-preparation.md#000605-演练网络出口故障)

### 00.07 建立内部 DNS 与客户端解析

[00.07.01 部署集群外 DNS 服务](00-preparation.md#000701-部署集群外-dns-服务)

[00.07.02 配置 macOS 的内网域名解析路径](00-preparation.md#000702-配置-macos-的内网域名解析路径)

[00.07.03 处理 Rocky、构建镜像和浏览器的 DNS 差异](00-preparation.md#000703-处理-rocky构建镜像和浏览器的-dns-差异)

[00.07.04 建立 DNS 故障与恢复流程](00-preparation.md#000704-建立-dns-故障与恢复流程)

### 00.08 建立内部 CA 与证书信任

[00.08.01 建立内部 PKI 信任链](00-preparation.md#000801-建立内部-pki-信任链)

[00.08.02 分发各语言和系统的 CA 信任](00-preparation.md#000802-分发各语言和系统的-ca-信任)

[00.08.03 规划公网证书与内部证书隔离](00-preparation.md#000803-规划公网证书与内部证书隔离)

### 00.09 建立 GitLab、Harbor 与依赖仓库

[00.09.01 部署集群外 GitLab CE](00-preparation.md#000901-部署集群外-gitlab-ce)

[00.09.02 部署 Harbor 与项目权限](00-preparation.md#000902-部署-harbor-与项目权限)

[00.09.03 建立上游代理缓存和引导镜像库](00-preparation.md#000903-建立上游代理缓存和引导镜像库)

[00.09.04 部署 Nexus 和语言依赖代理](00-preparation.md#000904-部署-nexus-和语言依赖代理)

[00.09.05 补充 C/C++ 与构建工具缓存](00-preparation.md#000905-补充-cc-与构建工具缓存)

[00.09.06 建立镜像扫描与数据库同步起点](00-preparation.md#000906-建立镜像扫描与数据库同步起点)

### 00.10 建立自动化、备份与阶段验收

[00.10.01 部署独立管理工具环境](00-preparation.md#001001-部署独立管理工具环境)

[00.10.02 初始化十台节点并验证幂等性](00-preparation.md#001002-初始化十台节点并验证幂等性)

[00.10.03 建立独立备份位置和恢复清单](00-preparation.md#001003-建立独立备份位置和恢复清单)

[00.10.04 执行指定物料的断网验收](00-preparation.md#001004-执行指定物料的断网验收)

[00.10.05 完成 Phase 00 交接](00-preparation.md#001005-完成-phase-00-交接)

## Phase 01｜Kubernetes 高可用、核心资源与生命周期

### 01.01 核验节点与运行时

[01.01.01 复核十节点的基础状态](01-kubernetes.md#010101-复核十节点的基础状态)

[01.01.02 复核 cgroup、资源预留和 Swap](01-kubernetes.md#010102-复核-cgroup资源预留和-swap)

[01.01.03 复核内核、防火墙和 SELinux 基线](01-kubernetes.md#010103-复核内核防火墙和-selinux-基线)

[01.01.04 复验 containerd 与 CRI 交接](01-kubernetes.md#010104-复验-containerd-与-cri-交接)

[01.01.05 处理引导镜像和仓库认证](01-kubernetes.md#010105-处理引导镜像和仓库认证)

### 01.02 建立控制平面与基础网络

[01.02.01 确定 kubeadm 集群配置](01-kubernetes.md#010201-确定-kubeadm-集群配置)

[01.02.02 建立 API VIP 的引导路径](01-kubernetes.md#010202-建立-api-vip-的引导路径)

[01.02.03 初始化第一个控制平面](01-kubernetes.md#010203-初始化第一个控制平面)

[01.02.04 建立敏感信息加密和审计起点](01-kubernetes.md#010204-建立敏感信息加密和审计起点)

[01.02.05 安装 Cilium 基础 CNI](01-kubernetes.md#010205-安装-cilium-基础-cni)

[01.02.06 加入第二和第三控制平面](01-kubernetes.md#010206-加入第二和第三控制平面)

[01.02.07 加入七个 Worker 并设置角色](01-kubernetes.md#010207-加入七个-worker-并设置角色)

[01.02.08 配置集群访问与恢复管理员](01-kubernetes.md#010208-配置集群访问与恢复管理员)

### 01.03 验证集群 DNS、高可用与基础备份

[01.03.01 验证服务发现和集群外解析](01-kubernetes.md#010301-验证服务发现和集群外解析)

[01.03.02 执行单控制平面故障实验](01-kubernetes.md#010302-执行单控制平面故障实验)

[01.03.03 建立 etcd 与控制平面备份](01-kubernetes.md#010303-建立-etcd-与控制平面备份)

### 01.04 建立核心实验空间与 Pod 生命周期

[01.04.01 建立实验命名空间与应用基准](01-kubernetes.md#010401-建立实验命名空间与应用基准)

[01.04.02 观察 Pod、容器状态和重启](01-kubernetes.md#010402-观察-pod容器状态和重启)

[01.04.03 实施 Init Container 与 Sidecar](01-kubernetes.md#010403-实施-init-container-与-sidecar)

[01.04.04 验证临时容器与故障诊断](01-kubernetes.md#010404-验证临时容器与故障诊断)

[01.04.05 观察 OOMKilled、Eviction 与终止](01-kubernetes.md#010405-观察-oomkilledeviction-与终止)

### 01.05 配置 Startup、Liveness、Readiness 与 PreStop

[01.05.01 验证 Startup Probe 的启动保护](01-kubernetes.md#010501-验证-startup-probe-的启动保护)

[01.05.02 验证 Liveness Probe 的自愈边界](01-kubernetes.md#010502-验证-liveness-probe-的自愈边界)

[01.05.03 验证 Readiness 与 EndpointSlice](01-kubernetes.md#010503-验证-readiness-与-endpointslice)

[01.05.04 实现 PreStop 与应用优雅终止](01-kubernetes.md#010504-实现-prestop-与应用优雅终止)

[01.05.05 比较探针协议和误判](01-kubernetes.md#010505-比较探针协议和误判)

### 01.06 研究 RC、ReplicaSet 与 Deployment

[01.06.01 比较 RC 与 ReplicaSet](01-kubernetes.md#010601-比较-rc-与-replicaset)

[01.06.02 建立 Deployment 与版本记录](01-kubernetes.md#010602-建立-deployment-与版本记录)

[01.06.03 实施手动扩缩容](01-kubernetes.md#010603-实施手动扩缩容)

[01.06.04 比较 RollingUpdate 与 Recreate](01-kubernetes.md#010604-比较-rollingupdate-与-recreate)

[01.06.05 验证暂停、继续、失败和回滚](01-kubernetes.md#010605-验证暂停继续失败和回滚)

[01.06.06 区分普通滚动更新与灰度发布](01-kubernetes.md#010606-区分普通滚动更新与灰度发布)

### 01.07 验证 StatefulSet 与 DaemonSet

[01.07.01 建立 StatefulSet 稳定身份](01-kubernetes.md#010701-建立-statefulset-稳定身份)

[01.07.02 比较 StatefulSet 更新与扩缩策略](01-kubernetes.md#010702-比较-statefulset-更新与扩缩策略)

[01.07.03 部署 DaemonSet 并验证节点覆盖](01-kubernetes.md#010703-部署-daemonset-并验证节点覆盖)

[01.07.04 实施 DaemonSet 更新和回滚](01-kubernetes.md#010704-实施-daemonset-更新和回滚)

### 01.08 研究删除传播、所有权与 Finalizer

[01.08.01 比较 Foreground 与 Background 删除](01-kubernetes.md#010801-比较-foreground-与-background-删除)

[01.08.02 实施 Orphan 非级联删除](01-kubernetes.md#010802-实施-orphan-非级联删除)

[01.08.03 观察 Finalizer 与删除保护](01-kubernetes.md#010803-观察-finalizer-与删除保护)

### 01.09 实现 Job、CronJob 与基础 HPA

[01.09.01 部署批处理 Job](01-kubernetes.md#010901-部署批处理-job)

[01.09.02 部署 CronJob 并处理时间语义](01-kubernetes.md#010902-部署-cronjob-并处理时间语义)

[01.09.03 建立资源指标入口](01-kubernetes.md#010903-建立资源指标入口)

[01.09.04 实施 CPU 与内存 HPA 基础实验](01-kubernetes.md#010904-实施-cpu-与内存-hpa-基础实验)

### 01.10 管理配置、身份与阶段交接

[01.10.01 比较 ConfigMap 注入与刷新](01-kubernetes.md#011001-比较-configmap-注入与刷新)

[01.10.02 管理 Secret 和容器拉取凭据](01-kubernetes.md#011002-管理-secret-和容器拉取凭据)

[01.10.03 建立最小 ServiceAccount 与 RBAC](01-kubernetes.md#011003-建立最小-serviceaccount-与-rbac)

[01.10.04 完成核心实验清理与版本归档](01-kubernetes.md#011004-完成核心实验清理与版本归档)

## Phase 02｜云原生网络、调度与服务治理

### 02.01 核对网络路径与诊断基准

[02.01.01 绘制实际通信与信任路径](02-networking.md#020101-绘制实际通信与信任路径)

[02.01.02 建立跨节点连通性测试集](02-networking.md#020102-建立跨节点连通性测试集)

[02.01.03 启用 Hubble 基础观测](02-networking.md#020103-启用-hubble-基础观测)

### 02.02 完整验证 Service 与服务发现

[02.02.01 验证 ClusterIP 与端点选择](02-networking.md#020201-验证-clusterip-与端点选择)

[02.02.02 验证 NodePort 和流量策略](02-networking.md#020202-验证-nodeport-和流量策略)

[02.02.03 验证 LoadBalancer Service](02-networking.md#020203-验证-loadbalancer-service)

[02.02.04 验证 Headless 与无 Selector Service](02-networking.md#020204-验证-headless-与无-selector-service)

[02.02.05 验证 ExternalName 和 DNS 限制](02-networking.md#020205-验证-externalname-和-dns-限制)

[02.02.06 验证集群域、搜索域和 DNS 缓存](02-networking.md#020206-验证集群域搜索域和-dns-缓存)

### 02.03 建立 MetalLB 主负载均衡与 VIP 规则

[02.03.01 部署 MetalLB L2 主方案](02-networking.md#020301-部署-metallb-l2-主方案)

[02.03.02 验证地址漂移与入口故障](02-networking.md#020302-验证地址漂移与入口故障)

[02.03.03 建立地址使用与撤销流程](02-networking.md#020303-建立地址使用与撤销流程)

### 02.04 建立 Gateway API 与传统 Ingress 对照

[02.04.01 锁定 Gateway API 与实现兼容性](02-networking.md#020401-锁定-gateway-api-与实现兼容性)

[02.04.02 部署 Envoy Gateway 与统一入口](02-networking.md#020402-部署-envoy-gateway-与统一入口)

[02.04.03 配置内部 HTTP 与 HTTPS 路由](02-networking.md#020403-配置内部-http-与-https-路由)

[02.04.04 配置跨命名空间路由与授权](02-networking.md#020404-配置跨命名空间路由与授权)

[02.04.05 配置 gRPC、TCP 与 UDP 实验](02-networking.md#020405-配置-grpctcp-与-udp-实验)

[02.04.06 部署传统 Ingress 对比](02-networking.md#020406-部署传统-ingress-对比)

[02.04.07 验证流量权重与发布接口](02-networking.md#020407-验证流量权重与发布接口)

### 02.05 接入证书自动化与公网发布边界

[02.05.01 部署 cert-manager 与内部签发器](02-networking.md#020501-部署-cert-manager-与内部签发器)

[02.05.02 执行证书轮换和过期故障实验](02-networking.md#020502-执行证书轮换和过期故障实验)

[02.05.03 按白名单发布 egon.top 应用](02-networking.md#020503-按白名单发布-egontop-应用)

### 02.06 建立网络隔离与出站策略

[02.06.01 实施 Namespace 默认拒绝策略](02-networking.md#020601-实施-namespace-默认拒绝策略)

[02.06.02 比较 Kubernetes 与 Cilium 网络策略](02-networking.md#020602-比较-kubernetes-与-cilium-网络策略)

[02.06.03 验证出站访问与代理绕行](02-networking.md#020603-验证出站访问与代理绕行)

[02.06.04 实验 Cilium Egress Gateway 联动 OpenWrt](02-networking.md#020604-实验-cilium-egress-gateway-联动-openwrt)

### 02.07 建立调度约束与物理故障域

[02.07.01 建立节点角色与物理宿主机标签](02-networking.md#020701-建立节点角色与物理宿主机标签)

[02.07.02 验证 NodeSelector 与 Node Affinity](02-networking.md#020702-验证-nodeselector-与-node-affinity)

[02.07.03 验证 Taint 与 Toleration](02-networking.md#020703-验证-taint-与-toleration)

[02.07.04 验证 Pod Affinity 与 Anti-Affinity](02-networking.md#020704-验证-pod-affinity-与-anti-affinity)

[02.07.05 验证 Topology Spread Constraints](02-networking.md#020705-验证-topology-spread-constraints)

### 02.08 实施资源配额、QoS 与可用性预算

[02.08.01 设置 Requests、Limits、LimitRange 与 Quota](02-networking.md#020801-设置-requestslimitslimitrange-与-quota)

[02.08.02 比较 Guaranteed、Burstable 与 BestEffort](02-networking.md#020802-比较-guaranteedburstable-与-besteffort)

[02.08.03 验证 CPU 限流和临时存储耗尽](02-networking.md#020803-验证-cpu-限流和临时存储耗尽)

[02.08.04 验证 PriorityClass 与抢占](02-networking.md#020804-验证-priorityclass-与抢占)

[02.08.05 验证 PDB 与节点维护](02-networking.md#020805-验证-pdb-与节点维护)

### 02.09 对比 Cilium 数据面和负载均衡能力

[02.09.01 比较 kube-proxy 与 eBPF 替代](02-networking.md#020901-比较-kube-proxy-与-ebpf-替代)

[02.09.02 比较 Overlay 与 Native Routing](02-networking.md#020902-比较-overlay-与-native-routing)

[02.09.03 实验 Cilium LB IPAM 与 L2 Announcements](02-networking.md#020903-实验-cilium-lb-ipam-与-l2-announcements)

[02.09.04 实验 Cilium BGP Control Plane](02-networking.md#020904-实验-cilium-bgp-control-plane)

### 02.10 实验 Istio 与工作负载身份

[02.10.01 部署 Sidecar 模式服务网格](02-networking.md#021001-部署-sidecar-模式服务网格)

[02.10.02 部署 Ambient 模式并按需增加 waypoint](02-networking.md#021002-部署-ambient-模式并按需增加-waypoint)

[02.10.03 实现 mTLS、授权与流量策略](02-networking.md#021003-实现-mtls授权与流量策略)

[02.10.04 部署 SPIFFE/SPIRE 身份对比](02-networking.md#021004-部署-spiffespire-身份对比)

[02.10.05 完成网络清理与阶段交接](02-networking.md#021005-完成网络清理与阶段交接)

## Phase 03｜Ceph、Kubernetes 存储与有状态数据平台

### 03.01 确认存储硬件与数据保护边界

[03.01.01 复核 OSD 设备与物理故障域](03-ceph-middleware.md#030101-复核-osd-设备与物理故障域)

[03.01.02 制定容量与副本预算](03-ceph-middleware.md#030102-制定容量与副本预算)

[03.01.03 明确三故障域的恢复限制](03-ceph-middleware.md#030103-明确三故障域的恢复限制)

[03.01.04 保护宿主机和 Ceph 资源](03-ceph-middleware.md#030104-保护宿主机和-ceph-资源)

### 03.02 部署独立 cephadm 集群

[03.02.01 准备宿主机容器和 Ceph 依赖](03-ceph-middleware.md#030201-准备宿主机容器和-ceph-依赖)

[03.02.02 引导首个 Ceph 管理节点](03-ceph-middleware.md#030202-引导首个-ceph-管理节点)

[03.02.03 扩展为三个 MON 与两个 MGR](03-ceph-middleware.md#030203-扩展为三个-mon-与两个-mgr)

[03.02.04 按明确设备清单创建 OSD](03-ceph-middleware.md#030204-按明确设备清单创建-osd)

[03.02.05 配置 CRUSH、池与基础监控](03-ceph-middleware.md#030205-配置-crush池与基础监控)

[03.02.06 建立 Ceph 配置与凭据备份](03-ceph-middleware.md#030206-建立-ceph-配置与凭据备份)

### 03.03 提供 RBD、CephFS 与 RGW

[03.03.01 建立 RBD 块存储池](03-ceph-middleware.md#030301-建立-rbd-块存储池)

[03.03.02 建立 CephFS 与 MDS 主备](03-ceph-middleware.md#030302-建立-cephfs-与-mds-主备)

[03.03.03 建立 RGW 对象存储入口](03-ceph-middleware.md#030303-建立-rgw-对象存储入口)

[03.03.04 区分对象存储与灾备目的地](03-ceph-middleware.md#030304-区分对象存储与灾备目的地)

### 03.04 接入 Rook External 与 Ceph CSI

[03.04.01 准备外部集群最小权限连接](03-ceph-middleware.md#030401-准备外部集群最小权限连接)

[03.04.02 部署 Rook External 控制与 CSI](03-ceph-middleware.md#030402-部署-rook-external-控制与-csi)

[03.04.03 检查所有卷消费者的 Ceph 网络](03-ceph-middleware.md#030403-检查所有卷消费者的-ceph-网络)

[03.04.04 建立 StorageClass 与默认策略](03-ceph-middleware.md#030404-建立-storageclass-与默认策略)

[03.04.05 验证 RWO、RWOP 与 RWX](03-ceph-middleware.md#030405-验证-rworwop-与-rwx)

### 03.05 完整验证 PV、PVC 与快照生命周期

[03.05.01 比较静态 PV 与动态供应](03-ceph-middleware.md#030501-比较静态-pv-与动态供应)

[03.05.02 验证卷扩容与文件系统变化](03-ceph-middleware.md#030502-验证卷扩容与文件系统变化)

[03.05.03 部署快照控制链并还原测试数据](03-ceph-middleware.md#030503-部署快照控制链并还原测试数据)

[03.05.04 验证克隆、回收与保留策略](03-ceph-middleware.md#030504-验证克隆回收与保留策略)

[03.05.05 验证 Pod 迁移和卷重新挂载](03-ceph-middleware.md#030505-验证-pod-迁移和卷重新挂载)

[03.05.06 回访 StatefulSet 持久化实验](03-ceph-middleware.md#030506-回访-statefulset-持久化实验)

### 03.06 实施存储故障与 Rook 自管理对照

[03.06.01 演练单 OSD 和存储 VM 故障](03-ceph-middleware.md#030601-演练单-osd-和存储-vm-故障)

[03.06.02 演练计划维护和安全下线](03-ceph-middleware.md#030602-演练计划维护和安全下线)

[03.06.03 测试容量水位和恢复限速](03-ceph-middleware.md#030603-测试容量水位和恢复限速)

[03.06.04 准备 Rook 自管理独立实验资源](03-ceph-middleware.md#030604-准备-rook-自管理独立实验资源)

[03.06.05 实验 CephCluster 与存储 CRD](03-ceph-middleware.md#030605-实验-cephcluster-与存储-crd)

[03.06.06 安全清理内部 Ceph 对比实验](03-ceph-middleware.md#030606-安全清理内部-ceph-对比实验)

### 03.07 建设 PostgreSQL 与关系型数据库实验

[03.07.01 部署单实例 PostgreSQL 基准](03-ceph-middleware.md#030701-部署单实例-postgresql-基准)

[03.07.02 使用 CloudNativePG 建立高可用](03-ceph-middleware.md#030702-使用-cloudnativepg-建立高可用)

[03.07.03 实施 WAL 归档、备份与 PITR](03-ceph-middleware.md#030703-实施-wal-归档备份与-pitr)

[03.07.04 演练数据库故障切换与升级](03-ceph-middleware.md#030704-演练数据库故障切换与升级)

[03.07.05 增加 MySQL Operator 对照](03-ceph-middleware.md#030705-增加-mysql-operator-对照)

### 03.08 建设 Redis、Kafka、RabbitMQ 与 NATS

[03.08.01 部署 Redis 并验证持久化](03-ceph-middleware.md#030801-部署-redis-并验证持久化)

[03.08.02 比较 Sentinel、Redis Cluster 与 Valkey](03-ceph-middleware.md#030802-比较-sentinelredis-cluster-与-valkey)

[03.08.03 使用 Strimzi 部署 Kafka KRaft](03-ceph-middleware.md#030803-使用-strimzi-部署-kafka-kraft)

[03.08.04 验证 Kafka 数据与消费者生命周期](03-ceph-middleware.md#030804-验证-kafka-数据与消费者生命周期)

[03.08.05 使用 RabbitMQ Operator 建立消息集群](03-ceph-middleware.md#030805-使用-rabbitmq-operator-建立消息集群)

[03.08.06 测试 RabbitMQ 故障与队列积压](03-ceph-middleware.md#030806-测试-rabbitmq-故障与队列积压)

[03.08.07 部署 NATS 与 JetStream](03-ceph-middleware.md#030807-部署-nats-与-jetstream)

### 03.09 开发 Operator 并完成数据平台交接

[03.09.01 设计自定义 DemoApp API](03-ceph-middleware.md#030901-设计自定义-demoapp-api)

[03.09.02 实现调谐、幂等与 Finalizer](03-ceph-middleware.md#030902-实现调谐幂等与-finalizer)

[03.09.03 验证 CRD 版本与控制器权限](03-ceph-middleware.md#030903-验证-crd-版本与控制器权限)

[03.09.04 建立数据平台启停与恢复顺序](03-ceph-middleware.md#030904-建立数据平台启停与恢复顺序)

[03.09.05 完成 Phase 03 验收与交接](03-ceph-middleware.md#030905-完成-phase-03-验收与交接)

## Phase 04｜双 CI、GitOps、IaC 与开发者平台工程

### 04.01 定义代码、制品和交付契约

[04.01.01 划分应用、平台和 GitOps 仓库](04-devops-platform.md#040101-划分应用平台和-gitops-仓库)

[04.01.02 建立环境隔离与资源预算](04-devops-platform.md#040102-建立环境隔离与资源预算)

[04.01.03 定义制品标识与发布标准](04-devops-platform.md#040103-定义制品标识与发布标准)

[04.01.04 定义可复用应用接口](04-devops-platform.md#040104-定义可复用应用接口)

### 04.02 建设构建镜像、依赖和缓存

[04.02.01 制作受控 Builder 镜像](04-devops-platform.md#040201-制作受控-builder-镜像)

[04.02.02 配置各语言依赖代理](04-devops-platform.md#040202-配置各语言依赖代理)

[04.02.03 部署隔离的 BuildKit 构建能力](04-devops-platform.md#040203-部署隔离的-buildkit-构建能力)

[04.02.04 划分四类缓存并防止污染](04-devops-platform.md#040204-划分四类缓存并防止污染)

[04.02.05 验证离线构建与制品保留](04-devops-platform.md#040205-验证离线构建与制品保留)

### 04.03 实现 GitLab CI 完整流水线

[04.03.01 部署 Runner 管理器和 Kubernetes Executor](04-devops-platform.md#040301-部署-runner-管理器和-kubernetes-executor)

[04.03.02 建立公共 GitLab CI 模板](04-devops-platform.md#040302-建立公共-gitlab-ci-模板)

[04.03.03 实现合并请求和分支流水线](04-devops-platform.md#040303-实现合并请求和分支流水线)

[04.03.04 实现制品发布与 GitOps 提交](04-devops-platform.md#040304-实现制品发布与-gitops-提交)

[04.03.05 验证 GitLab CI 故障恢复](04-devops-platform.md#040305-验证-gitlab-ci-故障恢复)

### 04.04 实现 Jenkins 完整流水线

[04.04.01 部署 Jenkins Controller 与持久化](04-devops-platform.md#040401-部署-jenkins-controller-与持久化)

[04.04.02 配置动态 Kubernetes Agent](04-devops-platform.md#040402-配置动态-kubernetes-agent)

[04.04.03 建立 Jenkins Configuration as Code 与共享库](04-devops-platform.md#040403-建立-jenkins-configuration-as-code-与共享库)

[04.04.04 实现 Multibranch 与标准阶段](04-devops-platform.md#040404-实现-multibranch-与标准阶段)

[04.04.05 实现 Jenkins GitOps 发布与失败恢复](04-devops-platform.md#040405-实现-jenkins-gitops-发布与失败恢复)

### 04.05 完成七类语言的双流水线适配

[04.05.01 完成 Java 与 Spring Boot 服务](04-devops-platform.md#040501-完成-java-与-spring-boot-服务)

[04.05.02 完成 Rust 服务与原生制品](04-devops-platform.md#040502-完成-rust-服务与原生制品)

[04.05.03 完成 C 服务或计算 Worker](04-devops-platform.md#040503-完成-c-服务或计算-worker)

[04.05.04 完成 C++ 服务与依赖缓存](04-devops-platform.md#040504-完成-c-服务与依赖缓存)

[04.05.05 完成 C# 与现代 .NET 服务](04-devops-platform.md#040505-完成-c-与现代-net-服务)

[04.05.06 完成 JS/TS 前后端交付](04-devops-platform.md#040506-完成-jsts-前后端交付)

[04.05.07 完成 Python 服务和任务程序](04-devops-platform.md#040507-完成-python-服务和任务程序)

[04.05.08 执行十四种构建发布组合验收](04-devops-platform.md#040508-执行十四种构建发布组合验收)

### 04.06 通过两套 CI 实施 IaC

[04.06.01 划定 OpenTofu、Ansible 与 GitOps 管理范围](04-devops-platform.md#040601-划定-opentofuansible-与-gitops-管理范围)

[04.06.02 建立远端 State、锁和备份](04-devops-platform.md#040602-建立远端-state锁和备份)

[04.06.03 实现 GitLab CI 的 IaC 流程](04-devops-platform.md#040603-实现-gitlab-ci-的-iac-流程)

[04.06.04 实现 Jenkins 的 IaC 流程](04-devops-platform.md#040604-实现-jenkins-的-iac-流程)

[04.06.05 实现 Ansible 幂等、分批和漂移修复](04-devops-platform.md#040605-实现-ansible-幂等分批和漂移修复)

[04.06.06 建立集群外恢复执行器](04-devops-platform.md#040606-建立集群外恢复执行器)

[04.06.07 验证 IaC 失败补偿与销毁保护](04-devops-platform.md#040607-验证-iac-失败补偿与销毁保护)

### 04.07 建设 Helm、Kustomize 和 Argo CD

[04.07.01 制作 Helm Chart 与多环境覆盖](04-devops-platform.md#040701-制作-helm-chart-与多环境覆盖)

[04.07.02 部署 Argo CD 与最小权限项目](04-devops-platform.md#040702-部署-argo-cd-与最小权限项目)

[04.07.03 建立分层同步和依赖顺序](04-devops-platform.md#040703-建立分层同步和依赖顺序)

[04.07.04 验证 HPA 与 GitOps 字段所有权](04-devops-platform.md#040704-验证-hpa-与-gitops-字段所有权)

[04.07.05 建立 ApplicationSet 与通知](04-devops-platform.md#040705-建立-applicationset-与通知)

### 04.08 实现渐进式发布和供应链安全

[04.08.01 部署 Argo Rollouts 并验证路由适配](04-devops-platform.md#040801-部署-argo-rollouts-并验证路由适配)

[04.08.02 实现 Canary 与 Blue/Green](04-devops-platform.md#040802-实现-canary-与-bluegreen)

[04.08.03 接入发布分析与自动中止](04-devops-platform.md#040803-接入发布分析与自动中止)

[04.08.04 建立 SBOM、扫描和来源证明](04-devops-platform.md#040804-建立-sbom扫描和来源证明)

[04.08.05 使用 Cosign 签名并保留可信材料](04-devops-platform.md#040805-使用-cosign-签名并保留可信材料)

[04.08.06 接入准入校验与拒绝发布实验](04-devops-platform.md#040806-接入准入校验与拒绝发布实验)

### 04.09 建设 Backstage 与 Crossplane 平台入口

[04.09.01 部署 Backstage 并建立服务目录](04-devops-platform.md#040901-部署-backstage-并建立服务目录)

[04.09.02 实现 Software Templates 与双 CI 选择](04-devops-platform.md#040902-实现-software-templates-与双-ci-选择)

[04.09.03 部署 Crossplane 与版本化平台 API](04-devops-platform.md#040903-部署-crossplane-与版本化平台-api)

[04.09.04 划分 Argo CD、Crossplane 与 Operator 所有权](04-devops-platform.md#040904-划分-argo-cdcrossplane-与-operator-所有权)

[04.09.05 完成开发者自助服务端到端交付](04-devops-platform.md#040905-完成开发者自助服务端到端交付)

[04.09.06 完善 TechDocs、API 目录与权限](04-devops-platform.md#040906-完善-techdocsapi-目录与权限)

### 04.10 开展 Tekton、Flux 与镜像分发对照

[04.10.01 实验 Tekton 原生流水线](04-devops-platform.md#041001-实验-tekton-原生流水线)

[04.10.02 实验 Flux GitOps](04-devops-platform.md#041002-实验-flux-gitops)

[04.10.03 实验 Dragonfly P2P 分发](04-devops-platform.md#041003-实验-dragonfly-p2p-分发)

[04.10.04 完成 Phase 04 交接与清理](04-devops-platform.md#041004-完成-phase-04-交接与清理)

## Phase 05｜可观测性、日志、性能、SLO 与成本治理

### 05.01 建立遥测契约和容量计划

[05.01.01 定义服务、环境和版本标识](05-observability.md#050101-定义服务环境和版本标识)

[05.01.02 确定保留、采样和成本预算](05-observability.md#050102-确定保留采样和成本预算)

[05.01.03 建立遥测隐私与访问边界](05-observability.md#050103-建立遥测隐私与访问边界)

[05.01.04 部署集群外可达性探测](05-observability.md#050104-部署集群外可达性探测)

### 05.02 建设 Prometheus、Grafana 与 Alertmanager

[05.02.01 部署指标平台与持久化](05-observability.md#050201-部署指标平台与持久化)

[05.02.02 采集 Kubernetes 与节点状态](05-observability.md#050202-采集-kubernetes-与节点状态)

[05.02.03 建立 ServiceMonitor、PodMonitor 与规则](05-observability.md#050203-建立-servicemonitorpodmonitor-与规则)

[05.02.04 建立 Grafana 数据源和基础面板](05-observability.md#050204-建立-grafana-数据源和基础面板)

[05.02.05 建立 Alertmanager 分组与路由](05-observability.md#050205-建立-alertmanager-分组与路由)

[05.02.06 验证观测组件自身故障](05-observability.md#050206-验证观测组件自身故障)

### 05.03 覆盖 Ceph、基础设施和中间件监控

[05.03.01 接入 Ceph 指标和容量告警](05-observability.md#050301-接入-ceph-指标和容量告警)

[05.03.02 接入 ESXi、Rocky 与网络设备](05-observability.md#050302-接入-esxirocky-与网络设备)

[05.03.03 接入 PostgreSQL 与 Redis](05-observability.md#050303-接入-postgresql-与-redis)

[05.03.04 接入 Kafka、RabbitMQ 与 NATS](05-observability.md#050304-接入-kafkarabbitmq-与-nats)

[05.03.05 接入 GitLab、Jenkins、Harbor 与 Nexus](05-observability.md#050305-接入-gitlabjenkinsharbor-与-nexus)

### 05.04 建立 OpenTelemetry 统一入口

[05.04.01 部署 Collector 采集与汇聚层](05-observability.md#050401-部署-collector-采集与汇聚层)

[05.04.02 接入多语言 SDK 与自动插桩](05-observability.md#050402-接入多语言-sdk-与自动插桩)

[05.04.03 贯通同步和异步上下文](05-observability.md#050403-贯通同步和异步上下文)

[05.04.04 控制采样、高基数与重传](05-observability.md#050404-控制采样高基数与重传)

### 05.05 实现 ELK 日志平台

[05.05.01 部署 ECK 与小规模 Elasticsearch](05-observability.md#050501-部署-eck-与小规模-elasticsearch)

[05.05.02 部署 Fluent Bit 节点日志采集](05-observability.md#050502-部署-fluent-bit-节点日志采集)

[05.05.03 建立 Logstash 解析与缓冲链路](05-observability.md#050503-建立-logstash-解析与缓冲链路)

[05.05.04 建立索引模板与生命周期](05-observability.md#050504-建立索引模板与生命周期)

[05.05.05 建立 Kibana 查询与故障案例](05-observability.md#050505-建立-kibana-查询与故障案例)

### 05.06 实现 Loki、Tempo 与 Pyroscope

[05.06.01 部署 Loki 并规划对象存储](05-observability.md#050601-部署-loki-并规划对象存储)

[05.06.02 控制 Loki 标签与查询模式](05-observability.md#050602-控制-loki-标签与查询模式)

[05.06.03 部署 Tempo 并关联日志与指标](05-observability.md#050603-部署-tempo-并关联日志与指标)

[05.06.04 接入 Pyroscope 持续性能剖析](05-observability.md#050604-接入-pyroscope-持续性能剖析)

[05.06.05 验证对象存储与观测后端中断](05-observability.md#050605-验证对象存储与观测后端中断)

### 05.07 建立 SLI、SLO 与发布分析

[05.07.01 为参考业务定义 SLI 与 SLO](05-observability.md#050701-为参考业务定义-sli-与-slo)

[05.07.02 建立错误预算和燃尽告警](05-observability.md#050702-建立错误预算和燃尽告警)

[05.07.03 将指标接入 Argo Rollouts](05-observability.md#050703-将指标接入-argo-rollouts)

[05.07.04 建立统一故障时间线](05-observability.md#050704-建立统一故障时间线)

### 05.08 开展压测、容量和成本实验

[05.08.01 建立 k6/Locust 压测基准](05-observability.md#050801-建立-k6locust-压测基准)

[05.08.02 比较七类语言的运行表现](05-observability.md#050802-比较七类语言的运行表现)

[05.08.03 比较双 CI 和镜像缓存效率](05-observability.md#050803-比较双-ci-和镜像缓存效率)

[05.08.04 评估 Ceph 与应用的共享瓶颈](05-observability.md#050804-评估-ceph-与应用的共享瓶颈)

[05.08.05 部署 OpenCost 与自建成本模型](05-observability.md#050805-部署-opencost-与自建成本模型)

[05.08.06 分析 Requests、实际用量与效率](05-observability.md#050806-分析-requests实际用量与效率)

### 05.09 完成观测平台交接

[05.09.01 归档配置、面板和告警回归](05-observability.md#050901-归档配置面板和告警回归)

[05.09.02 整理故障样例与资源结果](05-observability.md#050902-整理故障样例与资源结果)

[05.09.03 清理重型对照并保留最低监控](05-observability.md#050903-清理重型对照并保留最低监控)

## Phase 06｜安全、弹性、Serverless、多集群、高级计算与灾难恢复

### 06A · 安全与弹性

#### 06.01 建立安全验证范围和统一身份

[06.01.01 建立授权实验与恢复边界](06-advanced-security-dr.md#060101-建立授权实验与恢复边界)

[06.01.02 部署 Keycloak 与 OIDC 集成](06-advanced-security-dr.md#060102-部署-keycloak-与-oidc-集成)

[06.01.03 为 Kubernetes API 建立 OIDC 授权](06-advanced-security-dr.md#060103-为-kubernetes-api-建立-oidc-授权)

[06.01.04 轮换 ServiceAccount 和机器人凭据](06-advanced-security-dr.md#060104-轮换-serviceaccount-和机器人凭据)

#### 06.02 落实 Pod 安全与准入策略

[06.02.01 实施 Pod Security Admission 基线](06-advanced-security-dr.md#060201-实施-pod-security-admission-基线)

[06.02.02 验证 SecurityContext、Seccomp 和 SELinux](06-advanced-security-dr.md#060202-验证-securitycontextseccomp-和-selinux)

[06.02.03 完善 Kyverno 策略治理](06-advanced-security-dr.md#060203-完善-kyverno-策略治理)

[06.02.04 演练供应链和准入恢复](06-advanced-security-dr.md#060204-演练供应链和准入恢复)

#### 06.03 管理密钥、审计和工作负载信任

[06.03.01 使用 SOPS 与 age 管理 GitOps 敏感配置](06-advanced-security-dr.md#060301-使用-sops-与-age-管理-gitops-敏感配置)

[06.03.02 部署 External Secrets 与秘密后端对照](06-advanced-security-dr.md#060302-部署-external-secrets-与秘密后端对照)

[06.03.03 验证 Vault 解封、备份与故障](06-advanced-security-dr.md#060303-验证-vault-解封备份与故障)

[06.03.04 轮换 Kubernetes 数据加密密钥](06-advanced-security-dr.md#060304-轮换-kubernetes-数据加密密钥)

[06.03.05 建立 API 与平台审计链路](06-advanced-security-dr.md#060305-建立-api-与平台审计链路)

[06.03.06 回访 SPIFFE/SPIRE 与跨服务信任](06-advanced-security-dr.md#060306-回访-spiffespire-与跨服务信任)

#### 06.04 实验运行时安全

[06.04.01 部署 Falco 并建立检测基准](06-advanced-security-dr.md#060401-部署-falco-并建立检测基准)

[06.04.02 部署 Tetragon 对照](06-advanced-security-dr.md#060402-部署-tetragon-对照)

[06.04.03 将运行时事件接入调查流程](06-advanced-security-dr.md#060403-将运行时事件接入调查流程)

#### 06.05 完善 HPA、VPA 与事件扩缩容

[06.05.01 回访 HPA 多指标与稳定窗口](06-advanced-security-dr.md#060501-回访-hpa-多指标与稳定窗口)

[06.05.02 部署 VPA 并验证资源建议](06-advanced-security-dr.md#060502-部署-vpa-并验证资源建议)

[06.05.03 使用 KEDA 扩缩 Kafka 消费者](06-advanced-security-dr.md#060503-使用-keda-扩缩-kafka-消费者)

[06.05.04 使用 KEDA 扩缩 RabbitMQ Worker](06-advanced-security-dr.md#060504-使用-keda-扩缩-rabbitmq-worker)

[06.05.05 比较三种缩容到零方式](06-advanced-security-dr.md#060505-比较三种缩容到零方式)

[06.05.06 结合 PDB、优先级与伸缩做压力实验](06-advanced-security-dr.md#060506-结合-pdb优先级与伸缩做压力实验)

#### 06.14 实施 Chaos Mesh 与故障工程

[06.14.01 建立故障实验假设和安全中止](06-advanced-security-dr.md#061401-建立故障实验假设和安全中止)

[06.14.02 部署 Chaos Mesh 并限制权限](06-advanced-security-dr.md#061402-部署-chaos-mesh-并限制权限)

[06.14.03 执行网络、Pod 和压力故障](06-advanced-security-dr.md#061403-执行网络pod-和压力故障)

[06.14.04 执行仓库、DNS 和 VPN 故障](06-advanced-security-dr.md#061404-执行仓库dns-和-vpn-故障)

[06.14.05 执行 ESXi 与存储域故障](06-advanced-security-dr.md#061405-执行-esxi-与存储域故障)

### 06B · Serverless 与事件平台

#### 06.06 建设 Knative 与 Serverless 实验

[06.06.01 部署 Knative Serving 基础](06-advanced-security-dr.md#060601-部署-knative-serving-基础)

[06.06.02 实验 Revision、灰度与冷启动](06-advanced-security-dr.md#060602-实验-revision灰度与冷启动)

[06.06.03 部署 Knative Eventing](06-advanced-security-dr.md#060603-部署-knative-eventing)

[06.06.04 比较常驻与 Serverless 模式](06-advanced-security-dr.md#060604-比较常驻与-serverless-模式)

#### 06.07 建设 Dapr 与多语言事件应用

[06.07.01 部署 Dapr 控制面与组件](06-advanced-security-dr.md#060701-部署-dapr-控制面与组件)

[06.07.02 对比原生 SDK 与 Dapr 调用](06-advanced-security-dr.md#060702-对比原生-sdk-与-dapr-调用)

[06.07.03 实验 Dapr Workflow 与恢复](06-advanced-security-dr.md#060703-实验-dapr-workflow-与恢复)

#### 06.08 建设 Argo Workflows、Events 与批处理

[06.08.01 部署 Argo Workflows 与受控制品存储](06-advanced-security-dr.md#060801-部署-argo-workflows-与受控制品存储)

[06.08.02 部署 Argo Events 触发链路](06-advanced-security-dr.md#060802-部署-argo-events-触发链路)

[06.08.03 比较 Workflow、Tekton 与应用 CI](06-advanced-security-dr.md#060803-比较-workflowtekton-与应用-ci)

### 06C · 多集群

#### 06.09 建立第二集群与 Cluster API

[06.09.01 核算临时集群资源与地址](06-advanced-security-dr.md#060901-核算临时集群资源与地址)

[06.09.02 部署 CAPI 管理组件与 CAPV](06-advanced-security-dr.md#060902-部署-capi-管理组件与-capv)

[06.09.03 声明并创建实验集群](06-advanced-security-dr.md#060903-声明并创建实验集群)

[06.09.04 测试 Machine 扩容、修复与升级](06-advanced-security-dr.md#060904-测试-machine-扩容修复与升级)

[06.09.05 备份管理状态并测试销毁](06-advanced-security-dr.md#060905-备份管理状态并测试销毁)

#### 06.10 实现多集群交付与网络

[06.10.01 接入多集群 Argo CD/ApplicationSet](06-advanced-security-dr.md#061001-接入多集群-argo-cdapplicationset)

[06.10.02 部署 Cilium Cluster Mesh](06-advanced-security-dr.md#061002-部署-cilium-cluster-mesh)

[06.10.03 验证 MCS API 与服务导入导出](06-advanced-security-dr.md#061003-验证-mcs-api-与服务导入导出)

[06.10.04 实施跨集群策略和访问隔离](06-advanced-security-dr.md#061004-实施跨集群策略和访问隔离)

[06.10.05 实施跨集群流量恢复实验](06-advanced-security-dr.md#061005-实施跨集群流量恢复实验)

### 06D · 高级计算

#### 06.11 实验 KubeVirt 与嵌套虚拟化

[06.11.01 检查嵌套虚拟化和 KVM 前置](06-advanced-security-dr.md#061101-检查嵌套虚拟化和-kvm-前置)

[06.11.02 部署 KubeVirt 与虚拟机资源](06-advanced-security-dr.md#061102-部署-kubevirt-与虚拟机资源)

[06.11.03 接入 CDI 与 Ceph 磁盘](06-advanced-security-dr.md#061103-接入-cdi-与-ceph-磁盘)

[06.11.04 验证网络、迁移与存储限制](06-advanced-security-dr.md#061104-验证网络迁移与存储限制)

#### Kueue 队列准入前置（原 06.08.04）

[06.08.04 部署 Kueue 队列准入](06-advanced-security-dr.md#060804-部署-kueue-队列准入)

#### 06.12 检查 GPU、驱动与设备调度

[06.12.01 核实实际 GPU 硬件与接入方式](06-advanced-security-dr.md#061201-核实实际-gpu-硬件与接入方式)

[06.12.02 核对 Rocky、驱动、CUDA 与框架矩阵](06-advanced-security-dr.md#061202-核对-rocky驱动cuda-与框架矩阵)

[06.12.03 部署 GPU Operator 或受控驱动链](06-advanced-security-dr.md#061203-部署-gpu-operator-或受控驱动链)

[06.12.04 比较 Device Plugin 与 DRA](06-advanced-security-dr.md#061204-比较-device-plugin-与-dra)

#### 06.13 建设 AI、推理与训练实验

[06.13.01 部署 KServe 的 CPU 模型服务](06-advanced-security-dr.md#061301-部署-kserve-的-cpu-模型服务)

[06.13.02 部署适配硬件的 vLLM 推理样例](06-advanced-security-dr.md#061302-部署适配硬件的-vllm-推理样例)

[06.13.03 部署 Kubeflow 必要模块](06-advanced-security-dr.md#061303-部署-kubeflow-必要模块)

[06.13.04 联合 Kueue 管理训练和批任务](06-advanced-security-dr.md#061304-联合-kueue-管理训练和批任务)

[06.13.05 研究 llm-d 与分布式推理](06-advanced-security-dr.md#061305-研究-llm-d-与分布式推理)

[06.13.06 评估 GPU 与模型服务成本](06-advanced-security-dr.md#061306-评估-gpu-与模型服务成本)

### 06E · 升级与容灾

#### 06.15 完成 kubeadm、CNI、CSI 与系统升级

[06.15.01 准备升级兼容矩阵与隔离预演](06-advanced-security-dr.md#061501-准备升级兼容矩阵与隔离预演)

[06.15.02 冻结变更并检查恢复材料](06-advanced-security-dr.md#061502-冻结变更并检查恢复材料)

[06.15.03 升级首个控制平面](06-advanced-security-dr.md#061503-升级首个控制平面)

[06.15.04 逐台升级其余控制平面](06-advanced-security-dr.md#061504-逐台升级其余控制平面)

[06.15.05 分批升级 Worker 与存储共置节点](06-advanced-security-dr.md#061505-分批升级-worker-与存储共置节点)

[06.15.06 回归 CNI、CSI、网关与数据服务](06-advanced-security-dr.md#061506-回归-cnicsi网关与数据服务)

[06.15.07 验证 Memory QoS 与目标版本新增能力](06-advanced-security-dr.md#061507-验证-memory-qos-与目标版本新增能力)

[06.15.08 单独验证系统和 Ceph 滚动升级](06-advanced-security-dr.md#061508-单独验证系统和-ceph-滚动升级)

[06.15.09 验证升级失败恢复而非任意降级](06-advanced-security-dr.md#061509-验证升级失败恢复而非任意降级)

#### 06.16 建设分层备份和实际数据搬运

[06.16.01 建立配置、身份、数据备份目录](06-advanced-security-dr.md#061601-建立配置身份数据备份目录)

[06.16.02 部署 Velero 与适用的数据移动方案](06-advanced-security-dr.md#061602-部署-velero-与适用的数据移动方案)

[06.16.03 协调数据库与文件备份一致性](06-advanced-security-dr.md#061603-协调数据库与文件备份一致性)

[06.16.04 测试备份介质和密钥丢失边界](06-advanced-security-dr.md#061604-测试备份介质和密钥丢失边界)

#### 06.17 实施灾难重建与项目交付

[06.17.01 选择两条不同的集群恢复路线](06-advanced-security-dr.md#061701-选择两条不同的集群恢复路线)

[06.17.02 从集群外恢复基础服务](06-advanced-security-dr.md#061702-从集群外恢复基础服务)

[06.17.03 恢复 Kubernetes、存储与平台组件](06-advanced-security-dr.md#061703-恢复-kubernetes存储与平台组件)

[06.17.04 校验业务数据与服务恢复](06-advanced-security-dr.md#061704-校验业务数据与服务恢复)

[06.17.05 执行冷启动与有序停机演练](06-advanced-security-dr.md#061705-执行冷启动与有序停机演练)

[06.17.06 清理扩展模块并核对资源台账](06-advanced-security-dr.md#061706-清理扩展模块并核对资源台账)

[06.17.07 完成 V3.0 文档和复制验收](06-advanced-security-dr.md#061707-完成-v30-文档和复制验收)
