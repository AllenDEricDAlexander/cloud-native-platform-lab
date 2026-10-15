# Phase 00：首批资产登记

## 1. 执行上下文

日期：2026-10-14（Asia/Shanghai）。对应步骤：[00.01.01 登记三台物理宿主机与现有数据](../../../../plan/00-preparation.md#000101-登记三台物理宿主机与现有数据)、[00.01.02 检查网络设备与 DHCP 可控程度](../../../../plan/00-preparation.md#000102-检查网络设备与-dhcp-可控程度)。

状态：进行中。证据来源是用户提供的硬件清单和地址说明；用户已确认两台 R730xd 配置相同，.51–.53 为 iDRAC 地址。尚未连接 ESXi、iDRAC、vCenter 或路由器，未执行部署或现场检查。

## 2. 已提供的信息

| 对象 | 型号 | iDRAC | ESXi | 用户提供的内存 |
| --- | --- | --- | --- | --- |
| esxi01 | Dell PowerEdge R730，3.5 英寸 8 盘位 | 192.168.9.51 | 192.168.9.61，ESXi 8 | 4 × 32 GB，DDR4 2400 |
| esxi02 | Dell PowerEdge R730xd，3.5 英寸 12 盘位 | 192.168.9.52 | 192.168.9.62，ESXi 8 | 2 × 32 GB，DDR4 2133 |
| esxi03 | Dell PowerEdge R730xd，3.5 英寸 12 盘位 | 192.168.9.53 | 192.168.9.63，ESXi 8 | 2 × 32 GB，DDR4 2133 |

R730：2 × E5-2673 v4，清单标注每颗 20 核/40 线程、2.3 GHz；3 × 6 TB SAS HDD、1 × 480 GB SAS SSD；PERC H730P，2 GB 缓存；1 × 1100 W 电源；RISER 1/2/3、M.2 转 PCIe 卡和盘架满配。M.2 转接卡不代表已安装 M.2 磁盘。

每台 R730xd：2 × E5-2686 v4，清单标注每颗 14 核/28 线程、2.4 GHz；3 × 4 TB SAS HDD、1 × 480 GB SAS SSD；PERC H730，1 GB 缓存；1 × 750 W 电源；RISER 卡和盘架满配。CPU 型号、核心数和频率按清单登记，待主机页面核对，不作为已实测容量。

VCSA 地址：192.168.9.5。物理路由器地址：192.168.9.1。另有一台 24 口千兆交换机，型号与 VLAN 管理能力未知。路由器地址不自动证明客户端默认网关或 LAN 掩码；这两项仍需实际查看。

用户描述实验环境“全部空的，啥都没配置”。这作为尚未部署实验服务的背景记录；ESXi、VCSA、RAID、Datastore 和既有虚拟机的实际配置与占用仍待核实。不得将未知占用写成零。

硬盘容量为单盘标称值，不能等同于 Datastore 空闲容量或 Ceph 可用容量。已存在的 ESXi 启动设备、VCSA 虚拟机及承载它们的存储和管理网络作为保留对象；盘位、序列号、RAID/虚拟磁盘与 Datastore 映射未核实前，不初始化或重建存储。

## 3. 台账更新与待核实项

已更新 [hosts.yaml](../../../inventory/hosts.yaml)、[resources.yaml](../../../inventory/resources.yaml)、[networks.yaml](../../../inventory/networks.yaml)。新增信息保留用户提供的来源；整体状态仍为 `planned_unverified`，`verified_at` 仍为空。

- 三台 ESXi 的具体版本/Build、许可证、实际 CPU/内存、物理网卡和当前资源占用。
- iDRAC 中物理盘、PERC 工作模式、已有 RAID/虚拟磁盘与健康状态；ESXi 的启动位置及 Datastore 名称、容量、剩余空间和物理来源。
- VCSA 版本、所在宿主机、内存/存储占用、三台主机是否已纳管及 EVC 设置。
- 路由器 LAN 掩码、DHCP 池、保留/排除地址、已分配租约；管理 Mac 的默认路由与 VPN 网段。
- 三台 ESXi 的 Port Group、VLAN、MTU、物理上联及跨主机路径。

下一次操作先只读查看路由器 LAN/DHCP 配置，核对 .5、.10–.17、.51–.53、.61–.63、.100–.110、.201–.220 是否与 DHCP、保留地址或现有设备冲突。核实后再确定保留/排除方案，未确认前不批量分配静态地址。

## 4. 本次结论

完成首批用户提供信息的登记；00.01.01、00.01.02 均未通过验收。未修改网络设备、虚拟机、RAID 或磁盘，未启动任何项目进程；没有部署、连通性或容量验收结果。

## 5. 同日补充：地址分组与 VCSA 现状

用户补充确认 LAN 为 192.168.9.0/24，Wi-Fi DHCP 使用 .30–.49，iDRAC 规划 .51–.60，ESXi 规划 .61–.70。已将完整地址用途分组写入 [networks.yaml](../../../inventory/networks.yaml) 和 [地址规划](../../../../arch/ip-address-plan.md)。这些分组仍须核对当前租约与静态设备占用；未修改路由器或部署 VLAN。

VCSA 的当前名称为 `vcenter.egon.local`，SSO 账号为 `administrator@egon.local`；用户报告旧 DNS 丢失，当前没有 DNS IP，但 VAMI 可以登录。VCSA 位于 R730 / ESXi .61 / iDRAC .51。目标名称仍为 `vcsa.mgmt.internal.egon.top`，尚未迁移，SSO 域保留。实际版本/Build、PNID、主机纳管状态和服务健康尚未复验。

已通过本地文件列表发现 `/Users/mario/Downloads/Rocky-10.2-x86_64-minimal.iso`；尚未计算并对照官方 SHA256/签名，未上传或安装。此后实际顺序调整为：核实 esxi01 的 Datastore/Port Group 与 ISO → 直接在 ESXi 创建 DNS VM → 恢复旧名称的 A/PTR 与 VCSA DNS → 在备份和目标名称 A/PTR 就绪后正式迁移 VCSA 名称。

本次仅更新计划与台账并核对官方资料；未连接服务器，DNS 恢复、ISO 校验和名称迁移均未执行。原先的空 DNS/DHCP 字段是当时未知状态，不表示此前实际不存在配置。

## 6. 同日继续：Rocky ISO 的 SHA256 核对

实际执行只读命令：`shasum -a 256 /Users/mario/Downloads/Rocky-10.2-x86_64-minimal.iso`，退出码 0。随后通过 HTTPS 读取 [官方 CHECKSUM](https://download.rockylinux.org/pub/rocky/10.2/isos/x86_64/CHECKSUM)，读取成功，匹配到同名 ISO 的 SHA256 条目。

本地计算值与官方值均为 `aac6ac3ce781b91a91ce78463405f66c611a5dca4b3840c79e5e01d97302f6c8`。SHA256 对照通过，已在 [versions.lock.yaml](../../../versions.lock.yaml) 登记候选版本、ISO 和证据；版本锁整体仍为 draft，Rocky 组件仍为 pending。

尚未验证 GPG 签名、CPU/EVC 兼容性、客体安装或服务运行；未上传 ISO、创建 VM、部署 DNS 或变更 VCSA。此结果只证明本地 ISO 的 SHA256 与通过 HTTPS 获取的官方校验值一致。

## 7. 同日调整：优先准备十台 Rocky 节点

用户补充 esxi01 的 Datastore 为 `esxi01-sas10t5`，报告剩余 9.9 TB；VCSA 使用 `VM Network` 端口组，vSwitch 推测为默认 `vSwitch0`。已记录 Datastore 和端口组；容量保留用户提供的单位，不换算为现场确认的 GiB，vSwitch 仍待核实。Datastore 名称不作为 RAID 级别或物理盘映射证据。

用户明确要求先推进十台 Rocky Linux 10 虚拟机和 Kubernetes 实验节点准备，VCSA 等事项以后处理。本批暂停此前先修复 VCSA DNS/改名的顺序，优先执行以下主线：

1. 在 esxi01 上传已核对 SHA256 的 ISO，创建 `rocky10-base`，规格 2 vCPU / 4 GiB / 80 GiB Thin 系统盘，EFI、VMXNET3、`VM Network`。只新建本项目 VM/VMDK，不重建现有 Datastore。首次安装采用最小化系统，DHCP 可用时临时获取网络；未核实前不将模板固定为节点 IP。
2. 验证 Rocky 10 启动、实际虚拟 CPU 能力、网络和最小系统；安装并确认 open-vm-tools、时间与 SSH 等公共基线。ESXi 8 的客体列表未提供 RHEL 10 时，按官方流程选择 RHEL 9 64-bit 选项，安装介质仍为 Rocky 10。[Broadcom 客体类型说明](https://knowledge.broadcom.com/external/article/395093)
3. 封装公共基线并保留关机母机；VCSA 暂缓时，不把转换成 vCenter 模板对象当作前置条件。克隆前确定实际可用的复制/部署方式，先用两个克隆检查 machine-id、SSH host key、MAC、UUID 和 IP 唯一，再展开十台。复制不得共享同一可写 VMDK。
4. 十节点沿用 [hosts.yaml](../../../inventory/hosts.yaml) 的角色、IP 和三宿主机分布，以及 [resources.yaml](../../../inventory/resources.yaml) 的起步规格，总计 64 vCPU / 128 GiB。esxi02/03 的 Datastore、容量、端口组和 CPU 暴露能力在部署到各自宿主机前核实；不得把全部节点放到 esxi01 后宣称高可用分布完成。模板、ESXi、VCSA 和基础服务另计。
5. 用已核实的网关和可达 DNS 完成静态网络、软件来源、时间、SSH、cgroup v2、Swap 与安全基线。不得引用尚未部署的 DNS .11 或 Harbor .12 作为现成依赖；内部权威 DNS 尚未建设时，相关验收仍为待完成，不把临时 hosts 文件计作正式 DNS 交付。
6. 安装锁定版本的 containerd/runc/crictl 和入群工具，附加并验证运行时盘、预热镜像、执行 CRI 自测，再做重启与幂等验证。本阶段不执行 kubeadm init/join；候选 Ceph OSD 不初始化。

各节点先从 80 GiB 系统盘母机创建，运行时和候选 OSD 盘按角色与实际容量另行附加；本次尚未确定或创建这些数据盘。

本机只读检查发现 Mac 当前默认网关为 192.168.0.1，系统 DNS 为 192.168.1.1、192.168.0.1。这是管理 Mac 的现状，不是实验节点的网络参数；不能直接复制到 192.168.9.0/24 节点。以目标 Rocky 客体的 DHCP、路由与实际连通性检查确定自举配置。

OpenWrt、AdGuard Home、Windows AD 不作为本批节点制作的前置；AdGuard Home 与 Windows AD 仍是讨论候选，未选择或部署。VCSA DNS/改名按用户要求暂缓。正式内部 DNS/CA、仓库、离线供应和独立备份/恢复等原 00 验收项仍保留未完成状态；只完成节点主线不能将整个 00 标记为通过。

本次已更新台账和执行顺序；尚未上传 ISO、创建模板或部署十台 VM，没有客体或 CRI 运行证据。

## 8. 同日继续：Rocky 母机安装与首次 SSH

证据来源：用户在安装后提供的 `cat /etc/os-release`、`ip -br address`、`ip route`、`lsblk` 与 SSH 登录输出。由用户完成操作；本助手未连接客体。只记录安装配置与脱敏结果，不记录密码。

安装设置：语言/键盘 US，时区 Asia/Shanghai，Kdump disabled，唯一系统盘实际为 100 GiB、自动分区；IPv4 手动配置为 192.168.9.9/24，网卡 ens33，主机名 rocky10-base。用户选择继续采用 root 密码 SSH 登录；本批公共配置不调整该登录方式。

| 检查 | 用户提供的结果 | 本次判断 |
| --- | --- | --- |
| OS | Rocky Linux 10.2 (Red Quartz)，VERSION_ID=10.2 | 安装与启动成功；不代表三类客体/EVC 均验证 |
| SSH | Mac 成功登录 root@192.168.9.9 | 该客户端到母机的 SSH 路径可用 |
| IPv4 | ens33 UP，192.168.9.9/24 | 母机临时地址已配置，不供克隆共用 |
| 路由 | default via 192.168.9.1 dev ens33 | 已确认母机默认网关；外网和 DNS 尚未验证 |
| 系统盘 | sda 100G，600M EFI、2G /boot、97.4G LVM | EFI 启动分区已建立；不重新分区 |
| LVM | rlm-root 62.8G XFS /、rlm-home 30.7G XFS /home | 保留现有分区；运行时专用盘另行配置 |
| Swap | rlm-swap 3.9G，标记 [SWAP] | 当前激活，待关闭并验证重启后不再启用 |

台账已将母机系统盘调整为实际 100 GiB，将 .9 从虚拟化扩展预留单独划给母机，并根据用户提供的路由更新默认网关；不会将母机 IP、machine-id 或 SSH host key 原样复制给十节点。此前第 7 节的 80 GiB/DHCP 是创建前建议，以本节实际安装状态为准。

下一批先检查当前 DNS 和软件源，再安装基础工具及 open-vm-tools/chrony、持久关闭 Swap，验证 cgroup v2、VMXNET3 驱动、时间源和安全模式。暂不清理克隆身份、修改网卡地址、删除 Swap LV 或改变 root SSH 登录；软件来源/运行时版本和模板封装尚未完成。

验收范围：母机安装和首次 SSH 已有用户输出，Linux/CRI、镜像预热、克隆唯一身份、十节点部署、重启和幂等仍待执行。实际 VM 的 CPU/内存规格、Thin 属性与 ESXi 客体类型还没有输出证据，不能仅凭创建建议标为已核实。

## 9. 下一批待执行：母机公共配置

下面由用户在母机 root 会话中执行，尚无执行输出。先检查 DNS/软件源；任一步失败则保留错误，先排查再继续依赖操作。安装通过后启用 VMware Tools 与 chrony，Swap 仅停止并注释 fstab 项，保留 LV 和原始 fstab 备份，不删除分区。

```bash
cat /etc/resolv.conf
dnf makecache --refresh
```

```bash
dnf install -y open-vm-tools chrony curl jq tar bind-utils ethtool iproute iputils
systemctl enable --now vmtoolsd chronyd

cp -an /etc/fstab /etc/fstab.before-k8s
swapoff -a
sed -ri '/^[[:space:]]*[^#[:space:]]+[[:space:]]+[^[:space:]]+[[:space:]]+swap[[:space:]]/s/^/# /' /etc/fstab
systemctl daemon-reload
findmnt --verify --verbose
```

```bash
swapon --show
stat -fc %T /sys/fs/cgroup
systemctl is-active vmtoolsd chronyd
ethtool -i ens33
vmware-toolbox-cmd timesync status
chronyc sources -v
chronyc tracking
getenforce
systemctl is-active firewalld
```

预期：软件源元数据下载成功，基础包安装成功；Swap 输出为空、fstab 验证无错误；cgroup 为 cgroup2fs；VMware Tools 与 chrony 均 active；网卡驱动为 vmxnet3。chrony 必须有真实可达的同步源，启用服务本身不代表已同步；VMware 周期时间同步状态用于下一步确定时间职责。SELinux/firewalld 先记录现状，不因安装 Kubernetes 就直接关闭。持久关闭 Swap 的重启验收仍需后续执行。[Kubernetes Swap 配置说明](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/)

## 10. 同日继续：公共配置验证与参考笔记

用户报告第 9 节此前命令均未报错，并提供客体检查输出。当前 Swap 无激活项，cgroup 为 cgroup2fs；vmtoolsd/chronyd 均 active；ens33 驱动为 vmxnet3（1.9.0.0-k-NAPI）；VMware 周期时间同步 Disabled。chrony 选中 119.28.206.193，Reach=377，tracking 的 Leap status=Normal、Stratum=3、System time=0.000698015 seconds slow。SELinux=Enforcing，firewalld=active。

这些结果证明本次母机的当前状态；开机启用与重启持久性、其他宿主机客体、十节点和 CRI 尚未验证。chrony 选中的 IP 是当时观测到的源，不直接将其替换为固定配置；VMware 周期同步关闭不自动证明所有启动/恢复事件同步设置均已核实。

已读取用户提供的参考笔记 `/Users/mario/book/编程书籍&后台开发/DevOpsAndOS/rocky/rocky.md`，未修改原文件。参考范围为公共工具、时间、VMware Tools 与网络配置思路；笔记中的数据库、Web 服务、Docker Engine、软件源批量替换、EPEL/CRB 扩展、未知磁盘格式化和大批性能参数不作为母机初始化指令。当前软件源已有成功结果，先保留；Rocky 10 网络使用 NetworkManager/keyfile，不能沿用旧 ifcfg/network service 流程。[Rocky 10 网络变更说明](https://docs.rockylinux.org/latest/releases/release_notes/10_0/)

用户随后明确本次禁止关闭 SELinux 和防火墙，要求接近生产。已固定为 Enforcing + firewalld enabled；不采用笔记中的禁用命令，也不采用 permissive 作为替代。后续按节点角色与来源配置必要规则、核实 runtime/CNI 的 SELinux 支持、文件标签与 AVC；兼容性未解决时保持该门槛，不宣称运行时已就绪。

## 11. 下一批待执行：公共工具、内核参数与重启复验

采用直接、可重复执行的公共配置，不新增架构层。以下命令仅供用户在母机 root 会话执行，尚无输出；目前不清理身份或封装母机，也不修改网卡和 SSH 登录。下一步验证通过后准备锁定运行时与入群工具，再安排克隆。

```bash
dnf install -y vim-enhanced wget bash-completion lsof sysstat tcpdump nmap-ncat rsync conntrack-tools socat container-selinux policycoreutils-python-utils audit

cat > /etc/modules-load.d/90-kubernetes.conf <<'EOF'
overlay
EOF
modprobe overlay

cat > /etc/sysctl.d/90-kubernetes.conf <<'EOF'
net.ipv4.ip_forward = 1
EOF
sysctl -p /etc/sysctl.d/90-kubernetes.conf
```

工具用于编辑、排障和后续 kubeadm/容器运行时；container-selinux 提供容器策略，policycoreutils-python-utils/audit 用于标签与拒绝日志诊断，安装它们不代表 CRI 已在 Enforcing 下验收。不启用 EPEL/CRB。只加载目前需要的 overlay 和 IPv4 转发，不预设 br_netfilter、rp_filter 或大批内核调优。软件源/安装失败时先处理错误，不继续依赖步骤；sysctl 预期输出 net.ipv4.ip_forward = 1。

由用户执行 `reboot`；SSH 会断开，重新连接 192.168.9.9 后执行：

```bash
uname -r
sysctl net.ipv4.ip_forward
lsmod | grep '^overlay'
swapon --show
systemctl is-enabled vmtoolsd chronyd firewalld
systemctl is-active vmtoolsd chronyd firewalld
chronyc tracking
getenforce
nmcli -g GENERAL.CONNECTION,IP4.DNS device show ens33
firewall-cmd --get-active-zones
df -hT / /home
```

预期转发=1、overlay 已加载、Swap 无激活项，服务启用且 active；SELinux 仍 Enforcing。chrony 需要重新取得有效同步，初始尚未同步时继续检查源和连通性，不能只看服务 active。NetworkManager 连接名、DNS 和 active zones 输出供后续精确配置使用，不假定连接名等于 ens33，不把防火墙绑定到尚未识别的 zone。root/home 空间按真实 df 输出记录。

## 12. 同日继续：公共配置重启复验

用户报告第 11 节命令全部成功并实际重启母机，提供重新登录后的检查输出。内核为 6.12.0-211.16.1.el10_2.0.1.x86_64；IPv4 转发=1，overlay 已加载，Swap 输出为空；vmtoolsd、chronyd、firewalld 全部 enabled 且 active，SELinux 仍 Enforcing。

chrony 重新同步到 time.nju.edu.cn，Stratum=2、Leap status=Normal，System time=0.000000023 seconds slow。NetworkManager 连接名为 ens33，DNS 为 8.8.8.8；public（默认）zone 绑定 ens33。根分区约 63G、已用 2.5G、可用 61G；home 约 31G、已用 633M、可用 30G。

本次母机公共配置的重启复验已有用户输出；时间源变化符合池化源的当前观测，不强行固定选中的 IP。该 DNS 用于当前外部解析，不代表内部权威 DNS 已部署。尚未验证十节点、CRI、CNI 或 API；SELinux/firewalld 门槛保持不变。

## 13. 下一批待执行：固定版本 RPM 与运行时盘准备

本助手通过 HTTPS 读取 Docker CentOS 10 / x86_64 stable 的 repomd.xml 与 primary 元数据，并对压缩 primary 数据校验 SHA256 成功。确认候选 RPM 为 containerd.io-2.4.2-2.el10.x86_64，元数据的 RPM SHA256 为 323346eb71f8886bce5c382978cf0b3934c14c08e20e10837b395c19b9ebd11e，依赖 container-selinux、libseccomp 和 systemd；当前尚未下载或验证 RPM 本身的签名。

采用 Docker 分发的 containerd.io RPM 路线，包内包含 runc，保留包管理、systemd 与发行版 SELinux 策略集成。[containerd 官方安装路线](https://github.com/containerd/containerd/blob/main/docs/getting-started.md)；[Docker 官方 EL10 包安装与签名说明](https://docs.docker.com/engine/install/centos/)。该来源说明不等于已经完成 Rocky 10 兼容性或 Enforcing 验收。候选记录已加入版本锁，整体仍为 draft，最终版本与 runc 版本以安装后的真实输出核对。

以下由用户在母机 root 会话执行，任一步失败先处理，不继续依赖步骤。先获取并核对公钥指纹，再导入公钥和校验 RPM；不跳过 GPG 检查。

```bash
dnf install -y gnupg2
mkdir -p /root/lab-artifacts
cd /root/lab-artifacts
curl -fL --retry 3 -o docker.gpg https://download.docker.com/linux/centos/gpg
gpg --show-keys --with-fingerprint docker.gpg
```

预期主公钥指纹为 `060A 61C5 1B55 8A7F 742B 77AA C52F EB6B 621E 9F35`；只有匹配才继续：

```bash
cd /root/lab-artifacts
curl -fL --retry 3 -o containerd.io-2.4.2-2.el10.x86_64.rpm \
  https://download.docker.com/linux/centos/10/x86_64/stable/Packages/containerd.io-2.4.2-2.el10.x86_64.rpm
echo '323346eb71f8886bce5c382978cf0b3934c14c08e20e10837b395c19b9ebd11e  containerd.io-2.4.2-2.el10.x86_64.rpm' | sha256sum -c -
rpmkeys --import docker.gpg
rpmkeys --checksig containerd.io-2.4.2-2.el10.x86_64.rpm
```

预期 SHA256 检查 OK，RPM 的 digests/signatures OK。服务尚未安装时 mask 可能提示 Unit 不存在但继续创建 mask，此为预期；必须成功保持 masked 才安装。运行时盘尚未挂载，不启动服务：

```bash
(
set -euo pipefail
cd /root/lab-artifacts
LAB_DOCKER_FPR=$(gpg --batch --show-keys --with-colons docker.gpg | awk -F: '$1 == "fpr" { print $10; exit }')
test "$LAB_DOCKER_FPR" = '060A61C51B558A7F742B77AAC52FEB6B621E9F35'
echo '323346eb71f8886bce5c382978cf0b3934c14c08e20e10837b395c19b9ebd11e  containerd.io-2.4.2-2.el10.x86_64.rpm' | sha256sum -c -
rpmkeys --checksig containerd.io-2.4.2-2.el10.x86_64.rpm
systemctl mask containerd.service
dnf install -y --setopt=localpkg_gpgcheck=1 /root/lab-artifacts/containerd.io-2.4.2-2.el10.x86_64.rpm
)
containerd --version
runc --version
rpm -q containerd.io container-selinux
systemctl is-enabled containerd
```

预期 containerd=2.4.2，RPM=2.4.2-2.el10.x86_64，服务 masked；is-enabled 对 masked 返回非零属于状态输出，不代表安装失败。尚未生成并验收 CRI 配置，也未安装 cri-tools/CNI/kubeadm；下一步配置将使用 version=3、systemd cgroup、enable_selinux=true，并验证实际文件/进程标签。[锁定 tag 的配置说明](https://github.com/containerd/containerd/blob/v2.4.2/docs/cri/config.md)

并行准备由用户在 ESXi .61 给 rocky10-base 新增一块 100 GiB Thin VMDK，保持已有系统盘不变。此为运行时盘，后续用于 /var/lib/containerd；不与未来 Ceph OSD 混用，也不把系统剩余空间当成已部署的独立盘。新增磁盘后，在 Rocky 执行只读检查：

```bash
lsblk -e7 -o NAME,PATH,SIZE,TYPE,FSTYPE,UUID,MOUNTPOINTS,MODEL,SERIAL
```

先根据新建任务与设备输出确认空盘，再在下一批创建文件系统和 UUID 挂载。不要预先假定设备为 /dev/sdb。待挂载、SELinux 标签及 systemd 挂载依赖就绪后才解除 mask 并启动 containerd。上面全部客体命令及新磁盘创建均尚未执行。

## 14. 同日故障：Rocky 下载签名公钥时 TLS 连接重置

用户执行安装块时，gnupg2 已安装，版本为 2.4.5-4.el10_1.x86_64；curl 下载 Docker 公钥时失败，错误为 `curl: (35) Recv failure: Connection reset by peer`。错误发生在第一份下载，依照 set -e 的顺序，后续 RPM 下载、密钥导入、mask 与 containerd 安装未执行。此时尚不能认定根因是 DNS、代理、出口路径或站点限制，也没有 SELinux/firewalld 拒绝证据；保持两个安全机制启用。

本助手从 Mac 的当前网络路径对同一官方 URL 发起 HTTPS 请求，结果 HTTP 200，TLS 校验结果为 0，下载得到 1627 字节公钥。连接记录 remote_ip=127.0.0.1，说明该次路径并非可直接等同于 Rocky 的公网访问路径；没有据此宣称 Rocky 网络已修复。

已在 `/Users/mario/Downloads/cloud-native-lab-seed-2026-10-14/` 保存两份官方来源物料：

- `docker.gpg`：解析 OpenPGP 主公钥包得到指纹 `060A61C51B558A7F742B77AAC52FEB6B621E9F35`，与 Docker 官方文档一致。未向 Mac 的用户密钥环导入密钥。
- `containerd.io-2.4.2-2.el10.x86_64.rpm`：36670556 字节，实际 SHA256 为 `323346eb71f8886bce5c382978cf0b3934c14c08e20e10837b395c19b9ebd11e`，与官方仓库元数据一致。已在版本锁补充本地物料与 SHA256 核对日期；RPM 签名尚待目标机器验证，未将 signature_verified 提升为 true。

采用管理端种子物料 + SSH 传输的自举路线继续，不改用未核实镜像、不跳过 TLS/GPG 校验，不变更目标节点的全局网络或安全设置。以下检查供用户在 Rocky 执行，尚未取得结果：

```bash
getent ahostsv4 download.docker.com
curl -q -4 --noproxy '*' -I --connect-timeout 5 --max-time 15 https://dl.rockylinux.org/
curl -q -4 --noproxy '*' -I --connect-timeout 5 --max-time 15 https://download.docker.com/linux/centos/gpg
```

这里强制 IPv4 且本次请求不使用代理，用于对比直接 HTTPS 路径，不修改长期代理设置。getent 用于查看系统解析，响应头/错误用于区分站点特定与较广的 HTTPS 问题；这些结果仍不足以单独证明上游具体设备或策略是根因。请求未使用 verbose，避免无意打印代理认证信息。

由用户在 Mac 终端传输：

```bash
scp /Users/mario/Downloads/cloud-native-lab-seed-2026-10-14/docker.gpg \
  /Users/mario/Downloads/cloud-native-lab-seed-2026-10-14/containerd.io-2.4.2-2.el10.x86_64.rpm \
  root@192.168.9.9:/root/lab-artifacts/
```

由用户回到 Rocky 执行本地校验与安装，括号内任一环节失败则停止：

```bash
(
set -euo pipefail
cd /root/lab-artifacts
LAB_DOCKER_FPR=$(gpg --batch --show-keys --with-colons docker.gpg | awk -F: '$1 == "fpr" { print $10; exit }')
test "$LAB_DOCKER_FPR" = '060A61C51B558A7F742B77AAC52FEB6B621E9F35'
echo '323346eb71f8886bce5c382978cf0b3934c14c08e20e10837b395c19b9ebd11e  containerd.io-2.4.2-2.el10.x86_64.rpm' | sha256sum -c -
rpmkeys --import docker.gpg
rpmkeys --checksig containerd.io-2.4.2-2.el10.x86_64.rpm
systemctl mask containerd.service
dnf install -y --setopt=localpkg_gpgcheck=1 ./containerd.io-2.4.2-2.el10.x86_64.rpm
)
```

仍可能需要从已有 Rocky 源获取依赖，这不是完整离线依赖闭包。目标机的 SSH 传输、签名检查、安装、网络诊断和新增运行时盘均待用户执行并返回证据。

## 15. 同日继续：containerd/runc 安装结果存档

用户回传 containerd --version、runc --version 和 systemctl is-enabled containerd 的输出，已保存至 [00.10.02 安装证据](evidence/00.10.02-containerd-install.txt)。containerd 为 2.4.2，commit=b7a25261e029d68978bbf290df0a62fc819b3c51；runc 为 1.5.2，commit=v1.5.2-0-g29dd3dc2，OCI spec=1.3.0，Go=1.27.2，libseccomp=2.5.6。containerd 服务状态 masked，与专用盘配置前的保护状态一致。

据此更新实际二进制版本和安装状态为 installed_unvalidated，整体版本锁仍为 draft。用户没有回传安装事务、rpm -q 或 RPM 签名结果，未补造这些证据，也未将 artifact.signature_verified 改为 true；原网络错误的根因仍未定位。

用户要求每一步存档用于复现：本批已新增 [批次索引](README.md) 和独立原始输出文件；此前命令、调整、故障和回传结果继续保存在本记录中。保存复现材料，不代表允许将密码或其他秘密入库。

## 16. 下一批待执行：运行时盘的新增与只读核实

先确认 ESXi .61 上的 rocky10-base 是否已经有第二块 100 GiB Thin 硬盘；仅当尚未新增时，在虚拟机编辑设置中新增一块，保留既有 100 GiB 系统盘。记录 Datastore、容量、Thin 属性和虚拟 SCSI 地址；不把“100G”本身当作设备身份证据。

当前尚未取得第二块盘的客体输出，不提供绑定 /dev/sdb 的格式化命令。下一步根据真实设备与空盘状态确定格式化对象，然后配置 UUID 挂载、SELinux 标签和 containerd 的挂载依赖；服务继续 masked，SELinux Enforcing/firewalld enabled 要求保持不变。

用户在 Rocky 执行下面的只读检查并保存日志；包签名检查与标签检查也用于补足本次复现证据。括号内 set -x 只跟踪本段公开命令，不覆盖密码交互：

```bash
install -d -m 0700 /root/lab-evidence/phase00
(
set -x
date -Is
hostnamectl --static
lsblk -e7 -o NAME,PATH,SIZE,TYPE,FSTYPE,UUID,MOUNTPOINTS,MODEL,SERIAL
rpm -q containerd.io container-selinux
rpmkeys --checksig /root/lab-artifacts/containerd.io-2.4.2-2.el10.x86_64.rpm
ls -lZ "$(command -v containerd)" "$(command -v runc)"
matchpathcon /var/lib/containerd
systemctl is-enabled containerd
getenforce
firewall-cmd --state
) 2>&1 | tee /root/lab-evidence/phase00/00.10.02-runtime-disk-before.txt
```

此块为诊断采集，没有 set -e：masked 的 is-enabled 会返回非零，仍应继续采集后续安全状态；整个管道完成不能代表每项都通过。日志要逐项检查，原始文件保留于客体，用户回传后再归档到本批 evidence/。这一批磁盘新增和采集尚未执行。

## 17. 同日继续：运行时空盘与包签名确认

用户回传 2026-10-14T22:15:18+08:00 的检查输出，并确认新增盘 SCSI 0:1。证据摘要已存至 [运行时盘检查](evidence/00.10.02-runtime-disk-before.txt)：系统盘 /dev/sda 有 EFI、boot 和 LVM，新增 /dev/sdb 为 100G、无分区/文件系统/UUID/挂载；包为 containerd.io-2.4.2-2.el10 与 container-selinux-2.246.0-1.el10；rpmkeys 显示 digests signatures OK。

已将版本锁的目标 RPM signature_verified 更新为 true。两个执行文件均为 container_runtime_exec_t，/var/lib/containerd 默认标签为 container_var_lib_t；SELinux Enforcing、firewalld running、服务 masked。运行时兼容性仍未验收。

## 18. 下一批待执行：/dev/sdb 的 XFS 与 UUID 挂载

仅操作已确认的新盘 /dev/sdb；重新检查空盘、目标目录和 fstab，出现既有分区、签名、挂载或数据就停止，不使用强制格式化。创建 GPT 单分区与 XFS，用 UUID 写入 fstab，按现有策略 restorecon；本批仍不解除 containerd mask。初始化不是可随意重跑的命令，失败后根据日志恢复，不删除分区重新开始。

```bash
install -d -m 0700 /root/lab-evidence/phase00
(
set -euxo pipefail
trap 'LAB_STEP_RC=$?; printf "step_exit=%s\n" "$LAB_STEP_RC"' EXIT
date -Is
dnf install -y parted xfsprogs
test "$(hostnamectl --static)" = rocky10-base
test "$(systemctl is-enabled containerd || true)" = masked
test "$(blockdev --getsize64 /dev/sdb)" -eq 107374182400
test "$(lsblk -nrpo NAME /dev/sdb | wc -l)" -eq 1
LAB_DISK_SIGNATURES=$(wipefs --no-act --noheadings --output TYPE /dev/sdb)
test -z "$LAB_DISK_SIGNATURES"
test -z "$(lsblk -nro MOUNTPOINTS /dev/sdb | tr -d '[:space:]')"
test ! -L /var/lib/containerd
mkdir -p /var/lib/containerd
if mountpoint -q /var/lib/containerd; then exit 1; fi
test -z "$(find /var/lib/containerd -mindepth 1 -maxdepth 1 -print -quit)"
test -z "$(awk '$0 !~ /^[[:space:]]*#/ && $2 == "/var/lib/containerd" {print}' /etc/fstab)"

parted -s -a optimal /dev/sdb mklabel gpt mkpart containerd xfs 1MiB 100%
partprobe /dev/sdb
udevadm settle
mkfs.xfs -L containerd /dev/sdb1

LAB_CONTAINERD_UUID=$(blkid -s UUID -o value /dev/sdb1)
test -n "$LAB_CONTAINERD_UUID"
cp -a /etc/fstab "/etc/fstab.phase00.$(date +%Y%m%d%H%M%S).bak"
printf 'UUID=%s /var/lib/containerd xfs defaults,nodev,nosuid 0 0\n' "$LAB_CONTAINERD_UUID" >> /etc/fstab
systemctl daemon-reload
mount /var/lib/containerd
test "$(findmnt -rn -M /var/lib/containerd -o UUID)" = "$LAB_CONTAINERD_UUID"
chmod 0700 /var/lib/containerd
restorecon -RFv /var/lib/containerd
findmnt --verify --verbose
findmnt -M /var/lib/containerd
xfs_info /var/lib/containerd
ls -Zd /var/lib/containerd
blkid /dev/sdb1
getenforce
firewall-cmd --state
) 2>&1 | tee -a /root/lab-evidence/phase00/00.10.02-runtime-disk-configure.txt
```

日志追加保存时间、命令、输出与括号内步骤退出码；tee 的成功不能代替 step_exit=0。预期挂载来自 /dev/sdb1、XFS 的 ftype=1、标签 container_var_lib_t；SELinux/firewalld 保持原状态。UUID 待用户实际输出后填写，不编造。下一批再添加 systemd 挂载依赖、配置 CRI 与执行启动测试；当前未格式化、未挂载、未启动服务。依据 [RHEL 10 XFS 操作说明](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/10/html/managing_file_systems/creating-an-xfs-file-system)。

## 19. 同日失败与修正：wipefs 输出列参数

用户回传执行时间 2026-10-14T22:37:43+08:00，parted-3.6-7.el10、xfsprogs-6.16.0-1.el10 已安装；主机、masked、磁盘大小与单设备检查通过。在空盘签名检查处报 `wipefs: invalid offset argument: 'TYPE': Invalid argument`，step_exit=1。原命令使用了错误的 `-o TYPE`：-o 是 offset，输出列是 -O/--output；这是本助手的命令错误，Bash 语法检查不能验证工具选项。

错误发生于 parted/mkfs/fstab/mount 之前；根据命令顺序和 set -e 的退出结果，本次没有修改分区、格式化或挂载。保留失败日志于客体 /root/lab-evidence/phase00/00.10.02-runtime-disk-configure.txt，并已归档 [本次失败输出](evidence/00.10.02-runtime-disk-failure.txt)。

已将第 18 节的命令修正为 `wipefs --no-act --noheadings --output TYPE /dev/sdb`，依据 [util-linux 官方手册](https://github.com/util-linux/util-linux/blob/master/misc-utils/wipefs.8.adoc)。原错误和回传输出在本节保留，不删除失败历史。

修正后的完整命令另存为 [磁盘初始化命令脚本](commands/00.10.02-runtime-disk-configure.sh)，由用户传至客体执行。脚本仍包含空盘、挂载和目录检查，日志采用追加保存；检测到已初始化磁盘会停止，不强制重新格式化。修正只通过本地语法检查和官方选项核对，尚未在客体成功执行。

## 20. 同日继续：运行时盘配置通过

已原样归档用户附件至 [成功执行输出](evidence/00.10.02-runtime-disk-configure.txt)。时间为 2026-10-14T22:41:41+08:00，step_exit=0；创建 /dev/sdb1，XFS ftype=1；UUID=1b36c022-c96c-4b0f-9570-d8e291ba03c0，PARTUUID=74232beb-f101-4f23-94c0-cba200c0023e。

fstab 备份为 /etc/fstab.phase00.20261014224144.bak，新增 UUID 挂载行，findmnt 验证成功且无错误/警告。/var/lib/containerd 实际来自 /dev/sdb1，选项含 nosuid/nodev/seclabel；restorecon 将初始 unlabeled_t 恢复为 container_var_lib_t。SELinux Enforcing、firewalld running。已更新母机盘台账；该盘无需再初始化，重跑初始化会被空盘检查拦截。

## 21. 下一批待执行：containerd 挂载依赖与 CRI 配置

执行入口：[00.10.02-containerd-configure.sh](commands/00.10.02-containerd-configure.sh)。只针对本批母机，在 masked、Enforcing 且指定 UUID 已挂载时执行；备份包自带配置，使用明确的 v3 最小配置，其他选项由锁定版本的默认值提供。设置 enable_selinux=true、SystemdCgroup=true、CRI 启用和独立存储路径；registry 仅配置可扩展的 certs.d 路径，保持默认 TLS 校验，不引用未部署的 Harbor，不开放 TCP 管理端点。

使用 systemd drop-in 的 RequiresMountsFor、BindsTo、After 和 AssertPathIsMountPoint 约束运行时依赖真实挂载；校验后解除 mask、启用并启动服务。不改包自带 unit，不修改 SELinux 模式或 firewalld，不部署 CNI/API。依据 [containerd v2.4.2 配置](https://github.com/containerd/containerd/blob/v2.4.2/docs/cri/config.md) 和 [systemd 挂载依赖/断言说明](https://github.com/systemd/systemd/blob/v257/man/systemd.unit.xml)。

脚本追加保存命令、时间和 step_exit；有效配置另存 00.10.02-containerd-effective.toml。检查服务 enabled/active、挂载依赖、两个 CRI 插件状态、进程/Socket 标签与服务日志；CNI 尚未安装产生的网络配置日志不代表此时应提前部署集群。服务启动与插件初始化不能代替 crictl RuntimeReady、host-network sandbox 或容器运行测试，这些留待下一批。

当前只有本地 Bash/TOML 静态检查；该脚本尚未在客体执行。若失败保留日志，不直接重跑已解除 mask 的脚本，更不降低安全模式。

## 22. 同日失败与修正：离线 unit 检查没有包含生成器

用户回传执行时间 2026-10-14T22:48:13+08:00，已归档 [失败输出](evidence/00.10.02-containerd-configure-failure.txt)。CRI TOML 检查通过，原配置备份为 /etc/containerd/config.toml.phase00.20261014224814.bak；containerd config dump 接受 v3 配置并发出自动迁移警告，该 warning 不是此次退出来源。drop-in 已写入并恢复为 container_unit_file_t，mask 已解除，daemon-reload 已执行。

在 `systemd-analyze verify /usr/lib/systemd/system/containerd.service` 处报 Unit var-lib-containerd.mount not found，step_exit=1；脚本没有执行后面的 enable --now。路径 /var/lib/containerd 的 unit 名确为 var-lib-containerd.mount，本助手最初关于连字符转义的判断不准确，已纠正。离线 verify 未启用生成器是主要待验证解释，不等同于实际 PID 1 中挂载失效。

已将完整配置脚本的校验改为 `systemd-analyze --generators=yes verify ...`。官方 systemd analyze 的 --generators 用于运行 unit generators，v257 参数实现接受可选布尔值；恢复时同时查询真实 manager 的 mount LoadState/active，不能仅跳过失败或取消 BindsTo/挂载断言。[官方说明](https://github.com/systemd/systemd/blob/v257/man/systemd-analyze.xml)

当前不重做磁盘或覆盖已经写入的配置，只从挂载验证处恢复。以下命令由用户执行并追加日志，仍保持 SELinux/firewalld 要求：

```bash
(
set -euxo pipefail
trap 'LAB_STEP_RC=$?; printf "step_exit=%s\n" "$LAB_STEP_RC"' EXIT
date -Is
test "$(getenforce)" = Enforcing
firewall-cmd --state
test "$(findmnt -rn -M /var/lib/containerd -o UUID)" = 1b36c022-c96c-4b0f-9570-d8e291ba03c0
systemctl daemon-reload
LAB_RUNTIME_MOUNT_UNIT=$(systemd-escape --path --suffix=mount /var/lib/containerd)
test "$(systemctl show --value -p LoadState "$LAB_RUNTIME_MOUNT_UNIT")" = loaded
systemctl is-active "$LAB_RUNTIME_MOUNT_UNIT"
systemd-analyze --generators=yes verify /usr/lib/systemd/system/containerd.service
systemctl enable --now containerd
systemctl is-active containerd
ctr plugins ls
ps -eZ | grep '[c]ontainerd'
getenforce
firewall-cmd --state
) 2>&1 | tee -a /root/lab-evidence/phase00/00.10.02-containerd-start.txt
```

恢复执行结果尚未取得。若 manager 中 LoadState 不是 loaded 或 mount 不是 active，应检查 fstab/generated mount 的真实状态，不启用容器运行时。若 verify/启动失败，保留错误继续定位；不重跑要求初始 masked 的原配置脚本。启动通过后再检查完整 CRI/SELinux 行为，不能仅凭配置文件验收。

## 23. 同日继续：真实挂载已加载，离线生成器仍失败

用户回传 2026-10-14T22:53:43+08:00 的结果，已存 [生成器失败证据](evidence/00.10.02-containerd-generator-failure.txt)。真实 manager 中 var-lib-containerd.mount 为 loaded/active，指定 UUID 仍正确，SELinux Enforcing、firewalld running。加 --generators=yes 后，离线检查的 systemd-ssh-generator、systemd-fstab-generator 均返回 1，并继续报告挂载 unit 缺失；step_exit=1，仍未执行 enable --now。

实际挂载与离线检查环境的结果必须区分；生成器失败的具体原因尚未确定，不能归因为 SELinux、磁盘损坏或 fstab 无效。下一步先查看 manager 实际加载的 containerd unit 和 drop-in，保留挂载保护，不关闭安全机制，也不直接宣布问题已修复。

## 24. 后续操作方式：逐条命令学习与留痕

用户明确要求像 dnf 安装一样一点点执行，说明每条命令的目的，避免复杂脚本遮蔽实际操作。后续每次给 1–3 条短命令、作用、预期结果和执行环境；根据用户输出再推进。既有脚本保留为历史复现材料，不再作为默认交互入口，不要求用户为常规步骤先 scp 大脚本。

用户回传的命令和输出由本助手继续归档，失败历史不删除；不要求每条教学命令都额外套日志管道。当前先执行只读命令：

```bash
systemctl cat containerd
```

目的：显示实际服务配置，包括 RPM 原始 unit 和本批 10-runtime-mount.conf；不启动服务或修改配置。预期看到 ExecStart 与挂载依赖/断言，用输出逐项解释后再检查加载状态和启动条件。该命令尚待用户执行。

## 25. 同日继续：服务文件与挂载保护确认

用户执行 systemctl --no-pager cat containerd，输出已转录至 [unit 配置证据](evidence/00.10.02-containerd-unit.txt)，只去除粘贴的 Markdown 标记和许可证头，保留全部实际配置项；执行时间和退出码未提供。

RPM unit 的 ExecStart=/usr/bin/containerd，ExecStartPre 加载 overlay，Type=notify、Delegate=yes、Restart=always/RestartSec=5；multi-user.target 供后续 enable 使用。drop-in 中 RequiresMountsFor、BindsTo、After、AssertPathIsMountPoint 均与 /var/lib/containerd 对应的正确挂载 unit 一致。结合第 23 节真实 mount loaded/active，下一步通过真实 manager 测试启动；不继续重复失败的离线生成器检查，其根因仍为独立待查项。

下一次只给以下三条命令，每条说明用途。第一条失败即保留错误，不继续依赖步骤。先测试启动和插件，开机 enable 待验证成功后再设置；SELinux/firewalld 不变。

```bash
systemctl start containerd
systemctl --no-pager -l status containerd
ctr plugins ls
```

预期服务 active/running，CRI images/runtime 和 gRPC cri 插件状态为 ok。未部署 CNI 时可能出现相关网络配置日志；其他可选插件的 skip 不能直接解读为 CRI 失败。上述启动和插件结果尚未取得，不计为 RuntimeReady 或容器执行验收。

## 26. 同日继续：containerd 服务运行

用户报告状态为 `active (running)`。根据回传更新母机服务状态；未提供完整 status 输出、时间、PID 或退出码，不补造这些数据。开机 enable、CRI 插件、RuntimeReady 和实际容器执行仍待验证。

下一条只读命令：`ctr plugins ls`，用于查看 containerd 已加载插件及初始化状态。重点查看 io.containerd.cri.v1 的 images/runtime，以及 io.containerd.grpc.v1 的 cri 行；其他未选用插件的 skip 不等同于 CRI 失败。

## 27. 同日继续：三个 CRI 插件初始化正常

用户确认前一步强调的 images/runtime/cri 三行均为 ok。未回传完整插件表，按用户确认记录这三项，不补造其他插件状态。母机仍待 RuntimeReady 与容器 smoke 测试；CRI 插件 ok 不代表 CNI 已就绪。

下一组设置并检查开机自启：

```bash
systemctl enable containerd
systemctl is-enabled containerd
```

enable 设置开机启动链接；is-enabled 为只读检查，预期 enabled。启动成功和自启设置是不同检查项，执行结果待用户回传。

## 28. 同日继续：自启确认与阶段进度汇报

用户确认 systemctl is-enabled containerd 输出 enabled；已更新母机启用记录。未提供该次执行时间或完整输出，不补造这些字段。设置自启成功不等于新配置已经过重启后 CRI 验证。

截至本次汇报，已有三宿主/IP/地址用途登记、Rocky ISO/运行时 RPM 来源和校验记录；一台 rocky10-base 安装、公共 Linux 基线重启验证、独立 XFS 运行时盘 UUID 挂载/标签、containerd/runc 安装、服务运行/自启和三个 CRI 插件初始化结果。SELinux Enforcing 与 firewalld 启用约束始终保留。

仍未完成：crictl RuntimeReady 与 host-network sandbox/容器运行/清理，CNI 通用物料和 kubeadm/kubelet/kubectl 的版本锁定与准备，当前 runtime 完整重启复验、最终模板封装和双克隆唯一身份检查，十台 VM 分布式部署与 Linux/CRI 全部验收、角色化防火墙/SELinux 用例和 Ansible 幂等。正式节点为 0/10；母机不是 cp01，不计作已交付节点。

完整 00 共 43 步，另包括两台 ESXi 的 Datastore/Port Group 与三宿主资源/物理盘映射复核、跨宿主及 VIP 网络、集群外 DNS/CA/管理和软件供应、OpenWrt/VPN/代理、GitLab/Harbor/Nexus/缓存/扫描、指定离线物料/七类最小构建以及独立备份恢复。上述条目未被母机工作替代。VCSA 名称调整按用户要求暂缓；AdGuard/Windows AD 未作为当前必做前置新增。

阶段状态更新为进行中，不能宣布完整 00 通过。当前按用户选择优先完成节点准备主线，下一步是安装 crictl 并做实际 CRI 自测；不在本次状态汇报中派发新的部署命令。原网络出口与离线生成器故障根因仍待独立复核，失败及恢复过程均已保存。
