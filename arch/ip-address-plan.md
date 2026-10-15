# IP、DNS 与地址分配

权威台账为 [networks.yaml](../ops/inventory/networks.yaml) 与 [hosts.yaml](../ops/inventory/hosts.yaml)。2026-10-14 用户确认 LAN 为 192.168.9.0/24，路由器地址为 .1，Wi-Fi DHCP 规划为 .30–.49，iDRAC 使用 .51–.60，ESXi 使用 .61–.70。以下分组保留这些范围；现场占用、DHCP 实际配置和反向解析仍须在 00 复验。

## 1. 地址分组

| 范围 / 地址 | 规划用途 | 管理规则 |
| --- | --- | --- |
| 192.168.9.0 / .255 | 网络地址 / 广播地址 | 不分配给设备 |
| .1 | 物理路由器、实验节点默认网关 | 已从用户提供的母机 ip route 确认；其他客户端仍需核对 |
| .2–.4 | 交换机/AP 管理预留 | 设备具备管理功能时才分配 |
| .5 | 现有 VCSA | 位于 esxi01，保留当前地址 |
| .6–.8 | 虚拟化管理扩展预留 | 不默认部署额外 vCenter |
| .9 | Rocky 母机临时地址 | 仅母机使用；克隆时改为每台节点的独立地址 |
| .10–.19 | 集群外基础服务 | .10 OpenWrt、.11 DNS、.12 Harbor、.13 GitLab、.14 Nexus、.15 管理机、.16 独立备份、.17 第二 DNS；.18–.19 预留 |
| .20–.29 | 固定管理终端 | Mac、运维工作站等按实际需要登记；普通 DHCP 客户端继续使用 .30–.49 |
| .30–.49 | 路由器 Wi-Fi DHCP | 用户确定的唯一规划 DHCP 池；须检查有线客户端是否也使用同一池 |
| .50 | 保留 | 不分配 |
| .51–.60 | 物理服务器 iDRAC | 已用 .51–.53；.54–.60 扩展预留 |
| .61–.70 | ESXi 管理 | 已用 .61–.63；.64–.70 扩展预留 |
| .71–.89 | 其他物理设备管理扩展 | 不与 iDRAC/ESXi 段混用 |
| .90–.99 | 临时诊断地址 | 先查占用，登记使用者和释放时间 |
| .100 | Kubernetes API VIP | kube-vip 唯一宣告 |
| .101–.103 | cp01–cp03 | 三控制平面、三个物理故障域 |
| .104–.105 | infra01–infra02 | 平台工作负载 |
| .106–.108 | storage01–storage03 | cephadm + 受限 Worker |
| .109–.110 | worker01–worker02 | 应用和构建实验 |
| .111–.119 | 主集群节点扩展预留 | 主集群节点整体使用 .101–.119 |
| .120–.139 | 第二集群预留 | 节点和第二 API VIP 在启用前进一步细分；当前不分配 |
| .140–.159 | 独立数据服务 VM 预留 | 仅用于明确需要集群外 VM 的实验；集群内数据库不消耗本段 LAN 地址 |
| .160–.179 | CI/构建 VM 预留 | 仅分配给独立 VM；Pod 不按本段静态分配 |
| .180–.199 | 高级实验 VM 预留 | 多集群、嵌套虚拟化等按需登记，不提前部署 |
| .200 | 保留 | 不分配 |
| .201–.210 | MetalLB 业务池 | .201 为规划网关入口，按 Service 实际分配登记 |
| .211–.220 | Cilium 或扩展实验池 | 与主池、API VIP 隔离 |
| .221–.239 | VIP 扩展预留 | 未确定唯一宣告者前，不加入任何控制器地址池 |
| .240–.254 | 恢复与远期扩展预留 | 不默认用于第二个 DHCP 池 |
| 10.244.0.0/16 | 主集群 Pod | Cilium 分配，每节点 /24 |
| 192.168.20.0/24 | 主集群 Service | .1 API Service、.10 CoreDNS，其余动态分配 |
| 10.245.0.0/16 / 10.96.0.0/16 | 第二集群 Pod / Service | 06C 使用前重查重叠 |

表中的简写 `.x` 均属于 `192.168.9.0/24`，Service 行中的 `.1`、`.10` 属于该行的 `192.168.20.0/24`。

这些是同一个 /24 内的地址用途分组，不是 VLAN 或子网隔离。DHCP 池之外的地址仍可能已有静态设备，分组不能代替占用检查。OpenWrt .10 保持旁路由用途，不能因为部署它就把全网默认网关改为 .10。第二集群、独立服务和高级实验均为保留用途，不新增常驻 VM 预算。

## 2. 名称模板

| 用途 | 示例与目标 |
| --- | --- |
| 管理入口 | `esxi01.mgmt.internal.egon.top`、`idrac01.mgmt.internal.egon.top`、`openwrt.mgmt.internal.egon.top`、`dns.mgmt.internal.egon.top`、`admin.mgmt.internal.egon.top` |
| vCenter 目标名称 | `vcsa.mgmt.internal.egon.top` → .5；当前 `vcenter.egon.local` 尚未迁移 |
| 待定管理服务 | `ceph.mgmt.internal.egon.top`，实际端点核实后发布 |
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

## 4. 现有 VCSA 的 DNS 恢复与名称迁移

2026-10-14 用户确认：VCSA 位于 R730 / esxi01（.61），地址为 .5，当前名称 `vcenter.egon.local`，SSO 账号 `administrator@egon.local`；旧 DNS 服务器丢失，当前未配置 DNS IP，但 VAMI 可登录。均为用户提供的信息，尚未远程复验。

采用先恢复解析、后迁移名称的顺序。VCSA 的主机名/PNID 与 SSO 域分别登记；本次保留 SSO 域 `egon.local`，不把账号后缀当成需要发布的 DNS 区，也不将其跟随主机名替换。SSO 域变更有独立的 domain-repoint 流程与依赖，不纳入此次 DNS 修复。[Broadcom SSO 域处理说明](https://knowledge.broadcom.com/external/article/418490/vcenter-cant-join-active-directory-domai.html)

1. 通过 ESXi .61 的 Host Client 直接创建第一台基础 DNS VM，避开 vCenter 对旧 DNS 的依赖。先核实 Datastore 与 Port Group，并校验 Mac 上的 Rocky ISO。DNS 目标为 .11，FQDN 为 `dns.mgmt.internal.egon.top`；其系统和数据使用本地存储，不依赖 Kubernetes/Ceph。
2. 先在 DNS 上建立兼容记录 `vcenter.egon.local A 192.168.9.5`，恢复期间 `.5` 的 PTR 指向旧名称；为已经纳管的 ESXi 建立其当前实际名称的 A/PTR，不假设它们已使用目标 FQDN。兼容旧名称不改变新建设施统一采用 `internal.egon.top` 的规范，不创建通配旧域记录。
3. 分别从管理客户端和 VCSA 检查 DNS 可达性、旧名称正向/反向解析与 ESXi 名称解析。通过 VAMI 在记录已就绪并具备官方要求的备份/离线快照后，将 DNS 服务器设置为 .11，主机名仍保留旧值。仅修改 Mac 的 hosts 文件不能恢复 VCSA 和 ESXi 的 DNS 依赖。[Broadcom DNS 服务器变更流程](https://knowledge.broadcom.com/external/article/375247/how-to-changeupdate-dns-server-ip-addres.html)
4. 恢复管理功能后，为 `vcsa.mgmt.internal.egon.top` 建立指向 .5 的 A 记录。在单独的迁移窗口准备备份，并将 `.5` 的 PTR 改为目标名称，验证新名称 A/PTR 后，按 VAMI 正式流程变更主机名/PNID。先核实实际 VCSA 版本、ELM/VCHA、证书和已注册外部产品依赖；不直接修改 PNID 数据库、hostname 或 `/etc/hosts` 充当完整迁移。[Broadcom FQDN 变更流程](https://knowledge.broadcom.com/external/article/418448/update-or-change-vcenter-server-applianc.html)；[A/PTR 与迁移前置条件](https://knowledge.broadcom.com/external/article/369413)
5. 验证新 URL、原 SSO 账号登录、ESXi 连接与证书名称。旧名称的 A 记录仅用于迁移兼容，不把它当作新证书支持的访问地址；依赖完成切换后再清理。SSO 域继续使用 `egon.local`，Kubernetes Service 域继续使用 `cluster.local`。

验收查询示例（DNS 尚未部署，不代表已经通过）：

```bash
# 恢复旧名称时执行；预期 A 为 .5，PTR 为旧名称。
dig @192.168.9.11 vcenter.egon.local A +short
dig @192.168.9.11 -x 192.168.9.5 +short

# 准备正式改名时执行；预期 A 为 .5，PTR 为目标名称。
dig @192.168.9.11 vcsa.mgmt.internal.egon.top A +short
dig @192.168.9.11 -x 192.168.9.5 +short
```

Mac 上已发现 `/Users/mario/Downloads/Rocky-10.2-x86_64-minimal.iso`，2026-10-14 计算的 SHA256 与官方 CHECKSUM 一致，物料记录见 [ops/versions.lock.yaml](../ops/versions.lock.yaml)，证据见 [本批资产记录](../ops/00-preparation/records/2026-10-14/assets.md)。尚未验证 GPG 签名、上传或试装；Rocky 10 要求客体具备 x86-64-v3，仍需检查实际虚拟 CPU/EVC 暴露能力。[Rocky 10 发布说明](https://docs.rockylinux.org/latest/releases/release_notes/10_0/)

## 5. 地址与网段补充约定

以下保留 2026-10-13 初始基线中的网段与地址约定。网关等现场参数已在前文补充 2026-10-14 的用户确认；当前分配以该确认和台账为准，初始候选值不覆盖后续实际记录。

### 主集群网络

节点/管理网络为 192.168.9.0/24，Pod 网络为 10.244.0.0/16，Cilium 每节点 Pod 地址块为 /24。Service 网络为 192.168.20.0/24；192.168.20.1 留给 Kubernetes API Service，192.168.20.10 留给 CoreDNS，业务 ClusterIP 主要自动分配。

Service 网段不是物理 VLAN，无需建立家用路由器网关，也不应接入 DHCP。整个 Service /24 的容量有限，本版要求跟踪分配量，并以约 180 个已分配地址作为提前评估点，而非平台硬限制。开启大型模块前估算新增 Service；不足时优先减少闲置模块或放到第二集群，不把运行中扩 Service CIDR 当作轻松的常规步骤。

### 基础设施地址

192.168.9.10 为 OpenWrt，.11 为 DNS，.12 为 Harbor，.13 为 GitLab，.14 为 Nexus，.15 为管理机，.16 为独立备份接入预留，.17 为可选第二 DNS。是否有真实的外部备份设备不能只靠给 .16 分配一个地址来满足。

ESXi .61/.62/.63 与 iDRAC .51/.52/.53 保持不变。主网关暂以现有实际值为准，192.168.9.1 仅是待现场核实的常见候选。所有静态地址启用前核对 DHCP 保留和占用。

### 十节点与入口地址

cp01/cp02/cp03 对应 .101/.102/.103；infra01/infra02 对应 .104/.105；storage01/storage02/storage03 对应 .106/.107/.108；worker01/worker02 对应 .109/.110。

API VIP 使用 192.168.9.100，由 kube-vip 管理。业务 VIP 预留 .201–.220，第一条 MetalLB 主线先使用 .201–.210，默认网关入口可用 .201；.211–.220 留给不重叠的对照或扩展。kube-vip、MetalLB 与 Cilium 不得共同宣告同一地址。

### 第二集群与后续存储网络

第二集群 Pod CIDR 为 10.245.0.0/16、Service CIDR 为 10.96.0.0/16，节点 IP 与 API VIP 在启用前从已核实可用范围划出。跨集群网络要求唯一身份和无冲突路由，不能只创建几个 CRD 便视为连通。

Ceph 第一版共用节点网络。独立存储网、BGP、VLAN 和高速网卡都需真实硬件和配置能力；未经核实不假定现有交换机支持。所有 CIDR 都要与家庭网络、VPN 远端和容器桥接网络交叉检查。
