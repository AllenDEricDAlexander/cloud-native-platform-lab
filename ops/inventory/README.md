# 资产与参数台账

[项目入口](../../README.md) · [操作总览](../README.md) · [Phase 00 操作流程](../00-preparation/README.md)

三份 YAML 是主机、网络和资源参数的**唯一来源**。Ansible Inventory、DNS 区域和节点检查的期望值都由它们生成或读取，不在别处另写一份。所有版本、校验值与镜像 Digest 归 [版本锁](../versions.lock.yaml)。

| 文件 | 内容 |
| --- | --- |
| [hosts.yaml](hosts.yaml) | 宿主机、模板、十台节点、基础服务 VM、vCenter：名称、地址、规格、放置、状态 |
| [networks.yaml](networks.yaml) | 网段、网关、DHCP、DNS、地址分配、域名层级、集群 CIDR 与 VIP |
| [resources.yaml](resources.yaml) | 宿主机硬件与预算、节点规格、基础服务内存、安全策略、存储与容量门槛 |

[vips.yaml](vips.yaml)补充网络台账内 `.201–.210` 主池的具体用途、负责人和撤销流程；不扩大 `networks.yaml` 的地址范围。每批实际 Service UID、分配与撤销另见执行记录中的 `vip-ledger.json`。

`null` 表示未知，不代表零或不存在；`reported_*` 字段来自用户报告，未经独立核实。Phase 00 完成时应有哪些对象（目标台账）见 [阶段计划](../../plan/00-preparation.md#阶段完成时的目标状态)，本目录记录它们的实际参数。

## 1. 修改台账的流程

1. 修改 YAML，在注释中写明日期和依据（执行记录小节）。
2. 重新生成 Ansible Inventory（只纳入 `vm_status` 不是 planned 的服务 VM）：
   ```bash
   cd ~/SelfProject/cloud-native-platform-lab && ruby ops/00-preparation/scripts/generate-ansible-inventory.rb
   ```
3. 增删主机或改地址时，递增 `ops/00-preparation/ansible/roles/dns_server/defaults/main.yml` 中的 `dns_zone_serial`，再运行 `playbooks/dns.yml`，DNS 区域随之更新。
4. 管理端地址（`lab_mgmt_sources`，在 `inventories/lab/group_vars/all.yml`）或节点地址变化时，重跑 node_base 的防火墙部分，使 ipset 来源一致。
5. 新 VM 的数据盘容量必须与台账 `data_disk_gib` 一致：data_disk 与 harbor 角色按容量选盘，不一致时会停止。

生成的 `inventories/lab/hosts.yml` 不要手改；主机专属设置（如数据盘挂载点）写在 `inventories/lab/host_vars/`。

## 2. 台账速览（2026-10-17）

以下摘自 YAML，便于阅读；两者不一致时以 YAML 为准。

### 2.1 物理设备

| 设备 | 规格 | 管理地址 | 说明 |
| --- | --- | --- | --- |
| esxi01 | Dell R730，2× E5-2673 v4（40 核 80 线程），128 GiB，3×6 TB SAS + 480 GB SSD | ESXi .61 / iDRAC .51 | 数据存储 esxi01-sas10t5（报告剩余约 9.9 TB），端口组 VM Network；运行模板、vCenter 与全部基础服务 |
| esxi02 | Dell R730xd，2× E5-2686 v4（28 核 56 线程），64 GiB，3×4 TB SAS + 480 GB SSD | ESXi .62 / iDRAC .52 | vCenter 报过 IO 筛选器注册失败，未查 |
| esxi03 | 同 esxi02 | ESXi .63 / iDRAC .53 | — |
| vCenter | VCSA（在 esxi01） | .5 | 当前名称 vcenter.egon.local，改名暂缓 |
| 路由器 / 交换机 | 型号未登记；交换机 24 口千兆 | .1 / .2–.4 | .1 为默认网关，DHCP 池 .30–.49 |
| 管理 Mac | Wi-Fi 上外网（Clash 系统代理），USB 网卡 en5 接入实验网 | .200 | 防火墙规则中的 lab-mgmt 来源 |

### 2.2 地址与域名

| 地址段 | 用途 | 地址段 | 用途 |
| --- | --- | --- | --- |
| .1–.5 | 路由器、交换机、vCenter | .100 | 主集群 API VIP（kube-vip） |
| .9 | 模板 rocky10-base | .101–.119 | 主集群节点（已用 .101–.110） |
| .10–.19 | 基础服务 | .120–.199 | 第二集群、数据服务、CI、进阶实验预留 |
| .30–.49 | 路由器 DHCP | .200 | 管理 Mac |
| .51–.70 | iDRAC、ESXi | .201–.220 | MetalLB 业务 VIP 与对比实验 |

| 域 | 用途 |
| --- | --- |
| mgmt.internal.egon.top | 物理与管理设施：esxi、idrac、dns、openwrt、backup |
| k8s.internal.egon.top | 节点与平台：cp01–worker02、api、harbor |
| svc.internal.egon.top | 开发服务：gitlab、nexus |
| cluster.local | 集群内部（01 起） |

集群地址：Pod 10.244.0.0/16（每节点 /24），Service 192.168.20.0/24（kubernetes .1、DNS .10）。

### 2.3 虚拟机

所有 Rocky VM 从 `rocky10-base@sealed-2026-10-16` 克隆，网卡 VMXNET3（ens33）。宿主机为计划放置，除 cp01 外未从 vSphere 导出核对。

| VM | IP | 宿主机 | vCPU / 内存 GiB | 磁盘 | 用途 |
| --- | --- | --- | --- | --- | --- |
| rocky10-base | .9 | esxi01 | 2 / 4 | 系统 100 + 运行时 100 GiB | 模板，已封装关机 |
| cp01 / cp02 / cp03 | .101–.103 | esxi01 / 02 / 03 | 4 / 8 | 运行时盘 100 GiB（/var/lib/containerd） | 控制平面 |
| infra01 / infra02 | .104–.105 | esxi01 / 02 | 6 / 12 | 同上 | 基础设施 |
| storage01 / 02 / 03 | .106–.108 | esxi01 / 02 / 03 | 8 / 16 | 同上；OSD 盘未添加 | 存储 |
| worker01 / worker02 | .109–.110 | esxi01 / 03 | 8 / 16 | 同上 | 工作负载 |
| openwrt | .10 | esxi01 | 2 / 1 | 1 GiB | 显式代理 |
| dns | .11 | esxi01 | 2 / 2 | — | 内部 DNS |
| harbor | .12 | esxi01 | 4 / 8 | /data 200 GiB | 镜像仓库 |
| gitlab | .13 | esxi01 | 4 / 16 | /var/opt/gitlab 150 GiB | 代码仓库 |
| nexus | .14 | esxi01 | 4 / 8 | /opt/sonatype-work 250 GiB | 依赖仓库 |
| backup | .16 | esxi01 | 2 / 2 | /srv/backup 500 GiB | 备份目标（与被备份服务同宿主，学习用途） |
| admin（计划） | .15 | — | — | — | 未创建 |
| 第二台 DNS（预留） | .17 | — | — | — | 未部署 |

### 2.4 资源（按计划放置推算）

| 宿主机 | 物理资源 | 已分配 vCPU / 内存 | 内存占比 |
| --- | --- | --- | --- |
| esxi01 | 80 线程 / 128 GiB | 44 / 89 GiB（节点 26 / 52，服务 18 / 37） | 约 70%，另有 vCenter（大小未登记） |
| esxi02 | 56 线程 / 64 GiB | 18 / 36 GiB | 约 56% |
| esxi03 | 56 线程 / 64 GiB | 20 / 40 GiB | 约 63% |

模板已关机，不计入。各宿主机现有占用与数据存储剩余空间（esxi01 除外）在 resources.yaml 中仍为空，以 vSphere 实际监控为准。
