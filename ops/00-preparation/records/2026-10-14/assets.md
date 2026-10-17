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

## 29. 2026-10-16 继续：恢复母机 CRI 检查

用户继续实验。已重新核对迁移后的 ops/inventory/hosts.yaml、ops/versions.lock.yaml 和本记录：最后确认 containerd running/enabled、三个 CRI 插件 ok；cri_tools 仍 pending，未记录 RuntimeReady 或实际容器自测结果。正式节点仍为 0/10。

本次客户端日期/时区为 2026-10-16、America/New_York；母机此前设置的 Asia/Shanghai 不随客户端时区调整。本节是继续工作的记录，不修改此前原始输出的时间。保持逐次 1–3 条短命令说明和回传方式，SELinux Enforcing/firewalld enabled 要求不变。

下一次由用户登录母机 root@192.168.9.9，再执行以下只读检查：

```bash
systemctl is-active containerd
command -v crictl
```

第一条预期 active；第二条输出已安装的 crictl 路径，若无输出则表示当前 PATH 未找到该命令，不能仅据此排除其他目录存在文件。先取得实际结果，再决定安装或直接配置 CRI endpoint；今天的服务状态和工具存在性尚未复验。

## 30. 2026-10-16 继续：准备 crictl 物料

用户回传 systemctl is-active containerd 为 active；command -v crictl 无输出，当前 PATH 没有找到该工具，已据实更新台账。未提供时间或退出码，不补造。下一步准备与候选 Kubernetes 1.36 系列一致的 crictl v1.36.0，先下载校验，再解包安装；不能将候选字段标为已安装。

已核对官方 v1.36.0 release 页面，并通过 HTTPS 读取对应 linux-amd64 归档的 .sha256 文件，值为 83855e114566a8a8c44c548d515670f51de3a5e1da8b2effb59870e2f10c25a3；写入版本锁作为期望值。GitHub API 查询被 403 限流，改用同一官方项目的 release 页面与直接校验文件获取，未更换第三方来源。目标机尚未下载或校验归档。

下一组仅在 Rocky root 会话下载和校验，curl 失败时先返回错误，不继续解包或安装：

```bash
cd /root/lab-artifacts
curl -fL --retry 2 --connect-timeout 10 --max-time 180 -o crictl-v1.36.0-linux-amd64.tar.gz https://github.com/kubernetes-sigs/cri-tools/releases/download/v1.36.0/crictl-v1.36.0-linux-amd64.tar.gz
echo '83855e114566a8a8c44c548d515670f51de3a5e1da8b2effb59870e2f10c25a3  crictl-v1.36.0-linux-amd64.tar.gz' | sha256sum -c -
```

预期校验输出文件名和 OK。这组命令不安装程序、不改变容器运行时服务或安全设置；取得校验结果后再给解包、恢复执行文件标签与版本验证命令。尚未取得此次下载和 SHA256 结果。

## 31. 2026-10-16 调整：crictl 改用 Kubernetes 官方签名 RPM

用户回传与第 30 节相同的两条检查：containerd 为 active，`command -v crictl` 无输出。第 30 节给出的 Rocky 端 GitHub 下载命令尚未执行，没有下载或校验结果。

本助手在 Mac 复核：GitHub v1.36.0 linux-amd64 归档的 .sha256 仍为 83855e114566a8a8c44c548d515670f51de3a5e1da8b2effb59870e2f10c25a3，与第 30 节一致；但该值与归档同源，只证明完整性。另读取 pkgs.k8s.io core:/stable:/v1.36 的 repomd.xml、repomd.xml.asc 与公钥：公钥 isv:kubernetes OBS Project，指纹 DE15B14486CD377B9E876E1A234654DA9A296436，到期 2026-12-29；Mac 上临时 GPG 目录验证 repomd 签名为 Good signature（未导入用户密钥环）。primary.xml.gz 的 SHA256 ee341fd1…0d43 与 repomd 一致，其中 cri-tools-1.36.0-150500.1.1.x86_64 的 SHA256 为 e622a370e92664907b660c7bd7af73831d3d8132be5616be8ec11581a7443970，7805276 字节，只安装 /usr/bin/crictl，无额外依赖；同仓库 kubeadm/kubelet/kubectl 最新为 1.36.5-150500.1.1，kubelet 依赖 kubernetes-cni ≥ 1.2.0（仓库为 1.9.1）。

因此改用该签名 RPM：与 containerd.io 相同的「签名 + rpmkeys --checksig + dnf 本地包」路线，后续入群工具也来自同一仓库和签名链，避免 /usr/local/bin 归档与 RPM 两套 crictl 并存。版本锁的 cri_tools artifact 已改为该 RPM，GitHub 归档不再作为安装输入。公钥到期日早于后续可能的模板重建，到期后需重新获取并核对续期公钥，不跳过签名检查。

Rocky 到 download.docker.com 曾出现 TLS reset，pkgs.k8s.io 的可达性未验证，因此沿用第 14 节的管理端种子 + scp 路线。以下命令均待用户执行，尚无输出。

Mac 终端下载并校验：

```bash
cd ~/Downloads/cloud-native-lab-seed-2026-10-14
curl -fL -o cri-tools-1.36.0-150500.1.1.x86_64.rpm https://pkgs.k8s.io/core:/stable:/v1.36/rpm/x86_64/cri-tools-1.36.0-150500.1.1.x86_64.rpm
curl -fL -o k8s-v1.36-rpm.key https://pkgs.k8s.io/core:/stable:/v1.36/rpm/repodata/repomd.xml.key
echo 'e622a370e92664907b660c7bd7af73831d3d8132be5616be8ec11581a7443970  cri-tools-1.36.0-150500.1.1.x86_64.rpm' | shasum -a 256 -c -
```

Mac 终端传输：

```bash
scp ~/Downloads/cloud-native-lab-seed-2026-10-14/cri-tools-1.36.0-150500.1.1.x86_64.rpm ~/Downloads/cloud-native-lab-seed-2026-10-14/k8s-v1.36-rpm.key root@192.168.9.9:/root/lab-artifacts/
```

Rocky 端先校验，指纹与 SHA256 均一致才继续：

```bash
cd /root/lab-artifacts
echo 'e622a370e92664907b660c7bd7af73831d3d8132be5616be8ec11581a7443970  cri-tools-1.36.0-150500.1.1.x86_64.rpm' | sha256sum -c -
gpg --show-keys --with-fingerprint k8s-v1.36-rpm.key
```

再导入公钥、检查包签名并安装：

```bash
rpmkeys --import k8s-v1.36-rpm.key
rpmkeys --checksig cri-tools-1.36.0-150500.1.1.x86_64.rpm
dnf install -y --setopt=localpkg_gpgcheck=1 ./cri-tools-1.36.0-150500.1.1.x86_64.rpm
```

最后只读确认：`crictl --version`、`rpm -q cri-tools`、`ls -Z /usr/bin/crictl`。预期版本 v1.36.0、包 1.36.0-150500.1.1.x86_64；安装 crictl 不改变 containerd、SELinux 或 firewalld。之后再写 /etc/crictl.yaml 并检查 RuntimeReady。

## 32. 2026-10-16 继续：种子目录缺失修正与 crictl 安装结果

用户在 Mac 下载公钥时报 `Failed to open the file .../cloud-native-lab-seed-2026-10-14/k8s-v1.36-rpm.key: No such file or directory` 与 `curl: (56) Failure writing output`。本助手只读核对：该种子目录已不存在，curl 不自动建目录，属于写入路径错误，不是网络或来源问题。`~/Downloads/` 下另有 cri-tools-1.36.0-150500.1.1.x86_64.rpm，7805276 字节，SHA256 e622a370…3970 与签名元数据一致。修正为 `mkdir -p` 重建目录、将该 RPM 移入并重新下载公钥。

同时发现 10-14 记录的 containerd.io RPM 与 docker.gpg 不在原种子目录，版本锁中 containerd 的 local_source 已失效；母机 /root/lab-artifacts/ 应仍有副本，Mac 侧备份位置待用户确认，本次不改写该字段。

用户随后回传安装结果，已归档 [crictl 安装证据](evidence/00.10.02-crictl-install.txt)：crictl v1.36.0，RPM cri-tools-1.36.0-150500.1.1.x86_64，/usr/bin/crictl 标签 bin_t。版本锁 cri_tools 更新为 version 1.36.0、installed_unvalidated，台账同步。客体端 sha256sum、公钥指纹、rpmkeys --checksig 与 dnf 事务输出未回传，signature_verified 保持 false，不补造。

下一组由用户在母机执行，写入 crictl 端点配置并只读检查 CRI 状态与 sandbox 引用：

```bash
cat > /etc/crictl.yaml <<'CRICTL'
runtime-endpoint: unix:///run/containerd/containerd.sock
image-endpoint: unix:///run/containerd/containerd.sock
timeout: 20
debug: false
CRICTL
```

```bash
crictl info | jq '.status.conditions'
containerd config dump | grep -A2 'pinned_images'
```

预期 RuntimeReady 为 true；NetworkReady 为 false 且原因指向 CNI 未初始化，这是 00 未装 CNI 的阶段边界，不代表故障。第二条显示实际 sandbox 引用，用于第 10.1 节种子导入，不预设 pause tag。尚无输出。

## 33. 2026-10-16 继续：RuntimeReady 通过与镜像来源调整

用户写入 /etc/crictl.yaml 后回传 CRI 状态，已归档 [CRI 状态证据](evidence/00.10.02-cri-runtime-status.txt)：RuntimeReady=true；NetworkReady=false、原因 NetworkPluginNotReady（cni plugin not initialized），属于 00 未安装 CNI 的阶段边界；ContainerdHasNoDeprecationWarnings=true。实际 sandbox 引用为 registry.k8s.io/pause:3.10.2。config dump 仍提示 v3 配置被自动迁移，与第 22 节相同；不是弃用告警，封装模板前再决定是否用 `containerd config migrate` 生成新格式配置，本次不改动。

本助手从 Mac 只读查询官方仓库：pause:3.10.2 的 index Digest 为 sha256:f548e0e8e3dc1896ca956272154dde3314e8cc4fde0a57577ee9fa1c63f5baf4（linux/amd64 manifest sha256:412c4a72…0f17）；选定测试镜像 registry.k8s.io/e2e-test-images/busybox:1.38.0-1，index Digest 为 sha256:302d6221f7d600725e0f926f9f04f8fbbb2a32678b4e991da760a5062d4dc7e1（amd64 manifest sha256:7d31f97b…340f）。二者已从 pending_by_phase 提升为版本锁 components 记录，状态 pending。

Mac 上 Docker Desktop 未运行；用户说明 Mac 性能不适合运行 Docker。因此改用手册 10.1 的「目标机直连官方仓库」变体：母机直接 `crictl pull` 两个镜像并核对 Digest。该变体依赖公网出口，不替代 10.2 内网仓库验收，也不构成十节点离线物料；若母机访问 registry.k8s.io 失败，再改用不需要虚拟机的管理端工具导出归档。

下一组由用户在母机执行，尚无输出：

```bash
crictl pull registry.k8s.io/pause:3.10.2
crictl pull registry.k8s.io/e2e-test-images/busybox:1.38.0-1
crictl images --digests
```

预期两次 pull 均返回 `Image is up to date for sha256:…`；images 列表中 pause 的 DIGEST 以 f548e0e8e3dc1 开头，busybox 以 302d6221f7d60 开头。任何一条失败时保留完整错误，不更换镜像源、不跳过 TLS。

## 34. 2026-10-16 失败与调整：母机直连官方镜像仓库超时

用户执行第 33 节的拉取，两次 crictl pull 均失败，已归档 [拉取超时证据](evidence/00.10.02-crictl-pull-timeout.txt)。registry.k8s.io 把 manifest 请求重定向到 Google Artifact Registry `europe-west3-docker.pkg.dev`，解析到 74.125.204.82，TCP 443 连接 i/o timeout，CRI 返回 DeadlineExceeded；`crictl images` 为空，没有写入任何镜像。DNS 解析成功，失败发生在建立 TCP 连接阶段。

本助手只读确认 Mac 系统 HTTPS 代理为 127.0.0.1:7897，shell 也设置了 HTTPS_PROXY/HTTP_PROXY；Mac 访问同一仓库成功不能说明母机直连路径可用。与第 14 节 download.docker.com 的连接重置一起看，最可能的解释是母机的直连出口无法到达部分境外站点；具体是哪个设备或哪条策略在丢包，仍未证实。这正是计划中节点应从内网 Harbor 取镜像、由受控显式代理（00.06.02）负责外部同步的原因；本次不为 containerd 配置代理，也不改用未核实的镜像站。

调整为手册 10.1 的种子导入路线，管理端工具改用 Homebrew 提供的 crane（单个 Go 程序，不启动虚拟机），以满足用户「Mac 不运行 Docker」的要求。crane 默认 tarball 格式与 docker save 兼容，RepoTags 保留完整镜像名，`ctr -n k8s.io images import` 后名称应能匹配 sandbox 引用。导入后 containerd 会根据 tarball 重新生成 manifest，所以 DIGEST 列不一定等于仓库 Digest；用 IMAGE ID（即 config digest）核对。已从仓库补查并自校验 amd64 manifest：pause config sha256:4a83b15d3ecfe0d916b2d0a7991bc2854a629b8097017c2ee1ff65b30ae4c07c，busybox config sha256:45a1d298552b4ed95d21af416e729f4340ef42a54050de7e0aebb37c1bee9606，已写入版本锁。

以下命令待用户执行，尚无输出。Mac：

```bash
brew install crane
crane version
crane pull --platform linux/amd64 registry.k8s.io/pause:3.10.2 ~/Downloads/cloud-native-lab-seed-2026-10-14/pause-3.10.2-amd64.tar
crane pull --platform linux/amd64 registry.k8s.io/e2e-test-images/busybox:1.38.0-1 ~/Downloads/cloud-native-lab-seed-2026-10-14/busybox-1.38.0-1-amd64.tar
shasum -a 256 ~/Downloads/cloud-native-lab-seed-2026-10-14/pause-3.10.2-amd64.tar ~/Downloads/cloud-native-lab-seed-2026-10-14/busybox-1.38.0-1-amd64.tar
scp ~/Downloads/cloud-native-lab-seed-2026-10-14/pause-3.10.2-amd64.tar ~/Downloads/cloud-native-lab-seed-2026-10-14/busybox-1.38.0-1-amd64.tar root@192.168.9.9:/root/lab-artifacts/
```

母机：

```bash
cd /root/lab-artifacts
sha256sum pause-3.10.2-amd64.tar busybox-1.38.0-1-amd64.tar
ctr -n k8s.io images import --platform linux/amd64 pause-3.10.2-amd64.tar
ctr -n k8s.io images import --platform linux/amd64 busybox-1.38.0-1-amd64.tar
crictl images
```

预期两端 tar 的 SHA256 相同；crictl images 中 registry.k8s.io/pause:3.10.2 的 IMAGE ID 以 4a83b15d3ecfe 开头，busybox 以 45a1d298552b4 开头。crane 版本取得后再锁定 image_export_tool。

## 35. 2026-10-16 继续：种子镜像导入通过，准备 host-network CRI 自测

用户回传 `crictl images`：registry.k8s.io/pause:3.10.2 的 IMAGE ID 为 4a83b15d3ecfe，registry.k8s.io/e2e-test-images/busybox:1.38.0-1 为 45a1d298552b4，与第 34 节锁定的 config digest 前缀一致，说明两镜像已在 k8s.io 命名空间对 CRI 可见。客体端 tar 的 sha256sum 与 ctr import 输出未回传，不补造；内容身份由 config digest 一致证明。

本助手在 Mac 只读补查：crane 0.22.1（Homebrew）；pause tar SHA256 a7061466…9db6（321024 字节），busybox tar SHA256 2f116433…70a0（2215936 字节）；两份 manifest.json 的 Config 与 RepoTags 分别等于锁定 config digest 与完整镜像名。已归档 [镜像导入证据](evidence/00.10.02-cri-image-import.txt)；版本锁中 pause、cri_smoke_image 更新为 installed_unvalidated 并登记本地归档，crane 提升为 image_export_tool 组件；台账母机状态更新为 runtime_ready_images_imported_cri_smoke_pending。

下一步按手册 10.3 执行 host-network 自测。以下命令待用户在母机同一 SSH 会话执行，尚无输出。先准备工作目录与两份 JSON：

```bash
install -d -m 0700 /root/lab-cri-smoke
install -d -m 0755 /var/log/phase00-cri
cd /root/lab-cri-smoke
cat > sandbox.json <<'JSON'
{
  "metadata": {"name": "phase00-cri-smoke", "namespace": "phase00", "uid": "phase00-cri-smoke", "attempt": 1},
  "log_directory": "/var/log/phase00-cri",
  "linux": {"security_context": {"namespace_options": {"network": 2}}}
}
JSON
cat > container.json <<'JSON'
{
  "metadata": {"name": "smoke", "attempt": 1},
  "image": {"image": "registry.k8s.io/e2e-test-images/busybox:1.38.0-1"},
  "command": ["/bin/sh", "-c", "echo phase00-cri-ok"],
  "log_path": "smoke.log",
  "linux": {}
}
JSON
jq . sandbox.json container.json >/dev/null && echo json-ok
```

创建 sandbox 并检查网络模式与 SELinux 进程标签：

```bash
SANDBOX_ID=$(crictl runp sandbox.json); echo "SANDBOX_ID=$SANDBOX_ID"
crictl pods
crictl inspectp "$SANDBOX_ID" | jq '.status.linux.namespaces.options'
ps -eZ | grep '[p]ause'
```

创建并运行容器，检查日志、退出码与 AVC：

```bash
CONTAINER_ID=$(crictl create "$SANDBOX_ID" container.json sandbox.json); echo "CONTAINER_ID=$CONTAINER_ID"
crictl start "$CONTAINER_ID"
crictl ps -a
crictl logs "$CONTAINER_ID"
crictl inspect "$CONTAINER_ID" | jq '.status | {state, exitCode, reason}'
ausearch -m AVC -ts recent
```

预期：sandbox Ready，network 为 NODE；pause 进程标签含 container_t 与 MCS 类别；容器 Exited，日志 phase00-cri-ok，state CONTAINER_EXITED、exitCode 0；ausearch 为 `<no matches>`。清理（rm/stopp/rmp）在取得输出后进行，失败时先保留对象和证据，不清空 runtime 数据目录。

## 36. 2026-10-16 失败与修正：sandbox 配置缺少 systemd cgroup_parent

用户执行第 35 节第二组命令，`crictl runp` 失败，已归档 [runp 失败证据](evidence/00.10.02-cri-smoke-runp-failure.txt)。crictl 先警告 `cgroup_parent is not set`，随后 runc 报 `expected cgroupsPath to be of format "slice:prefix:name" for systemd cgroups, got "/k8s.io/<id>"`。后续 inspectp 的 `prefix can't be empty` 是 SANDBOX_ID 为空导致的连带错误；`crictl pods` 为空，没有遗留 sandbox。

原因是本助手给出的 sandbox.json 缺少 `linux.cgroup_parent`。containerd 按配置以 SystemdCgroup=true 调用 runc，runc 要求 systemd 形式的 cgroup 路径；kubelet 总会提供 `.slice` 父级，手写测试配置没有，containerd 退回 cgroupfs 形式路径而被拒绝。这是测试输入错误，不是运行时缺陷；该拒绝反而证明 systemd cgroup 驱动已按配置生效。手册 10.3 的同一模板已补 `"cgroup_parent": "phase00.slice"` 及说明。

用户表示希望直接进入下一步。本助手说明：host-network CRI smoke 是计划 00 的验收用例（十台节点通过 node-readiness 与 host-network CRI smoke），「组件已安装」与「功能已通过」是不同状态；修正只需改一个字段，且应在克隆前确认，否则任何缺陷会被复制到十台节点，并推迟到 01 的 kubeadm init 才暴露。是否继续由用户决定；若跳过，本项记为未执行而非通过。

修正后的重试命令（attempt 改为 2，避免与失败尝试的名称混淆），待用户执行：

```bash
cd /root/lab-cri-smoke
cat > sandbox.json <<'JSON'
{
  "metadata": {"name": "phase00-cri-smoke", "namespace": "phase00", "uid": "phase00-cri-smoke", "attempt": 2},
  "log_directory": "/var/log/phase00-cri",
  "linux": {
    "cgroup_parent": "phase00.slice",
    "security_context": {"namespace_options": {"network": 2}}
  }
}
JSON
jq . sandbox.json >/dev/null && echo json-ok
```

随后重新执行第 35 节的第二组、第三组命令，预期不变。

## 37. 2026-10-16 通过：母机 host-network CRI 自测（重启前）

用户按第 36 节重写 sandbox.json（attempt 2，cgroup_parent phase00.slice）并重跑第 35 节第二、三组命令，全部成功，完整输出已归档 [CRI 自测通过证据](evidence/00.10.02-cri-smoke-pass.txt)：sandbox c928451e94377 Ready，命名空间 network=NODE、ipc/pid=POD；pause 进程为 `system_u:system_r:container_t:s0:c961,c999`，说明 Enforcing 下被限制在 container_t 并分配了独立 MCS 类别；容器 8159cd15fb42a 输出 phase00-cri-ok，状态 CONTAINER_EXITED、exitCode 0、reason Completed；`ausearch -m AVC -ts recent` 为 `<no matches>`。

`crictl ps -a` 中的 Running 是启动后立即取的快照，随后 inspect 已为 EXITED；POD/NAMESPACE 显示 unknown 是因为手写 container.json 未带 kubelet 才会添加的 io.kubernetes.pod.* 标签，不是失败。版本锁中 containerd、runc、cri_tools、pause、cri_smoke_image 追加该执行证据，状态仍为 installed_unvalidated，待重启复验；台账母机状态更新为 cri_smoke_passed_reboot_revalidation_pending。

本次通过只证明母机重启前的运行时链路。尚未证明：重启后的挂载依赖、服务自启与镜像持久性；10.2 仓库拉取路径（需 Harbor）；CNI 与普通 Pod 网络（01）。

下一组由用户在同一 SSH 会话执行。先只清理本次两个对象，保留镜像：

```bash
crictl rm "$CONTAINER_ID"
crictl stopp "$SANDBOX_ID"
crictl rmp "$SANDBOX_ID"
crictl ps -a
crictl pods
```

预期 rm/stopp/rmp 各回显对应 ID，ps -a 与 pods 只剩表头。若 SSH 已断开，用 `crictl pods --name phase00-cri-smoke -q` 与 `crictl ps -a --name smoke -q` 找回 ID。临时 phase00.slice 在重启后消失。

随后执行 `reboot`。这是 containerd 配置挂载依赖后的第一次真实开机，重新登录后只读检查：

```bash
systemctl is-enabled containerd; systemctl is-active containerd
findmnt -M /var/lib/containerd -o SOURCE,UUID,FSTYPE
crictl info | jq -c '.status.conditions[] | {type, status}'
crictl images
getenforce; firewall-cmd --state; swapon --show
```

预期 containerd enabled/active；挂载来源 /dev/sdb1、UUID 1b36c022-c96c-4b0f-9570-d8e291ba03c0、xfs；RuntimeReady=true、NetworkReady=false；两镜像仍在且 IMAGE ID 不变；Enforcing、running，Swap 无输出。之后再以 attempt 3 重跑一次自测，证明重启后仍可运行容器。

## 38. 2026-10-16 通过：运行时配置后的首次重启复验

用户报告已完成第 37 节的清理、重启与检查，已归档 [重启复验证据](evidence/00.10.02-reboot-revalidation.txt)：containerd enabled/active；/var/lib/containerd 来自 /dev/sdb1，UUID 1b36c022-c96c-4b0f-9570-d8e291ba03c0，xfs；RuntimeReady=true、NetworkReady=false、ContainerdHasNoDeprecationWarnings=true；两镜像仍在且 IMAGE ID 不变；SELinux Enforcing、firewalld running、Swap 无输出。这是配置挂载依赖 drop-in 后的第一次真实开机，说明依赖在开机流程中成立、镜像确实持久化在运行时盘。

清理命令输出与明确的开机时间未回传，不补造；下一组先补查。台账母机状态更新为 reboot_revalidated_post_reboot_smoke_pending。

下一组待用户执行。先确认已重启、没有遗留对象，并把 attempt 改为 3：

```bash
uptime -s
crictl pods; crictl ps -a
cd /root/lab-cri-smoke && sed -i 's/"attempt": 2/"attempt": 3/' sandbox.json && grep -o '"attempt": [0-9]' sandbox.json
```

重启后再跑一次自测：

```bash
SANDBOX_ID=$(crictl runp sandbox.json); echo "SANDBOX_ID=$SANDBOX_ID"
ps -eZ | grep '[p]ause'
CONTAINER_ID=$(crictl create "$SANDBOX_ID" container.json sandbox.json); echo "CONTAINER_ID=$CONTAINER_ID"
crictl start "$CONTAINER_ID"; sleep 2
crictl logs "$CONTAINER_ID"
crictl inspect "$CONTAINER_ID" | jq '.status | {state, exitCode, reason}'
ausearch -m AVC -ts recent
```

结果符合预期再清理：

```bash
crictl rm "$CONTAINER_ID"; crictl stopp "$SANDBOX_ID"; crictl rmp "$SANDBOX_ID"
crictl ps -a; crictl pods
```

预期 uptime -s 为本次重启时间，pods/ps 只有表头，attempt 为 3；自测结果与第 37 节相同（MCS 类别会不同）；清理后只剩表头。之后进入 kubeadm/kubelet/kubectl 的锁定与安装。

## 39. 2026-10-16 通过：重启后 CRI 自测；准备入群工具

用户回传第 38 节全部输出，已归档 [重启后自测证据](evidence/00.10.02-cri-smoke-post-reboot.txt)：开机时间 2026-10-16 19:49:21，晚于 19:42 的 runp 失败与重启前通过；重启前清理无遗留。attempt 3 自测再次通过，pause 为 container_t:s0:c692,c750（与上次 c961,c999 不同，每个 Pod 获得新 MCS 类别），日志 phase00-cri-ok、exitCode 0，无 AVC；清理后 pods/ps 只剩表头。

母机运行时部分至此完成：版本锁中 containerd、runc、cri_tools、pause、cri_smoke_image 更新为 validated_on_template_host（只代表母机；十节点矩阵与 10.2 仓库拉取仍待验）；台账母机状态为 runtime_validated_kube_tools_pending。/root/lab-cri-smoke 与 /var/log/phase00-cri 暂留作复测输入，封装模板前清理。

下一步按手册第 8 节第 4 项安装入群工具，00 不执行 init/join。本助手复核 pkgs.k8s.io v1.36 repomd 与先前一致且签名有效，锁定 kubeadm/kubelet/kubectl 1.36.5-150500.1.1；kubelet 依赖 kubernetes-cni ≥ 1.2.0 与 util-linux，同仓库 kubernetes-cni 1.9.1-150500.1.1 一并锁定为 cni_plugins，并从 01 待锁定列表提升到 00。kubernetes-cni 只安装 /opt/cni/bin 插件与空的 /etc/cni/net.d，不写网络配置，NetworkReady 应继续为 false。四个包的 SHA256 与大小已写入版本锁；公钥沿用安装 cri-tools 时导入的同一把（DE15…6436）。以下命令待用户执行，尚无输出。

Mac：

```bash
cd ~/Downloads/cloud-native-lab-seed-2026-10-14 && for p in kubeadm-1.36.5-150500.1.1 kubelet-1.36.5-150500.1.1 kubectl-1.36.5-150500.1.1 kubernetes-cni-1.9.1-150500.1.1; do curl -fL -o "$p.x86_64.rpm" "https://pkgs.k8s.io/core:/stable:/v1.36/rpm/x86_64/$p.x86_64.rpm" || break; done
cat > ~/Downloads/cloud-native-lab-seed-2026-10-14/k8s-1.36.5-rpms.sha256 <<'SUMS'
0f857b25db48cb01e5c69dc1d02a1fc02c125a0d04a5cd58440a4e9adb631f5a  kubeadm-1.36.5-150500.1.1.x86_64.rpm
15b55de802c19f1c5b89c065086ad8feec3430fd58da836300f51688ecbbb63b  kubelet-1.36.5-150500.1.1.x86_64.rpm
9e406829bad036e45e08f6c49176f479c06d239cf64a96befa56f8b1b55a37fc  kubectl-1.36.5-150500.1.1.x86_64.rpm
a228e611f547cf3554873c383078a7ff9abf289e5b7ae315cd38c3811804e2f7  kubernetes-cni-1.9.1-150500.1.1.x86_64.rpm
SUMS
cd ~/Downloads/cloud-native-lab-seed-2026-10-14 && shasum -a 256 -c k8s-1.36.5-rpms.sha256
cd ~/Downloads/cloud-native-lab-seed-2026-10-14 && scp kubeadm-1.36.5-150500.1.1.x86_64.rpm kubelet-1.36.5-150500.1.1.x86_64.rpm kubectl-1.36.5-150500.1.1.x86_64.rpm kubernetes-cni-1.9.1-150500.1.1.x86_64.rpm k8s-1.36.5-rpms.sha256 root@192.168.9.9:/root/lab-artifacts/
```

母机先校验：

```bash
cd /root/lab-artifacts
sha256sum -c k8s-1.36.5-rpms.sha256
rpmkeys --checksig kubeadm-1.36.5-150500.1.1.x86_64.rpm kubelet-1.36.5-150500.1.1.x86_64.rpm kubectl-1.36.5-150500.1.1.x86_64.rpm kubernetes-cni-1.9.1-150500.1.1.x86_64.rpm
```

全部 OK 再安装并只读检查：

```bash
dnf install -y --setopt=localpkg_gpgcheck=1 ./kubeadm-1.36.5-150500.1.1.x86_64.rpm ./kubelet-1.36.5-150500.1.1.x86_64.rpm ./kubectl-1.36.5-150500.1.1.x86_64.rpm ./kubernetes-cni-1.9.1-150500.1.1.x86_64.rpm
kubeadm version -o short; kubelet --version; kubectl version --client
rpm -q kubeadm kubelet kubectl kubernetes-cni
systemctl is-enabled kubelet; ls /etc/cni/net.d; ls /opt/cni/bin | head -5
kubeadm config images list --kubernetes-version v1.36.5
```

预期四份 OK 与 digests signatures OK；三者 v1.36.5；kubelet 保持 disabled，00 不启动（未经 kubeadm 生成配置时会反复重启），01 引导时再 enable；/etc/cni/net.d 为空；最后一条列出 01 需要预置的控制面镜像，并用于核对 kubeadm 期望的 pause 版本是否与 containerd 的 3.10.2 一致。

## 40. 2026-10-16 继续：入群工具安装通过；封装与克隆方式决定

用户回传入群工具安装结果，已归档 [入群工具安装证据](evidence/00.10.02-kube-tools-install.txt)：dnf `Complete!`；kubeadm/kubelet/kubectl 均为 v1.36.5（RPM 1.36.5-150500.1.1），kubernetes-cni 1.9.1-150500.1.1；kubelet disabled；/etc/cni/net.d 为空，/opt/cni/bin 有 bandwidth/bridge/dhcp/dummy/firewall 等插件。`kubeadm config images list --kubernetes-version v1.36.5` 列出 kube-apiserver/controller-manager/scheduler/proxy v1.36.5、coredns v1.14.2、pause 3.10.2、etcd 3.6.8-0；kubeadm 期望的 pause 与 containerd 的 sandbox 引用一致，init 时不应出现 sandbox 版本不一致告警。第 39 节第 3 步的 sha256sum/checksig 输出未回传；安装使用 localpkg_gpgcheck=1 只能间接说明签名检查通过，signature_verified 暂不提升，下一组用已安装包的签名信息补证。版本锁四个组件更新为 installed_unvalidated，kubeadm 记录 v1.36.5 所需镜像列表；台账母机状态为 kube_tools_installed_seal_pending。

用户就封装与克隆作出三项选择：

| 事项 | 选择 | 影响 |
| --- | --- | --- |
| 克隆方式 | vCenter 克隆 | 选项表述为三台 ESXi 已纳管、vSphere Client 可登录；本助手未核实。vCenter 克隆会生成新的 BIOS UUID 与 MAC。不依赖 Linux guest customization，节点身份在客体内处理。 |
| 首次开机网络 | 封装时 ens33 改 DHCP | 克隆机可同时开机，从路由器 DHCP（登记为 .30–.49）取得临时地址，再改为 .101–.110 静态地址。若有线网段无 DHCP，退回 ESXi 控制台逐台配置。 |
| 控制面镜像 | 以后通过 Harbor | 模板只保留 pause 与 cri_smoke_image。00.09 的 Harbor 及其 DNS/CA 前置须在 01 kubeadm init 前完成，否则十节点无法取得控制面镜像（母机已证实不能直连 registry.k8s.io）。 |

封装会删除母机身份并不可逆，因此拆成两批：本批只做只读检查、种子物料回传 Mac 与 vCenter 快照；确认后下一批再执行封装和关机。以下待用户执行，尚无输出。

母机只读检查：

```bash
rpm -qi containerd.io cri-tools kubeadm kubelet kubectl kubernetes-cni | grep -E '^(Name|Signature)'
nmcli -g connection.uuid,connection.interface-name,802-3-ethernet.mac-address,ipv4.method,ipv4.addresses connection show ens33
ls -l /etc/machine-id /var/lib/dbus/machine-id; systemctl list-unit-files 'sshd-keygen@.service'
ls /root/lab-artifacts /root/lab-evidence/phase00
```

Mac 回传种子物料与客体原始日志（第 32 节发现 containerd RPM 与 docker.gpg 不在 Mac 种子目录）：

```bash
scp root@192.168.9.9:/root/lab-artifacts/containerd.io-2.4.2-2.el10.x86_64.rpm root@192.168.9.9:/root/lab-artifacts/docker.gpg ~/Downloads/cloud-native-lab-seed-2026-10-14/
scp -r root@192.168.9.9:/root/lab-evidence ~/Downloads/cloud-native-lab-seed-2026-10-14/guest-lab-evidence-rocky10-base
cd ~/Downloads/cloud-native-lab-seed-2026-10-14 && echo '323346eb71f8886bce5c382978cf0b3934c14c08e20e10837b395c19b9ebd11e  containerd.io-2.4.2-2.el10.x86_64.rpm' | shasum -a 256 -c -
gpg --show-keys --with-fingerprint ~/Downloads/cloud-native-lab-seed-2026-10-14/docker.gpg
```

vSphere Client：对运行中的 rocky10-base 拍快照 `pre-seal-2026-10-16`，不勾选内存，作为封装前回退点。

预期：containerd.io 的 Key ID 为 c52feb6b621e9f35，五个 Kubernetes 包为 234654da9a296436；ens33 的 mac-address 若非空，封装时须清空，否则新 MAC 的克隆机不会激活该连接；machine-id 与 dbus 的关系及 sshd-keygen 模板单元用于确定封装命令；Mac 端 RPM 校验 OK，docker.gpg 指纹 060A 61C5 1B55 8A7F 742B 77AA C52F EB6B 621E 9F35。

## 41. 2026-10-16 继续：封装前检查结果与封装步骤

用户回传第 40 节全部输出并确认已拍快照，已归档 [封装前检查证据](evidence/00.10.02-pre-seal-checks.txt)。ens33 连接只按接口名绑定、mac-address 为空，克隆机新 MAC 不影响该连接；/var/lib/dbus/machine-id 不存在，只需处理 /etc/machine-id；sshd-keygen@.service 为 disabled/disabled，通常经 sshd-keygen.target 拉起，删除主机密钥前先核对依赖。Mac 已取回 containerd.io RPM（shasum OK）与 docker.gpg（指纹 060A…9F35），客体 5 份原始日志存于种子目录 guest-lab-evidence-rocky10-base；版本锁 containerd 的 local_source 恢复有效，其余 RPM 登记 Mac 种子路径。快照由用户报告完成，未提供任务结果。

`rpm -qi` 的 Signature 对六个包均为空。containerd.io 文件此前 checksig 为 digests signatures OK，因此不将该显示解读为未签名，原因未确定；改为在删除物料前用 `rpmkeys --checksig -v` 对文件取证。

封装分三组，前一组全部符合预期才执行下一组；任何异常即停止，可回退到快照 pre-seal-2026-10-16。以下待用户执行，尚无输出。

第一组，只读取证与依赖核对：

```bash
cd /root/lab-artifacts
sha256sum -c k8s-1.36.5-rpms.sha256
echo 'e622a370e92664907b660c7bd7af73831d3d8132be5616be8ec11581a7443970  cri-tools-1.36.0-150500.1.1.x86_64.rpm' | sha256sum -c -
rpmkeys --checksig -v containerd.io-2.4.2-2.el10.x86_64.rpm cri-tools-1.36.0-150500.1.1.x86_64.rpm kubeadm-1.36.5-150500.1.1.x86_64.rpm kubelet-1.36.5-150500.1.1.x86_64.rpm kubectl-1.36.5-150500.1.1.x86_64.rpm kubernetes-cni-1.9.1-150500.1.1.x86_64.rpm
rpm -q gpg-pubkey --qf '%{NAME}-%{VERSION}-%{RELEASE}\t%{SUMMARY}\n'
systemctl show -p Wants sshd-keygen.target; systemctl show -p Wants sshd.service | tr ' ' '\n' | grep -i keygen
```

第二组，清理实验文件并把 ens33 改为 DHCP（只改配置文件，不重新激活，当前 SSH 不断开）：

```bash
cd /root
rm -rf /root/lab-cri-smoke /var/log/phase00-cri /root/lab-artifacts /root/lab-evidence
nmcli connection modify ens33 ipv4.method auto ipv4.addresses "" ipv4.gateway "" ipv4.dns ""
nmcli -g ipv4.method,ipv4.addresses,ipv4.gateway,ipv4.dns connection show ens33
ip -br address show ens33
```

第三组，清除身份并关机；删除主机密钥后不再新开 SSH 会话：

```bash
truncate -s 0 /etc/machine-id
rm -f /var/lib/systemd/random-seed /var/lib/NetworkManager/secret_key /var/lib/NetworkManager/*.lease
journalctl --rotate && journalctl --vacuum-time=1s
dnf clean all
rm -f /etc/ssh/ssh_host_*
unset HISTFILE; rm -f /root/.bash_history
ls -l /etc/machine-id; ls /etc/ssh/ssh_host_* 2>&1
```

确认 machine-id 为 0 字节、主机密钥不存在后执行 `poweroff`（不是 reboot；母机再开机会生成新身份而失去封装状态）。关机后在 vSphere 对 rocky10-base 拍快照 `sealed-2026-10-16`，此后不再开启母机，克隆以它为源。

预期：第一组 sha256 全 OK；checksig -v 中 containerd.io 显示 key ID 621e9f35、其余五个 key ID 9a296436，均 OK；gpg-pubkey 含 621e9f35 与 9a296436 两把；sshd-keygen.target 的 Wants 含 sshd-keygen@ 实例，sshd.service 依赖 sshd-keygen.target。第二组 method 为 auto，地址/网关/DNS 为空，`ip` 仍显示当前 192.168.9.9/24。首次开机时 machine-id 为空会被 systemd 视为 first boot，可能按 preset 启用默认启用的单元（如 kdump），克隆验收时检查 `systemctl --failed` 与相关单元状态。

## 42. 2026-10-16 继续：身份清除完成（第三组）

用户回传第 41 节第三组输出并认为命令执行出错。已归档 [身份清除证据](evidence/00.04.03-seal-identity.txt)：machine-id 为 0 字节，`ls /etc/ssh/ssh_host_*` 报 No such file or directory，正是主机密钥已删除的预期确认；journald 删除 1.3M 归档日志，dnf 清理 18 个文件。第三组按设计完成，没有执行错误。

日志位于 /run/log/journal，说明母机 journal 为易失存储，重启后不保留。封装期间不改动，记为 node_base 待办：按手册第 6 节以容量预算设置持久化和上限。

第一、二组的输出未回传，不能确认 checksig 取证、sshd-keygen 依赖、DHCP 切换与实验文件清理是否已执行。主机密钥已删除，当前 SSH 会话不得断开；若已断开，只能经 vSphere 网页控制台以 root 登录处理，或回退到 pre-seal-2026-10-16。下一组在同一会话只读确认：

```bash
nmcli -g ipv4.method,ipv4.addresses connection show ens33
ls -d /root/lab-cri-smoke /var/log/phase00-cri /root/lab-artifacts /root/lab-evidence 2>&1
systemctl show -p Wants sshd-keygen.target
```

预期第一条为 auto 与空行；第二条四个路径都 No such file or directory；第三条含 sshd-keygen@ 实例。若第一组未执行而物料仍在，先补第一组再补第二组；若物料已删，签名文件取证缺口如实保留。全部符合后 `poweroff`，并在 vSphere 拍快照 sealed-2026-10-16。尚无输出。

## 43. 2026-10-16 封装完成；准备双克隆唯一性验证

用户回传第 42 节检查：ens33 为 auto 且无静态地址；四个实验目录均不存在；sshd-keygen.target Wants 含 ecdsa/ed25519/rsa 三个实例。用户报告已 poweroff 并拍快照 sealed-2026-10-16。证据追加至 [身份清除证据](evidence/00.04.03-seal-identity.txt)。母机状态更新为 sealed_powered_off，clone_status 为 seal_test_pending。第 41 节第一组输出从未回传，物料已从客体删除，cri-tools 与四个 Kubernetes RPM 的文件签名取证仍为缺口，如实保留。

按 00.04.03 与手册第 3 节第 5 项，正式克隆十台前先做两个临时克隆，对比 machine-id、BIOS UUID、MAC、SSH 主机密钥与 DHCP 地址。两台分放 esxi01 与 esxi02，同时验证 esxi02 的 Datastore/端口组、Rocky 10 对 x86-64-v3 的 CPU 暴露（R730xd 为 E5-2686 v4）以及跨宿主机二层互通（00.04.01 的一部分）。临时克隆验证后删除，不计入十节点。

vSphere Client 操作，待用户执行：右键已关机的 rocky10-base → 克隆到虚拟机；名称 seal-test-01，计算资源 esxi01，存储 esxi01-sas10t5，磁盘格式与源相同；不勾选「自定义操作系统」，不改硬件；完成后开机。seal-test-02 同样操作，计算资源选 esxi02，存储选 esxi02 本地 Datastore，网络选与 VM Network 相同用途的端口组，并记下实际 Datastore 与端口组名称。若 seal-test-02 启动时报 CPU ISA level 低于要求，说明集群 EVC 屏蔽了 x86-64-v3 指令，停下处理，不改用其他系统。

两台开机后，从 VM 摘要读取 VMware Tools 报告的 IP，由 Mac 分别 SSH 登录（首次连接确认新主机密钥；若该 IP 曾被其他设备使用并报主机标识变化，先 `ssh-keygen -R <IP>`）。每台执行只读检查：

```bash
hostnamectl --static; cat /etc/machine-id; cat /sys/class/dmi/id/product_uuid
ip -br link show ens33; ip -br -4 address show ens33; ip route show default; cat /etc/resolv.conf
for f in /etc/ssh/ssh_host_*_key.pub; do ssh-keygen -lf "$f"; done
systemctl --failed --no-legend; systemctl is-enabled kdump kubelet 2>&1
getenforce; firewall-cmd --state; findmnt -M /var/lib/containerd -o SOURCE,UUID
systemctl is-active containerd; crictl info | jq -c '.status.conditions[] | {type, status}'; crictl images
chronyc tracking | grep -E 'Reference ID|Leap status'
```

两台都检查后，在 seal-test-01 上 `ping -c 3 <seal-test-02 的 IP>`。预期：两台 machine-id、product_uuid、MAC、IP、三种主机密钥指纹均不同；地址来自 DHCP、有默认路由和 DNS；无失败单元或只有可解释项；kubelet disabled，kdump 状态记录实际值；Enforcing、running；运行时盘、containerd、RuntimeReady 与两个镜像均与母机一致；chrony 同步；跨宿主机 ping 通。尚无输出。

## 44. 2026-10-16 问题：seal-test-02 无网络与 esxi02 的 IO 筛选器告警

用户报告 seal-test-01（esxi01）已正常；seal-test-02（esxi02）提示「没有为该虚拟机分配网络」，同时 vCenter 对 esxi02 报「在主机上注册/取消注册第三方 IO 筛选器存储提供程序失败」。没有截图或任务详情，以下判断均待核实。

无网络：标准交换机的端口组按主机分别存在，vCenter 中同名端口组才视为同一网络。母机网卡连接的是 esxi01 的 `VM Network`；台账中 esxi02 的端口组一直为空。最可能的解释是 esxi02 没有同名端口组，或克隆向导中网络没有选到 esxi02 上的有效端口组，所以克隆后网卡没有后端网络。处理顺序：先只读对比 esxi01 与 esxi02 的虚拟交换机、上行链路和端口组（名称与 VLAN ID）；若 esxi02 的 vSwitch0 缺少 VM Network，就在同一 vSwitch0 上新增同名、同 VLAN 的虚拟机端口组，不修改 Management Network、vmk0 或上行链路；再为 seal-test-02 的网卡选择该端口组，并勾选「已连接」与「打开电源时连接」。新增端口组不改变唯一管理通道。

IO 筛选器告警：这是 vCenter 的存储管理服务向 esxi02 注册 IO Filter VASA Provider 失败。本实验没有使用 IO 筛选器（虚拟机加密及第三方缓存/复制等会用到），因此它不阻塞克隆验证和节点准备。常见原因是 vCenter 与该主机之间的证书、时间或名称解析问题；第 5 节记录的 VCSA DNS 丢失是可能因素之一，但未证实。先只读检查三台主机中哪台有该告警、esxi02 的时间配置与证书有效期，以及 vCenter 存储提供程序列表中 esxi02 的状态；可选的低风险操作是在 esxi02 上重启 iofiltervpd 服务后同步存储提供程序。若仍反复出现，与 VCSA DNS/改名一起处理，不在节点主线上展开。

seal-test-01 的第 43 节检查可以同时进行。尚无输出。

## 45. 2026-10-16 继续：第一台克隆检查通过，待第二台对比

用户报告两台测试克隆均已正常、跨宿主机 ping 通（ping 输出与 seal-test-02 的修复步骤未提供），回传了 192.168.9.30 一台的检查输出，未说明它是 seal-test-01 还是 seal-test-02。已归档 [克隆检查证据](evidence/00.04.03-clone-test-seal-test-01.txt)。

该克隆首次开机已重新生成身份：machine-id db35c4b6…d7ec 与母机 journal 目录 id 6eda8862…bbbd 不同；SSH 主机密钥为新生成，Mac 首次连接显示的 ED25519 指纹与磁盘上密钥一致；DHCP 取得 .30，网关 .1，DNS 为路由器下发的 8.8.8.8 与 223.5.5.5。无失败单元；kdump 为 not-found，即系统未安装 kdump，第 41 节担心的 first-boot preset 不适用；kubelet disabled、Enforcing、running、containerd 与两镜像、RuntimeReady、chrony 均正常。

两个观察：运行时文件系统在母机上是 /dev/sdb1，在克隆上变为 /dev/sda1，而挂载仍正确，因为 fstab 与 systemd 依赖按 UUID 指定——磁盘设备名在克隆后不稳定，台账与 OSD 映射只能用 UUID、SCSI 地址或序列号。登录提示中的 `Last login ... from 192.168.9.200` 来自母机的 wtmp/lastlog，封装未清理登录记录，属外观问题，补入封装清单。

唯一性需两台对比才能下结论。下一组请用户在另一台执行第 43 节同一组检查，并在两台各执行 `lsblk -e7 -o NAME,SIZE,TYPE,HCTL,MOUNTPOINTS`，同时说明哪台是 .30、esxi02 网络如何修复（是否新建 VM Network 及 VLAN ID）、esxi02 所用 Datastore 名称与 IO 筛选器告警现状。尚无输出。

## 46. 2026-10-16 继续：克隆与地址对应、esxi02 网络自行恢复

用户确认 seal-test-01 为 192.168.9.30，seal-test-02 为 192.168.9.32；第 45 节证据文件已据此改名为 [seal-test-01 检查证据](evidence/00.04.03-clone-test-seal-test-01.txt)。seal-test-02 的「没有为该虚拟机分配网络」在用户等待后自行恢复，没有新建端口组或修改设置。可能是克隆或开机后 vCenter 清单、网络信息尚未同步，但未经证实；esxi02 端口组名称、VLAN 与 Datastore 仍未登记。

seal-test-02 的检查输出与两台的 lsblk 仍未回传，唯一性尚不能下结论。下一组：在 seal-test-02 执行第 43 节同一组检查并加 `lsblk -e7 -o NAME,SIZE,TYPE,HCTL,MOUNTPOINTS`；在 seal-test-01 只执行 lsblk；从 vSphere 中 seal-test-02 的摘要页读取其数据存储与网络名称。尚无输出。

## 47. 2026-10-16 继续：seal-test-02 用户报告正常；唯一性待最小对比

用户报告 seal-test-02 的检查命令「执行都正确」，并说明其网络名与存储名「一样」，未回传输出。按本记录规则，该结果记为用户报告；唯一性需要两台的实际值对比，目前只有 seal-test-01 的证据。「一样」存在两种理解：与 esxi02 的名称一致，或与 seal-test-01 相同（VM Network、esxi01-sas10t5）。若数据存储也是 esxi01-sas10t5，说明 seal-test-02 可能实际运行在 esxi01，esxi02 的存储、CPU 与跨宿主网络就未被测到。需由用户在摘要页确认「主机」一栏。

为减少往返，改用 Mac 上一条命令同时读取两台的四项身份值（machine-id、BIOS UUID、MAC、ED25519 指纹），用户输入两次密码即可；四行在两台之间都不同即通过，并请回传该输出存档。待执行：

```bash
for ip in 192.168.9.30 192.168.9.32; do echo "== $ip"; ssh root@$ip 'cat /etc/machine-id; cat /sys/class/dmi/id/product_uuid; cat /sys/class/net/ens33/address; ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub'; done
```

通过后的顺序：核对 esxi02/esxi03 的 VM Network 与本地 Datastore 名称 → 关机并从磁盘删除两台测试克隆 → 按 hosts.yaml 位置和 resources.yaml 规格克隆十台（不自定义操作系统，只改 vCPU/内存）→ 按手册第 5 节「先改一个节点并验证 SSH 回连，再小批量执行」，先只对 cp01 设置 FQDN 与静态地址。DNS 暂用 DHCP 下发并已验证可用的 8.8.8.8、223.5.5.5，不引用尚未部署的 .11；内部名称解析在 DNS 部署后补。路由器 DHCP 池 .30–.49 只有 20 个地址且与 Wi-Fi 共用，十台同时开机可能耗尽，按宿主机分批开机并改为静态地址；取不到地址时用网页控制台直接配置。尚无输出。

## 48. 2026-10-16 继续：双克隆与 cp01（用户报告）；其余九台步骤

用户报告：双克隆对比「没问题」，seal-test-02 的存储、主机、网卡「都对」「名字都一样」；cp01 已按第 47 节完成克隆、FQDN 与静态地址设置。均未回传输出。以下按用户报告记录：双克隆唯一性只有 seal-test-01 一侧证据；seal-test-02 实际所在主机与 esxi02 Datastore 名称仍不明确；cp01 的 hostname/IP/路由/DNS 检查无输出。台账 cp01 记为 cloned_hostname_static_ip_user_reported，actual_hypervisor 按用户报告填 esxi01；运行时盘 UUID 继承自模板，十台相同，属预期（每台是独立磁盘）。测试克隆是否已删除未说明。

为不再逐台索取输出，改为十台完成后一次性取证：在 Mac 生成专用 SSH 密钥并分发到十台（保留现有 root 密码登录，不收紧），然后用一条命令批量读取身份、网络、运行时和安全状态，作为十节点矩阵证据；该密钥同时作为后续 Ansible 的连接方式。

其余九台按 cp01 的方法逐台执行：先克隆（不开机），开机后取得 DHCP 地址；Mac 先 `ping` 确认目标静态地址未被占用；SSH 到 DHCP 地址后执行以下三条，并把第一行替换为该节点的值：

```bash
N=cp02; IP=192.168.9.102
hostnamectl set-hostname "$N.k8s.internal.egon.top"
nmcli connection modify ens33 ipv4.method manual ipv4.addresses "$IP/24" ipv4.gateway 192.168.9.1 ipv4.dns "8.8.8.8 223.5.5.5"
nmcli connection up ens33
```

用新地址重新登录后检查 `hostnamectl --static; ip -br -4 address show ens33; ping -c 2 192.168.9.1; ping -c 2 192.168.9.101`，其中 ping cp01 用于验证跨宿主机互通。顺序先 cp02（esxi02 第一台正式节点）、cp03（esxi03 第一台），再其余。尚无输出。

## 49. 2026-10-16 继续：十台改址完成（用户报告）；交付 node-readiness 批量取证

用户报告十台节点均已克隆并配置 FQDN 与静态地址，未回传输出。台账九台节点状态同步为 cloned_hostname_static_ip_user_reported，clone_status 为 ten_nodes_cloned_user_reported。

为把「用户报告」转为可复核证据、并避免逐台粘贴输出，本次交付手册第 2 节规划的只读检查与管理端汇总：

- [node-readiness.sh](../../tests/smoke/node-readiness.sh)：在节点以 root 运行，只读采集身份、虚拟硬件、网络、安全基线、运行时盘、containerd/CRI、入群工具与失败单元，逐项输出 key=value；经 `ssh 'bash -s' <` 推送，节点上不留文件。
- [collect-node-readiness.sh](../../scripts/collect-node-readiness.sh)：管理端用 ruby 标准库读取 hosts/resources/networks 台账与版本锁，为每台写期望值，以密钥和 BatchMode 采集，记录 SSH 退出码，默认输出到本批 evidence 下带时间戳的目录。
- [summarize-node-readiness.py](../../scripts/summarize-node-readiness.py)：只读汇总为 matrix.md，每台 24 项检查与六个字段（machine-id、BIOS UUID、MAC、SSH ED25519、主机名、IPv4）的跨节点唯一性；采集失败的节点只报一次且不参与比对；任一不通过退出码为 1。

本助手在 Mac 用模拟 ssh 做了本地验证（未连接节点）：全部正常的数据退出码 0、「全部通过」；注入不可达节点、重复 machine-id、错误 vCPU 与已启用 kubelet 时，四类问题均被列出、退出码 1。节点端脚本只做了 bash 语法检查，尚未在 Rocky 上运行，首次真实运行的输出即为其验证。

取证前需要密钥登录：在 Mac 生成专用 ed25519 密钥（建议设置口令并加入钥匙串代理），用 ssh-copy-id 分发到十台 root，保留现有密码登录、不收紧 SSH。该密钥也作为后续 Ansible 的连接方式；改用专用管理账户与 sudo 仍按手册第 6 节在 node_base 中实施。以下待用户执行，尚无输出：

```bash
ssh-keygen -t ed25519 -f ~/.ssh/cnpl_lab_ed25519 -C "cnpl-lab-admin@MarioMacBook-Pro"
ssh-add --apple-use-keychain ~/.ssh/cnpl_lab_ed25519
for i in $(seq 101 110); do ssh-copy-id -i ~/.ssh/cnpl_lab_ed25519.pub root@192.168.9.$i || break; done
for i in $(seq 101 110); do ssh -i ~/.ssh/cnpl_lab_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes root@192.168.9.$i hostname; done
cd ~/SelfProject/cloud-native-platform-lab && ops/00-preparation/scripts/collect-node-readiness.sh
```

采集完成后由本助手直接读取输出目录的 matrix.md 与原始文件，不需要用户粘贴。

## 50. 2026-10-16 十节点 node-readiness 首次实测：身份唯一，规格未调整

用户按第 49 节分发密钥并运行收集脚本（密钥生成、分发与免密验证的输出未回传；采集本身以 BatchMode 成功即说明十台密钥登录可用）。本助手直接读取输出目录 [00.10.02-node-readiness-20261016-094918](evidence/00.10.02-node-readiness-20261016-094918/matrix.md)：十台 collect_exit 均为 0，这也是 node-readiness.sh 在 Rocky 上的首次真实运行，各项均有值，脚本可用。

**通过**：六项身份字段在十台之间全部唯一（machine-id、BIOS UUID、MAC、SSH ED25519、主机名、IPv4），这同时补足了第 47–48 节双克隆对比只有单侧证据的缺口。十台主机名与台账 FQDN 一致，地址为 .101–.110/24 静态配置，网关 .1，DNS 8.8.8.8/223.5.5.5；VMXNET3 与 VMware Tools 正常；SELinux Enforcing、firewalld running、无 Swap、cgroup v2、ip_forward=1、overlay 已加载、chrony Normal；运行时盘按 UUID 1b36c022… 挂载为 xfs；containerd enabled/active，containerd v2.4.2、runc 1.5.2、crictl v1.36.0、kubeadm/kubelet/kubectl v1.36.5 与版本锁一致；RuntimeReady=true、NetworkReady=false；pause:3.10.2 存在；kubelet disabled；/etc/cni/net.d 为空。

**未通过**：

1. 十台 vCPU 均为 2、MemTotal 3908 MiB，即模板规格，未按 resources.yaml 调整为 cp 4/8、infra 6/12、storage 8/16、worker 8/16。第 47 节要求在克隆向导中「自定义此虚拟机的硬件」，实际没有生效或未执行。需逐台关机后在 vSphere 修改 CPU 与内存再开机；修改后 esxi01/02/03 预计分别占用 52/36/40 GiB，未超过各自物理内存。
2. worker01 有失败单元 dnf-makecache.service。这是定时刷新软件源元数据的 oneshot 服务，其余九台没有。原因未查：可能是当时访问外部镜像源失败（母机已证实部分境外站点不可达），也可能是其他问题。先查看 `systemctl status dnf-makecache.service` 与本次开机日志后再 reset-failed，不能直接清除。

**观察**：运行时盘在八台为 sdb、cp03 为 sda、infra02 的 SCSI host 号为 2，但十台的 SCSI 目标号/LUN 均为 1:0；挂载按 UUID 始终正确。台账为每台登记 runtime_disk_scsi_hctl 与 MAC，设备名不作为标识。十台都带有 1.9G 的 sr0，即模板安装时挂载的 ISO 仍连接在虚拟光驱上；调整规格时可一并改为客户端设备并取消「打开电源时连接」。

台账十台状态更新为 identity_verified_resize_pending，clone_status 为 ten_nodes_cloned_identity_verified。规格调整并排查 worker01 后重跑收集脚本，以新的输出目录作为验收证据；本目录作为首次实测与失败记录保留。

## 51. 2026-10-16 合并与 worker01 dnf-makecache 失败分析

用户要求合并到 main：本助手将 phase00/template-seal-ten-nodes 以 fast-forward 合并，main 指向 78b3fe3，未推送（比 origin/main 领先 1 个提交），分支保留。

用户按第 50 节在关机前取回 worker01 的服务状态与本次开机日志，已归档 [worker01 失败证据](evidence/00.10.02-worker01-dnf-makecache-failure.txt)。dnf-makecache.timer 在克隆机首次开机后不久触发；由于封装时执行过 `dnf clean all`，每台克隆都要在首次开机时完整下载元数据。Rocky 的 mirrorlist 选中两个国内镜像：mirror.nyist.edu.cn 对当前 repomd 指向的 primary.xml.gz 返回 404（该镜像的 repodata 与期望不同步），mirrors.ustc.edu.cn 速度低于 1000 B/s 超过 30 秒；BaseOS 只以 3.3 kB/s 下载了 533 kB，最终失败。

结论：这是一次外部镜像可用性失败，不是节点配置缺陷。十台的源定义、签名和网络配置相同，其余九台没有失败；但同样的镜像是否会再次失败，未证实。失败状态不持久，重启或下一次成功运行即清除。节点仍直接依赖公网镜像，这正是手册第 6 节与计划 00.09.04 要求改为受控内网源的原因；在此之前不批量替换软件源（第 10 节已决定不采用参考笔记中的换源操作），也不为通过检查而禁用定时器。是否在节点上保留 dnf-makecache.timer，在内网源就绪后由 node_base 决定。

下一步不变：关机、按角色调整 vCPU/内存并断开 ISO、开机后重跑收集脚本。若重跑时 worker01 或其他节点再出现 dnf-makecache 失败，先看对应日志确认仍是镜像问题，再记录为已知外部问题，不把它当成节点规格或运行时问题。本节为工作区改动，尚未提交。

## 52. 2026-10-16 失败与修正：收集脚本在 UTF-8 终端报 unbound variable；cp01 连接超时

用户关机调整规格后重跑收集脚本，在 cp01 一行报 `line 63: ssh_rc?: unbound variable` 并中止。输出目录 [00.10.02-node-readiness-20261016-100443](evidence/00.10.02-node-readiness-20261016-100443/) 只有十份 .expect、cp01.txt（collect_exit=255）与 cp01.err，作为失败记录保留，不作为验收证据。

原因有两层。第一层是 cp01 的 SSH 失败：cp01.err 为 `ssh: connect to host 192.168.9.101 port 22: Operation timed out`。第二层是脚本缺陷，由此暴露：失败分支的提示 `"…退出码 $ssh_rc，见…"` 中，变量后紧跟全角逗号。macOS 自带 bash 3.2 在 UTF-8 locale 下会把多字节字符的首字节当作变量名字符，于是查找 `ssh_rc` 加一个字节的变量，`set -u` 报错退出。本助手已在本机复现：C locale 正常，en_US.UTF-8 与 zh_CN.UTF-8 均报错。第 49 节的本地测试在未设置 LANG 的环境中运行，因而没有发现。用户终端为 en_US/zh-Hans 的 UTF-8 环境。

修正：第 26 与第 63 行改为 `${KEY}`、`${ssh_rc}`、`${id}`，并在脚本中注明这一约束；扫描两个 shell 脚本，已无变量紧接非 ASCII 字符的写法。在 en_US.UTF-8 下用模拟 ssh 让 cp01、infra02 失败重测，失败提示正常输出、其余节点继续采集、矩阵正常生成；缺少私钥的提示也正常，退出码 2。

cp01 超时的原因未查明：可能是虚拟机尚未开机或仍在启动，也可能是编辑设置时网卡未连接。下一步先从 Mac 对十个地址做连通检查，确认全部在线后再重跑收集脚本。尚无输出。

## 53. 2026-10-16 通过：十节点 node-readiness 重跑 24/24；交付批量 CRI 自测

用户按角色调整规格并开机后重跑收集脚本（ping 检查与调整过程的输出未回传）。本助手读取 [00.10.02-node-readiness-20261016-101221](evidence/00.10.02-node-readiness-20261016-101221/matrix.md)：十台均为 24/24，六项身份全部唯一，总体「全部通过」。vCPU/MemTotal 为 cp 4/7934 MiB、infra 6/11953 MiB、storage 与 worker 8/15985 MiB，符合 resources.yaml；worker01 无失败单元，与第 51 节的外部镜像判断一致，但不证明 dnf-makecache 此后每次都会成功。

与第 50 节首次实测对比：十台 machine-id、SSH ED25519 指纹与 MAC 在关机调整和重启后完全不变，说明身份只在克隆后的首次开机生成一次，后续开机保持稳定（手册第 11 节要求不得重建身份）。运行时盘设备名在同一台虚拟机的两次开机之间也发生变化（如 cp01 由 sdb1 变为 sda1、cp03 由 sda1 变为 sdb1），按 UUID 的挂载始终正确；台账备注改为「sda/sdb 在重启间会变化」。十台仍带有 1.9G 的 sr0，安装 ISO 未从虚拟光驱断开，不影响检查项，属于待清理项。由于规格调整需要关机，本次结果同时是十台重启后的基线复验。

台账十台状态更新为 node_readiness_passed_cri_smoke_pending，node_readiness_evidence 指向本目录；版本锁中运行时与入群工具组件追加该矩阵作为十节点执行证据。

计划验收要求十台通过 node-readiness 与 host-network CRI smoke，后者此前只在母机做过。本次交付：

- [cri-smoke.sh](../../tests/smoke/cri-smoke.sh)：第 10.3 节流程的脚本化版本。必须设置 CRI_SMOKE_CONFIRM=yes；只使用本地镜像，不拉取；sandbox 带 `cgroup_parent: phase00.slice` 与主机网络；每次用时间戳作 uid/attempt，工作目录在 /run 下；通过 trap 只清理本次创建的对象；输出 smoke_* 键值，日志为 phase00-cri-ok、退出码 0、状态 EXITED 且近期 AVC 为 0 才判 PASS。
- 收集脚本新增 `--with-cri-smoke`：在只读检查之后逐台执行自测，结果追加到同一节点文件；汇总增加第 25 项「CRI 自测」与自测明细表。不加该参数时行为不变，仍为只读。

本地验证（未连接节点）：未确认时脚本拒绝运行并退出 2；在 en_US.UTF-8 下用模拟 ssh 复用本次十台真实数据，注入 cp03 自测失败与 infra02 不可达，两者都被正确判定，其余八台 25/25；不加参数时仍为 24/24 且不产生 smoke 字段。cri-smoke.sh 在 Rocky 上的首次真实运行即为其验证。下一步待用户执行：

```bash
cd ~/SelfProject/cloud-native-platform-lab && ops/00-preparation/scripts/collect-node-readiness.sh --with-cri-smoke
```

## 54. 2026-10-16 失败与修正：批量 CRI 自测被 ausearch 读走脚本

用户运行 `collect-node-readiness.sh --with-cri-smoke`，输出目录 [00.10.02-node-readiness-20261016-101955](evidence/00.10.02-node-readiness-20261016-101955/matrix.md) 中十台只读检查仍全部通过、身份唯一，但「CRI 自测」十台均 FAIL。十台的现象完全一致：sandbox 已创建（SANDBOX_READY、network NODE，pause 为 container_t 且各有独立 MCS 类别，例如 cp01 c120,c968），清理 yes，退出码 1，但 smoke_container_* 全部缺失，smoke_reason 为空，也没有 stderr。

原因是本助手脚本的缺陷，而不是节点问题。收集脚本以 `ssh … 'bash -s' < cri-smoke.sh` 推送执行，bash 边从标准输入读取边执行脚本。`ausearch` 在标准输入不是终端时会改为从标准输入读取审计事件，于是把脚本中尚未执行的部分（记录容器状态与判定 PASS 的代码）当作输入读走。bash 随即读到 EOF 而结束，退出码取自最后的 `grep -c`（无匹配为 1），trap 照常清理并输出 FAIL 和空原因。母机上手动执行时 ausearch 在终端中运行，第 53 节的本地测试则以文件方式执行，均未触发该问题。

修正：ausearch 改为 `--input-logs`，明确读取审计日志；cri-smoke.sh 与 node-readiness.sh 的主体包入 `{ … } </dev/null`，bash 先读完整个块，块内任何命令的标准输入都是 /dev/null。本地按真实方式（`bash -s <` 加一个与 ausearch 一样在非终端下读取标准输入的模拟命令）对比：修复前复现「FAIL、原因为空、无容器字段」，修复后得到 CONTAINER_EXITED、phase00-cri-ok、AVC 0、PASS；node-readiness 经 `bash -s` 仍输出全部 45 项。

推论：十台的容器很可能都已运行成功，但这次没有可用记录，不能据此判为通过。因为 CID 已赋值且 cleanup 为 yes，本次创建的容器和 sandbox 均已删除，没有遗留。本目录作为失败记录保留。下一步由用户重跑同一命令。尚无输出。

## 55. 2026-10-16 通过：十节点 node-readiness 与 host-network CRI 自测

用户按第 54 节重跑 `collect-node-readiness.sh --with-cri-smoke`。本助手读取 [00.10.02-node-readiness-20261016-102410](evidence/00.10.02-node-readiness-20261016-102410/matrix.md)：十台均 25/25，总体「全部通过」，无 .err 文件。六项身份全部唯一。CRI 自测十台 PASS：sandbox SANDBOX_READY、network NODE，容器 CONTAINER_EXITED、退出码 0、日志 phase00-cri-ok，近期 AVC 0，cleanup yes；pause 均为 container_t，十台的 MCS 类别各不相同（如 cp01 c84,c829、storage01 c15,c31）。这也是修正后 cri-smoke.sh 在 Rocky 上的首次成功运行。

据此，计划 00 验收用例中「十台节点通过 node-readiness 和 host-network CRI smoke」有了实测证据。台账十台状态更新为 node_readiness_and_cri_smoke_passed；版本锁中 containerd、runc、cri_tools、pause、cri_smoke_image 更新为 validated_ten_nodes_host_network，入群工具与 cni_plugins 追加执行证据，状态仍为 installed_unvalidated（00 只验证安装与版本，功能在 01 验收）。

本结果不代表以下事项已完成：10.2 仓库拉取、registry 配置与 CA 信任（需 Harbor/DNS/CA）；手册第 7 节按角色与来源配置 firewalld 规则；journald 持久化与容量上限；Ansible node_base/container_runtime 角色、bootstrap-nodes.yml 与第二次执行无变更的幂等验收；storage 节点候选 OSD 盘的附加与稳定 ID 登记；十台虚拟光驱仍连接安装 ISO。整个 Phase 00 中的 DNS/CA、GitLab/Harbor/Nexus、OpenWrt/VPN/代理、离线验收与独立备份恢复仍未开始。

## 56. 2026-10-16 开始节点收尾：建立 Ansible 控制端（00.10.01）

用户确认按「先节点收尾、后基础服务」推进。第一步按 00.10.01 在管理 Mac 准备不依赖 Kubernetes 的 Ansible 控制端，后续防火墙、journald 与幂等验收都通过它执行。

本助手只读核对：Mac 未安装 ansible/pipx，有 Homebrew Python 3.14.6（系统 Python 3.9.6 不满足要求）。PyPI 上 ansible-core 最新为 2.21.5（2026-10-05），requires_python >=3.12，分类声明支持 3.12–3.14，wheel SHA256 08886f9f…1222。Galaxy 上 ansible.posix 最新为 2.2.2（2026-07-13，requires_ansible >=2.16.0），归档 SHA256 00a58c5d…b82b。只用 ansible-core 加 ansible.posix（firewalld、sysctl、mount、selinux 模块），不安装体积大、版本难锁的 ansible 社区全集。版本锁的 ansible 填入候选与 wheel 校验值，ansible_collections 从 pending_by_phase 提升为组件；依赖的实际解析版本待安装后用 pip freeze 记录。Mac 在实验网段的有线地址为 192.168.9.200（en5），与 networks.yaml 中 .200「reserved」重合，已在台账标注实际用途；后续防火墙「管理来源」规则以此为准，地址固定方式待确认。

新增文件（均在 ops/00-preparation/ansible/，按手册第 2 节）：

- requirements.txt：ansible-core==2.21.5；requirements.yml：ansible.posix 2.2.2，安装到本目录 collections/（已加入 .gitignore）。
- ansible.cfg：在该目录运行时生效；inventory 指向 inventories/lab/hosts.yml，只扫描本地 collections，host_key_checking 开启，forks 10，pipelining。
- inventories/lab/group_vars/all.yml：root + 第 49 节的专用密钥，IdentitiesOnly；改为专用管理账户由 node_base 实施。
- inventories/lab/hosts.yml：由新增的 [generate-ansible-inventory.rb](../../scripts/generate-ansible-inventory.rb) 从 hosts.yaml 生成，不手改；组为 k8s_nodes 下的 control_plane/infra/storage/worker，主机变量带 FQDN、计划宿主、连接名、运行时盘 UUID 与 SCSI 位置。生成时发现 Psych 不给 `2:0:1:0` 这类值加引号，而 Ansible 使用的 PyYAML（YAML 1.1）会把它解析为六十进制整数，生成脚本已强制加单引号；本地确认十台分组正确、infra02 的值为字符串。

以下待用户在 Mac 执行，尚无输出：

```bash
python3 -m venv ~/.venvs/cnpl-ansible
~/.venvs/cnpl-ansible/bin/pip install -r ~/SelfProject/cloud-native-platform-lab/ops/00-preparation/ansible/requirements.txt
source ~/.venvs/cnpl-ansible/bin/activate && cd ~/SelfProject/cloud-native-platform-lab/ops/00-preparation/ansible
ansible-galaxy collection install -r requirements.yml -p collections
ansible --version; pip freeze; ansible-galaxy collection list -p collections
ansible-inventory --graph
ansible k8s_nodes -m ping
ansible k8s_nodes -m command -a 'python3 --version'
```

预期 ansible-core 2.21.5、Python 3.14.6、config file 指向本目录 ansible.cfg；ansible.posix 2.2.2；inventory 为 4 组 10 台；十台 ping 返回 pong；节点 Python 版本作为目标解释器记录。

## 57. 2026-10-16 通过：Ansible 控制端可用，十台 ping 通

用户执行第 56 节命令，验证输出由 tee 直接写入 [Ansible 控制端证据](evidence/00.10.01-ansible-control-node.txt)（venv 创建、pip 安装与集合安装的输出未保存）。ansible [core 2.21.5]，config file 为本目录 ansible.cfg，collection location 为本目录 collections，Python 3.14.6，jinja 3.1.6，PyYAML 6.0.3 带 libyaml 0.2.5；pip freeze 的依赖解析为 cffi 2.1.1、cryptography 50.0.2、Jinja2 3.1.6、MarkupSafe 3.0.4、packaging 26.3、pycparser 3.11、PyYAML 6.0.3、resolvelib 1.2.1；集合 ansible.posix 2.2.2。`ansible-inventory --graph` 为 k8s_nodes 下 control_plane 3、infra 2、storage 3、worker 2。十台 `ping` 均 SUCCESS/pong，发现的解释器均为 /usr/bin/python3.12，`python3 --version` 均为 3.12.13（command 模块总报告 CHANGED，属正常）。版本锁 ansible 与 ansible_collections 更新为已安装版本、installed_management_side，并登记依赖与目标解释器。

00.10.01 的「独立管理工具环境」现有 Ansible 一项可用，OpenTofu 与凭据分离尚未开始。下一步按手册第 7 节配置角色化 firewalld 规则；先只读收集十台当前的 firewalld 状态与监听端口，作为设计输入和回退依据。管理 Mac 地址是否固定（第 56 节提问）用户尚未答复。

## 58. 2026-10-16 继续：firewalld 现状与 node_base 防火墙角色

用户执行第 57 节后的只读收集，输出已由 tee 写入 [firewalld 现状证据](evidence/00.10.02-firewalld-before.txt)，并答复管理 Mac 的地址为自动获取。

十台在去除 pid、fd、临时端口和链路本地地址后完全一致：firewalld 2.4.0，默认区域 public，ens33 在运行时属于 public（永久配置中的 interfaces 为空，由 NetworkManager 归入默认区域）；服务为 cockpit、dhcpv6-client、ssh；无自定义端口、ipset 与富规则；forward yes、masquerade no；存在发行版默认 policy。监听端口：sshd 0.0.0.0:22 与 [::]:22，chronyd 127.0.0.1:323，NetworkManager 在链路本地地址 546/udp，containerd 只在 127.0.0.1 的临时端口。节点未安装 Cockpit，9090 无监听。

Mac 经 DHCP 取得 .200，而 networks.yaml 登记的 DHCP 池是 .30–.49（dhcp_ranges_verified: false）。这说明路由器的实际地址池或绑定与台账不同。若实际池覆盖 .101–.110 或 .201–.220，路由器可能把节点地址或 VIP 分配给其他设备，违反 00.01.02「节点、基础服务和 VIP 不与 DHCP 冲突」。需要用户查看路由器的 DHCP 池、排除范围与已有绑定，并为 Mac 做地址绑定。台账已标注 .200 为 DHCP 获得、待核实。

本次编写 node_base 的防火墙部分（[角色目录](../../ansible/roles/node_base/)）与 [bootstrap-nodes.yml](../../ansible/playbooks/bootstrap-nodes.yml)，落实手册第 7 节：

- ipset 以模板写入 /etc/firewalld/ipsets/：k8s-nodes（十台）、k8s-control-plane（三台 cp）、lab-mgmt（group_vars 中的 lab_mgmt_sources，暂为 .200）；变化时 reload，并在添加规则前 flush_handlers。
- public 区域富规则：所有节点放行来自 k8s-nodes 的 10250/tcp、8472/udp、4240/tcp；控制平面另放行来自 k8s-nodes 与 lab-mgmt 的 6443/tcp，以及只来自 k8s-control-plane 的 2379–2380/tcp。10257/10259 由 kubeadm 绑定回环，不开放；NodePort、Ceph、Hubble 留待 02/03。
- 移除未使用的 cockpit 放行；ssh 与 dhcpv6-client 不动。SSH 收紧要等管理端地址固定、并确认网页控制台可用后再做。
- 保护措施：网卡区域与预期不符时 assert 停止；首次运行前把 /etc/firewalld 备份到 /root/firewalld.before-phase00-node-base；结束时运行 `firewall-cmd --check-config`。playbook 默认 serial 1，gather_facts 关闭。

本地验证（未连接节点）：`--syntax-check` 通过；以本地连接渲染 cp01 与 worker01 的三个 ipset 模板，内容符合预期且 XML 格式正确，两台的 ipset 相同；规则列表 cp01 为 6 条、worker01 为 3 条。ansible.posix.firewalld 的检查模式只比较规则字符串，不校验 ipset 是否已存在，因此首次 check 不会因 ipset 尚未创建而报错；这一判断待首次 check 输出确认。

Cilium 与 firewalld 的数据面配合（cilium_* 接口归属区域、转发策略）属于 01 部署 CNI 后的验证项，本角色只处理主机入口规则。

下一步：用户核实路由器 DHCP 与 Mac 绑定；在 cp01 上执行检查模式。待执行：

```bash
cd ~/SelfProject/cloud-native-platform-lab/ops/00-preparation/ansible && ~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/bootstrap-nodes.yml --check --diff --limit cp01 2>&1 | tee ../records/2026-10-14/evidence/00.10.02-node-base-firewall-check-cp01.txt
```

## 59. 2026-10-16 继续：DHCP 范围确认；cp01 检查模式通过；允许/拒绝验证剧本

用户确认路由器 DHCP 池为 .30–.49，不与节点 .101–.110、API VIP .100、业务 VIP .201–.220 或基础服务 .10–.17 重叠，00.01.02 的这一冲突风险据此关闭（用户查看，未导出路由器配置）。管理 Mac 的 .200 在池外，推测为路由器已有绑定；用户决定不再追踪。影响仅限 lab-mgmt 来源：地址变化时修改 lab_mgmt_sources 并重跑 node_base 即可，SSH 不受影响。

cp01 检查模式输出见 [检查证据](evidence/00.10.02-node-base-firewall-check-cp01.txt)：区域断言通过；备份、三个 ipset（diff 与本地渲染一致）、移除 cockpit、6 条富规则均显示将变更；reload handler 在检查模式下跳过；`firewall-cmd --check-config` 正常；ok=7 changed=4 failed=0。第 58 节关于「检查模式不因 ipset 尚未存在而报错」的判断得到证实。

新增 [verify-firewall.yml](../../ansible/playbooks/verify-firewall.yml)，用于手册第 7 节「允许与拒绝用例都通过」：在目标节点用 ncat 临时监听 6443、10250、2379、9090（最长 120 秒，always 中按命令行精确清理），分别从另一台控制平面、一台非控制平面节点（排除目标自身，因为回环访问不经过区域规则）和管理端（本机 nc）探测，再与按端口表手写的期望比较。期望不从角色变量推导，避免角色写错时测试跟着一起错。8472/udp 与 4240/tcp 未覆盖，前者留待 01 数据面验证。本地语法检查通过，十台的探测来源选择正确（storage02 作为目标时改用 worker01）。

下一步只在 cp01 实际执行并验证。回退方式：若规则导致异常，在 cp01 上用 `/root/firewalld.before-phase00-node-base` 恢复 /etc/firewalld 后 `firewall-cmd --reload`，必要时经网页控制台操作。待执行：

```bash
cd ~/SelfProject/cloud-native-platform-lab/ops/00-preparation/ansible && ~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/bootstrap-nodes.yml --diff --limit cp01 2>&1 | tee ../records/2026-10-14/evidence/00.10.02-node-base-firewall-apply-cp01.txt
cd ~/SelfProject/cloud-native-platform-lab/ops/00-preparation/ansible && ~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/verify-firewall.yml -e target=cp01 2>&1 | tee ../records/2026-10-14/evidence/00.10.02-firewall-verify-cp01.txt
```

## 60. 2026-10-16 通过：cp01 防火墙实际执行与允许/拒绝验证

用户在 cp01 实际执行 node_base，输出见 [执行证据](evidence/00.10.02-node-base-firewall-apply-cp01.txt)：区域断言通过；备份 /etc/firewalld 到 /root/firewalld.before-phase00-node-base；写入三个 ipset 后 reload handler 实际执行；移除 cockpit；添加 6 条富规则；`--check-config` 正常；ok=8 changed=5 failed=0。剧本经 SSH 完整结束，说明 SSH 放行未受影响。

验证输出见 [验证证据](evidence/00.10.02-firewall-verify-cp01.txt)：四个被测端口经一次重试后全部处于监听状态；从 cp02 探测 6443/10250/2379 open、9090 blocked；从 infra02 探测 6443/10250 open、2379/9090 blocked；从管理 Mac 探测 6443 open、10250/2379/9090 blocked。与手写期望完全一致，failed=0，临时监听已清理。由此在 cp01 上证明：etcd 只对控制平面开放；kubelet 不对管理端开放；即使 9090 有程序监听，移除 cockpit 后也被拒绝。本次非控制平面的探测来源为 infra02 而不是第 59 节示例中的 storage02，因为 difference 结果不保证顺序；脚本只保证不选目标自身，不影响结论。

下一步按手册第 11 节推广到其余九台（serial 1），对十台运行允许/拒绝验证，再以第二次执行 changed=0 证明幂等，最后重跑 node-readiness 与 CRI 自测，确认基线没有退化。

## 61. 2026-10-16 通过：十台防火墙推广、允许/拒绝验证、幂等与基线复验

用户按第 60 节依次执行四组命令，输出均由 tee 或收集脚本直接写入仓库：

1. [其余九台执行](evidence/00.10.02-node-base-firewall-apply-rest.txt)：serial 1 逐台执行，九台均 ok=8 changed=5 failed=0，无 fatal。
2. [十台允许/拒绝验证](evidence/00.10.02-firewall-verify-all.txt)：十台均「符合期望」，failed=0。cp01–03 的结果为控制平面期望：来自控制平面 6443/10250/2379 open、9090 blocked；来自普通节点 2379 blocked；来自管理端仅 6443 open。其余七台为普通节点期望：6443、2379、9090 对所有来源 blocked，10250 只对节点 open。本次探测来源分别为 cp03 与 worker01（cp03 作为目标时改用其他控制平面）。
3. [幂等](evidence/00.10.02-node-base-firewall-idempotency.txt)：十台同批（bootstrap_serial=10）再次执行，均 ok=7 changed=0 failed=0。备份不重复、ipset 不改写、handler 未触发、规则无变化，满足手册第 11 节「第二次真实执行应无非预期变更」。
4. [node-readiness 与 CRI 自测复验](evidence/00.10.02-node-readiness-20261016-105750/matrix.md)：十台 25/25，CRI 自测 10/10 PASS，无 .err，加入防火墙规则后基线没有退化。

台账十台增加 node_base_firewall: applied_verified_idempotent，node_readiness_evidence 指向本次矩阵。

手册第 7 节的「firewalld/nftables：按表配置来源受限规则，保存原规则与回退入口；允许与拒绝用例都通过」在十台上有了证据。仍未完成：SSH 来源收紧（维持现状）；8472/udp 与 4240/tcp 的实际流量验证（01 数据面）；Ceph/Hubble/NodePort 规则（02/03）；Cilium 接口与 firewalld 区域、转发的配合（01）。node_base 目前只覆盖防火墙；第 11 节的完整幂等验收要求把已手工完成的基线（sysctl、模块、Swap、chrony、journald、运行时盘挂载）与 container_runtime（containerd 配置、crictl.yaml、systemd 挂载依赖）也纳入 Ansible，并在现有节点上做到第二次执行无变更。

## 62. 2026-10-16 提交与 journald 持久化角色

用户要求提交：本助手在分支 phase00/node-base-firewall 提交 a76326c（47 个文件，§56–§61 与 Ansible 全套），fast-forward 合并到 main，未推送（比 origin/main 领先 3 个提交）；提交前确认无私钥、collections/ 与 .pyc 均未进入。

下一项按手册第 6 节处理 journald。第 42 节已观察到日志在 /run/log/journal，属易失存储；第 51 节 worker01 的失败日志正是因此只能在关机前人工取回。node_base 新增 journald 任务（标签 journald）：

- 在 /etc/systemd/journald.conf.d/50-phase00.conf 写入 Storage=persistent、SystemMaxUse=2G、SystemKeepFree=10G、MaxRetentionSec=30day，不修改发行版自带的 journald.conf。取值依据实测：根分区约 63G、已用约 2.5G；运行时数据在独立盘，但 01 之后 kubelet 的容器日志 /var/log/pods 在根分区，因此保留 10G 空闲。
- 配置变化时，handler 执行 `systemctl restart systemd-journald && journalctl --flush`（服务的 stdout 连接保存在 systemd fd store 中，重启 journald 不会断开），随后 flush_handlers，并确认 /var/log/journal/<machine-id> 存在。检查模式下目录尚不存在，不判为失败。
- node-readiness 增加 journal_storage、journal_system_max_use（取 `systemd-analyze cat-config` 合并后的最终值）与 journal_boots；汇总增加第 25 项「持久化日志」，只读检查共 25 项，加 CRI 自测为 26 项。boots 只作记录。

本地验证：syntax-check 与 list-tasks 正常，journald 四个任务带 journald 标签。用第 61 节的真实矩阵数据重算，只有新项不通过（25/26）；补入持久化键后为 26/26。node-readiness.sh 新增三项在 Rocky 上的首次运行即为其验证。

持久化是否跨重启生效，需要重启后 `journalctl --list-boots` 至少出现两次开机，计划用 worker02 验证。以下待用户执行，尚无输出：

```bash
cd ~/SelfProject/cloud-native-platform-lab/ops/00-preparation/ansible && ~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/bootstrap-nodes.yml --tags journald --check --diff --limit cp01 2>&1 | tee ../records/2026-10-14/evidence/00.10.02-node-base-journald-check-cp01.txt
cd ~/SelfProject/cloud-native-platform-lab/ops/00-preparation/ansible && ~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/bootstrap-nodes.yml --tags journald 2>&1 | tee ../records/2026-10-14/evidence/00.10.02-node-base-journald-apply.txt
cd ~/SelfProject/cloud-native-platform-lab/ops/00-preparation/ansible && ~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/bootstrap-nodes.yml -e bootstrap_serial=10 2>&1 | tee ../records/2026-10-14/evidence/00.10.02-node-base-idempotency-2.txt
cd ~/SelfProject/cloud-native-platform-lab/ops/00-preparation/ansible && { ~/.venvs/cnpl-ansible/bin/ansible worker02 -m ansible.builtin.reboot; ~/.venvs/cnpl-ansible/bin/ansible worker02 -m command -a 'journalctl --list-boots --no-pager'; } 2>&1 | tee ../records/2026-10-14/evidence/00.10.02-journald-reboot-worker02.txt
cd ~/SelfProject/cloud-native-platform-lab && ops/00-preparation/scripts/collect-node-readiness.sh --with-cri-smoke
```

## 63. 2026-10-16 journald 推广、幂等与重启验证通过；收集脚本一次中断

用户按第 62 节执行五组命令。

1. [cp01 检查模式](evidence/00.10.02-node-base-journald-check-cp01.txt)：将创建 drop-in 目录并写入 Storage=persistent、SystemMaxUse=2G、SystemKeepFree=10G、MaxRetentionSec=30day；flush_handlers 跳过；持久目录检查在检查模式下不判失败；ok=3 changed=2 failed=0。
2. [十台实际执行](evidence/00.10.02-node-base-journald-apply.txt)：serial 1，十台均 ok=4 changed=3（目录、配置、handler）failed=0。持久目录确认任务通过，说明十台都已存在 /var/log/journal/<machine-id>。第 62 节说「会显示每台日志占用」不准确：默认输出不显示成功任务的 stdout，占用量未进入证据。
3. [第二次幂等](evidence/00.10.02-node-base-idempotency-2.txt)：不带标签执行防火墙与 journald，十台同批 ok=10 changed=0 failed=0。
4. [worker02 重启](evidence/00.10.02-journald-reboot-worker02.txt)：reboot 模块 rebooted true、耗时 51 秒；`journalctl --list-boots` 列出 -1（22:09:49–23:07:04 CST）与 0（23:07:20 起）两次开机，证明日志已跨重启保留。持久化之前只能看到当前一次开机（第 42、51 节）。
5. [node-readiness 与 CRI 自测](evidence/00.10.02-node-readiness-20261016-110931/matrix.md) **采集中断，结果无效**：整轮只用 6 秒（11:09:35–11:09:41，Mac 时间）。cp01 的只读检查完整，新增三项为 journal_storage=persistent、journal_system_max_use=2G、journal_boots=1；cp01 的 CRI 自测在 sandbox 创建并记录 pause 标签后断开，smoke_collect_exit=255；其余九台两次 ssh 均立即以 255 退出，且没有 stderr（.err 为空已删除）。

第 5 项的原因未查明。可排除的：用户 ~/.ssh/config 只有一个无关的 rocky-pi 条目，没有 LogLevel 或 ControlMaster 设置；ssh-agent 中仍有实验密钥；第 1–4 项刚用同一密钥成功连接十台。本助手在本机用 ProxyCommand 模拟发送信号，SIGINT 时有报错输出，SIGHUP/SIGTERM 的退出码为 129/143，都不能复现「无输出的 255」，因此不下结论。比较可能的是本次运行在终端中被中断，但未证实。本目录作为中断记录保留。

由于 cp01 的自测在 sandbox 创建后中断，trap 清理是否执行无法从记录判断。下一步先只读检查 cp01 是否残留名为 phase00-cri-smoke 的 sandbox、容器或 /run 下的临时目录，有残留则只清理这些对象，然后重跑收集脚本。尚无输出。

## 64. 2026-10-16 更正：第五项实际已通过；中断的是紧接着的第二次运行

用户重跑收集脚本后，本助手列出全部结果目录，发现 11:08:13 还有一次运行：[00.10.02-node-readiness-20261016-110813](evidence/00.10.02-node-readiness-20261016-110813/matrix.md)。这次运行逐台完整执行，11:09:20 结束，十台 26/26、总体通过。第 63 节只读取了最新的目录（11:09:31），因此误把紧随其后、6 秒后中断的第二次运行当作第五项的结果。第五项应以 11:08 的目录为准，结果为通过；11:09:31 的目录是同一命令的重复运行在中途被中断（很可能为手动停止，未证实），保留为记录。第 63 节的事实陈述保留不改，结论以本节为准。教训：读取结果时应按时间列出本轮全部目录，不能只取最新一个。

用户之后再次重跑：[00.10.02-node-readiness-20261016-111359](evidence/00.10.02-node-readiness-20261016-111359/matrix.md)，11:14–11:15，十台 26/26、总体通过，无 .err；十台 journal_storage=persistent、SystemMaxUse=2G，worker02 的 journal_boots=2、其余为 1，与只有 worker02 在配置后重启过一致；CRI 自测 10/10 PASS；六项身份唯一。

手册第 6 节「journald 明确的占用上限和保留」在十台上有了证据：配置、幂等、跨重启保留与矩阵复验均已通过。台账十台增加 node_base_journald，node_readiness_evidence 指向 111359；模板 rocky10-base 未改动，其易失日志状态如实保留，下次重新封装时应纳入。

第 63 节要求的 cp01 残留检查，用户未回传输出。11:13 的自测在 cp01 上 PASS，但这只说明新建对象正常，不能证明 11:09 中断时创建的 sandbox 已被清理。下一步对十台只读检查 CRI 残留，与基线配置收集一并进行。

## 65. 2026-10-16 基线配置编码为 Ansible（node_base system + container_runtime）

用户回传第 64 节两组只读收集，分别存于 [校验和证据](evidence/00.10.02-baseline-files-checksums.txt) 与 [cp01 文件内容](evidence/00.10.02-baseline-files-cp01.txt)。十台 pods=0、containers=0、tmpdirs=0，11:09 的中断没有留下 CRI 残留。config.toml、10-runtime-mount.conf、crictl.yaml、90-kubernetes 模块与 sysctl 文件、chrony.conf、fstab 七个文件在十台上的 SHA256 完全一致。chrony.conf 为发行版默认（2.rocky.pool.ntp.org）；fstab 中 swap 行已注释，rlm/swap LV 保留且未激活；无 dnf exclude；七个关键包版本与版本锁一致。

用户提出最近推进太慢，本助手承认验证与记录过多，且工具缺陷造成多轮返工。随后让用户在「先用预置镜像跑起集群」与「按计划先做 DNS/CA/Harbor」之间选择，用户选择按计划进行：先完成基线编码，再依次建设 DNS、CA、Harbor，最后进入 01。

本次编码原则是把已手工完成的状态原样写成代码，用检查模式证明代码与十台现状一致：

- node_base 新增 system 部分（标签 system）：用 package_facts 断言 25 个基础包已安装，缺失时停止而不联网安装；SELinux targeted/enforcing；vmtoolsd、chronyd、firewalld 开机启动并运行；fstab 中未注释的 swap 行改为注释，若有激活的 swap 则执行 swapoff，LV 保留；写入 overlay 模块文件，未加载时 modprobe；写入 sysctl 文件，运行时值不符时重新应用；VMware 周期时间同步保持关闭。chrony.conf 暂不管理，待内部时间源就绪。
- 新增 container_runtime 角色（标签 runtime）：版本从 versions.lock.yaml 读取（经 inventory_dir 定位；最初用 playbook_dir，本地 ad-hoc 测试时路径错误，已改），逐包断言版本与 release；运行时盘用 ansible.posix.mount 按 UUID 挂载，从不格式化；写入 config.toml、挂载依赖 drop-in 与 crictl.yaml，变更时 daemon-reload 并重启 containerd；containerd 开机启动并运行。kubelet 的启用状态有意不管理：01 由 kubeadm 启用，本角色不得把它改回 disabled。首次安装路线（从种子物料安装 RPM）尚未编码，新节点缺包时断言会停止。
- bootstrap-nodes.yml 改为 node_base → container_runtime。已有文件不指定 mode/owner，沿用现状，不产生无关差异；权限未纳入强制范围，这是有意的取舍。

本地验证：角色中三个文件与 sysctl、模块文件的内容 SHA256 与十台一致（5/5 MATCH）；syntax-check 通过；list-tasks 共 35 个任务；版本解析为 containerd.io 2.4.2-2.el10、cri-tools 1.36.0-150500.1.1、kubeadm/kubelet/kubectl 1.36.5-150500.1.1、kubernetes-cni 1.9.1-150500.1.1。待用户执行检查模式，预期十台 changed=0：

```bash
cd ~/SelfProject/cloud-native-platform-lab/ops/00-preparation/ansible && ~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/bootstrap-nodes.yml --check --diff -e bootstrap_serial=10 2>&1 | tee ../records/2026-10-14/evidence/00.10.02-baseline-as-code-check.txt
```

## 66. 2026-10-16 通过：基线即代码，十台检查模式 changed=0

用户执行第 65 节命令，输出见 [基线检查证据](evidence/00.10.02-baseline-as-code-check.txt)：完整 playbook（node_base 的 system/firewall/journald 与 container_runtime）对十台同批以检查模式执行，均 ok=29 changed=0 failed=0 skipped=4，无 diff。跳过的四个任务恰好是只在状态不符时执行的修复动作：关闭激活的 swap、加载 overlay、重新应用 sysctl、关闭 VMware 时间同步；它们被跳过，说明十台这四项本已正确。软件包、SELinux、服务、fstab、模块与 sysctl 文件、运行时盘挂载、containerd 配置/drop-in/crictl.yaml 均与代码一致，防火墙与 journald 保持第 61、63 节的结果。

由此，手册第 11 节「以已编写并语法验证的 Playbook 为前提……第二次真实执行应无非预期变更」在十台上有了证据：手工建立的母机基线、克隆后的节点状态与仓库中的 node_base、container_runtime 一致。台账十台状态更新为 baseline_as_code_verified。仍未覆盖：权限与属主的强制；从种子物料首次安装软件包的路线；chrony 内部时间源；SSH 收紧；Harbor 就绪后的 10.2 仓库拉取。

节点主线到此告一段落。按用户选择，下一步建设集群外基础服务，顺序为 DNS（.11）、CA、Harbor（.12）。

## 67. 2026-10-16 提交基线编码；开始内部 DNS（00.07.01）

本助手提交 d074968（基线即代码，§65–§66）并 fast-forward 合并到 main，未推送（领先 origin/main 5 个提交）。

开始集群外基础服务的第一项：内部 DNS 192.168.9.11 / dns.mgmt.internal.egon.top。为减少往返，本助手先完成全部自动化与本地验证，用户只需克隆 VM、改地址、分发密钥并运行一条 playbook。

- 台账：dns 计划宿主改为 esxi01（基础服务优先使用 esxi01 的内存余量），2 vCPU / 2 GiB（resources.yaml bootstrap_memory.dns），vm_status creating，连接名 ens33。Inventory 生成脚本增加 bootstrap_services 组，只纳入 vm_status 不是 planned 的服务 VM，不对尚未创建的主机发起连接。
- node_base 区分角色：Kubernetes 端口规则、overlay 与 IPv4 转发只作用于 k8s_nodes。本地确认 cp01 仍为 6 条规则、worker01 3 条、dns 0 条，节点侧行为不变。
- 新增 service_vm 角色：服务 VM 由节点模板克隆，带 containerd、入群工具与运行时盘。该角色停止并禁用 containerd，卸载 /var/lib/containerd 并移出 fstab（不格式化），以 disablerepo='*' 本地卸载六个运行时与入群工具包，清理运行时配置和 Kubernetes 内核前置文件，并把 ip_forward 设为 0（DNS 不是路由器）。磁盘卸载后，由用户在 vSphere 删除「硬盘 2」。
- 新增 dns_server 角色：安装 bind 与 bind-utils（需要发行版软件源）；named.conf 以 Rocky 默认配置为基础，监听 127.0.0.1 与 .11，allow-query/allow-recursion 只限 localhost 与 192.168.9.0/24，allow-transfer none，forward only 到 223.5.5.5、8.8.8.8，dnssec-validation auto；正向区域 internal.egon.top 与反向区域 9.168.192.in-addr.arpa 由 hosts.yaml 与 networks.yaml 生成：Kubernetes 节点、基础服务、ESXi、由 esxiNN 推得的 idracNN、vCenter 目标名称 vcsa、API VIP。模板写入时分别用 named-checkzone 与 named-checkconf 校验。firewalld 只对 192.168.9.0/24 开放 53/udp 与 53/tcp。区域序列号为人工维护的 2026101601。
- 新增 playbooks/dns.yml：service_vm → node_base → dns_server，随后在管理端用 dig 验证六个内部名称（含 API VIP、iDRAC 与 PTR）、外部名称经上游递归以及内部区域的 aa 权威标志。

本地验证：两个 playbook 的 syntax-check 通过；以本地连接渲染三个模板，正向区域 24 条 A 记录，反向区域 24 条 PTR 且无重复；named.conf 的监听、来源限制与转发符合设计。首次渲染因 zip 产生的元组与字面列表混合排序而失败，已改为按名称字段排序。vcsa 的 PTR 指向目标名称，而 VCSA 当前的 PNID 仍是 vcenter.egon.local，因此在 VCSA 改名（暂缓）之前不要让 VCSA 使用本服务器。

待用户执行：在 vSphere 从 rocky10-base 克隆 dns（esxi01、esxi01-sas10t5、VM Network、2 vCPU/2 GB，不自定义操作系统）；开机后按节点方式改为 dns.mgmt.internal.egon.top / 192.168.9.11；从 Mac 执行 ssh-copy-id；然后运行：

```bash
cd ~/SelfProject/cloud-native-platform-lab/ops/00-preparation/ansible && ~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/dns.yml --diff 2>&1 | tee ../records/2026-10-14/evidence/00.07.01-dns-deploy.txt
```

成功后在 vSphere 删除 dns 的「硬盘 2」（同时从数据存储删除文件）。尚无输出。

## 68. 2026-10-16 通过：内部 DNS 部署；OpenWrt 部署方式调整

用户报告 BIND 下载很慢，曾要求先部署 OpenWrt 旁路由和 VPN；随后又报告 DNS「好像部署好了」，硬盘 2 暂不删除。本助手读取 [DNS 部署证据](evidence/00.07.01-dns-deploy.txt)：dns ok=32 changed=19 failed=0，localhost ok=3 failed=0。管理端 dig 六个用例全部符合：cp01→.101、api→.100、harbor→.12、esxi02→.62、idrac03→.53、.109 的 PTR 为 worker01；外部名称 rockylinux.org 经上游递归有 A 记录；internal.egon.top 的 SOA 带 aa 标志。00.07.01「从节点能够解析内部服务」的服务端部分完成；节点与 Mac 仍使用公共 DNS，改用 .11 由后续任务处理。台账 dns 的 vm_status 记为 deployed。service_vm 已卸载运行时盘并移出 fstab，用户暂留 vSphere「硬盘 2」，之后删除不影响开机。

OpenWrt：用户选择代理订阅（Clash 类）与显式代理模式，与 00.06.02 的设计一致：默认网关保持 .1，只有显式配置代理的程序经 192.168.9.10。用户问能否直接下载 ISO 上传安装。答复：OpenWrt 官方不发布 x86 ISO，只提供磁盘镜像；第三方 ISO 来源无法核实，不采用。改用比借 DNS VM 执行 dd 更简单的方式：把镜像作为 VMFS 平面磁盘的数据文件，另写描述文件，两者经数据存储浏览器上传后作为现有硬盘挂载。

本助手在 Mac 种子目录完成：官方 sha256sums 校验 openwrt-25.12.5-x86-64-generic-ext4-combined-efi.img.gz 为 OK（c8ee59ce…0290，HTTPS 获取，签名未验证）；解压为 openwrt-flat.vmdk，原始 126123520 字节（不是整 MiB），SHA256 d02a23a6…1f31；补零到 1 GiB，使容量为整 MiB 并为以后扩容留空间，补零后前 126123520 字节的 SHA256 不变；生成描述文件 openwrt.vmdk（createType vmfs，RW 2097152 扇区，几何 130/255/63）。补零后 GPT 备份头不在磁盘末尾，内核会提示，不影响启动。

VM 设计：esxi01、2 vCPU、2 GiB、EFI 关闭安全引导；网卡用 E1000E，因为 OpenWrt x86 默认镜像自带 e1000e 驱动，VMXNET3 驱动是否内置未核实，这与节点统一使用 VMXNET3 不同；磁盘挂在 SATA 控制器上，因为 OpenWrt 默认内核是否带 LSI Logic/PVSCSI 驱动未核实，而 AHCI 一定内置。首次开机前断开网卡：OpenWrt 默认在 LAN 上启用 DHCP 与 IPv6 RA，接入现有 LAN 前必须在控制台关闭（00.05.02「不存在第二个 DHCP 服务抢答」），再把地址设为 .10 并设置 root 密码。OpenWrt 没有 Python，暂不纳入 Ansible inventory（vm_status planned）。若 vSphere 不接受上传的平面磁盘，退回 vmkfstools 转换或 dd 路线。订阅链接按秘密处理，不进入对话或仓库。尚无部署输出。

## 69. 2026-10-16 失败与修正：OpenWrt 无网卡，原因是 E1000E 驱动不在镜像中

用户报告 OpenWrt 已开机、地址已改为 .10，但 Mac 无法 ping 通；控制台 `ip -br link` 中没有 eth0。本助手核对 25.12.5 x86-64 的官方 manifest：只有 28 个 kmod，没有任何网卡驱动包。再核对 v25.12.5 标签下的内核配置：target/linux/x86/config-6.12 有 CONFIG_ATA_PIIX=y、CONFIG_FUSION_SPI=y，target/linux/x86/64/config-6.12 有 CONFIG_SATA_AHCI=y、CONFIG_VIRTIO_NET=y、CONFIG_VMWARE_PVSCSI=y、CONFIG_VMXNET3=y。可见 VMXNET3 已内置，E1000/E1000E 不在内置也不在默认包中。第 68 节「OpenWrt 默认镜像自带 e1000e，VMXNET3 驱动是否内置未核实」的判断是错的：本助手凭印象选择 E1000E，没有先核实。LSI Logic（FUSION_SPI）与 PVSCSI 也已内置，因此改挂 SATA 并无必要，但不影响使用。

用户随后找到 OpenWrt 官方 wiki [OpenWrt on VMware alternative howto](https://openwrt.org/inbox/openwrt_on_vmware_alternative_howto)（基于 24.10.2 与 ESXi 6.7 U3）。该文档使用 VMXNET3 网卡、PVSCSI 控制器、BIOS 固件与非 EFI 镜像，经 qemu-img 转换后用 vmkfstools 导入；文档写明 EFI 不可用，并以双网卡作为主路由。与本次做法对照：网卡类型是唯一导致失败的差异；我们使用的是 combined-efi 镜像，已能在 EFI 固件下开机进入命令行，所以 EFI 限制不适用于本镜像；单网卡旁路由与文档的双网卡主路由用途不同。结论是保留现有 VM，只把网卡换成 VMXNET3（vSphere 不能修改现有适配器类型，需删除后重新添加，MAC 会变化）。因为 DHCP 与 RA 已在配置中关闭，新网卡可以直接连接。台账 openwrt 的 network_adapter 改为 vmxnet3。

若更换网卡后 eth0 出现但 br-lan 没有地址，可能是首次开机时没有可识别网卡，生成的 /etc/config/network 未把 eth0 加入 br-lan，需要查看 `uci show network` 后补上。尚无更换后的输出。

## 70. 2026-10-16 OpenWrt 改为按官方文档的组合重建

用户报告按第 69 节更换网卡后，OpenWrt「好像坏了，开不了机」，未提供控制台画面或 vSphere 报错。最可能的解释是 EFI 启动项在删除和新增设备后失效，或者固件优先尝试从新网卡 PXE 启动，但未经证实。该 VM 没有需要保留的数据，不继续排查，改为按 wiki 文档已验证的组合重建：BIOS 固件、非 EFI 镜像、VMware 准虚拟（PVSCSI）控制器与 VMXNET3 网卡。磁盘导入继续采用描述文件加平面数据文件的上传方式，不需要 qemu 或 ESXi SSH。

本助手在 Mac 种子目录下载 openwrt-25.12.5-x86-64-generic-ext4-combined.img.gz，按 sha256sums 校验为 OK（23e2538e…4461，HTTPS 获取，签名未验证）。解压后为 126353408 字节，首扇区以 55aa 结尾（MBR 引导盘），SHA256 c1b1fd76…2416；补零到 1 GiB 作为 openwrt-bios-flat.vmdk，补零后前 126353408 字节的 SHA256 不变；描述文件 openwrt-bios.vmdk 为 2097152 扇区。MBR 分区表不存在 GPT 备份头的问题。旧 VM 及其已首启修改过的 openwrt-disk 文件夹不再使用，由用户从磁盘删除。新镜像同样默认启用 LAN DHCP 与 RA，首次开机仍须断开网卡，并先在控制台确认 eth0 存在。尚无重建输出。

## 71. 2026-10-16 OpenWrt 暂停；内部 CA 脚本与 Harbor 物料准备

用户按第 70 节重建 OpenWrt。第一张截图显示 `ip -br link` 只打印 BusyBox ip 的用法：OpenWrt 的 ip 是 BusyBox applet，不支持 -br。这是本助手给错了命令。因此第 69 节「没有 eth0」的观察可能同样出自这个原因；但 E1000E 驱动确实不在镜像中，两者可以同时成立。改用 `ls /sys/class/net` 后，第二张截图显示在 OpenWrt 内 `ping 192.168.9.1` 返回 Network unreachable，说明当时没有任何接口持有 192.168.9.0/24 的地址：uci 配置未生效或 eth0 未加入 br-lan，未进一步检查。用户决定暂停 OpenWrt，先做 CA 与 Harbor。待查命令为 `ip addr` 与 `uci show network`。

内部 CA（00.08.01）：新增 [create-ca.sh](../../pki/create-ca.sh) 与 [issue-cert.sh](../../pki/issue-cert.sh)，在管理 Mac 运行（OpenSSL 3.6.3）。根 CA 为 ECDSA P-384、10 年、pathlen 1，只签中间 CA；中间 CA 为 ECDSA P-384、5 年、pathlen 0，带关键的名称约束，只允许 internal.egon.top、.internal.egon.top 与 IP 192.168.9.0/24。私钥以 AES-256 加密，运行时输入口令，写在仓库外的 ~/cnpl-pki；仓库只保存公开证书 ops/00-preparation/pki/public/。服务端证书为 ECDSA P-256、825 天，每个服务单独私钥，SAN 写实际访问名称，并生成含中间 CA 的 fullchain。已存在的 CA 与证书不覆盖。

在临时目录用测试口令完整验证：第一次运行发现 OpenSSL 3 的 genpkey 口令参数应为 -pass 而不是 -passout，已修正。修正后根 CA 与中间 CA 生成且 verify OK；harbor.k8s.internal.egon.top（含 IP 192.168.9.12）证书签发且链验证通过，fullchain 含两张证书；为 evil.example.com 签发的证书在验证时报 `permitted subtree violation` 而失败，名称约束有效；重复运行拒绝覆盖；两个 CA 私钥均为 ENCRYPTED PRIVATE KEY。测试产物已删除，未在用户的 ~/cnpl-pki 生成任何文件。

Harbor 物料：GitHub 最新发布为 v2.15.4，提供 harbor-offline-installer-v2.15.4.tgz、sigstore 签名与 md5sum。Docker CE 的 el10 仓库元数据为 zstd 压缩，用 Python 3.14 的 compression.zstd 解析：docker-ce 3:29.9.1-1.el10、docker-ce-cli 1:29.9.1-1.el10、docker-buildx-plugin 0.38.0-1.el10、docker-compose-plugin 5.6.0-1.el10、containerd.io 2.4.2-2.el10（与节点一致，种子目录已有）。docker-ce 依赖 iptables-nft 或 iptables、nftables、container-selinux、containerd.io ≥ 2.1.5、tar、xz。四个 RPM 的 SHA256 已写入种子目录 docker-29.9.1-rpms.sha256。Harbor VM 计划为 esxi01、4 vCPU、8 GiB、另加 200G 数据盘、地址 .12；esxi01 的内存预计为节点 52 + dns 2 + openwrt 2 + harbor 8 + VCSA，仍在 128 GiB 内。Harbor 按官方方式使用 Docker 与 compose，只装在 Harbor VM，不进入 Kubernetes 节点。

待用户执行：运行 create-ca.sh 与 issue-cert.sh（harbor）；在 vSphere 克隆 harbor 并改地址、分发密钥；在 Mac 下载 Harbor 离线包与四个 Docker RPM。尚无输出。

## 72. 2026-10-16 失败与修正：CA 脚本在 macOS bash 3.2 下的两个缺陷

用户运行 create-ca.sh，在第 41 行报 `pass_out[@]: unbound variable` 后退出。失败发生在根 CA 私钥生成之前；本助手只读确认 ~/cnpl-pki 只有空目录与 root/root.cnf，没有私钥，可直接重跑。

缺陷一：macOS 自带的 bash 3.2 在 `set -u` 下展开空数组 `"${arr[@]}"` 会报 unbound variable（bash 4.4 起修复）。第 71 节的测试设置了 CNPL_PKI_PASS，数组非空，因此没有覆盖用户实际的交互输入路径。两个脚本的数组展开改为 `${arr[@]+"${arr[@]}"}`，并加注释说明；bash 3.2 下验证空数组展开为空、非空数组按元素展开。

缺陷二：修正缺陷一后复测，第 60 行报 `PKI?: unbound variable`。`$PKI` 后紧跟全角括号，与第 52 节收集脚本的问题相同：bash 3.2 在 UTF-8 下把多字节字符的首字节并入变量名。本助手写新脚本时没有沿用第 52 节的检查，属于重复犯错。已用脚本把紧邻非 ASCII 字符的变量统一改为 `${VAR}` 形式，扫描两个 PKI 脚本已无残留。

验证：在 /bin/bash 3.2、en_US.UTF-8 下以导出的测试口令完整运行 create-ca.sh，退出码 0，根 CA、中间 CA、verify、公开证书复制与指纹输出全部完成；issue-cert.sh 也能成功签发。交互输入口令的路径需要终端，无法在本助手的环境中端到端运行；但在无终端时，脚本已越过第 41 行，进入 openssl 的口令提示阶段，说明不再被数组展开阻断。一次复测因测试命令传递口令的方式不当而失败，与脚本无关。今后在 macOS 运行的 shell 脚本，发布前都以 /bin/bash 3.2 加 UTF-8 并覆盖空数组路径测试。尚未在用户的 ~/cnpl-pki 生成 CA。

## 73. 2026-10-16 内部 CA 建成；Harbor 部署自动化

用户运行修正后的 create-ca.sh 与 issue-cert.sh。本助手只读核对，不读取私钥内容：

- 根 CA：CN=CNPL Lab Root CA 2026，2026-10-17 至 2036-10-14（GMT），pathlen 1，SHA-256 指纹 04:39:0E:06:D8:FB:A9:54:A1:55:01:B0:BA:D2:3B:7B:59:62:AF:26:41:13:2B:0D:3B:A8:05:74:1A:B2:D8:14。
- 中间 CA：CN=CNPL Lab Issuing CA 2026，由根 CA 签发，有效期至 2031-10-16，pathlen 0，关键名称约束为 internal.egon.top、.internal.egon.top 与 192.168.9.0/24，指纹 36:51:42:E3:80:05:79:F9:9F:3D:E3:78:0D:EF:BD:A7:C2:1C:F3:AD:C2:7F:89:D0:30:2A:52:19:3E:88:D5:EC。
- Harbor 证书：SAN 为 DNS:harbor.k8s.internal.egon.top 与 IP:192.168.9.12，EKU serverAuth，有效期至 2029-01-19，经根 CA 与中间 CA 验证 OK；fullchain 含两张证书；server.key 与证书公钥一致。
- 两个 CA 私钥均为 ENCRYPTED PRIVATE KEY，三个私钥权限都是 0600，均位于仓库外的 ~/cnpl-pki。仓库中的公开证书由 0600 改为 0644。

00.08.01「内部 PKI 信任链、根私钥离线、签发权限分离」在管理端完成；分发信任（00.08.02）随 Harbor 与节点角色执行。用户尚未开始克隆 Harbor VM 与下载物料，本助手先编写部署自动化：

- service_vm 增加 service_vm_keep_containerd：为 true 时只移除 Kubernetes 入群工具与 crictl.yaml，保留 containerd、运行时盘、配置与 IPv4 转发，供 Docker 使用；DNS 仍走原来的完整清理路径（dns.yml 语法检查通过）。
- node_base 增加 ca_trust（标签 ca_trust）：把仓库中的公开根 CA 安装到 /etc/pki/ca-trust/source/anchors/，变化时执行 update-ca-trust extract。
- 新增 docker_host 角色：从管理端种子目录传输四个 Docker RPM 与 docker.gpg，rpm_key 导入并核对指纹 060A…9F35，dnf 本地安装并验签（iptables-nft 等依赖仍取自发行版软件源）；daemon.json 设置 json-file 日志上限与 live-restore。
- 新增 harbor 角色：数据盘只在恰好有一块 200 GiB、无分区、无文件系统的磁盘时才格式化为 XFS（标签 harbor-data），按 UUID 挂载到 /data；已带标签时直接复用。证书链与私钥从 ~/cnpl-pki 传到 /etc/harbor/tls（私钥 0600）。传输离线包并解压到 /opt/harbor；harbor.yml 以发行模板为基础，只替换 hostname、证书、私钥、管理员口令、数据库口令与 data_volume（no_log）。install.sh 只在 docker-compose.yml 不存在时运行；配置或证书变化时由处理器执行 prepare 与 docker compose up -d。firewalld 对 192.168.9.0/24 开放 443。管理员与数据库口令由 password lookup 在管理端 ~/.cnpl-secrets（0700，仓库外）随机生成，文件内容即完整口令。
- 新增 playbooks/harbor.yml：service_vm（保留 containerd）→ node_base → docker_host → harbor，随后在 Mac 上用内部根 CA 校验证书链访问 /api/v2.0/ping（Pong）、/api/v2.0/health（healthy）与 /v2/（401）。Mac 尚未使用内部 DNS，因此用 curl --resolve 指定地址。

本地验证：三个 playbook 的 syntax-check 通过，Harbor 任务列表完整。用五种模拟磁盘布局测试数据盘选择：只有「系统盘 + 运行时盘 + 一块新 200G 空盘」得到唯一候选；新盘已有文件系统、已有分区、容量为 100G 时没有候选，有两块 200G 空盘时得到两个候选，这些情况都会被断言拦下，不会格式化。

已知限制，均未在本次处理：Docker 默认不启用 SELinux 标签（selinux-enabled false），Harbor 容器以非受限域运行，主机仍为 Enforcing；Docker 发布的端口通过它自己的 nftables/iptables 规则放行，可能绕过 firewalld 的来源限制，目前依赖 VM 只接入实验 LAN；Trivy 未启用（00.09.06）；节点仍使用公共 DNS，不能用名称访问 Harbor，containerd 的 hosts.toml 也还没有配置（10.2）。尚无部署输出。

## 74. 2026-10-17 Harbor 部署卡在 Docker 依赖下载；改为全离线安装

用户首次运行 harbor.yml，在 docker_host「安装 Docker」一步停留数分钟。用户回传的 harbor 日志显示：/var/log/dnf.librepo.log 在 09:52:50（客体时间）开始从 mirrors.ustc.edu.cn 下载 BaseOS 元数据（primary、comps、updateinfo），之后没有新记录；dnf.log 显示 repo: downloading from remote: baseos；rpm -q 显示 iptables-nft 未安装，iptables-libs-1.8.11-13.el10 已安装。mirrors.ustc.edu.cn 正是第 51 节 worker01 失败时低于 1000 B/s 的镜像。

本助手在 Mac 读取 Rocky 10.2 官方元数据：docker-ce 29.9.1 的全部依赖中，除 iptables-nft 外均为模板已有的系统组件（glibc、libsystemd、shadow-utils 的 groupadd、nftables、tar、xz、container-selinux、containerd.io）。iptables-nft 位于 AppStream，有 1.8.11-13.el10、-15.el10_2 与 -16.el10_2 三个版本。-13 与已装的 iptables-libs-13 匹配，但带有 `(kernel-modules-extra if kernel-modules-core)` 富依赖，会要求额外的大型内核模块包；-15/-16 没有该依赖，但要求同版本的 iptables-libs。因此选用 iptables-nft-1.8.11-16.el10_2 与 iptables-libs-1.8.11-16.el10_2（SHA256 a8072c48…dfc9 与 b2d94196…720c，取自官方 primary 元数据，写入种子目录 rocky-iptables-1.8.11-16.sha256），由系统已有的 Rocky 公钥验签。

docker_host 角色改为传输并离线安装 Docker 四个 RPM 与这两个依赖包，dnf 使用 disablerepo='*'，不再访问镜像站。注意：Harbor VM 的 iptables-libs 将从 -13 更新到 -16，与十个节点的版本不同。harbor.yml 语法检查通过。当前运行中的 dnf 仍处在下载元数据阶段，尚未进入事务，中断是安全的；重跑时已完成的步骤会跳过。尚无重跑输出。

## 75. 2026-10-17 Harbor 服务端部署完成；管理端验证因剧本缺陷未执行

用户报告 harbor.yml 执行完毕且「都是 ok 的」。本助手读取 [Harbor 部署证据](evidence/00.09.02-harbor-deploy.txt)：harbor ok=47 changed=29 failed=0 skipped=15，其中 Docker 安装、数据盘格式化（XFS，标签 harbor-data）、按 UUID 挂载 /data 与首次安装 install.sh 均为 changed。第 74 节的离线安装改动当时尚未告知用户，这次运行仍按原方式从镜像站取得依赖并成功完成，未被中断。

但 localhost ok=0 failed=1：管理端验证的第一个任务报 `'inventory_dir' is undefined`。隐式 localhost 不在 inventory 中，没有 inventory_dir，是本助手的剧本缺陷，与 Harbor 无关。因此 ping、health 与 /v2/ 401 三项验证都没有执行，「都是 ok」不成立，Harbor 的 HTTPS 与证书链尚未从管理端验证。已改为 `hostvars['harbor']['inventory_dir']`，本地确认路径可解析到根 CA 文件，syntax-check 通过。

种子物料核对：harbor-offline-installer-v2.15.4.tgz 共 747317006 字节，md5 1dab0faa…dc99 与发布页 md5sum 一致；本地 SHA256 为 ec4152a6…5ccfc；sigstore 签名已下载，未用 cosign 验证。补下载的 iptables-libs 与 iptables-nft 1.8.11-16.el10_2 两个 RPM 按种子目录校验文件均为 OK。管理端 ~/.cnpl-secrets 下已生成 harbor_admin_password 与 harbor_db_password（0600）。版本锁新增 harbor v2.15.4（installed_unvalidated）与 registry_runtime（Docker 29.9.1 及 iptables 依赖），台账 harbor 记为 deployed、验证待重跑。

Harbor VM 实际安装的 iptables-nft 版本未取证；重跑时 docker_host 会用种子目录的 -16 版离线安装，若当前为 -13 则会更新。下一步重跑完整 harbor.yml：同时完成管理端三项验证，并检查服务端第二次执行的变更（预期只有 docker_host 新增的两个依赖 RPM 传输，以及可能的 iptables 更新）。

## 76. 2026-10-17 安全修正：--diff 把 Harbor TLS 私钥写入证据文件

用户要求提交。提交前的检查发现 00.09.02-harbor-deploy.txt 中有一个 PEM 私钥块：部署命令带 --diff，harbor 角色传输 /etc/harbor/tls/server.key 的 copy 任务把文件内容作为差异打印出来，tee 随之写入证据文件。管理员与数据库口令的替换任务设置了 no_log（日志中为 censored），私钥传输任务却遗漏了同等保护。这是本助手的缺陷。

处理：用脚本把证据中的私钥块整体替换为脱敏说明，过程中不输出原内容，替换 1 处；全仓库扫描已无私钥内容（执行记录中只有描述私钥格式的文字）。harbor 角色的证书与私钥传输任务增加 `diff: false`，以后即使带 --diff 也不打印。复查其余带 --diff 的传输任务：Docker RPM 为二进制，docker.gpg 与根 CA 为公开内容，harbor.yml 模板复制时尚未写入口令，均不涉及秘密。

影响评估：该文件未提交、未推送，私钥只出现在管理端本地的这个文件和用户终端的滚动记录中；同一私钥本来就以明文形式保存在同一用户主目录的 ~/cnpl-pki 中，因此没有产生新类别的暴露。暂不轮换证书；若终端记录或该文件曾被复制到其他位置，应使用 issue-cert.sh 重新签发并重跑 harbor.yml。今后部署记录先检查 PEM 与口令再提交，后续涉及私钥的任务一律加 diff: false 或 no_log。

## 77. 2026-10-17 Harbor 验证仍失败：管理端代理拦截内部域名；后续节点与镜像自动化

用户报告重跑「脚本成功了」，并要求继续，同时希望在 Mac 上登录 Harbor。本助手读取 [重跑证据](evidence/00.09.02-harbor-verify.txt)：harbor ok=37 changed=2 failed=0 skipped=20，只有 docker_host 新增的两个 iptables RPM 传输与本地安装为 changed，其余服务端任务均无变化，第二次执行符合预期。但 localhost failed=1：访问 /api/v2.0/ping 重试 12 次，均报 `curl: (35) LibreSSL SSL_connect: SSL_ERROR_SYSCALL`。因此「成功」不成立，Harbor 仍未从管理端验证。

原因：管理端 shell 设置了 HTTPS_PROXY/HTTP_PROXY（Clash，127.0.0.1:7897），而 NO_PROXY 只有 localhost、127.0.0.1、::1、.local。curl 经代理发送 CONNECT harbor.k8s.internal.egon.top:443，Clash 无法解析内部域名，随即断开连接；--resolve 只作用于直连，对经代理的请求无效。macOS 系统代理的例外列表包含 192.168.0.0/16，但不包含 *.internal.egon.top，浏览器按名称访问会遇到同样的问题。第 67 节的 DNS 验证使用 dig，不经代理，因此未受影响。

修正：harbor.yml 的三个 curl 都加 `--noproxy '*'`，验证局域网直连路径，不受管理端代理设置影响。Mac 端需要用户处理：/etc/resolver/internal.egon.top 指向 192.168.9.11（00.07.02）；把根 CA 加入登录钥匙串并设为信任（浏览器与 crane 使用，Go 在 macOS 上使用系统钥匙串，不读取 SSL_CERT_FILE）；在 Clash Verge 的系统代理绕过中加入 *.internal.egon.top；在 shell 的 NO_PROXY 中加入 .internal.egon.top 与 192.168.9.0/24。

同时编写后续自动化（均已通过 syntax-check）：

- node_base 新增 dns（标签 dns）：DNS 地址取自 networks.yaml 的 planned_dns_servers（.11），搜索域 k8s.internal.egon.top；值不同时用 nmcli 修改连接，并以 `nmcli device reapply` 生效（不断开链路、不改变地址），随后用 getent 确认能解析 harbor 与 rockylinux.org。DNS 服务器自身跳过（本地确认 cp01、harbor 应用，dns 跳过）。只配置内部 DNS，单点风险如实保留。
- container_runtime 新增 Harbor 的 /etc/containerd/certs.d/harbor.k8s.internal.egon.top/hosts.toml：capabilities 为 pull、resolve，ca 指向系统锚点中的根 CA；containerd 按 config_path 动态读取，无需重启；只配置端点与信任，不提供认证。
- 新增 playbooks/harbor-bootstrap-images.yml：管理端用 Harbor API 创建公开项目 bootstrap（已存在时返回 409 视为成功，no_log）；crane 以 --password-stdin 登录（no_log）；按版本锁 kubeadm.required_images_v1_36_5 以 --platform linux/amd64 复制七个镜像，coredns/coredns 映射为 bootstrap/coredns，符合 kubeadm 对自定义仓库的约定（本地确认映射正确）；逐一比较源与目标摘要。随后十个节点执行 `kubeadm config images pull --image-repository harbor.k8s.internal.egon.top/bootstrap`，经 CRI 从 Harbor 预拉，即手册 10.2 路线。源仓库经代理访问，Harbor 通过 NO_PROXY 直连。

尚未处理：containerd 的 pinned_images.sandbox 仍是 registry.k8s.io/pause:3.10.2，与 kubeadm 在自定义仓库下期望的 Harbor 路径不同，init 时会出现 sandbox 镜像不一致告警；手册第 8 节要求 Harbor 投产后改为固定 Digest 并重做自测，留到下一步。公开项目允许匿名拉取，依赖 Harbor 只在实验 LAN 中可达；只读机器人账号留待后续。crane 登录凭据会写入管理端 ~/.docker/config.json。尚无执行输出。

## 78. 2026-10-17 更正：Harbor 服务未正常运行，不是管理端代理问题

用户按第 77 节设置 Mac：/etc/resolver/internal.egon.top 生效，系统解析 harbor.k8s.internal.egon.top 为 .12；根 CA 已加入登录钥匙串（SHA-256 04390E06…D814，trust settings 为空，即对所有用途作为根信任）；~/.zshrc 已追加 NO_PROXY。macOS 系统代理例外中没有 *.internal.egon.top，用户在 Clash Verge 中找不到代理绕过设置。本助手查到 Clash Verge 开启了 enable_proxy_guard，proxy_guard_duration 为 30，会定期重置系统代理，因此 networksetup 的修改会被覆盖；随后由用户退出 Clash Verge，备份 verge.yaml，并把 system_proxy_bypass 从 null 改为 '*.internal.egon.top'（use_default_bypass 为 true，保留默认列表；TUN 模式关闭）。

用户反映域名和 IP 都无法访问。直接用 IP 访问不经代理，说明第 77 节「SSL_ERROR_SYSCALL 由代理导致」的结论不完整。只读诊断见 [诊断证据](evidence/00.09.02-harbor-diagnose.txt)：Mac 到 192.168.9.12:443 为 Connection refused；harbor 上 `ss -lntp` 没有 80/443 监听，本机经 127.0.0.1 访问 443 同样被拒绝。部署约 27 分钟后，harbor-core 为「Up 51 seconds (health: starting)」，即在反复重启；harbor-jobservice 为 Restarting (2)；harbor-db、redis、registry、portal、nginx 仍为 health: starting；只有 harbor-log 与 registryctl 为 healthy。nginx 映射 0.0.0.0:443->8443，但主机上没有对应监听。firewalld 中 docker 区域包含 docker0 与 harbor 网桥，public 区域有对 192.168.9.0/24 放行 443 的富规则。

结论：Harbor 服务端没有正常运行，这才是两次管理端验证失败与浏览器无法访问的直接原因；第 77 节把 SSL_ERROR_SYSCALL 归因于代理，是在没有先查看服务端状态时下的结论。管理端代理确实也会拦截内部域名，对应的修正保留。根因尚未确定，可能与容器间网络、数据库初始化、Docker 端口发布方式或 SELinux 有关，均未证实。下一步只读收集 docker-proxy、docker info、健康检查最近一次结果、/var/log/harbor 下各组件日志、AVC 与 docker 服务日志。

## 79. 2026-10-17 Harbor 未运行的原因：Docker 在 Harbor 安装后才重启（live-restore）

第二次只读诊断见 [诊断证据](evidence/00.09.02-harbor-diagnose-2.txt)。harbor-core 日志反复出现 `dial tcp: lookup redis on 127.0.0.11:53: no such host`，即容器内置 DNS 无法解析同一 compose 网络中的服务名 redis；dockerd 日志对应地把 `redis.` 的查询转发到外部 8.8.8.8。jobservice 因连不上 core:8080 而 panic，重启计数为 core 23 次、jobservice 37 次。postgres 与 redis 进程本身正常。harbor-db、redis、nginx 的健康状态为 starting，FailingStreak 为 0，Log 为空，说明健康检查从未执行。主机上只有 127.0.0.1:1514 的 docker-proxy，没有 80/443 的转发进程。无 AVC；Docker 防火墙后端为 iptables+firewalld，cgroup v2 与 systemd 驱动；daemon.json 含 `"live-restore": true`。

对照[部署证据](evidence/00.09.02-harbor-deploy.txt)的执行顺序：docker_host 写入 daemon.json 后，「重启 docker」作为处理器被推迟到 play 末尾执行，此时 harbor 的 install.sh 已经创建并启动了全部容器；随后 harbor 处理器执行 `./prepare && docker compose up -d`，但配置未变，compose 没有重建容器。判断（推断，与证据一致，未单独复现）：dockerd 在 live-restore 下重启后续接了运行中的容器，但这些容器在 compose 网络内置 DNS 中的名称记录、健康检查与发布端口的转发没有恢复，于是出现上述现象。这是本助手编写角色时处理器顺序的缺陷。

修正：

- docker_host 末尾增加 `meta: flush_handlers`，daemon.json 有变化时在安装任何应用之前重启 Docker。
- daemon.json 去掉 live-restore。单机 Harbor 不需要在 dockerd 升级或重启时保持容器运行，去掉后行为更可预期。
- harbor 角色在 install.sh 之后增加一次幂等的 `docker compose up -d`：已运行时不做改动，容器缺失或停止时创建并启动。
- 管理端验证的重试从 12 次增加到 30 次（间隔 10 秒），覆盖首次启动时数据库初始化所需的时间。

本地 syntax-check 与 list-tasks 已通过：「在部署应用前让 Docker 配置生效」位于 Docker 启动之后、Harbor 任务之前。现有错误状态的容器需要先由用户执行 `docker compose down` 删除（数据在 /data 的绑定挂载中，不删除；没有使用 -v），再重跑 harbor.yml：daemon.json 变化后 Docker 在空载时重启，compose 重新创建容器，最后执行管理端验证。尚无执行输出。

## 80. 2026-10-17 重建 Harbor 中断：harbor 改用内部 DNS 后外部名称解析失败

用户按第 79 节执行。`docker compose down` 成功。重跑 harbor.yml 时，node_base 新增的 dns 任务（第 77 节）首次作用于 harbor：nmcli 把 DNS 改为 192.168.9.11、搜索域改为 k8s.internal.egon.top，并执行 reapply（changed）。随后的解析确认中，harbor.k8s.internal.egon.top 解析成功，rockylinux.org 失败（getent rc=2，耗时约 1.5 秒），play 在 node_base 中止（ok=22 changed=2 failed=1），docker_host 与 harbor 均未执行。因此容器没有重建，用户第三条 `docker compose ps` 为空、`ss | grep` 返回 1，见[证据](evidence/00.09.02-harbor-recreate.txt)。

现状：harbor 的 DNS 已经切换到内部 DNS，没有回退。内部名称可用，说明网络与 53 端口可达。外部名称失败的原因未确定：00.07.01 部署时从管理端 dig rockylinux.org 成功，但从节点经 BIND 递归尚未验证过。可能的原因包括转发器（223.5.5.5、8.8.8.8）在 dns VM 上不可达、DNSSEC 验证失败或 BIND 递归异常，均未证实。检查任务按设计在切换后立即暴露问题，这是期望的行为。Harbor 自身运行不依赖外部解析（容器之间由 Docker 内置 DNS 解析），可以先用 `--skip-tags dns` 恢复 Harbor；十台 Kubernetes 节点在外部解析修好之前不切换 DNS。下一步对 harbor 与 dns 只读采集 resolv.conf、经各服务器的 dig 结果与 named 日志。

## 81. 2026-10-17 Harbor 重建并通过管理端验证；内部 DNS 外部解析失败的原因是 DNSSEC 验证

**Harbor**：用户以 `--skip-tags dns` 重跑 harbor.yml，见[证据](evidence/00.09.02-harbor-recreate-2.txt)。daemon.json（去掉 live-restore）为 changed，「重启 docker」在 docker_host 末尾的 flush_handlers 处执行，早于 Harbor 任务，顺序符合第 79 节的修正。install.sh 已安装而跳过，新增的 `docker compose up -d` 为 changed，重新创建了全部容器。管理端验证全部通过：/api/v2.0/ping 返回 Pong；/api/v2.0/health 在一次重试后为 healthy；/v2/ 未认证时返回 401。harbor failed=0，localhost failed=0。这是 Harbor 第一次从管理端经内部根 CA 校验证书链并通过 API 验证，第 79 节的推断得到间接支持：重启顺序改正后问题没有再出现。证据中没有私钥块。

**DNS**：只读诊断见[证据](evidence/00.07.03-dns-external-diagnose.txt)。harbor 经 192.168.9.11 查询 rockylinux.org 为 SERVFAIL，直接查询 223.5.5.5 与 8.8.8.8 均为 NOERROR（76.223.126.88）。dns VM 上经本机 named 查询为 SERVFAIL，加 +cd（不做验证）则为 NOERROR，说明递归与转发本身正常，失败来自 DNSSEC 验证。named 日志中对根、org、in-addr.arpa 都报 `got insecure response; parent indicates it should be secure`、`no valid RRSIG`、`broken trust chain`，两个转发器表现相同。

判断：到上游的路径（家庭路由器或运营商）会拦截或改写 53 端口的查询，去掉 DNSSEC 签名，因此本地验证对所有已签名区域都会失败。两个不同的公共转发器同样缺少根区签名，这一判断有较强依据，但拦截发生在哪一跳未证实。00.07.01 从管理端 dig rockylinux.org 能成功的原因未确定，可能是当时的缓存或拦截时有时无。

修正：named.conf 改为 `dnssec-validation no`。主配置变化的处理器从 reload 改为 restart，因为 reload 会保留缓存，按旧策略缓存的验证失败结果不会立即清除；区域文件变化仍为 reload。取舍如实记录：外部应答的可信度等同于上游转发器及其路径，本地不再能发现篡改。内部区域由本服务器权威应答，不受影响。若以后需要恢复验证，可以改用 DoT 转发，绕过 53 端口的拦截，届时再评估 BIND 版本是否支持。此外日志显示 Docker 网桥的反向查询（如 1.0.18.172.in-addr.arpa）与 jobservice 这类单标签名称会被转发到公共 DNS，不影响功能，暂不处理。本地 syntax-check 通过，尚无执行输出。

## 82. 2026-10-17 Mac 浏览器：IP 可以访问 Harbor，域名不行；系统层面已确认正常

用户报告浏览器用 IP 能打开 Harbor，用域名打不开，并指出 Mac 是经 USB 网卡接入实验网的。本助手在管理端只读确认：

- 网络：默认路由走 Wi-Fi（en0，网关 192.168.0.1），这是主服务。到 192.168.9.0/24 的路由走 USB 网卡（en5，192.168.9.200）。macOS 对所有连接使用主服务的代理设置。scutil --proxy 的有效配置为 Clash 127.0.0.1:7897，例外列表已包含 *.internal.egon.top。USB 网卡服务本身没有配置代理，不需要修改。
- 解析：dscacheutil 把 harbor.k8s.internal.egon.top 解析为 192.168.9.12，scutil --dns 中有 internal.egon.top → 192.168.9.11 的作用域解析器。
- 访问：在 shell 中按域名直连，/api/v2.0/ping 返回 200；http:// 返回 308，跳转到 https。证书链由系统信任通过。
- 浏览器设置：Chrome 与 Brave 的 Local State 中都没有自定义安全 DNS；Chrome 没有 DNS 或代理相关的托管策略。

结论：系统层面的解析、代理例外、路由与证书都正常，问题出在浏览器内部，可能是切换前缓存的失败结果或代理状态，尚未确定。下一步请用户用 Safari 对照，清空浏览器的主机缓存或彻底重启浏览器，并提供浏览器显示的错误码。

## 83. 2026-10-17 内部 DNS 修复、十节点切换 DNS/CA/hosts.toml、引导镜像经 Harbor 预拉；转入 10.2 路线

用户确认 Mac 浏览器已能按域名打开 Harbor（第 82 节的浏览器问题随之消失，具体原因未确认，最可能是浏览器缓存了之前失败的结果），并执行了第 81 节的四步：

1. [dns.yml](evidence/00.07.03-dns-fix.txt)：dns ok=30 changed=4，即 named.conf（dnssec-validation no）、根 CA 首次写入 dns VM 的系统信任及两个处理器（更新系统信任、重启 named）。管理端验证中内部名称、外部递归 rockylinux.org 与权威应答全部通过。同一文件中 `harbor.yml --tags dns` 为 ok=2 changed=0：harbor 能解析内部与外部名称。
2. [bootstrap-nodes.yml --tags dns,ca_trust,runtime](evidence/00.09.03-nodes-dns-ca-harbor.txt)：十台均为 ok=16 changed=6 failed=0。变更依次为根 CA 锚点、nmcli 改 DNS、更新系统信任、reapply、certs.d/harbor 目录与 hosts.toml。其余运行时任务无变化，containerd 未重启。十台的 getent 都解析成功（harbor 与 rockylinux.org）。
3. [harbor-bootstrap-images.yml](evidence/00.09.03-bootstrap-images.txt)：bootstrap 项目可用（创建或已存在），crane 登录成功；七个镜像复制完成，源与目标的平台摘要逐一相等。十台都执行了 `kubeadm config images pull --image-repository harbor.k8s.internal.egon.top/bootstrap` 且 failed=0，即每台节点都经 CRI、内部 DNS、hosts.toml 与内部根 CA 从 Harbor 拉取了全部控制面镜像。这是 Harbor 拉取路径的第一次十节点证据。
4. 三份证据中均没有私钥块。

接着按手册第 8 节与第 10.2 节切换 sandbox 镜像，并重做 CRI 自测：

- 版本锁：pause 与 cri_smoke_image 的 internal_source 填为 Harbor 中按平台 Digest 的引用（pause@sha256:412c4a72…、busybox@sha256:7d31f97b…）。由于 `crane copy --platform linux/amd64` 只复制该平台的清单，Harbor 中的 Digest 等于版本锁中的 platform_manifest_digest，而不是 index_digest。
- 镜像剧本：在复制列表中加入 CRI 自测镜像（映射为 bootstrap/busybox:1.38.0-1），新增一项检查：按 Digest 引用能在 Harbor 中取到，且等于版本锁记录的平台 Digest。本地已确认映射与查找结果正确。
- containerd config.toml：增加 `pinned_images.sandbox = harbor.k8s.internal.egon.top/bootstrap/pause@sha256:412c…`。取舍：本地缺少该镜像时，新 sandbox 依赖 Harbor 可用。
- cri-smoke.sh 增加 SMOKE_PULL=yes：先经 CRI 拉取自测镜像，记录 smoke_pull。采集脚本在版本锁有 internal_source 时，传入 Harbor 的 Digest 引用并要求拉取成功；sandbox 期望值同样取 pause 的 internal_source。
- node-readiness 新增 sandbox_image（containerd config dump 中实际生效的 pinned_images.sandbox）、sandbox_image_present，以及 DNS 一项（期望为 planned_dns_servers）。矩阵的「sandbox 镜像」检查改为比对实际生效的引用，不再只看镜像列表。用最近一次 cp01 采集加上合成字段做了本地测试，通过 26/26。

尚无执行输出。下一步由用户依次执行：复制剧本（补自测镜像并核对 Digest）、`bootstrap-nodes.yml --tags runtime`（config.toml 变化，十台重启 containerd）、`collect-node-readiness.sh --with-cri-smoke`，最后对 bootstrap-nodes.yml 全量 `--check` 确认幂等。

## 84. 2026-10-17 10.2 路线通过：sandbox 切换为 Harbor Digest，十节点经 Harbor 拉取的 CRI 自测 PASS；DNS 检查发现 IPv6 RA 下发的 DNS

用户执行第 83 节的四步：

1. [镜像剧本](evidence/00.10.02-harbor-images-pinned.txt)：八个镜像复制完成（新增 busybox），源与目标的摘要逐一相等。按 Digest 引用的 pause@sha256:412c4a72… 与 busybox@sha256:7d31f97b… 都能在 Harbor 中取到，且等于版本锁记录的平台 Digest。十台再次预拉，failed=0。
2. [bootstrap-nodes.yml --tags runtime](evidence/00.10.02-sandbox-harbor.txt)：十台均为 ok=11 changed=2，即 config.toml 与「重启 containerd」处理器，其余无变化。
3. [十节点矩阵](evidence/00.10.02-node-readiness-20261016-231349/matrix.md)（含 CRI 自测）：十台均为 26/27。sandbox_image 为实际生效的 Harbor Digest 引用，且镜像在本地。smoke_image 为 Harbor 中的 busybox Digest 引用，smoke_pull=ok，即经 CRI、内部 DNS、hosts.toml 与内部根 CA 从 Harbor 拉取成功。CRI 自测全部 PASS：sandbox 为 SANDBOX_READY，网络为 NODE，pause 进程标签为 container_t，容器正常退出（退出码 0），日志为 phase00-cri-ok，AVC 为 0，清理完成。六项身份字段唯一，没有 .err 文件。手册 10.2 要求的「registry 配置、CA 信任」验收证据由此产生。只读认证未验收：bootstrap 为公开项目，拉取是匿名的。
4. [全量检查模式](evidence/00.11-bootstrap-check.txt)：十台均为 ok=34 changed=0 failed=0，基线、防火墙、journald、CA、DNS、运行时全部幂等。

唯一的未通过项是新增的 DNS 检查：十台的 resolv.conf 都是 `192.168.9.11,fd5c:c6b4:3ca2::1`。第二个地址是家庭路由器经 IPv6 RA 下发的 ULA DNS。NetworkManager 只替换了 IPv4 DNS，IPv6 的自动 DNS 仍然写入 resolv.conf。影响：内部 DNS 超时时，glibc 会转而查询路由器，内部名称就会失败，解析结果不确定。harbor 的 resolv.conf 中没有这一项（原因未查）。新增检查发现了第 83 节「十台 getent 成功」没有暴露的问题。

修正：node_base dns 任务增加 `ipv6.ignore-auto-dns yes`，只忽略 IPv6 自动 DNS，不关闭 IPv6（手册第 7 节明确不盲目关闭 IPv6），幂等判断加入该字段。新增「resolv.conf 中只有内部 DNS」的检查。node-readiness 增加 ipv6_global，只作记录，供 01 选择节点地址时参考。

新增 playbooks/reboot-nodes.yml（手册第 11 节）：serial 1、any_errors_fatal，每次重启一台，失败即停止。重启后等待 systemd 完成启动，判定 SELinux、firewalld、DNS、失败单元，Kubernetes 节点另查运行时盘与 containerd；`-e target=dns,harbor` 可用于基础服务。完整复查仍由矩阵完成。本地 syntax-check 与表达式测试通过。下一步：dns 标签修正，然后逐台重启十节点并在重启后采集矩阵（含 CRI 自测），再重启 dns 与 harbor 并验证 Harbor。

## 85. 2026-10-17 提交；继续 Phase 00 剩余项，从 OpenWrt 旁路由开始

用户要求提交，并决定在进入 01 之前完成 GitLab、Nexus、OpenWrt/VPN、独立备份与恢复演练、断网验收。提交 f4ea193（分支 phase00/harbor-registry-route，快进合并到 main，未推送）包含第 79–84 节涉及的角色、剧本、脚本、台账与证据。提交前检查：没有 PEM 私钥块；用 grep -F -f 以两个 Harbor 口令文件比对，没有匹配，过程中不输出口令内容；口令相关的行只剩 harbor.yml 模板替换（引用变量）。用户提交时正在执行的 00.07.03-nodes-ipv6-dns.txt 与 00.11-reboot-nodes.txt 未纳入，待读取后随下次提交。

顺序：OpenWrt 旁路由与显式代理（00.05、00.06.02）放在最前，因为 GitLab、Nexus 与上游代理缓存的物料下载都依赖它。之后依次为 Harbor 上游代理缓存、GitLab、Nexus、独立备份与恢复、断网验收。

用户提供一篇 ESXi 部署 OpenWrt 软路由的博客。对照本实验的单网卡显式代理旁路由：

- 适用：客户机类型选 Other Linux 5.x 或更高版本 64 位；网卡选 VMXNET3（第 69 节已核实 25.12.5 内核内置该驱动）；用 uci 设置 LAN 地址；禁用声卡与 USB；从硬盘启动。
- 不适用：双网卡 WAN/LAN 是主路由形态，本实验默认网关保持 .1，单网卡即可，00.05.04 只保留双接口的升级路径。在 vSphere 界面添加 VMXNET3 与改 .vmx 效果相同，第 69 节的失败是网卡类型错误，不是添加方式的问题。
- 不采用：「把 zone 的 input、forward 设为 ACCEPT」会放开 WAN 区域；显式代理只需要 LAN 区域的入站，默认已允许。博客推荐的第三方证书平台不需要：内部服务使用内部 CA，不把内网名称提交给外部服务。
- 内存：128 MB 只够转发，运行 mihomo（Clash 内核）与规则集需要更多，台账的 2 GiB 可降为 1 GiB。

第 71 节的「Network unreachable」有一个此前未考虑到的可能原因：第 68、70 节要求首次开机前断开网卡。如果之后没有在 vSphere 中重新勾选「已连接」，br-lan 没有载波，netifd 不会让 lan 接口启用，地址与路由都不存在，ping 网关就会报 Network unreachable。这只是推断，需要用 vSphere 网卡状态与 `ip addr` 确认。下一步：控制台关闭 LAN 的 DHCP 与 RA，设置 .10、网关与 DNS，在 vSphere 确认网卡已连接，设置 root 口令（用户输入），再从 Mac 用 SSH 继续。

## 86. 2026-10-17 重启复验通过；Harbor 验证命令错误；IPv6 DNS 需重新激活；OpenWrt 掩码笔误；GitLab、Nexus、备份 VM 规划

**IPv6 DNS 修正**（[证据](evidence/00.07.03-nodes-ipv6-dns.txt)）：十台的 nmcli modify 与 reapply 均为 changed，但随后的检查全部失败：resolv.conf 仍是 `192.168.9.11,fd5c:c6b4:3ca2::1`。`nmcli device reapply` 写入了 ipv6.ignore-auto-dns，但不会清除已从 RA 学到的 IPv6 DNS，要等连接重新激活才生效。harbor 没有这一项，ok=5 changed=2 failed=0。检查任务改为 assert，失败时说明原因与处理方法（重启后重跑），不在剧本中重新激活连接，因为经 SSH 重新激活连接有中断会话的风险。

**十节点逐台重启**（[证据](evidence/00.11-reboot-nodes.txt)）：serial 1，十台都在 10 分钟内恢复 SSH。重启后的 boot_id 各不相同；SELinux 为 Enforcing，firewalld 为 running，DNS 只剩 192.168.9.11（IPv6 DNS 随重启清除），失败单元为空，运行时盘为 xfs，containerd 为 active。重启后的[矩阵](evidence/00.10.02-node-readiness-20261016-234651/matrix.md)（含经 Harbor 拉取的 CRI 自测）十台均为 27/27，总体全部通过，没有 .err 文件。ipv6_global 十台都为空：路由器只下发了 RDNSS，没有分配全局地址。00.10.02 要求的「重启后结果一致」由此产生证据。

**dns 与 harbor 重启**（[证据](evidence/00.11-reboot-services.txt)）：两台都通过。dns 的 DNS 仍是 8.8.8.8、223.5.5.5（DNS 服务器自身，预期如此），containerd 为 inactive（service_vm 已停用），没有失败单元；harbor 的 containerd 为 active（Docker 使用），运行时挂载点为 xfs。后半条 `harbor.yml --limit localhost` 报错，证据中没有它的输出，因为错误写在 stderr，没有经过 tee。原因：隐式 localhost 不在 inventory 中，`--limit localhost` 让 ansible-playbook 认为没有可执行的主机，直接退出。这条命令由本助手给出，未经验证。修正：管理端验证拆为 playbooks/verify-harbor.yml，harbor.yml 末尾用 import_playbook 导入，可单独运行。Harbor 重启后的 API 验证尚未执行。

**OpenWrt**（[证据](evidence/00.05.02-openwrt-network.txt)）：25.12.5 r33051；br-lan 包含 eth0，UP 且有载波；DHCP 已关闭（ignore=1），dhcpv6 与 ra 为 disabled。问题在于 network.lan.netmask 为 `225.225.225.0`，是 255 的笔误：内核将其按 /3 处理，地址为 192.168.9.10/3，路由为 192.0.0.0/3 直连。223.5.5.5 落在 192.0.0.0/3 之内，OpenWrt 把它当作同一链路上的主机直接 ARP，不经网关，所以 ping 全部丢失。网关与 Mac 在同一 /24 内，仍可访问，SSH 也因此能登录。network.lan.dns 为 192.168.9.1，nslookup 超时，未单独查原因，改用内部 DNS .11。第 85 节「网卡未连接」的推断不成立。

新增 ops/00-preparation/openwrt/：

- apply-base.sh：在 OpenWrt 上经 SSH 执行。设置主机名与时区；地址 .10/24、网关 .1、DNS .11；删除 ip6assign；关闭 LAN 的 DHCP、DHCPv6 与 RA，停用 odhcpd；dropbear 只用密钥、只监听 LAN。只在值不同时写入（uci set 即使值相同也记录变更），有变更才提交与重载，最后输出地址、路由与连通性。该脚本必须经密钥登录执行：执行即说明密钥可用，再关闭口令登录不会把自己锁在外面；控制台与 LuCI 仍可用 root 口令。
- mihomo/：显式代理配置模板与 procd 服务。mixed-port 7890 只绑定 .10，lan-allowed-ips 为 192.168.9.0/24 与本机；内部域名与私有地址直连，其余走订阅节点（url-test）。不使用 GEOIP，因为首次运行要从 GitHub 下载地址库。订阅地址只存在 OpenWrt 的 /etc/mihomo/subscription-url（0600），服务启动时用 awk 的 index/substr 做纯文本替换（本地用含 `& | / \1` 的测试地址验证），生成到 tmpfs，并先 `mihomo -t` 校验。
- install-mihomo.sh（管理 Mac）：mihomo v1.19.32 linux-amd64-compatible（GOAMD64 v1）。SHA256 ba3ce607… 取自 GitHub Releases 页面为该资产显示的摘要；GitHub API 因代理出口共享被限流，改为解析发布页，项目没有提供签名。下载到种子目录并校验，经 SSH 写入；有订阅文件时启用服务；输出的日志把 URL 替换为 `<url>` 再写入证据。
- 版本锁：openwrt 记为 25.12.5（BIOS 镜像 sha256 23e2538e…），新增 proxy_core（mihomo）。台账 openwrt 内存从 2 GiB 改为 1 GiB。

**新 VM 规划**：用户决定 GitLab、Nexus 与备份都放在 esxi01，备份只为学习，不追求严谨。台账：gitlab .13（4 vCPU、16 GiB、数据盘 150 GiB），nexus .14（4 vCPU、8 GiB、250 GiB），新增 backup.mgmt.internal.egon.top .16（2 vCPU、2 GiB、500 GiB），reserved_endpoints 中 independent_backup 的 .16 让出。三块数据盘大小互不相同，也不等于模板运行时盘的 100 GiB，便于角色按「唯一大小、无分区、无文件系统」选盘，沿用 harbor 的做法。偏差如实记录：备份与被备份的服务在同一台物理宿主机，不满足 00.10.03「独立备份」的定义，验收中标为偏差。DNS 区域序号递增为 2026101701，下一次 dns.yml 会加入 backup 的 A 与 PTR 记录。inventory 重新生成后没有变化（新 VM 为 planned）。尚无执行输出。

## 87. 2026-10-17 Harbor 重启后未恢复；OpenWrt 基线完成；写入订阅的命令「卡住」

用户执行第 86 节的步骤，并报告写入订阅地址的命令「一直卡着」。

- **Harbor**（[证据](evidence/00.11-reboot-services.txt) 后半部分）：verify-harbor.yml 重试 30 次（5 分钟）均为 `curl: (7) Failed to connect ... port 443`，localhost failed=1。harbor 重启后，443 不可连接。第 86 节「dns 与 harbor 重启都通过」只是重启剧本的系统级判定（SELinux、firewalld、DNS、失败单元），不包含 Harbor 服务本身，结论需据此收窄：harbor VM 重启成功，Harbor 服务重启后不可用。原因尚未确定。较常见的一种情况是：Harbor 各组件使用 syslog 日志驱动写入 harbor-log 容器，dockerd 开机按重启策略拉起容器时，harbor-log 若尚未就绪，其他容器就会启动失败，且不再重试。未证实，需要查看 `docker compose ps -a` 与本次开机的 docker 日志。修正（不依赖于具体原因）：harbor 角色新增 /etc/systemd/system/harbor.service，类型 oneshot，在 docker.service 与 /data 挂载之后执行 `docker compose up -d`，关机时先执行 `docker compose stop`，并设为开机启用。现有的 compose up 任务保证本次运行时的状态。syntax-check 通过。
- **节点 DNS**（[证据](evidence/00.07.03-nodes-ipv6-dns.txt) 末尾）：重启后重跑，十台均为 ok=4 changed=0 failed=0，resolv.conf 只剩内部 DNS。文件中的 10 个 fatal 来自第 86 节那一次运行。
- **DNS 区域**（[证据](evidence/00.07.01-dns-zone-backup.txt)）：dns changed=3（正向、反向区域与重新加载），管理端六项验证、外部递归与权威应答全部通过；backup 的 A 与 PTR 记录随序号 2026101701 加入。
- **OpenWrt**（[证据](evidence/00.05.03-openwrt-base.txt)）：变更为掩码 255.255.255.0、DNS .11、删除 ip6assign、主机名与时区、dropbear 只用密钥且只监听 LAN；odhcpd 已为 disabled。之后地址为 192.168.9.10/24，路由只有默认网关与 192.168.9.0/24，网关与 223.5.5.5 均可达。名称解析行显示的是 BusyBox nslookup 所用服务器（127.0.0.1:53），不是解析结果：脚本的 awk 只排除了 `#53` 形式，BusyBox 的格式是 `:53`。这是脚本缺陷，已改为取 Name 之后的 Address，并本地验证。dropbear 在后台重启，口令登录已关闭。用户之后能用 `ssh openwrt` 执行命令，说明密钥登录可用。
- **写入订阅地址卡住**：`cat > 文件` 会一直等待标准输入，直到粘贴后按 Ctrl-D；第 86 节虽有说明，但这种交互方式容易被误认为卡住。改为先在 Mac 上用 zsh 的 `read -rs` 不回显地读取（链接不出现在命令行与 shell 历史中），再经管道写入 OpenWrt，最后只回显文件字节数。

## 88. 2026-10-17 显式代理投入使用：Mac 与 cp01 经 OpenWrt 访问外网成功

用户改用第 87 节的 `read -rs` 方式写入订阅地址（输出只有字节数，本助手未见到链接），随后执行 install-mihomo.sh 与代理测试：

- [安装](evidence/00.06.02-mihomo-install.txt)：管理 Mac 经 Clash 下载 mihomo-linux-amd64-compatible-v1.19.32.gz（21.8 MB，约 5 秒），与版本锁 SHA256 校验 OK；OpenWrt 上 `mihomo -v` 为 Mihomo Meta v1.19.32 linux amd64（go1.26.8）。服务为 running，监听 192.168.9.10:7890，控制接口在 127.0.0.1:9090，订阅提供者开始初始化。`Command failed: ubus call service delete ... (Not found)` 来自首次安装时对未运行服务执行 restart，无害。
- [代理测试](evidence/00.06.02-proxy-test.txt)：经 http://192.168.9.10:7890 访问 https://www.google.com/generate_204，Mac 返回 204（0.31 s），cp01 返回 204（0.57 s）。cp01 的请求经过 lan-allowed-ips 与 OpenWrt LAN 区域入站，节点到代理的路径已验证。00.06.02「受控的显式代理」可用：默认网关仍是 .1，只有显式指定代理的程序经过 OpenWrt。

安全修正：安装日志中有一行 info 级别的逐连接记录，含订阅服务器域名（`mihomo --> <域名>:443`）。第 86 节的 URL 替换只匹配 `scheme://`，没有覆盖这种格式。证据中的该域名已替换为 `<subscription-host>`，全仓库检查不再出现。域名不是凭据，但会指向订阅提供方，因此按与订阅地址同等的方式处理。后续修改：install-mihomo.sh 输出日志时去掉 [TCP]/[UDP] 逐连接行；配置的 log-level 改为 warning，OpenWrt 本机的 logread 也不再记录每个连接；订阅提供者设为 `proxy: DIRECT`，首次启动时节点组为空，订阅本来就是直连拉取的，固定下来后，以后的更新也不依赖已有节点可用。改动需重跑一次 install-mihomo.sh 才生效（种子已缓存，不会重新下载）。

台账 openwrt 保持 planned，只是为了不纳入 Ansible inventory，注释已说明已部署；版本锁 openwrt 与 proxy_core 记为 deployed。GitLab 官方仓库已有 el/10 的 x86_64 仓库（repomd.xml 返回 200），Nexus 的 latest-linux-x86_64 安装包可下载，两者都可以在 Rocky 10 上原生安装，不需要另建 Docker 宿主。

## 89. 2026-10-17 Harbor 重启失败原因确认；mihomo 重装写满 OpenWrt 根分区

**Harbor**（[诊断](evidence/00.11-harbor-after-reboot.txt)）：命令本身 rc=0。重启后只有 harbor-log 为 Up (healthy)，映射 127.0.0.1:1514；其余八个容器在 39 分钟前 Exited (128)，80 与 443 都没有监听。本次开机的 dockerd 日志在 11:51:45 对八个容器报 `failed to start container ... failed to initialize logging driver: dial tcp [::1]:1514: connect: connection refused`。第 87 节的推断得到证实：dockerd 开机时按重启策略同时启动各容器，它们的 syslog 日志驱动连接 localhost:1514，而 harbor-log 尚未就绪，于是启动失败；这类失败不属于「容器退出」，restart: always 也不会重试。日志中的 [::1] 是 localhost 解析出的第一个地址，harbor-log 只发布在 127.0.0.1，平时会回退到 127.0.0.1 并连接成功（首次安装后运行了数小时），所以 IPv6 不是原因。其余几行（fsverity、nftables 表不存在、git）是 Docker 启动时的常规提示，与本问题无关。

修正：harbor.service 的 ExecStart 改为失败后间隔 10 秒重试，最多 6 次。compose 的 depends_on 只等 harbor-log 容器启动，不等日志端口就绪，同样可能遇到这一时序，因此不能只执行一次。用户在修改之前已开始执行 harbor.yml（单元为第一版，只执行一次 compose up），需要再执行一次 harbor.yml 写入新单元，然后再做重启测试。

**mihomo 重装**：用户按第 88 节重跑 install-mihomo.sh，校验 OK 之后报 `cat: write error: No space left on device`。原因：解压后的二进制为 62054526 字节，OpenWrt combined 镜像的根分区约 100 MB；脚本先写 /usr/bin/mihomo.new 再替换，新旧两份放不下。set -euo pipefail 让脚本在这一步停止，旧二进制、配置与正在运行的服务都未改动，但残留的 mihomo.new 写满了根分区。根分区写满时 uci commit 等写入都会失败，必须尽快清理。这是本助手的缺陷：第一次安装时没有旧文件，所以没有暴露。

修正：install-mihomo.sh 先删除残留的 .new，再比较本地解压后的 SHA256 与 OpenWrt 上现有文件；相同则跳过传输。不同时先停服务、删除旧文件，确认根分区剩余空间至少为二进制大小加 4 MB，然后直接写入并再次核对哈希；结束时输出根分区用量。版本锁 proxy_core 增加 binary_sha256（7a0d59da…）。重跑一次即可完成清理并应用第 88 节的配置改动。如需留出升级空间，可以按 OpenWrt 文档扩展根分区（镜像已补零到 1 GiB，分区之后约有 900 MB 未分配空间），暂不处理。

## 90. 2026-10-17 Harbor 重启复验通过；mihomo 重装完成、根分区恢复

**Harbor**（[证据](evidence/00.11-harbor-boot-unit.txt)）：文件中只有一次 harbor.yml 运行，为 ok=44 changed=3 failed=0。三项变更是 compose up（重启后容器处于停止状态，由它拉起）、写入 harbor.service、启用该单元；管理端验证通过，health 重试一次后为 healthy。随后 `reboot-nodes.yml -e target=harbor` 通过（新的 boot_id，SELinux Enforcing，firewalld running，DNS .11，没有失败单元）。重启后 verify-harbor.yml 通过：ping 第一次即成功，health 重试一次后为 healthy，/v2/ 返回 401。从证据无法判断写入的是哪一版单元，因此本助手从管理端只读执行了一次 `systemctl show harbor`：ExecStart 为带 6 次重试的版本，UnitFileState=enabled，ActiveState=active，本次开机在 12:41:39 启动、12:41:45 以 status=0 结束。6 秒说明第一次 compose up 就已成功，没有用到重试。Harbor 重启后的自动恢复由此得到证据。两份证据中都没有私钥块。

**mihomo**（[证据](evidence/00.06.02-mihomo-install.txt) 末尾）：SHA256 校验 OK；`/usr/bin/mihomo 已是该版本`，跳过传输；残留的 mihomo.new 已删除。根分区为 98.3M，已用 81.9M，剩余 14.3M。服务重启后为 running，监听 192.168.9.10:7890，新的日志级别与订阅直连配置已生效：输出中没有逐连接日志，其余几行是解析配置之前的启动信息。根分区只剩 14 MB，再写入大文件（例如升级 mihomo 时）前需要先删除旧文件；新脚本已按这个顺序执行。
