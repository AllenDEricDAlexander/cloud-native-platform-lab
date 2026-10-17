# Phase 00 阶段验收（2026-10-14 批次）

按 [阶段验收模板](../../../templates/phase-acceptance.md) 填写。每一项链接到实际证据；「第 N 节」指 [执行记录](assets.md)。没有运行证据的条目标为未执行，不以计划或清单代替。

## 1. 范围与输入

| 项目 | 内容 |
| --- | --- |
| 阶段 | Phase 00：基础设施、服务器初始化与软件供应准备（[计划](../../../../plan/00-preparation.md)，43 个步骤） |
| 执行时间 | 2026-10-14 至 2026-10-17 |
| 配置版本 | main 分支 0230b8f 起（本文件随后提交）；未推送到远端 |
| 版本锁 | [versions.lock.yaml](../../../versions.lock.yaml) |
| 台账 | [hosts.yaml](../../../inventory/hosts.yaml)、[networks.yaml](../../../inventory/networks.yaml)、[resources.yaml](../../../inventory/resources.yaml)（[速览](../../../inventory/README.md)） |
| 物理故障域 | 3 台 ESXi（esxi01 R730，esxi02、esxi03 R730xd），共用一台交换机与路由器；基础服务全部在 esxi01 |
| 操作流程 | [Phase 00 操作流程](../../README.md) |
| 前置阶段 | 无 |
| 本次测试范围 | 十台节点的 Linux/CRI、重启与幂等；DNS、CA、OpenWrt 显式代理、Harbor、GitLab、Nexus、备份；断网验收 |

## 2. 交付与用例

### 2.1 计划中的阶段验收用例

| 验收用例 | 测试入口 | 预期 | 实际结果与证据 | 状态 |
| --- | --- | --- | --- | --- |
| 十台节点通过 node-readiness 与 host-network CRI smoke | `scripts/collect-node-readiness.sh --with-cri-smoke` | 全部通过 | 重启后十台 27/27，六项身份唯一，CRI 自测经 Harbor 拉取镜像后 PASS：[矩阵](evidence/00.10.02-node-readiness-20261016-234651/matrix.md)（第 86 节） | 通过 |
| 关键服务不依赖 K8s/Ceph | 架构与部署方式 | 基础服务部署在集群外 VM，使用本地数据盘 | DNS、Harbor、GitLab、Nexus、备份都运行在集群外 VM，使用本地数据盘；重启后服务恢复：[证据](evidence/00.11-reboot-services.txt)（第 106 节） | 通过 |
| VPN 故障下内网可用 | `playbooks/offline-acceptance.yml -e stage=offline` | 出网中断时，内部服务仍可用 | 停止 OpenWrt 代理期间，内部服务提供了全部所需内容：[证据](evidence/00.10.04-offline-cut-2.txt)（第 114 节）。本实验没有独立的 VPN 隧道，出网由订阅代理承担 | 通过（以出网代理代替 VPN） |
| 干净客户端断网后完成指定物料的安装及七类最小构建 | 同上 | 15 项全部通过 | DNS/TLS、RPM、镜像、Git、Java/TS/Python/C#/Rust/C/C++ 全部 PASS：[阶段 A](evidence/00.10.04-offline-warm-4.txt)、[阶段 B](evidence/00.10.04-offline-cut-2.txt)（第 112–114 节） | 通过 |
| 独立备份恢复一个基础服务 | `playbooks/backup.yml`、`playbooks/restore-drill.yml` | 备份位于独立介质，恢复一个服务并验证数据 | restic 加密备份五个快照，`restic check` 无错误；DNS 配置与区域恢复到临时目录，经 BIND 工具校验，并与在用文件逐字节相同；CA 目录恢复后与原件一致：[备份](evidence/00.10.03-backup.txt)、[演练](evidence/00.10.03-restore-drill.txt)（第 103–104 节） | 部分通过：备份与被备份服务同在 esxi01，不是独立介质；只恢复并校验了数据，没有在新 VM 上重建服务 |

### 2.2 十节点 Linux/CRI/重启/幂等矩阵

| 项目 | 入口 | 结果 | 证据 |
| --- | --- | --- | --- |
| 身份唯一（machine-id、BIOS UUID、MAC、SSH 主机密钥、主机名、IP） | node-readiness | 十台唯一 | [矩阵](evidence/00.10.02-node-readiness-20261016-234651/matrix.md) |
| 系统基线（SELinux Enforcing、firewalld、Swap、cgroup v2、内核参数、时间、journald） | `bootstrap-nodes.yml` + node-readiness | 通过 | 同上；[防火墙允许与拒绝](evidence/00.10.02-firewall-verify-all.txt) |
| 内部 DNS 与 CA 信任 | `bootstrap-nodes.yml --tags dns,ca_trust` | 只用 .11，信任根 CA | [证据](evidence/00.09.03-nodes-dns-ca-harbor.txt)、[IPv6 DNS 修正](evidence/00.07.03-nodes-ipv6-dns.txt) |
| containerd/runc/crictl 与入群工具为锁定版本 | node-readiness | 与版本锁一致 | 矩阵「版本」项 |
| CRI：sandbox 来自 Harbor Digest，经 Harbor 拉取、运行、日志、清理 | `--with-cri-smoke` | PASS | 矩阵「CRI 自测」；[sandbox 切换](evidence/00.10.02-sandbox-harbor.txt) |
| 引导镜像经 CRI 从 Harbor 预拉 | `harbor-bootstrap-images.yml` | 十台 failed=0 | [证据](evidence/00.10.02-harbor-images-pinned.txt) |
| 重启后一致 | `reboot-nodes.yml` + 矩阵 | 十台通过 | [重启](evidence/00.11-reboot-nodes.txt)、重启后矩阵 |
| 幂等 | `bootstrap-nodes.yml --check` | 十台 changed=0 | [证据](evidence/00.11-bootstrap-check.txt) |
| OSD 候选盘未初始化 | 台账与角色设计 | 未添加、未初始化 | hosts.yaml 各 storage 节点 `osd_device_ids: []` |

### 2.3 基础服务

| 服务 | 交付 | 验证 | 证据 | 状态 |
| --- | --- | --- | --- | --- |
| 内部 DNS（.11） | `dns.yml`、dns_server 角色 | 内部名称、PTR、外部递归、权威应答 | [部署](evidence/00.07.01-dns-deploy.txt)、[修正](evidence/00.07.03-dns-fix.txt) | 通过 |
| 内部 CA | `pki/create-ca.sh`、`issue-cert.sh` | 链验证、名称约束拒绝外域；各服务经根 CA 校验 | 第 71–73 节；各服务验证 | 通过 |
| OpenWrt 显式代理（.10） | `openwrt/apply-base.sh`、`install-mihomo.sh` | Mac 与 cp01 经代理访问返回 204 | [基线](evidence/00.05.03-openwrt-base.txt)、[代理](evidence/00.06.02-proxy-test.txt) | 通过 |
| Harbor（.12） | `harbor.yml`、`harbor-projects.yml` | API、健康、/v2/；开机自恢复；代理缓存摘要与上游一致；只读机器人 | [部署](evidence/00.11-harbor-boot-unit.txt)、[项目](evidence/00.09.03-harbor-projects-2.txt) | 通过 |
| GitLab（.13） | `gitlab.yml` | HTTPS、root 口令核对、浏览器登录 | [证据](evidence/00.09.01-gitlab-deploy.txt) | 通过 |
| Nexus（.14） | `nexus.yml`、`nexus-repos.yml` | HTTPS、admin 口令；8 个代理仓库以只读账户取得固定内容；未认证返回 401 | [部署](evidence/00.09.04-nexus-deploy.txt)、[仓库](evidence/00.09.04-nexus-repos.txt)、[Conan](evidence/00.09.05-nexus-conan.txt) | 通过 |
| 备份（.16） | `backup.yml`、`restore-drill.yml` | 五个快照、check 无错误、恢复演练 | 见 2.1 | 部分通过（见 2.1） |
| 服务重启复验 | `reboot-nodes.yml`、`verify-services.yml` | 五台重启后服务恢复 | [证据](evidence/00.11-reboot-services.txt) | 通过 |

### 2.4 计划步骤对照

| 步骤 | 状态 | 说明 |
| --- | --- | --- |
| 00.01.01–03 资产、网络设备、预算 | 部分 | 用户报告的数据已登记；交换机型号与 VLAN、各宿主机现有占用未核实 |
| 00.01.04 主方案与对比实验的管理权 | 未执行 | 没有记录 |
| 00.02.01–03 目录、版本锁、物料清单 | 完成主体 | Rocky 与 OpenTofu、01 之后的组件尚未锁定 |
| 00.03.01–02、00.03.04 地址、域名、DNS 职责 | 完成 | — |
| 00.03.03 公网发布白名单 | 未执行 | 尚无公网入口（02 处理） |
| 00.04.01 vSwitch 与端口组核实 | 未执行 | — |
| 00.04.02 VIP 二层可达性 | 未执行 | **01 使用 API VIP 前必须完成** |
| 00.04.03 模板 | 完成 | 第 8–48 节 |
| 00.04.04 基础服务 VM | 完成主体 | admin VM（.15）未建，管理工作在 Mac 上 |
| 00.04.05 分散放置 | 部分 | 按计划克隆；除 cp01 外未从 vSphere 导出放置核对，**01 前应核对三台控制平面与存储节点分属三台宿主机** |
| 00.05.01–03 OpenWrt 旁路由 | 完成 | — |
| 00.05.04 双接口升级路径 | 未执行 | — |
| 00.06.01 VPN 隧道与凭据管理 | 部分 | 使用订阅代理，订阅地址只在设备上；无独立 VPN |
| 00.06.02 显式代理 | 完成 | — |
| 00.06.03–04 分流与绕行清单 | 部分 | 基础规则：内部域名与私有地址直连，其余走代理 |
| 00.06.05 出口故障演练 | 完成 | 断网验收阶段 B |
| 00.07.01–03 DNS 与客户端 | 完成 | — |
| 00.07.04 DNS 故障与恢复流程 | 部分 | 有备份与配置恢复演练；第二台 DNS（.17）未部署，DNS 为单点 |
| 00.08.01 内部 PKI | 完成 | — |
| 00.08.02 信任分发 | 完成主体 | 系统、Java、.NET、Node、pip、Cargo、Conan、Git、podman 均信任（断网验收覆盖） |
| 00.08.03 公网与内部证书隔离 | 未执行 | — |
| 00.09.01 GitLab | 完成 | — |
| 00.09.02 Harbor 与项目权限 | 完成 | 引导与代理缓存项目公开，只读机器人用于私有项目 |
| 00.09.03 上游代理缓存与引导镜像库 | 完成 | 代理缓存离线时只能按平台 Digest 取用（第 113 节） |
| 00.09.04 Nexus 与语言依赖代理 | 完成 | — |
| 00.09.05 C/C++ 与构建工具缓存 | 完成主体 | Conan 代理与发行版工具链；vcpkg 未做 |
| 00.09.06 镜像扫描与数据库同步 | 未执行 | — |
| 00.10.01 管理工具环境 | 部分 | Ansible 完成；OpenTofu 未开始；凭据分离只做到「口令在仓库之外」 |
| 00.10.02 十节点初始化与幂等 | 完成 | 见 2.2 |
| 00.10.03 独立备份与恢复 | 部分 | 见 2.1 |
| 00.10.04 断网验收 | 完成 | 见 2.1 |
| 00.10.05 交接 | 本文件 | — |

## 3. 恢复与清理

- **备份位置**：restic 仓库 `sftp:restic@192.168.9.16:/srv/backup/restic/lab`，加密；口令保存在管理端 `~/.cnpl-secrets/restic_password`，并由用户另存到 Mac 之外。dns、harbor、gitlab、nexus 每日 02:30 前后自动备份；管理端执行 `scripts/backup-mac.sh` 备份 CA、口令与 OpenWrt 配置。
- **恢复演练**：只恢复到临时目录，结束时已删除，没有覆盖任何在用文件。
- **临时状态的清理**：
  - 断网验收的路由与 nftables 规则已恢复，OpenWrt 代理已重新启动，经代理访问外网返回 204；
  - build01 保留，作为构建机；
  - GitLab 自动化令牌（cnpl-automation，api 范围，一年有效）保留，令牌只保存在管理端；
  - 测试仓库 lab/offline-smoke 保留，供以后复测。
- **主线回归**：服务 VM 重启后，`verify-services.yml` 全部通过；十节点重启后矩阵 27/27。

## 4. 未完成项与结论

| 未完成或偏差 | 原因 | 后续动作 | 回访阶段 | 实际状态 |
| --- | --- | --- | --- | --- |
| VIP 二层可达性（00.04.02） | 未单独验证 | 十台跨宿主机直接互通、同一网段，属同一二层；用户 2026-10-17 决定不单独验证，在 01 首个控制平面启动 kube-vip 时直接确认 | 01（cp01 初始化时） | 随 01 确认 |
| 实际放置核对（00.04.05） | 未从 vSphere 导出 | 用户 2026-10-17 决定不核对，只按 IP 管理：不影响集群功能，只影响容错——若两台控制平面实际在同一台 ESXi，该宿主机故障时 etcd 失去多数派 | 03 / 06（故障域实验前） | 已接受的风险 |
| vSwitch 与端口组核实（00.04.01） | 未执行 | 与上一项一起导出核对 | 01 之前 | 未执行 |
| 内部时间源 | planned_time_servers 为空，节点使用公共 NTP 池 | 断网时间较长时需要内部时间源（可放在 dns 或 OpenWrt） | 01–02 | 未执行 |
| 第二台 DNS（.17） | 未部署 | DNS 单点；部署到另一台宿主机 | 02 前 | 未执行 |
| 独立备份介质 | 用户决定放在 esxi01 的 VM（学习用途） | 另有 NAS 或外置盘时，迁移仓库，或复制一份到独立介质 | 03 / 06E | 偏差，已记录 |
| 整台服务的重建演练 | 只做了数据恢复与校验 | 在新 VM 上从备份重建 Harbor 或 GitLab | 06E | 未执行 |
| OpenTofu（00.10.01） | 未开始 | VM 目前在 vCenter 手工克隆 | 04 | 未执行 |
| admin VM（.15） | 未建 | 管理工作在 Mac 上 | 04 | 未执行 |
| 镜像扫描（00.09.06） | 未执行 | Trivy 与漏洞库同步 | 04 | 未执行 |
| 公网证书隔离、公网白名单（00.08.03、00.03.03） | 尚无公网入口 | 02 部署网关时处理 | 02 | 未执行 |
| 独立 VPN 隧道、双接口路由（00.06.01、00.05.04） | 使用订阅代理 | 需要时再建 | 02 / 06 | 未执行 |
| vcpkg、交换机型号与 VLAN、各宿主机现有占用 | 未执行 | 需要时补充 | — | 未执行 |

**主线是否可交接：是。** 十台节点完成 Linux 基线、CRI 与入群工具，镜像经内部 Harbor 提供，重启与幂等通过；01 所需的 DNS、CA、Harbor 引导镜像都可用。VIP 二层可达性在 01 初始化 cp01 时直接确认；实际放置由用户决定不核对，作为已接受的风险（影响容错，不影响功能）。

**阶段是否完整完成：否。** 上表各项未执行或存在偏差，在对应的回访阶段继续跟踪，不视为通过。
