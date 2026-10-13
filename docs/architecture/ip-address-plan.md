# IP、DNS 与地址分配

权威台账为 [networks.yaml](../../inventory/networks.yaml) 与 [hosts.yaml](../../inventory/hosts.yaml)。以下是设计基线，不是在线发现结果；网关、DHCP、现有占用和反向解析在 00 核实。

## 1. 地址分组

| 范围 / 地址 | 规划用途 | 管理规则 |
| --- | --- | --- |
| 192.168.9.0/24 | LAN、节点和管理 | 网关待确认，不假设 .1 已可用 |
| .10 / .11 / .12 / .13 / .14 / .15 | OpenWrt / DNS / Harbor / GitLab / Nexus / 管理机 | 集群外运行，静态地址须排除 DHCP |
| .16 / .17 | 独立备份入口 / 第二 DNS 预留 | 预留 IP 不代表有真实设备或冗余 |
| .51–.53 / .61–.63 | iDRAC / ESXi | 保持原规划，先核实再操作 |
| .100 | Kubernetes API VIP | kube-vip 唯一宣告 |
| .101–.103 | cp01–cp03 | 三控制平面、三个物理故障域 |
| .104–.105 | infra01–infra02 | 平台工作负载 |
| .106–.108 | storage01–storage03 | cephadm + 受限 Worker |
| .109–.110 | worker01–worker02 | 应用和构建实验 |
| .201–.210 | MetalLB 业务池 | .201 为规划网关入口，按 Service 实际分配登记 |
| .211–.220 | Cilium 或扩展实验池 | 与主池、API VIP 隔离 |
| 10.244.0.0/16 | 主集群 Pod | Cilium 分配，每节点 /24 |
| 192.168.20.0/24 | 主集群 Service | .1 API Service、.10 CoreDNS，其余动态分配 |
| 10.245.0.0/16 / 10.96.0.0/16 | 第二集群 Pod / Service | 06C 使用前重查重叠 |

表中的简写 `.x` 均属于 `192.168.9.0/24`，Service 行中的 `.1`、`.10` 属于该行的 `192.168.20.0/24`。

## 2. 名称模板

| 用途 | 示例与目标 |
| --- | --- |
| 管理入口 | `esxi01.mgmt.internal.egon.top`、`idrac01.mgmt.internal.egon.top`、`openwrt.mgmt.internal.egon.top`、`dns.mgmt.internal.egon.top`、`admin.mgmt.internal.egon.top` |
| 待定管理服务 | `vcsa.mgmt.internal.egon.top`、`ceph.mgmt.internal.egon.top`，实际端点核实后发布 |
| 节点 / API | `<node>.k8s.internal.egon.top`；`api.k8s.internal.egon.top` → .100 |
| 仓库 | `harbor.k8s.internal.egon.top` → .12；`gitlab.svc.internal.egon.top` → .13；`nexus.svc.internal.egon.top` → .14 |
| 平台入口 | `argocd`、`grafana`、`jenkins`、`backstage`、`keycloak` 的 `k8s.internal.egon.top` 子域，经批准后映射实际网关 |
| 数据 / 应用入口 | `mysql.svc.internal.egon.top`、`s3.svc.internal.egon.top`、`demo.svc.internal.egon.top`，按实际独立端点或网关创建 |
| 集群 Service | `service.namespace.svc.cluster.local`，例如 `kubernetes.default.svc.cluster.local` |
| 公网白名单 | `demo.apps.egon.top`、`api.egon.top` 仅为命名示例，不自动发布 |

## 3. 分配与验收动作

1. 导出当前 DHCP 池、保留地址、已用静态地址和路由；核对 VPN 远端 CIDR。先排除冲突再写入网络设备与 VM。
2. 按台账批量生成 DNS 精确记录；发布前检查 zone 语法、Serial、转发环路和 TTL。通配记录只面向已经验收的网关。
3. 从 LAN、管理机、每个节点和授权 VPN 客户端分别检查解析、路由、TLS；01 后再增加 Pod 内的检查。
4. 地址迁移同时修改台账、DNS、配置与验收结果；清理实验时释放 VIP/路由，不回收仍有数据依赖的节点地址。

Service /24 容量有限，约 180 个已分配地址作为本项目复核阈值，不是 Kubernetes 硬限制。启用大型模块前估算增量，不假设运行中扩 CIDR 没有迁移成本。
