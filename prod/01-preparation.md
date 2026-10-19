# 01 准备阶段部署手册

[建设总览与资源规划](readme.md)

本文从已经安装干净 Rocky Linux 10.2 的 `rocky-base` 开始，先封装模板，再准备 admin。平台交付 **18 台 Rocky Linux 10.2 + 1 台 OpenWrt，共 19 台运行 VM**；关机保存的 `rocky-base` 模板单独登记，不作为第 20 台运行节点。本文供逐条审查，编写时未连接目标环境、未执行部署，验收结果均待执行后填写。

## 阅读目录

- [0. 执行约定与交付清单](#0-执行约定与交付清单)
- [1. rocky-base 模板与 admin](#1-先准备-rocky-base-模板再准备-admin)
- [2. Mac 打包并人工安装 OpenWrt / Mihomo](#2-在-mac-打包并通过-vsphere-web-安装-openwrt)
- [3. 收紧管理入口与准备后续主机](#3-openwrt-就绪后建立管理环境与主机准备方法)
- [4. 双 DNS、时间与证书](#4-双-dns时间服务与内部证书)
- [5. DNF/RPM、PostgreSQL 与 Nexus 完整部署](#5-在-nexus-vm-完整部署-dnfrpmpostgresql-与-nexus)
- [6. Harbor](#6-部署-harbor-镜像私服)
- [7. GitLab](#7-部署-gitlab-代码私服)
- [8. 剩余 12 台 VM](#8-私服完成后再准备剩余-12-台-vm)
- [9. 内网与出网控制](#9-收紧内网访问与出网)
- [10. 备份与恢复](#10-建立备份与恢复流程)
- [11. 全量验收与交接](#11-全量验收与-01-交接)
- [12. 故障处理与资料](#12-故障处理与资料依据)

## 0. 执行约定与交付清单

### 0.1 操作边界与管理路径

| 操作 | 执行位置与方式 |
| --- | --- |
| vSphere 的所有操作 | 人工使用 vSphere Web 控制台：创建、克隆、模板转换、ISO / VMDK 上传、网卡连接、加盘、开关机、快照和资源核对 |
| rocky-base 准备 | vSphere 客体控制台设置初始网络与密码，随后允许 Mac 使用密码登录；不配置 SSH 免密 |
| admin 准备 | 从 rocky-base 模板人工部署，先用密码修改身份和网络，再从 Mac 使用 ssh-copy-id 配置公钥 |
| OpenWrt 首次安装 | Mac 下载 IMG、打包 VMDK，通过 Web 上传并挂盘；首次网络、口令和 Mihomo 由控制台 / Mac 完成，不经过 admin 中转 |
| OpenWrt 就绪后的日常管理 | Mac 只 SSH 到 admin；从 admin 管理其他 VM，Ansible、Helm、kubectl 等工具在 5.7 从内网源安装到 admin |

```text
引导期：Mac ── 浏览器 ── vSphere Web ── rocky-base / admin / OpenWrt 的客体控制台
         ├─ 密码 SSH → rocky-base（封装前）与 OpenWrt（Mihomo 就绪前）
         └─ SSH → admin

OpenWrt 验收完成后：Mac ── SSH → admin ── SSH / Ansible → 其余 18 台 VM
                   └─ 浏览器 → vSphere Web（人工虚拟化管理）
```

只有第 2 节完成后才实施第 3.1 节的 Mac SSH 来源限制。模板中没有 Mac 公钥、admin 公钥、部署私钥、CA 或订阅；新 Rocky 先密码登录、修改信息，再用 `ssh-copy-id` 增加 admin 公钥，验证后关闭该主机的 SSH 密码认证。无需继承、删除或重新写入上一台机器的登录授权。

本期不启用 VLAN。VM 共享二层网络，按角色采用主机防火墙与来源白名单。Rocky 保持 SELinux Enforcing、firewalld 启用，OpenWrt 保持 fw4 启用。后续服务和验收在 admin 发起；Mac 不安装 Ansible、Helm 或 Kubernetes 管理环境，也不为其他 VM 配置 ProxyJump、SSH 转发或管理密钥。

### 0.2 实际部署顺序

1. 准备干净的 rocky-base，验证密码登录，清理克隆身份并关机，人工转换为模板。
2. 从模板人工部署 admin，修改身份 / 地址 / 口令，以 `ssh-copy-id` 配置 Mac → admin。
3. 在 Mac 把 OpenWrt IMG 打包成 VMDK，通过 vSphere Web 人工安装；完成 OpenWrt 网络与原生 Mihomo 订阅代理，验证出网。
4. 由 admin 使用 `ssh-copy-id` 配置 OpenWrt 管理授权，再收紧 Mac SSH 来源；准备 admin 引导软件源、SSH 和 DNS / CA 所需基础命令。
5. 从模板依次准备 dns、dns02，建立双 DNS、NTP 和内部 CA。
6. 创建 nexus VM，连续完成本章的 DNF/RPM 源、5.7 的 admin 管理工具、PostgreSQL 与 Nexus 全部配置；通过当前阶段验收后，再部署 Harbor、GitLab。
7. 私服可用后，从 rocky-base 准备 build01、backup 和十台 Kubernetes 节点，共剩余 12 台。
8. 完成内网源、镜像、权限、备份、重启与断网供应验收，交接 01 集群部署。

引导物料先在 Mac 取得：Rocky DVD、OpenWrt 官方镜像、Mihomo 版本锁和校验材料。OpenWrt 自身必须先能安装和更新，不能依赖尚未部署的代理或私服；出口验收后，后续服务通过该出口获取必要物料，再逐步切换为内网供应。

### 0.3 19 台 VM 的目标配置

表中系统盘统一按 GiB 计，OSD 使用 TiB。磁盘为配置预算，创建前按 RAID5 容量复核。系统盘、运行时盘和业务盘分离；OSD 候选盘不分区、不格式化。

| VM | 系统 | IP | vCPU / 内存 GiB | 宿主机 | 磁盘预算 | 批次 |
| --- | --- | --- | --- | --- | --- | --- |
| admin | Rocky 10.2 | .15 | 2 / 4 | esxi01 | OS 100 + 管理数据 100 | 模板封装后 |
| openwrt | OpenWrt 25.12.5 | .10 | 2 / 1 | esxi01 | OS / 代理空间 8 | VPN |
| dns | Rocky 10.2 | .11 | 2 / 2 | esxi01 | OS 100 | DNS |
| dns02 | Rocky 10.2 | .17 | 2 / 2 | esxi02 | OS 100 | DNS |
| nexus | Rocky 10.2 | .14 | 8 / 24 | esxi01 | OS 100 + 数据 250 | DNF 与 Nexus 连续交付 |
| harbor | Rocky 10.2 | .12 | 4 / 8 | esxi03 | OS 100 + 数据 200 | Harbor |
| gitlab | Rocky 10.2 | .13 | 4 / 16 | esxi01 | OS 100 + 数据 150 | GitLab |
| build01 | Rocky 10.2 | .160 | 4 / 8 | esxi02 | OS 100 + 构建缓存 100 | 私服完成后 |
| backup | Rocky 10.2 | .16 | 2 / 2 | esxi02 | OS 100 + 备份 500 | 私服完成后 |
| cp01 | Rocky 10.2 | .101 | 4 / 8 | esxi01 | OS 100 + 运行时 100 | 私服完成后 |
| cp02 | Rocky 10.2 | .102 | 4 / 8 | esxi02 | OS 100 + 运行时 100 | 私服完成后 |
| cp03 | Rocky 10.2 | .103 | 4 / 8 | esxi03 | OS 100 + 运行时 100 | 私服完成后 |
| infra01 | Rocky 10.2 | .104 | 6 / 12 | esxi01 | OS 100 + 运行时 100 | 私服完成后 |
| infra02 | Rocky 10.2 | .105 | 6 / 12 | esxi02 | OS 100 + 运行时 100 | 私服完成后 |
| storage01 | Rocky 10.2 | .106 | 8 / 16 | esxi01 | OS 100 + 运行时 100 + OSD 候选 1 TiB | 私服完成后 |
| storage02 | Rocky 10.2 | .107 | 8 / 16 | esxi02 | OS 100 + 运行时 100 + OSD 候选 1 TiB | 私服完成后 |
| storage03 | Rocky 10.2 | .108 | 8 / 16 | esxi03 | OS 100 + 运行时 100 + OSD 候选 1 TiB | 私服完成后 |
| worker01 | Rocky 10.2 | .109 | 8 / 16 | esxi01 | OS 100 + 运行时 100 | 私服完成后 |
| worker02 | Rocky 10.2 | .110 | 8 / 16 | esxi03 | OS 100 + 运行时 100 | 私服完成后 |

合计 94 vCPU / 195 GiB。三台宿主机的平台 VM 内存分别为 99、48、48 GiB，另留 29、16、16 GiB 给 ESXi、VCSA 和运维。`rocky-base` 只保留 100 GiB OS 盘，封装后关机并转换为模板，磁盘占用另计；其安装时的 2 vCPU / 4 GiB 临时使用 esxi01 预留资源。所有 Rocky 均由该模板完整克隆，admin 只作为管理机。

### 0.4 安装方式与版本

| 对象 | 本文选型 | 安装与锁定方式 |
| --- | --- | --- |
| Rocky | 10.2 x86_64 | DVD / DNF / RPM；模板仅含公共系统工具 |
| OpenWrt | 25.12.5 x86/64 ext4 combined，BIOS | 官方非 EFI 镜像；Mac 打包描述文件与平面 VMDK；扩容工具用官方 APK |
| Mihomo | v1.19.32，amd64-compatible | 沿用现有 00 阶段成功的原生核心 + procd，固定 SHA-256，不安装 Docker |
| Harbor | v2.15.4 | 官方编排文件与官方容器；宿主机运行时用 RPM |
| GitLab CE | 官方 EL10 RPM | 执行时查询完整 NEVRA 并锁定，不混装 EL9 包 |
| Nexus | 3.97.0 UBI 官方镜像 | 固定摘要；同 VM 使用 RPM PostgreSQL |
| Helm | EPEL 10.2 Helm RPM | 当前选用 4.1.1-1.el10_2，安装前核对可用版本 |
| Ansible、备份工具 | 发行版 / EPEL RPM | 记录 NEVRA、签名与来源 |
| Kubernetes / CRI 工具 | 官方 RPM 仓库 | 00 准备软件与运行时，01 再初始化集群 |

Rocky 上的工具和服务遵守 DNF/RPM 或官方容器安装规则，不下载可执行文件 / 二进制压缩包手工安装。按本次明确指定的成功做法，**OpenWrt 的 Mihomo 使用原生核心与 procd**；这是本手册唯一的原生代理核心安装项。保留已验证方法的版本与摘要，重新执行本次环境验收，不搬用历史通过结论。

### 0.5 参数、记录与秘密

后续在 admin 的 `/srv/cnpl/{inputs,records,packages,images}` 保存公开参数和脱敏证据；私钥、订阅、口令、令牌放 `/etc/cnpl/secrets` 或运维账号的 `~/.local/share/cnpl/secrets`，目录 0700、文件 0600。禁止 `set -x`、录制秘密输入、输出完整容器环境或订阅节点、把秘密提交 GitLab。

每个步骤标注执行位置、配置和验收。命令中的网卡名、磁盘 ID、版本、域名必须先与本机核对；变量只在当前主机当前 shell 有效，重新登录后重新设置。步骤只在人工审查后执行，遇到失败先停在当前步骤，不将预期结果记为已通过。

### 0.6 基础设施人工核验

**位置：iDRAC / vSphere Web 控制台，人工操作。**

1. 在 iDRAC 的存储页面确认三台 RAID5 健康：esxi01 12 TB、esxi02 / 03 各 8 TB；480 GB SSD 独立核算。保留现有阵列。
2. 在 vSphere 的主机“摘要 / 配置”页面逐台核对 CPU、内存、ESXi 8 版本、时间和可用存储；只记录容量，不在本文记录 Datastore 名称。
3. 在三台主机“配置 → 网络 → 虚拟交换机 / 端口组”页面核对 VM 网络、上行链路和 MTU；本期无 VLAN 隔离，使用现有标准交换网络，不修改管理 vmkernel 接口。
4. 确认 vCenter `.5` 已纳管三台主机，可使用 Web 客体控制台；浏览器信任管理证书，并保留恢复账号。
5. 核对 DHCP 仅由 `.1` 提供，地址池 `.30–.49`；`.9` 为模板制作临时地址，`.10–.17` 与 `.101–.110` 等静态地址不进入 DHCP 池。
6. 在 Mac 准备官方 Rocky 10.2 DVD ISO、OpenWrt 镜像和校验材料；独立备份介质 / 异机目标另行登记。

验收：硬件、容量和网络与总览一致，Web 控制台和人工克隆可用；无需启用 ESXi SSH。新 Rocky 启动时还须检查 `lscpu`，确认客体 CPU 暴露满足 Rocky 10 的要求。

## 1. 先准备 rocky-base 模板，再准备 admin

### 1.1 确认模板机起点

**位置：vSphere Web。** 将已安装干净 Rocky 10.2 Minimal 的 VM 命名为 `rocky-base`，位于 esxi01；2 vCPU / 4 GiB、100 GiB OS 盘、VMXNET3、EFI。此时只有系统盘，不加业务盘。若使用安装向导，选择最小安装，系统盘采用 XFS，保留 SELinux 与 firewalld 默认安全能力。在“编辑设置 → 虚拟机选项 → VMware Tools → 时间同步”中人工关闭周期性宿主机时间同步，后续由 chrony 管理时间；克隆时核对该设置。

**位置：rocky-base 客体控制台，root，密码登录。** 网卡以实际名称为准，本文示例为 `ens33`。连接配置名从 `nmcli connection show` 人工选择；网卡尚未接通时，不能用“当前活动连接”字段推断配置名。

```bash
cat /etc/rocky-release
lscpu
ip -br link
nmcli -t -f NAME,DEVICE connection show
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
getenforce
hostnamectl set-hostname rocky-base
nmcli -f NAME,UUID,TYPE,DEVICE connection show
read -r -p '本机 ens33 对应的连接配置名称: ' CONNECTION
nmcli connection modify "$CONNECTION" ipv4.method manual ipv4.addresses 192.168.9.9/24 ipv4.gateway 192.168.9.1 ipv4.dns 192.168.9.1 ipv4.ignore-auto-dns yes ipv6.method disabled
nmcli connection up "$CONNECTION"
```

创建公共运维账号并设置模板制作期间使用的密码；账号已经由安装向导创建时只核对 wheel 成员并设置密码，不重复创建：

```bash
useradd -m -G wheel ops
passwd ops
visudo -c
```

验收：Rocky 10.2、`.9/24`、默认网关 `.1`、SELinux Enforcing；控制台可用。模板不生成个人或部署密钥，不配置公钥免密。

### 1.2 用 DVD 补齐模板的公共系统工具

**位置：vSphere Web。** 编辑 rocky-base 设置，为虚拟 CD/DVD 挂载已核验的 Rocky 10.2 DVD ISO，勾选连接。

**位置：rocky-base 控制台，root。**

```bash
mkdir -p /mnt/rocky-dvd
mount -o ro /dev/sr0 /mnt/rocky-dvd
test -d /mnt/rocky-dvd/BaseOS/repodata
test -d /mnt/rocky-dvd/AppStream/repodata
rpm -ql rocky-gpg-keys
cat > /etc/yum.repos.d/cnpl-media.repo <<'EOF'
[cnpl-media-baseos]
name=Rocky 10.2 DVD BaseOS
baseurl=file:///mnt/rocky-dvd/BaseOS
enabled=0
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-Rocky-10
[cnpl-media-appstream]
name=Rocky 10.2 DVD AppStream
baseurl=file:///mnt/rocky-dvd/AppStream
enabled=0
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-Rocky-10
EOF
dnf --disablerepo='*' --enablerepo='cnpl-media-*' install openssh-server openssh-clients firewalld sudo curl tar gzip python3 rsync chrony open-vm-tools policycoreutils-python-utils parted xfsprogs
systemctl enable --now sshd firewalld chronyd vmtoolsd
timedatectl set-timezone UTC
rpm -q openssh-server openssh-clients firewalld sudo open-vm-tools
command -v ssh-copy-id
```

使用 ISO 实际提供的 Rocky 10 公钥文件，校验 RPM 签名。若介质缺少某个包，先补充同版本官方签名 RPM 和依赖，不接入其他发行版源。模板不安装 Ansible、Helm、Docker、containerd、GitLab 等角色软件，不写入代理、私服地址或 CA。

为 Mac 密码登录保留发行版默认 SSH 入口，并记录 SSH 主机公钥指纹：

```bash
firewall-cmd --get-active-zones
firewall-cmd --zone=public --list-services
sshd -T | grep -E '^(passwordauthentication|pubkeyauthentication|permitrootlogin) '
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

预期 `PasswordAuthentication yes`，ops 可用密码登录。若最小安装策略未启用密码登录，在模板已有配置中人工确认原因后启用；此时不写日后管理机专用的 SSH 限制。

### 1.3 验证模板密码登录并封装

**位置：Mac。** 首次连接时，将显示的指纹与 1.2 控制台输出人工比对，一致后接受。这里明确禁用公钥认证，只输入模板 ops 密码。

```bash
ssh -o PubkeyAuthentication=no ops@192.168.9.9
```

**位置：rocky-base，ops → `sudo -i`。** 确认无个人授权和角色材料后封装；下列命令只在模板制作时执行一次。

```bash
test ! -e /home/ops/.ssh/authorized_keys
test ! -e /root/.ssh/authorized_keys
test ! -e /etc/cnpl
systemctl list-dependencies sshd.service
umount /mnt/rocky-dvd
dnf clean all
nmcli -f NAME,UUID,TYPE,DEVICE connection show
read -r -p '本机 ens33 对应的连接配置名称: ' CONNECTION
nmcli connection modify "$CONNECTION" ipv4.method auto ipv4.addresses '' ipv4.gateway '' ipv4.dns '' ipv4.ignore-auto-dns no 802-3-ethernet.mac-address '' ipv6.method disabled
hostnamectl set-hostname localhost.localdomain
```

下一组在 **Web 客体控制台** 执行。确认发行版 sshd 依赖包含主机密钥生成单元后，再清理模板专属身份：

```bash
systemctl stop sshd
rm -f /etc/ssh/ssh_host_*_key /etc/ssh/ssh_host_*_key.pub
truncate -s 0 /etc/machine-id
if [ -f /var/lib/dbus/machine-id ] && [ ! -L /var/lib/dbus/machine-id ]; then
    truncate -s 0 /var/lib/dbus/machine-id
fi
sync
systemctl poweroff
```

这里只清理模板的系统主机身份，克隆首次启动由 systemd / sshd 生成独立身份。模板没有用户 authorized_keys，不存在向克隆机传递个人 SSH 授权的步骤。

**位置：vSphere Web，人工操作。** 等待完全关机 → 断开 CD/DVD ISO → 右键 rocky-base →“模板 → 转换为模板”。保留该模板，后续统一“从此模板部署虚拟机”。不要再次启动源模板；需要更新时单独安排模板维护和重新封装。

验收：rocky-base 为关机模板，仅有 OS 盘；网络配置为 DHCP，不保留 `.9`；无用户公钥、私钥、订阅、CA、代理和角色服务。模板制作密码在克隆后逐台更改。

### 1.4 从模板人工部署 admin

**位置：vSphere Web，人工操作。**

1. 右键 rocky-base →“从此模板部署虚拟机”，名称填 `admin`，宿主机选 esxi01，选择容量足够的本地存储，完整克隆独立磁盘。
2. 设置 2 vCPU / 4 GiB，OS 100 GiB；添加独立 100 GiB 管理数据盘。在“虚拟机选项 → 高级 → 编辑配置”中增加 `disk.EnableUUID = TRUE`。
3. 网卡保持 VMXNET3 并选择现有 VM 端口组；暂取消“连接 / 打开电源时连接”，不勾选自动开机，不启用操作系统自定义。
4. 完成向导，人工开机，打开 Web 客体控制台；使用模板 ops 密码登录后 `sudo -i`。

验收：admin 是独立 VM，源对象为 rocky-base 模板；源模板仍关机。所有磁盘、MAC、UUID 由 vSphere 作为新对象创建。

### 1.5 admin 先改身份、地址与密码

**位置：admin 客体控制台，root。**

```bash
hostnamectl set-hostname admin.mgmt.internal.egon.top
nmcli -f NAME,UUID,TYPE,DEVICE connection show
read -r -p '本机 ens33 对应的连接配置名称: ' CONNECTION
nmcli connection modify "$CONNECTION" ipv4.method manual ipv4.addresses 192.168.9.15/24 ipv4.gateway 192.168.9.1 ipv4.dns 192.168.9.1 ipv4.ignore-auto-dns yes ipv6.method disabled
passwd ops
passwd root
cat /etc/machine-id
cat /sys/class/dmi/id/product_uuid
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

确认 machine-id 非空、主机密钥已首次生成，再在 Web 中接通网卡，在控制台执行：

```bash
nmcli connection up "$CONNECTION"
ip -4 address show dev ens33
ip -4 route
```

验收：admin 名称正确、`.15/24`、默认路由 `.1`，已使用独立口令。此时未配置管理工具；后续仅从 rocky-base 部署新 VM。

### 1.6 使用 ssh-copy-id 配置 Mac → admin

**位置：Mac。** 先确认 Mac 已有 `ssh-copy-id`；缺少时通过已安装的 Homebrew 包管理器执行 `brew install ssh-copy-id`。不下载或粘贴来源不明的安装脚本。

```bash
command -v ssh-copy-id
ssh -o PubkeyAuthentication=no ops@192.168.9.15
```

核对指纹与 1.5 相同，密码登录成功后退出远端。生成一把带口令的 Mac 个人密钥；同名文件已存在时先核对归属，禁止覆盖：

```bash
umask 077
mkdir -p "$HOME/.ssh"
test ! -e "$HOME/.ssh/cnpl_admin_personal" || { echo '个人密钥已存在，先核对' >&2; exit 1; }
ssh-keygen -t ed25519 -a 100 -f "$HOME/.ssh/cnpl_admin_personal" -C 'cnpl-mac-to-admin'
ssh-copy-id -i "$HOME/.ssh/cnpl_admin_personal.pub" ops@192.168.9.15
ssh-add "$HOME/.ssh/cnpl_admin_personal"
ssh -o IdentitiesOnly=yes -o BatchMode=yes -i "$HOME/.ssh/cnpl_admin_personal" ops@192.168.9.15 'hostname -f'
```

在 Mac 的 `~/.ssh/config` 人工追加以下独立条目，保留其他已有条目；这不是重写整个文件：

```sshconfig
Host cnpl-admin
    HostName 192.168.9.15
    User ops
    IdentityFile ~/.ssh/cnpl_admin_personal
    IdentitiesOnly yes
    StrictHostKeyChecking yes
    ForwardAgent no
    ClearAllForwardings yes
```

```bash
chmod 0600 "$HOME/.ssh/config"
ssh cnpl-admin
```

验收：`BatchMode=yes` 成功返回 admin 名称，没有请求服务器登录密码；密钥口令由 Mac 本地 agent 解锁。私钥只在 Mac，`ssh-copy-id` 只增加指定公钥。SSH 密码认证和来源限制在 OpenWrt 就绪后的 3.1 节统一收紧，当前先继续安装 OpenWrt。

### 1.7 在 admin 挂载管理数据盘

**位置：admin，root。** 在写入 `/srv/cnpl` 资料前挂载数据盘，避免后续迁移。先把 Web 硬盘容量与客体设备对应起来，仅选择新增的 100 GiB 空盘。

```bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,SERIAL
ls -l /dev/disk/by-id/
read -r -p '已核实的 admin 新增空盘 by-id 路径: ' DATA_DISK
readlink -f "$DATA_DISK"
lsblk "$DATA_DISK"
wipefs --no-act "$DATA_DISK"
```

只在确认空盘无分区、文件系统、挂载和历史数据后执行：

```bash
parted --script "$DATA_DISK" mklabel gpt mkpart primary xfs 1MiB 100%
udevadm settle
DATA_PART="${DATA_DISK}-part1"
test -b "$DATA_PART"
mkfs.xfs "$DATA_PART"
mkdir -p /srv/cnpl
UUID=$(blkid -s UUID -o value "$DATA_PART")
printf 'UUID=%s /srv/cnpl xfs defaults,nodev,nosuid 0 0\n' "$UUID" >> /etc/fstab
findmnt --verify
mount /srv/cnpl
install -d -o ops -g ops -m 0750 /srv/cnpl/{inputs,records,packages,images}
findmnt /srv/cnpl
```

验收：数据盘 UUID 与本机匹配、挂载生效，ops 可写四个资料目录。已有挂载只核对，不重复格式化或追加 fstab。

## 2. 在 Mac 打包并通过 vSphere Web 安装 OpenWrt

### 2.1 在 Mac 获取官方镜像

**位置：Mac 本地终端。** 沿用现有 00 阶段最终使用的组合：**非 EFI ext4 combined 镜像、BIOS、PVSCSI、VMXNET3**。使用普通文件制作磁盘，不接触 Mac 的块设备。

```bash
mkdir -p "$HOME/Downloads/cnpl-prod-seed/openwrt"
cd "$HOME/Downloads/cnpl-prod-seed/openwrt"
curl --fail --location --proto '=https' --tlsv1.2 -O https://downloads.openwrt.org/releases/25.12.5/targets/x86/64/openwrt-25.12.5-x86-64-generic-ext4-combined.img.gz
curl --fail --location --proto '=https' --tlsv1.2 -O https://downloads.openwrt.org/releases/25.12.5/targets/x86/64/sha256sums
grep 'openwrt-25.12.5-x86-64-generic-ext4-combined.img.gz$' sha256sums | shasum -a 256 --check -
gzip -dk openwrt-25.12.5-x86-64-generic-ext4-combined.img.gz
shasum -a 256 openwrt-25.12.5-x86-64-generic-ext4-combined.img
```

验收：压缩镜像 SHA-256 为 OK，解压成功。摘要来自官方 HTTPS 同版本目录；如另行完成签名验证，记录实际签名结果，不能把摘要校验写成签名已验证。

### 2.2 在 Mac 打包平面 VMDK 和描述文件

沿用已经使用过的双文件方法，无需 qemu、OVF 脚本或 ESXi 命令。`openwrt-flat.vmdk` 保存镜像数据，`openwrt.vmdk` 是描述文件，两者名称必须匹配。本次使用 8 GiB 虚拟磁盘，为原生代理和升级留空间；根分区在 2.5 节实际扩大。

**位置：Mac，同一目录。** 先确认目标文件不存在，再创建：

```bash
test ! -e openwrt-flat.vmdk || { echo '平面 VMDK 已存在，先核对' >&2; exit 1; }
test ! -e openwrt.vmdk || { echo 'VMDK 描述文件已存在，先核对' >&2; exit 1; }
mkfile -n 8g openwrt-flat.vmdk
dd if=openwrt-25.12.5-x86-64-generic-ext4-combined.img of=openwrt-flat.vmdk bs=1m conv=notrunc
cat > openwrt.vmdk <<'EOF'
# Disk DescriptorFile
version=1
encoding="UTF-8"
CID=fffffffe
parentCID=ffffffff
createType="vmfs"

# Extent description
RW 16777216 VMFS "openwrt-flat.vmdk"

# The Disk Data Base
#DDB
ddb.adapterType = "lsilogic"
ddb.geometry.cylinders = "1044"
ddb.geometry.heads = "255"
ddb.geometry.sectors = "63"
ddb.virtualHWVersion = "13"
EOF
stat -f '%z' openwrt-flat.vmdk
IMAGE_BYTES=$(stat -f '%z' openwrt-25.12.5-x86-64-generic-ext4-combined.img)
cmp -n "$IMAGE_BYTES" openwrt-25.12.5-x86-64-generic-ext4-combined.img openwrt-flat.vmdk
shasum -a 256 openwrt.vmdk openwrt-flat.vmdk > openwrt-vmdk.sha256
```

验收：平面文件长度为 8589934592 字节，等于描述文件的 16777216 × 512；`cmp` 无输出且退出 0，证明原 IMG 内容完整保留。此步骤只在 Mac 处理本地文件，不创建或修改 vSphere 对象。

### 2.3 通过 vSphere Web 人工创建与挂盘

**位置：Mac 浏览器中的 vSphere Web，全部人工操作。**

1. 新建虚拟机 `openwrt`，放在 esxi01，选择与 BIOS 启动兼容的 Linux 客体类型；规格 2 vCPU / 1 GiB。
2. 删除向导自动添加的空白硬盘，保留 / 添加 **VMware 准虚拟 SCSI（PVSCSI）控制器**；网卡选 **VMXNET3**，连接目标 VM 端口组。
3. 在“虚拟机选项 → 引导选项”选择 **BIOS**。网卡取消“连接”和“打开电源时连接”，避免默认 `.1`、DHCP 和 RA 接入现有网络。
4. 完成 VM 创建但先不开机。打开所在存储的“文件”页，在该 VM 文件夹上传 Mac 的 `openwrt-flat.vmdk` 和 `openwrt.vmdk`，等待两个任务完成。
5. 编辑 VM →“添加新设备 → 现有硬盘”，选择 **openwrt.vmdk 描述文件**，挂到 PVSCSI `SCSI(0:0)`；不要选择 `-flat` 文件。文件浏览器可能将双文件合并显示为一个虚拟磁盘。
6. 检查硬盘显示 8 GiB、网卡仍未连接，保存后开机，打开 Web 客体控制台。

验收：能够进入 OpenWrt 控制台，`ls /sys/class/net` 可见 `eth0`。上传或挂盘失败时先核对双文件名称、扇区数、同一文件夹与 Web 上传结果，不转用宿主机命令处理。

### 2.4 先在控制台设置网络和密码，再接网

**位置：OpenWrt 的 Web 客体控制台，root。** 网卡仍断开，先关闭 DHCP / RA，再配置 `.10`。

```sh
cat /etc/openwrt_release
ls /sys/class/net
passwd
uci set system.@system[0].hostname='openwrt'
uci set network.lan.proto='static'
uci set network.lan.ipaddr='192.168.9.10'
uci set network.lan.netmask='255.255.255.0'
uci set network.lan.gateway='192.168.9.1'
uci -q delete network.lan.dns
uci add_list network.lan.dns='192.168.9.1'
uci -q delete network.lan.ip6assign
uci set network.lan.delegate='0'
uci set dhcp.lan.ignore='1'
uci set dhcp.lan.dhcpv6='disabled'
uci set dhcp.lan.ra='disabled'
uci set dhcp.@dnsmasq[0].port='0'
```

检查 `uci show network`：若 `lan.device='br-lan'`，对应 bridge 的 ports 必须包含 eth0。对于本方案单网卡显式代理，可以直接使用 eth0：

```sh
uci set network.lan.device='eth0'
uci commit network
uci commit dhcp
uci commit system
/etc/init.d/odhcpd disable
/etc/init.d/odhcpd stop
/etc/init.d/dnsmasq restart
/etc/init.d/network restart
if [ ! -s /etc/dropbear/dropbear_ed25519_host_key ]; then
    dropbearkey -t ed25519 -f /etc/dropbear/dropbear_ed25519_host_key
fi
dropbearkey -y -f /etc/dropbear/dropbear_ed25519_host_key | grep 'Fingerprint:'
```

若已核验镜像没有 odhcpd 单元，只记录未安装，不凭此关闭防火墙。保持默认 Dropbear 密码认证供本次引导，不分发 Mac 公钥。

**位置：vSphere Web。** 现在才接通 openwrt 网卡。回到客体控制台检查：

```sh
ip addr show dev eth0
ip route
ping -c 2 192.168.9.1
nslookup downloads.openwrt.org 192.168.9.1
fw4 check
```

**位置：Mac。** 对比控制台指纹后，用刚设置的 root 密码登录：

```bash
ssh -o PubkeyAuthentication=no root@192.168.9.10
```

验收：25.12.5、`.10/24`、默认网关 `.1`；不提供 DHCP、RA、递归 DNS。Mac 此时仍可用密码引导 OpenWrt，访问限制尚未实施。

### 2.5 安装官方 APK 工具并扩大根分区

**位置：OpenWrt，root，由 Mac 密码登录。** 此时只为引导 OpenWrt 使用可达的官方仓库；签名校验保持开启。

```sh
apk update
apk add ca-bundle curl parted resize2fs
cat /proc/mounts
parted /dev/sda print
```

先核对根文件系统为 ext4，根分区对应本次 8 GiB 系统盘的第 2 分区。PVSCSI 一般显示 `/dev/sda`；实际不同则使用实测设备，不能照抄对其他盘操作。

在 `parted /dev/sda` 的交互提示中依次输入 `unit MiB`、`print`、`resizepart 2 100%`，确认只改变第 2 分区终点，保留起点和引导分区；若提示分区正在使用，核对确为本次新建系统盘后确认 `Yes`，再 `quit`。

```sh
parted /dev/sda
```

记录新的分区终点后重启，让内核读取分区表：

```sh
reboot
```

从 Mac 再次密码登录，核对分区后扩大 ext4：

```sh
parted /dev/sda print
resize2fs /dev/sda2
df -h /
```

验收：根文件系统已经使用扩大后的空间，不是仅在 Web 里显示 8 GiB；可用空间足以存放约 62 MB 核心、订阅缓存及升级材料。不要在挂载中的根分区运行离线 fsck。APK 安装失败先补齐同版本官方签名离线包，不跳过验证。

### 2.6 在 Mac 准备并传输已验证的 Mihomo 核心

本节依据现有 [00 阶段安装方法](../ops/00-preparation/openwrt/install-mihomo.sh)、[procd 服务](../ops/00-preparation/openwrt/mihomo/mihomo.init) 和 [代理配置模板](../ops/00-preparation/openwrt/mihomo/config.template.yaml) 展开；只参考成功方法，本次仍需重新验收。

**位置：Mac。** 固定上游版本，先校验压缩包，再校验解压核心；同名文件存在时先核对，不覆盖不明物料。

```bash
mkdir -p "$HOME/Downloads/cnpl-prod-seed/mihomo"
cd "$HOME/Downloads/cnpl-prod-seed/mihomo"
curl --fail --location --proto '=https' --tlsv1.2 -o mihomo-linux-amd64-compatible-v1.19.32.gz https://github.com/MetaCubeX/mihomo/releases/download/v1.19.32/mihomo-linux-amd64-compatible-v1.19.32.gz
printf '%s  %s\n' ba3ce607747a07f948fc35780e108a4a7c7f552a38b9bd4d115f313ebcb89c20 mihomo-linux-amd64-compatible-v1.19.32.gz | shasum -a 256 --check -
gzip -dc mihomo-linux-amd64-compatible-v1.19.32.gz > mihomo
printf '%s  %s\n' 7a0d59da2e678d56c899a3db996a2ad8963286c4f3634b0451435db248f13fa1 mihomo | shasum -a 256 --check -
scp -O mihomo root@192.168.9.10:/tmp/mihomo
```

`scp -O` 使用 OpenWrt 已有的 SCP 通道，此时输入 OpenWrt root 密码，不依赖 SFTP / Docker。Mac 不执行这个 Linux 核心。

**位置：OpenWrt，root。**

```sh
test ! -e /usr/bin/mihomo || { echo 'Mihomo 已存在，先核对' >&2; exit 1; }
printf '%s  %s\n' 7a0d59da2e678d56c899a3db996a2ad8963286c4f3634b0451435db248f13fa1 /tmp/mihomo | sha256sum -c -
mv /tmp/mihomo /usr/bin/mihomo
chmod 0755 /usr/bin/mihomo
/usr/bin/mihomo -v
mkdir -p /etc/mihomo/providers
chmod 0700 /etc/mihomo /etc/mihomo/providers
```

验收：两份摘要校验均通过，版本为 v1.19.32。本文只描述首次安装；升级另行安排备份、校验和回退，不叠加存放新旧核心导致根分区写满。

### 2.7 接入已购买的订阅 link，沿用 00 阶段做法

使用你已经购买、并在 00 阶段验证成功的 **Clash/Mihomo 订阅 link**。订阅中的节点和连接参数由服务商提供，Mihomo 通过该 link 获取；本节不手写订阅 YAML，也不重新设计节点、代理组或分流规则。

本节依据现有 [00 阶段执行记录第 87–90 节](../ops/00-preparation/records/2026-10-14/assets.md) 及 [安装脚本](../ops/00-preparation/openwrt/install-mihomo.sh)：用户录入订阅链接，安装过程使用现成的本机模板和 procd 服务。

**第一步：从 Mac 安全录入已有订阅 link。** 在 Mac 的 **zsh** 终端执行，提示后粘贴购买服务提供的完整 Clash/Mihomo 订阅链接并回车。沿用 00 阶段已经成功的 `read -rs` 方式，不回显链接；SSH 仍使用 2.4 设置的 OpenWrt root 密码，此时尚未收紧 Mac 访问。

```zsh
read -rs 'CNPL_SUBSCRIPTION_URL?粘贴已购买的 Clash/Mihomo 订阅 link（不回显）: '
printf '\n'
if [[ -n "$CNPL_SUBSCRIPTION_URL" ]]; then
    printf '%s\n' "$CNPL_SUBSCRIPTION_URL" | ssh -o PubkeyAuthentication=no root@192.168.9.10 '
        umask 077
        mkdir -p /etc/mihomo
        chmod 0700 /etc/mihomo
        cat > /etc/mihomo/subscription-url
        chmod 0600 /etc/mihomo/subscription-url
        wc -c < /etc/mihomo/subscription-url
    '
else
    printf '未输入订阅链接，请重新录入。\n' >&2
fi
unset CNPL_SUBSCRIPTION_URL
```

验收：远端只输出订阅文件字节数，长度大于 1；链接不出现在命令参数、shell 历史或执行记录中。不执行 `cat /etc/mihomo/subscription-url`，也不把购买链接贴到聊天或仓库。

**第二步：原样传输 00 阶段已有的本机启动模板。位置：Mac。** 下列路径使用当前项目目录；文件直接来自已经成功使用的 [config.template.yaml](../ops/00-preparation/openwrt/mihomo/config.template.yaml)，不在本手册另编一份 YAML。

```bash
cd "$HOME/SelfProject/cloud-native-platform-lab"
scp -O ops/00-preparation/openwrt/mihomo/config.template.yaml root@192.168.9.10:/etc/mihomo/config.template.yaml
```

该文件中的 `__SUBSCRIPTION_URL__` 保持原样，由现有 procd 服务启动时读取购买链接并填入运行配置。节点内容继续由订阅服务提供，不手工粘贴节点或编辑订阅缓存。

| 文件 | 来源与用途 |
| --- | --- |
| `/etc/mihomo/subscription-url` | 上一步录入的已购订阅 link，权限 0600 |
| `/etc/mihomo/config.template.yaml` | 00 阶段已有的本机启动模板，原样使用 |
| `/var/run/mihomo/config.yaml` | 现有 procd 服务填入订阅链接后生成的运行配置，不手工编写 |
| `/etc/mihomo/providers/subscription.yaml` | Mihomo 通过已购订阅 link 下载的服务商订阅内容，不手工编写 |

来源访问限制由 3.1、3.6 和 9.1 的 OpenWrt 防火墙规则控制，本节不改写已经验证的 YAML 模板。

### 2.8 沿用 00 阶段 procd 服务并验收订阅

**位置：Mac。** 原样传输已经成功使用的 [mihomo.init](../ops/00-preparation/openwrt/mihomo/mihomo.init)，不另写一套启动脚本：

```bash
cd "$HOME/SelfProject/cloud-native-platform-lab"
scp -O ops/00-preparation/openwrt/mihomo/mihomo.init root@192.168.9.10:/etc/init.d/mihomo
```

**位置：OpenWrt，root，通过 Mac 的引导会话操作。** 检查文件存在并设置权限，然后首次启用服务：

```sh
test -s /etc/mihomo/subscription-url
test -s /etc/mihomo/config.template.yaml
chmod 0600 /etc/mihomo/subscription-url /etc/mihomo/config.template.yaml
chmod 0755 /etc/init.d/mihomo
/etc/init.d/mihomo enable
/etc/init.d/mihomo start
pidof mihomo
netstat -ltn | grep -E ':7890|:9090'
```

现有服务会读取订阅 link、生成 tmpfs 中的运行配置，先执行 Mihomo 配置检查，再由 Mihomo 获取服务商订阅。等待首轮下载完成后，只检查文件是否存在及其权限，不输出链接、节点或运行配置内容：

```sh
test -s /var/run/mihomo/config.yaml
test -s /etc/mihomo/providers/subscription.yaml
ls -l /etc/mihomo/subscription-url /etc/mihomo/config.template.yaml
```

验收：进程存在，7890 绑定 `.10`、9090 绑定 `127.0.0.1`；订阅缓存已经从购买链接获取。最后必须继续 2.9 的实际出网请求验证，不能只凭进程运行判定订阅可用。若订阅获取失败，先核对本地录入的 link、有效期和 OpenWrt 解析 / 出网结果；不自行改造订阅或添加第三方转换服务。

### 2.9 从 admin 验收出口与恢复物料

**位置：admin，ops。** OpenWrt 软件已安装完成后，使用显式代理验证后续真正需要的入口，不依赖尚未安装的管理工具：

```bash
curl --fail --silent --show-error --max-time 30 --proxy http://192.168.9.10:7890 https://download.docker.com/linux/rhel/10/x86_64/stable/repodata/repomd.xml -o /dev/null -w '%{http_code}\n'
curl --fail --silent --show-error --max-time 30 --proxy http://192.168.9.10:7890 https://dl.fedoraproject.org/pub/epel/ -o /dev/null -w '%{http_code}\n'
ip -4 route
```

预期两个 HTTPS 请求成功，默认网关仍为 `.1`。在 Mac 到 OpenWrt 的引导会话执行 `/etc/init.d/mihomo stop`，再由 admin 重试第一条请求，预期非零失败；随后执行 `/etc/init.d/mihomo start`，重复请求应恢复。内网连接通过 `--noproxy '*'` 使用内部地址，不经过代理。

**位置：Mac。** 关闭 OpenWrt 引导会话前，将公开引导物料传给 admin 留档：

```bash
ssh cnpl-admin 'mkdir -p /srv/cnpl/images/openwrt /srv/cnpl/images/mihomo'
scp "$HOME/Downloads/cnpl-prod-seed/openwrt/openwrt-25.12.5-x86-64-generic-ext4-combined.img.gz" "$HOME/Downloads/cnpl-prod-seed/openwrt/sha256sums" "$HOME/Downloads/cnpl-prod-seed/openwrt/openwrt.vmdk" "$HOME/Downloads/cnpl-prod-seed/openwrt/openwrt-vmdk.sha256" cnpl-admin:/srv/cnpl/images/openwrt/
scp "$HOME/Downloads/cnpl-prod-seed/mihomo/mihomo-linux-amd64-compatible-v1.19.32.gz" cnpl-admin:/srv/cnpl/images/mihomo/
```

验收：出口可用、停止后失败、恢复后可用，公开种子在 admin 留存。平面 VMDK 可按原 IMG 与 2.2 步骤重建，不必将 8 GiB 的补零文件重复备份。订阅秘密在第 10 节进入加密备份；现在继续 3.1，建立 admin 管理授权后结束 Mac 直连。

## 3. OpenWrt 就绪后建立管理环境与主机准备方法

### 3.1 分发正式文件，建立 admin → OpenWrt，再限制 Mac SSH

本章至 5.6 使用 Shell，5.7 才安装 Ansible / Helm / kubectl；5.8 起由 admin 的 Ansible 编排。文件均为正式 `.sh`、`.yml` 和实际配置，不提供 example 文件、自定义 Python 或 Jinja 模板。脚本只执行当前指定步骤，没有贯穿 3–10 的自动部署入口。

**位置：Mac，本项目目录。** 先把已审核文件传给 admin；Mac 不连接其他 VM：

```bash
ssh cnpl-admin 'mkdir -p /srv/cnpl/configuration'
rsync -a prod/ cnpl-admin:/srv/cnpl/configuration/
```

**位置：admin，ops。**

```bash
cd /srv/cnpl/configuration
bash scripts/prepare-inputs.sh base
umask 077
mkdir -p "$HOME/.ssh"
if [ ! -e "$HOME/.ssh/cnpl_deploy" ]; then
    ssh-keygen -t ed25519 -a 100 -f "$HOME/.ssh/cnpl_deploy" -C cnpl-admin-to-managed-vms
fi
eval "$(ssh-agent -s)"
ssh-add "$HOME/.ssh/cnpl_deploy"
ssh -o StrictHostKeyChecking=ask -o PubkeyAuthentication=no root@192.168.9.10
```

人工比对 OpenWrt 控制台指纹，密码登录后退出；接着在 admin 执行：

```bash
ssh-copy-id -i "$HOME/.ssh/cnpl_deploy.pub" -t /etc/dropbear/authorized_keys root@192.168.9.10
ssh -o BatchMode=yes -i "$HOME/.ssh/cnpl_deploy" root@192.168.9.10 hostname
scp -O scripts/bootstrap/03-openwrt.sh root@192.168.9.10:/tmp/cnpl-openwrt.sh
ssh root@192.168.9.10 'CNPL_SSH_KEY_VERIFIED=yes sh /tmp/cnpl-openwrt.sh lock'
```

[03-openwrt.sh](scripts/bootstrap/03-openwrt.sh) 自动找到 lan zone，建立 admin SSH / 代理白名单，确认公钥已验证后关闭 Dropbear 密码认证。它不修改已购订阅、Mihomo 配置和 procd 服务。重新从 admin 建立 SSH 并复验代理后，结束 Mac → OpenWrt 会话。

**位置：admin，root。** 从已验证的 Mac 公钥会话 `sudo -i`，执行：

```bash
cd /srv/cnpl/configuration
CNPL_SSH_KEY_VERIFIED=yes bash scripts/bootstrap/03-management.sh lock-ssh
```

[sshd-auth.conf](config/sshd-auth.conf) 关闭 root / 密码登录和转发；独立 users 文件限制 admin 的 ops 来源为 Mac `.200`。脚本保留发行版主配置和已有 authorized_keys。另开 Mac 终端执行 `ssh cnpl-admin`，必须成功；保留 Web 控制台恢复入口。此后 Mac 唯一的 VM SSH 目标为 admin。

### 3.2 配置 admin 引导软件源与基础命令

**位置：admin，root。**

```bash
cd /srv/cnpl/configuration
bash scripts/bootstrap/03-management.sh admin-tools
bash scripts/bootstrap/03-management.sh proxy
bash scripts/bootstrap/03-management.sh proxy-check
```

安装范围为 DNF 插件、OpenSSL、dig、GPG、jq；通过已验收的 `.10:7890` 访问 Rocky 受信任源，不安装 Ansible、Helm、kubectl。[proxy.sh](config/proxy.sh) 同时设置大小写代理变量和内网直连范围；DNF main 设置保留其他选项。首次没有 config-manager 时，仅通过命令参数引导插件安装，再重跑 proxy 持久化。

验收：脚本退出 0，Google 输出 `HTTP=204 proxy=192.168.9.10`，RPM 签名校验开启。内网 DNF 源建成后，各仓库的 `proxy=_none_` 优先于 main 的公网代理。

### 3.3 建立 admin SSH 客户端配置与记录方式

**位置：admin，ops。**

```bash
cd /srv/cnpl/configuration
bash scripts/bootstrap/03-management.sh ssh-client
ssh -G cnpl-openwrt | sed -n '1,35p'
```

入口维护自己的 `~/.ssh/cnpl.d/management.conf`。已有其他 SSH 配置时，脚本要求人工把 Include 放到正确位置，保留原有条目；主机身份检查保持开启，不配置 ProxyJump 或转发。

[scripts/run-step.sh](scripts/run-step.sh) 为当前一条命令建立独立记录目录，保留输出与真实退出码。需要记录的配置命令按以下方式运行：

```bash
bash scripts/run-step.sh 03-admin-proxy sudo bash scripts/bootstrap/03-management.sh proxy-check
```

不在参数中传入口令、token 或订阅；秘密使用受限文件、交互输入和 Ansible Vault，相关 Ansible 任务关闭日志与 diff。`output.log` 记录执行结果，`exit-code` 为 0 才能继续。证书签发、GPG 解锁和首次 SSH 的秘密输入不录屏。

### 3.4 从 rocky-base 人工部署当前所需的一台 VM

**位置：vSphere Web，人工。** 依次准备 dns、dns02、nexus；Harbor、GitLab 和剩余 12 台在其章节开始时再创建。所有 VM 从 rocky-base 完整克隆；按 0.3 设置宿主机、CPU、内存和磁盘。VMXNET3、`disk.EnableUUID=TRUE`、周期宿主机时间同步关闭均在 Web 核对。首次开机前断开网卡，不选择系统自动自定义。

创建、克隆、加盘、挂 ISO、快照、开关机和宿主机放置均无自动化命令。模板始终干净、关机，不从 admin 克隆。

### 3.5 新 Rocky：密码登录 → 修改信息 → ssh-copy-id → 收紧 SSH

**位置：新 VM 的 Web 客体控制台，密码登录 ops 后 `sudo -i`，网卡仍断开。** 当前以 dns 为例；其他主机按 0.3 填本机 IP。FQDN 规则：admin/dns/dns02/backup 使用 `<主机>.mgmt.internal.egon.top`；harbor 和十节点使用 `<主机>.k8s.internal.egon.top`；nexus/gitlab/build01 使用 `<主机>.svc.internal.egon.top`。此处只做首次身份建立，不重置继承的身份或授权：

```bash
hostnamectl set-hostname dns.mgmt.internal.egon.top
passwd ops
cat /etc/machine-id
cat /sys/class/dmi/id/product_uuid
ip link show ens33
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
nmcli connection show
```

machine-id、BIOS UUID、MAC、主机指纹必须独立；重复时停止排查模板。选择本机连接名称，再设置网络和首次 SSH 来源：

```bash
read -r -p '本机 ens33 连接名称: ' CONNECTION
nmcli connection modify "$CONNECTION" ipv4.method manual ipv4.addresses 192.168.9.11/24 ipv4.gateway 192.168.9.1 ipv4.dns 192.168.9.1 ipv4.ignore-auto-dns yes
firewall-cmd --permanent --zone=public --add-rich-rule='rule family="ipv4" source address="192.168.9.15/32" port port="22" protocol="tcp" accept'
firewall-cmd --permanent --zone=public --add-rich-rule='rule priority="-300" family="ipv4" source address="192.168.9.200/32" drop'
firewall-cmd --permanent --zone=public --remove-service=ssh
firewall-cmd --reload
```

在 Web 接通网卡，再在客体控制台执行 `nmcli connection up "$CONNECTION"`，确认地址和默认路由。此处首次网络激活由人工操作，后续脚本只 reapply DNS。

**位置：admin，ops。** 先密码登录，人工比对控制台指纹，再用标准工具增加公钥：

```bash
TARGET_IP=192.168.9.11
ssh -o StrictHostKeyChecking=ask -o PubkeyAuthentication=no "ops@$TARGET_IP"
ssh-copy-id -i "$HOME/.ssh/cnpl_deploy.pub" "ops@$TARGET_IP"
ssh -o BatchMode=yes "ops@$TARGET_IP" hostname -f
bash /srv/cnpl/configuration/scripts/bootstrap/stage-host.sh dns
ssh -t "ops@$TARGET_IP"
```

**位置：当前新 VM，ops → root。**

```bash
sudo -i
cd /home/ops/.local/share/cnpl-bundle
bash scripts/bootstrap/03-management.sh import-public
CNPL_SSH_KEY_VERIFIED=yes bash scripts/bootstrap/03-management.sh lock-ssh
```

脚本首次按角色写入 users 文件：普通主机只有 `ops@.15`；GitLab 另外允许 `git@.15/.160`；backup 另外预置六个受限备份账号来源。公钥验证成功后才关闭密码认证。从 admin 再开新会话验证；Web 密码恢复入口保留。不清空 authorized_keys，不把 Mac 公钥或部署私钥分发给克隆机。

### 3.6 配置服务 VM 经 OpenWrt 出网及角色数据盘

**位置：admin，ops。** OpenWrt 脚本已上传，增加本期五台服务 VM 的代理白名单：

```bash
ssh root@192.168.9.10 'sh /tmp/cnpl-openwrt.sh proxies'
```

仅 admin、dns、dns02、nexus、harbor、gitlab 能访问 `.10:7890`；build01、backup、十节点无代理授权。

**位置：当前 dns/dns02/nexus/harbor/gitlab，root。**

```bash
cd /home/ops/.local/share/cnpl-bundle
bash scripts/bootstrap/03-management.sh proxy
bash scripts/bootstrap/03-management.sh proxy-check
```

每台输出 `HTTP=204 proxy=192.168.9.10`，默认网关仍为 `.1`。Harbor / Nexus 的 Docker 守护进程，以及 Nexus Java、Harbor 组件、GitLab Rails 等应用代理，在服务章节单独配置和验收。

角色数据盘先在 Web 添加，预算集中在 [data-disks.tsv](inputs/data-disks.tsv)，与 0.3 台账一致。随后只读核对 `lsblk --bytes --output PATH,TYPE,SIZE,FSTYPE,UUID,MOUNTPOINTS,SERIAL` 和 `/dev/disk/by-id/`。**位置：admin，ops。** 当前到 nexus 阶段时登记：

```bash
cd /srv/cnpl/configuration
bash scripts/prepare-inputs.sh disk nexus
bash scripts/bootstrap/stage-host.sh nexus
```

正式输入记录主机、by-id、容量、挂载点、UUID 和初始化开关。新卷只生成一次 UUID，必须输入当前主机名确认空盘；已有卷填写实际 UUID，不重建。

**位置：nexus，root。**

```bash
cd /home/ops/.local/share/cnpl-bundle
bash scripts/bootstrap/03-management.sh import-public
bash scripts/operations/disk-prepare.sh inspect /etc/cnpl/inputs/data-disk.json
bash scripts/operations/disk-prepare.sh apply /etc/cnpl/inputs/data-disk.json
```

[只读磁盘检查](ansible/files/disk-state.sh) 拒绝系统盘、错误容量、未知签名/分区、其他挂载点或错误 UUID；[disk-prepare.sh](scripts/operations/disk-prepare.sh) 只有显式批准的原始空盘才能建 GPT/XFS。已有匹配卷复用，fstab 冲突和目录已有数据则停止。

| 角色 | 预算与挂载点 | 执行方式 |
| --- | --- | --- |
| nexus | 250 GiB → /srv/nexus | 第五章前由上述 Shell 准备，Ansible 后续核验 |
| harbor | 200 GiB → /data | 第六章由 Ansible 准备 |
| gitlab | 150 GiB → /var/opt/gitlab | 第七章由 Ansible 准备 |
| build01 / backup | 100 / 500 GiB → /srv/build、/srv/backup | 第八章由 Ansible 准备 |
| 十节点 | 每台 100 GiB → /var/lib/containerd | 第八章专用 Ansible 任务 |
| 三台 storage | 每台另加 1 TiB 原始 OSD 盘 | 本阶段只读核验，不分区、不格式化 |

验收：挂载 UUID、XFS、nodev/nosuid 与记录一致，`findmnt --verify` 成功；失败保留当前盘，不强制格式化或重新生成 UUID。

## 4. 双 DNS、时间服务与内部证书

### 4.1 先交付 dns 与 dns02

先按 3.4–3.6 完成两台主机的首次身份、SSH 和代理；本章不依赖 Kubernetes 或私服。

**位置：admin，ops。** 查询上游时间服务，人工确认两台时间服务器实际可用的独立 IPv4，录入并保存：

```bash
cd /srv/cnpl/configuration
bash scripts/prepare-inputs.sh ntp-addresses
bash scripts/bootstrap/stage-host.sh dns
bash scripts/bootstrap/stage-host.sh dns02
```

入口生成 `/srv/cnpl/inputs/ntp-upstream-ip.txt` 和实际 `chrony-server.conf`。时间服务使用这些固定 IP，后续第九章的 UDP 123 白名单读取同一文件，避免 pool 地址变化后被自身防火墙阻断。UDP NTP 不走 HTTP 代理。

### 4.2 配置主 DNS

**位置：dns，root。**

```bash
cd /home/ops/.local/share/cnpl-bundle
bash scripts/bootstrap/03-management.sh import-public
bash scripts/run-step.sh 04-dns-primary bash scripts/bootstrap/04-dns.sh server
```

[03-management.sh](scripts/bootstrap/03-management.sh) 导入公开输入；[04-dns.sh](scripts/bootstrap/04-dns.sh) 安装 BIND/chrony，分发 [named-primary.conf](config/named-primary.conf)、[正向区域](config/cnpl-forward.zone)、[反向区域](config/cnpl-reverse.zone) 及已登记的上游时间配置。

实际配置：只监听 `.11` / 回环；递归与查询只接受登记 VM；正反向区域只向 `.17` 传送。Mac 不在 ACL 中，无通配业务解析。脚本在加载前执行 named-checkconf / named-checkzone，恢复 SELinux 标签。

区域变更先修改两份实际 zone 文件并递增 SOA serial，再分发；不能在相同 serial 下发布不同记录。

### 4.3 配置第二 DNS

**位置：dns02，root。**

```bash
cd /home/ops/.local/share/cnpl-bundle
bash scripts/bootstrap/03-management.sh import-public
bash scripts/run-step.sh 04-dns-secondary bash scripts/bootstrap/04-dns.sh server
```

使用 [named-secondary.conf](config/named-secondary.conf)：只监听 `.17` / 回环，两个区域均为 secondary，从 `.11` 传送到发行版 slaves 目录。不会另建同名 primary 区域。检查 named 正常、区域传送完成。

### 4.4 仅向登记客户端开放 DNS / NTP

server 入口建立 `cnpl-vms` ipset，其成员与正式 19 台清单一致，仅允许成员访问 TCP/UDP 53、UDP 123。已有集合含未知成员时停止，不自动删除未知配置。

**位置：两台 DNS，root。**

```bash
firewall-cmd --permanent --ipset=cnpl-vms --get-entries
firewall-cmd --zone=public --list-rich-rules
named-checkconf
```

验收：精确 19 个地址，无 Mac `.200`；53/123 未作为全网 service 放行；区域传送还受 BIND 的 `.17` 限制。

### 4.5 配置时间服务

两台 DNS 的实际 `/etc/chrony.conf` 使用 4.1 登记的上游 IP，允许 LAN 客户端但由 firewalld 收紧到登记 VM。server 入口在配置变化时重启 chronyd，启用开机恢复并等待同步。

```bash
chronyc tracking
chronyc sources -n -v
chronyc waitsync 30 1 0 2
```

验收：有已选择的外部来源，Leap status 正常；未同步时停止，不启用伪同步的 local 时钟源。上游地址变更需要同步修订正式输入、两台时间服务和第九章规则。

### 4.6 切换 admin 与已建服务的解析和时间

**位置：admin，root。**

```bash
cd /srv/cnpl/configuration
bash scripts/bootstrap/04-dns.sh client
```

**位置：当前已建普通 Rocky 服务，root。** 在其 bundle 目录运行同一 client 入口。它只修改 ens33 的 DNS 并 reapply，不改变 IP、默认路由或重新激活连接；分发 [chrony-client.conf](config/chrony-client.conf)，使用 `.11/.17`。DNS 服务器不运行 client 模式。

**位置：admin，ops。**

```bash
ssh root@192.168.9.10 'sh /tmp/cnpl-openwrt.sh dns-ntp'
ssh root@192.168.9.10 'ip -4 address show; ip -4 route; pidof mihomo'
```

OpenWrt 只切换 DNS/NTP 到两台内网服务，保持地址、网关与现有 Mihomo。重新建立 admin → OpenWrt 会话后再继续。

### 4.7 DNS / NTP 验收

**位置：admin，root。**

```bash
cd /srv/cnpl/configuration
bash scripts/run-step.sh 04-dns-acceptance bash scripts/bootstrap/04-dns.sh verify
```

必须通过两台 DNS 的 UDP/TCP 正向查询、PTR、系统解析和 chrony 同步。再从 admin 手工停止主 DNS 的 named，复验系统解析，经 dns02 成功后立即恢复：

```bash
ssh ops@192.168.9.11 'sudo systemctl stop named'
getent ahostsv4 harbor.k8s.internal.egon.top
ssh ops@192.168.9.11 'sudo systemctl start named'
```

不得同时停止两台；失败时先恢复主 named，再排查传送、监听、来源与解析配置。

### 4.8 在 admin 建立受保护的内部 CA

**位置：admin，root。**

```bash
cd /srv/cnpl/configuration
bash scripts/bootstrap/04-pki.sh init
```

[04-pki.sh](scripts/bootstrap/04-pki.sh) 首次创建加密 RSA 根私钥、中间 CA 和内部域名约束。口令由 OpenSSL 交互输入，不写脚本、环境变量或日志。根私钥不分发，日常由中间 CA 签发；保存独立受控离线副本。

已有完整 CA 时只验证；部分文件缺失则停止，不能自动另建一套 CA。公开根证书保存 `/srv/cnpl/inputs/cnpl-root.crt` 并安装到 admin 信任库。

### 4.9 为私服逐个签发叶证书

**位置：admin，root。**

```bash
cd /srv/cnpl/configuration
bash scripts/bootstrap/04-pki.sh issue nexus
bash scripts/bootstrap/04-pki.sh issue harbor
bash scripts/bootstrap/04-pki.sh issue gitlab
```

三项分别生成独立私钥；Nexus 叶证书同时包含 `nexus.svc.internal.egon.top` 和 `rpm.svc.internal.egon.top`。其他 SAN 与正式服务域名一致。脚本核验证书链、域名、公私钥匹配和至少 30 天剩余有效期；已有有效材料复用，不在重复执行中换钥。

### 4.10 安装根信任与后续服务的证书分发方法

**位置：admin，ops。** 重新 stage 已建两台 DNS；各主机 root 运行 import-public 和 trust：

```bash
bash /srv/cnpl/configuration/scripts/bootstrap/stage-host.sh dns
bash /srv/cnpl/configuration/scripts/bootstrap/stage-host.sh dns02
```

```bash
cd /home/ops/.local/share/cnpl-bundle
bash scripts/bootstrap/03-management.sh import-public
bash scripts/bootstrap/04-pki.sh trust
```

Nexus 在 5.1 创建后，**admin root** 暂存自己的叶材料：

```bash
bash /srv/cnpl/configuration/scripts/bootstrap/04-pki.sh stage nexus
```

**admin ops** 安全传输，目标公钥已核验：

```bash
ssh ops@192.168.9.14 'install -d -m 0700 /home/ops/.local/share/cnpl-tls'
scp /srv/cnpl-transfer/nexus/tls.key /srv/cnpl-transfer/nexus/fullchain.crt ops@192.168.9.14:/home/ops/.local/share/cnpl-tls/
```

**nexus root** 运行 trust / install-leaf。Harbor、GitLab 在第六、七章由 Ansible 读取各自暂存目录；普通 VM 只收到公开根证书。

```bash
cd /home/ops/.local/share/cnpl-bundle
bash scripts/bootstrap/04-pki.sh trust
bash scripts/bootstrap/04-pki.sh install-leaf
```

确认目标安装和 HTTPS 验收后，admin root 执行 `04-pki.sh unstage nexus`；目标 root 删除此次 `/home/ops/.local/share/cnpl-tls/{tls.key,fullchain.crt}`。Harbor、GitLab 同样清理各自暂存叶材料。CA 签发档案不删除；所有验收使用正式域名与可信 TLS，不使用 `curl -k`。

## 5. 在 nexus VM 完整部署 DNF/RPM、PostgreSQL 与 Nexus

本章连续交付 `.14`，顺序为 **DNF 文件服务 → 5.7 管理工具 → PostgreSQL → Docker/Nexus → 应用仓库和权限 → 请求及重启验收**。内网 DNF 使用 Nginx/RPM 文件，在 Nexus 应用之前即可提供安装包；本章全部完成才进入 Harbor。

### 5.1 准备 nexus VM 与受控同步环境

在 Web 人工创建 nexus，按 3.5 完成身份 / SSH，3.6 准备 250 GiB 数据盘与代理，4.6 接入 DNS/NTP，4.10 安装根信任及双 SAN 叶证书。

**位置：nexus，root。**

```bash
cd /home/ops/.local/share/cnpl-bundle
bash scripts/bootstrap/03-management.sh proxy-check
bash scripts/bootstrap/04-dns.sh client
findmnt /srv/nexus
```

必须确认数据盘真实挂载，再同步 RPM；250 GiB 同时承载快照、Nexus、PostgreSQL 与恢复种子。完整上游内容不保证能放入该预算；评估不足时通过 Web 人工扩盘并更新容量记录，禁止用删除在用快照或跳过签名继续。

### 5.2 登记需要镜像的上游仓库

**位置：nexus，root。**

```bash
cd /home/ops/.local/share/cnpl-bundle
bash scripts/run-step.sh 05-upstream bash scripts/bootstrap/05-rpm.sh upstream
```

安装 Nginx、同步工具、GPG、jq、EPEL release。上游配置单独保存 `/etc/cnpl/upstream-repos`，包括 Rocky BaseOS/AppStream/CRB、EPEL、Docker RHEL 10、Kubernetes v1.36、GitLab EL10；保留 SSL / RPM / 元数据校验。后续客户端切内网源不会破坏该独立上游目录。

```bash
dnf --setopt=reposdir=/etc/cnpl/upstream-repos repolist
```

验收：七个 repo ID 存在，发行版和架构正确。包版本与 01 兼容矩阵一致；不采用 EL9 GitLab 包或临时公共源回退。

### 5.3 下载原始公钥，建立内网元数据签名密钥

**位置：nexus，root。**

```bash
cd /home/ops/.local/share/cnpl-bundle
bash scripts/bootstrap/05-rpm.sh keys
bash scripts/bootstrap/05-rpm.sh signing-key
```

keys 入口取得官方公钥，逐个显示公开指纹，要求操作人从官方发布核实完整指纹后录入；不因刚下载的公钥自称可信而接受。指纹记录保存为 `/srv/nexus/repos/keys/*.fpr`。

signing-key 首次交互创建有口令的本地签名主钥，选择 RSA 4096、签名用途、合适有效期并记录指纹。已有记录时只复用原钥。公钥导出 `cnpl-metadata.asc`，六组公钥/指纹一致才导入 RPM。私钥只在 `/etc/cnpl/rpm-gnupg`；上游 RPM 原始签名保留。

### 5.4 首次镜像并签名一个完整快照

**位置：nexus，root。** 先查询完整包集合，核对现有快照占用和应用预留。capacity 只查询元数据与磁盘空间，不下载 RPM 正文：

```bash
cd /home/ops/.local/share/cnpl-bundle
bash scripts/bootstrap/05-rpm.sh capacity
BATCH=$(date -u +%Y%m%dT%H%M%SZ)
read -r -p '同步完成后必须保留的应用空间 GiB: ' MIN_FREE_GIB
bash scripts/run-step.sh 05-rpm-snapshot bash scripts/bootstrap/05-rpm.sh mirror "$BATCH" "$MIN_FREE_GIB"
```

mirror 再次估算完整 RPM 大小，要求额外 20% 元数据/变化余量及输入的应用保留空间。当前 250 GiB 预算若不足就停止，先审核调整台账与正式数据盘配置，再由 Web 人工准备；不会自行扩容。入口建立全新批次，`reposync --download-metadata --gpgcheck` 同步七个完整仓库，不将 newest-only 与完整旧元数据混用。每项元数据存在且签名成功后才原子切换 current；签名由维护会话解锁，不把口令写脚本。旧快照不自动删除，失败批次不复用或发布。

验收：七份 repomd.xml 均通过本地签名验证，current 指向本次 releases 目录。后续同步仍执行相同新批次流程。

### 5.5 配置 HTTPS 软件源入口

**位置：nexus，root。**

```bash
cd /home/ops/.local/share/cnpl-bundle
bash scripts/run-step.sh 05-rpm-https bash scripts/bootstrap/05-rpm.sh serve
```

实际配置见 [nginx.conf](config/nginx.conf)、[cnpl-rpm.conf](config/cnpl-rpm.conf)：只有 `.14:443`，使用双 SAN 叶证书；`/keys/` 提供公开密钥，内容来自只读 current。Nginx ACL 和 firewalld ipset 都限制到登记 VM；仓库内容使用 httpd_sys_content_t，叶材料使用 cert_t。nginx -t 通过才启用/重载。

### 5.6 内网客户端源配置

**位置：admin，ops。** 从已受控的 nexus 获取公开公钥、指纹及配置：

```bash
mkdir -p /srv/cnpl/inputs/rpm-keys
scp ops@192.168.9.14:/srv/nexus/repos/keys/*.asc /srv/cnpl/inputs/rpm-keys/
scp ops@192.168.9.14:/srv/nexus/repos/keys/*.fpr /srv/cnpl/inputs/rpm-keys/
install -m 0644 /srv/cnpl/configuration/config/cnpl-private.repo /srv/cnpl/inputs/cnpl-private.repo
```

**位置：admin，root。**

```bash
cd /srv/cnpl/configuration
CNPL_INPUTS=/srv/cnpl/inputs bash scripts/bootstrap/05-rpm.sh client
bash scripts/run-step.sh 05-rpm-client bash scripts/bootstrap/05-rpm.sh verify
```

[cnpl-private.repo](config/cnpl-private.repo) 七个仓库全部使用 HTTPS，`enabled=1`、`gpgcheck=1`、`repo_gpgcheck=1`、`sslverify=1`、`proxy=_none_`。client 校验六把公钥与指纹，归档模板公开源，未知源/重名归档停止；不删除原文件。DNF 缓存成功后补齐 jq 与 versionlock 插件。

dns、dns02、nexus：admin ops 依次执行 stage-host；各 VM root 运行 import-public、`05-rpm.sh client`、`05-rpm.sh verify`。此时仅处理已创建主机。后续新主机由 Ansible 完成相同接入。

验收：内网 HTTPS 和 RPM/元数据签名真实通过，默认源只有 cnpl-*；Nexus 的独立 upstream-repos 仍保留供下一次受控同步。

### 5.7 在 admin 统一安装管理工具并配置 Ansible

**位置：admin，ops。** 先只查询内网仓库，对照 0.4 与 01 兼容矩阵选定实际版本；无合适候选时停止，先审核版本计划：

```bash
cd /srv/cnpl/configuration
bash scripts/prepare-inputs.sh admin-packages
```

正式 NEVRA 保存为 /srv/cnpl/inputs/admin-tools.lock.json，后续安装和复现使用同一文件。**随后在 admin root 执行：**

```bash
cd /srv/cnpl/configuration
bash scripts/run-step.sh 05-admin-tools bash scripts/bootstrap/05-admin-tools.sh
```

该入口此时才从内网 RPM 安装 **Ansible、Helm、kubectl**，以及 Git、jq、restic、Skopeo、versionlock。记录实际 RPM 并锁定管理工具；只验证 Helm 和 kubectl 客户端，不查询或初始化集群。

**位置：admin，ops。** 正式 [hosts.ini](inputs/hosts.ini) 和 [ansible.cfg](inputs/ansible.cfg) 已进入 `/srv/cnpl/inputs`。四类 K8s 子组为 master 3、infra 2、storage 3、work 2；父组 k8s_nodes=10，rocky_nodes=18，全部=19，admin local，OpenWrt root/become=false 且不接受 Rocky Python 变量。

```bash
export ANSIBLE_CONFIG=/srv/cnpl/inputs/ansible.cfg
ansible-inventory --graph
ansible k8s_nodes --list-hosts
ansible rocky_nodes --list-hosts
ansible all --list-hosts
```

当前已存在 admin/dns/dns02/nexus，分别建立 Vault 文件；后来创建的 VM 在其首次 SSH 完成后再建立自己的文件：

```bash
cd /srv/cnpl/inputs
ansible-vault create host_vars/admin.yml
ansible-vault create host_vars/dns.yml
ansible-vault create host_vars/dns02.yml
ansible-vault create host_vars/nexus.yml
```

编辑器只写该主机实际 `ansible_become_password`，保存为 Vault 密文；SSH 免密不等于 sudo 无密码。公开共用参数放 group_vars，单机差异放 host_vars，密码不放清单或命令行。

回到 source 目录，录入真实软件版本锁：

```bash
cd /srv/cnpl/configuration
bash scripts/prepare-inputs.sh packages
```

入口从内网 repoquery 列出候选，要求逐个选择实际完整 NEVRA，保存 `packages.lock.json`。GitLab 必须 EL10；PostgreSQL major 必须在选定 Nexus 支持范围内。没有合适候选就停，不填占位或猜测版本。文件存在时不覆盖；版本变更按维护审核更新。

先离线检查整组脚本（只解析，不连接 VM），再接管已引导的 DNS：

```bash
bash /srv/cnpl/configuration/scripts/validate.sh
cd /srv/cnpl/configuration/ansible
ansible-playbook dns.yml --syntax-check --ask-vault-pass
ansible-playbook dns.yml --list-hosts --ask-vault-pass
bash ../scripts/run-step.sh 05-dns-adopt ansible-playbook dns.yml --ask-vault-pass
```

采用同一实际 BIND 配置与 NTP 输入，重新验证双 DNS、NTP 和内网信任。首次接管可补齐日志等基线；再次配置应无非预期变化。

### 5.8 连续部署 PostgreSQL 与 Nexus，核对数据目录

以下入口均在 **admin ops** 执行，Ansible 使用已核实的 ops 公钥和 Vault 提权。完整实现见 [nexus.yml](ansible/nexus.yml)。先确认目标和语法：

```bash
cd /srv/cnpl/configuration/ansible
export ANSIBLE_CONFIG=/srv/cnpl/inputs/ansible.cfg
ansible-playbook nexus.yml --syntax-check --ask-vault-pass
ansible-playbook nexus.yml --list-hosts --ask-vault-pass
```

目标只能是 nexus 一台。公共前置任务验证身份、安全、CA/内网源和正式磁盘记录，不创建 VM 或重建 SSH。目录分别为 `/srv/nexus/repos`、`/srv/nexus/postgres`、`/srv/nexus/data`。

### 5.9 通过内网 RPM 安装 PostgreSQL

```bash
bash ../scripts/run-step.sh 05-nexus-pg ansible-playbook nexus.yml --tags pg --ask-vault-pass
```

按正式 NEVRA 安装 PostgreSQL，空 PGDATA 才 initdb；已初始化 major 不匹配或默认目录另有实例就停止。数据目录标签 postgresql_db_t，systemd 绑定 `/srv/nexus`；监听仅 `127.0.0.1:5432`，使用 SCRAM。

### 5.10 创建 Nexus 数据库与连接秘密

pg 阶段同时执行 [postgresql.sh](scripts/operations/postgresql.sh)：首次生成独立连接秘密，创建非超级用户 nexus、其数据库/schema 与 pg_trgm。已有账号缺少原秘密时停止，不自动改密码。

**从 admin 登录 nexus，root，只读验收：**

```bash
sudo -u postgres psql -XAt -d nexus -c 'SHOW listen_addresses'
sudo -u postgres psql -XAt -c "SELECT rolname,rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname='nexus'"
ss -lnt | grep ':5432'
```

结果必须为回环监听，三个高权限标志均为 false。SQL 密码通过 stdin 和受限文件传递，不出现在 argv 或 Ansible 日志。

### 5.11 安装官方容器运行时与镜像

**位置：admin，ops。**

```bash
bash ../scripts/run-step.sh 05-nexus-runtime ansible-playbook nexus.yml --tags runtime --ask-vault-pass
```

[Docker 任务](ansible/tasks/docker.yml) 从内网安装锁定 RPM，分发 [daemon.json](config/docker-daemon.json) 与 [nexus drop-in](config/docker-nexus.conf)。保留 SELinux 和 Docker iptables，使用固定地址池、日志上限与 `.10:7890` 守护进程代理；ops 不加入 docker 组。

实际 Nexus 镜像锁在 [compose-nexus.yml](config/compose-nexus.yml)，来自官方 sonatype/nexus3 的完整 digest，不依赖尚未部署的 Harbor。

### 5.12 写入 Compose 并启动应用

```bash
bash ../scripts/run-step.sh 05-nexus-application ansible-playbook nexus.yml --tags application --ask-vault-pass
```

生成本机 0600 连接环境文件；数据归 UID/GID 200，`:Z` 挂载到 `/nexus-data`。Compose 使用 host network，应用只绑定 `127.0.0.1:8081`，内存上限 16 GiB，堆 8 GiB、direct 4 GiB，保留数据库与系统资源。配置校验只使用 `config --quiet`，不输出展开后的秘密。

### 5.13 建立 Nexus HTTPS 入口

```bash
bash ../scripts/run-step.sh 05-nexus-https ansible-playbook nexus.yml --tags https --ask-vault-pass
```

[cnpl-nexus.conf](config/cnpl-nexus.conf) 与 DNF 共用 Nginx，独立域名，后端仅回环。ACL 只允许本机、admin、build01；启用 Nginx 必需的 SELinux 反向代理 boolean。必须通过 nginx -t 和可信域名请求，不能用防火墙掩盖应用错误监听。

### 5.14 初始化管理员凭据

```bash
bash ../scripts/run-step.sh 05-nexus-api ansible-playbook nexus.yml --tags api --ask-vault-pass
```

api 阶段按顺序执行 [nexus-api.sh](scripts/operations/nexus-api.sh) 的 init、proxy、repositories、permissions。初始化先验证保存的正式管理员凭据；只有新实例仍有初始密码时才完成首次设密。重跑复用原口令，不无条件更改管理员密码。

### 5.15 配置 Nexus 自身的 HTTP 出网代理

api 阶段按 [nexus-http.json](config/nexus-http.json) 设置 Java HTTP/HTTPS 代理 `.10:7890`，内部域名/IP 直连。这与主机登录环境和 Docker 代理分别生效。先 GET 比较所管字段，存在差异才 PUT，再由真实依赖请求验证回源。

### 5.16 创建依赖仓库

api 阶段建立 Maven Central / npm / PyPI proxy、Maven releases / snapshots hosted、maven-public group。配置依据 [Maven proxy 请求](config/nexus-maven-proxy.json) 与脚本内正式 hosted/group 请求；releases 为 ALLOW_ONCE，snapshots 为 ALLOW。

每个对象先 GET，404 才创建；已存在但正式配置不符时停止。不会把冲突状态当作本次新建成功。

### 5.17 只读与发布权限、客户端接入

api 阶段关闭匿名访问；reader 只允许指定依赖仓库 browse/read，publisher 只允许指定 Maven hosted 的 browse/read/add/edit。已有角色额外权限、账号状态不符或本机缺少原凭据均停止。

**位置：admin，ops。** 只领取 reader，管理员与 publisher 留在 nexus：

```bash
ansible-playbook credentials.yml --limit nexus_servers --ask-vault-pass
```

秘密保存在 admin `~/.local/share/cnpl/secrets/`，0700/0600，不提交 Git。build01 仅在第八章创建后领取自己的 reader 配置。

### 5.17a 从 admin 验收固定版本内容

先从 admin 以 reader 取得真正的 Maven POM：

```bash
mkdir -p /srv/cnpl/packages/nexus-smoke
curl --fail --netrc-file "$HOME/.local/share/cnpl/secrets/nexus-reader.netrc" https://nexus.svc.internal.egon.top/repository/maven-public/org/slf4j/slf4j-api/2.0.16/slf4j-api-2.0.16.pom -o /srv/cnpl/packages/nexus-smoke/slf4j-api-2.0.16.pom
sha256sum /srv/cnpl/packages/nexus-smoke/slf4j-api-2.0.16.pom
ansible-playbook nexus.yml --tags acceptance --ask-vault-pass
```

acceptance 会在独立测试坐标上传一个小 POM。必须通过 Maven/npm/PyPI 真实读取、publisher 上传与 reader 回读摘要一致、只读上传 403、releases 重复写入拒绝、匿名缓存读取 401/403。每次测试使用新坐标，不覆盖业务制品。真实包客户端验收在 8.9a。

### 5.18 开机恢复与请求验收

[cnpl-nexus.service](config/cnpl-nexus.service) 绑定数据盘、PostgreSQL、Docker，Compose 开机恢复。先执行完整配置的重复验证，再在 vSphere Web 人工重启 nexus：

```bash
ansible-playbook nexus.yml --ask-vault-pass
ansible nexus_servers -m ansible.builtin.wait_for_connection -a timeout=180 --ask-vault-pass
ansible-playbook nexus.yml --tags verify --ask-vault-pass
ansible-playbook nexus.yml --tags acceptance --ask-vault-pass
```

另执行 `ansible-playbook nexus.yml --tags seed --ask-vault-pass` 保存 Nexus 自身镜像归档、原始 Image ID 和校验文件，随数据库/blob 一起备份。第二次配置不得出现非预期变化；重启后 DNF HTTPS、5432/8081 回环、Nexus health、真实依赖与权限测试仍通过。Nexus 暂存叶材料确认后清理。完成本章后才进入 Harbor。

## 6. 部署 Harbor 镜像私服

### 6.1 按计划创建 Harbor VM

第五章全部通过后，在 Web 人工创建 harbor，完成 3.5 首次身份和 SSH、3.6 主机代理 / Google 验收、Vault 文件。**admin ops** 登记数据盘和官方物料摘要：

```bash
cd /srv/cnpl/configuration
bash scripts/prepare-inputs.sh disk harbor
bash scripts/prepare-inputs.sh harbor
cd /srv/cnpl/inputs
ansible-vault create host_vars/harbor.yml
```

**admin root** 执行 `04-pki.sh stage harbor`。实际 by-id、200 GiB、UUID 和官方 online installer SHA-256 由操作人核对后输入，生成正式文件；没有手填占位脚本。

### 6.2 从内网 RPM 安装 Docker 与 Compose

**位置：admin，ops。**

```bash
cd /srv/cnpl/configuration/ansible
export ANSIBLE_CONFIG=/srv/cnpl/inputs/ansible.cfg
ansible-playbook harbor.yml --syntax-check --ask-vault-pass
ansible-playbook harbor.yml --list-hosts --ask-vault-pass
bash ../scripts/run-step.sh 06-harbor-runtime ansible-playbook harbor.yml --tags runtime --ask-vault-pass
```

公共前置任务接入内网源、准备批准的数据盘和本服务证书。Docker 使用锁定 RPM、[Harbor drop-in](config/docker-harbor.conf)，代理为 `.10:7890`，内网直连；保持 SELinux、iptables 与固定地址池。

### 6.3 限制容器发布端口的来源

[harbor-firewall.sh](ansible/files/harbor-firewall.sh) 只维护 CNPL-HARBOR 专用链并挂到 DOCKER-USER；登记 VM 只允许访问 `.12:443`，Mac 不在允许列表。容器内部互访、内部 DNS 和代理路径分别放行，其余容器主动出站拒绝。

[规则 unit](config/cnpl-harbor-firewall.service) 在 Docker/firewalld 后、Harbor 前执行。Docker 重启和 firewalld 重载后须重新检查链。配置入口如下，与后续 6.4–6.6 在同一 configure 阶段执行：

```bash
bash ../scripts/run-step.sh 06-harbor-configure ansible-playbook harbor.yml --tags configure --ask-vault-pass
```

### 6.4 获取官方编排文件

configure 从官方 v2.15.4 入口下载 online installer，使用 6.1 已核实摘要校验后解包。应用运行于官方容器；不手装裸二进制。不存在本地校验材料或下载摘要不符时停止。

官方完整 harbor.yml.tmpl 只作为上游安装物料保留；本项目不交付自编 `.j2` 模板。脚本精确修改官方配置并保留其他默认项。

### 6.5 配置 harbor.yml 与 TLS

[harbor.sh](scripts/operations/harbor.sh) configure 在服务器首次生成两个不同口令并保存，后续复用；已有数据但缺少原秘密时停止。设置正式 hostname、叶证书、`/data`、systemd 挂载依赖与 SELinux 标签。

主机与 Docker 代理已独立配置；应用 proxy 段启用 core/jobservice/**trivy**，沿用[该版本官方配置](https://raw.githubusercontent.com/goharbor/harbor/v2.15.4/make/harbor.yml.tmpl)的组件名，不写成 trivy-adapter。通过官方 storage_service.ca_bundle 将内部公开根 CA 注入各容器共享信任目录，扫描器保持 TLS 校验和数据库更新。配置/叶材料有变化才重新 prepare；私密配置不进入日志。

### 6.6 绑定固定 IPv4 地址并首次启动

configure 分发 [Compose 入口限制](config/compose-harbor.yml)：唯一公开端口为 `192.168.9.12:443:8443`。Compose 必须支持 `!override` 并通过 config --quiet，不能因插件不支持而扩大端口范围。

[harbor.sh](scripts/operations/harbor.sh) images 拉取官方组件，逐项取得真实 RepoDigest/Image ID，写 compose.images.yml 与 `/data/bootstrap-images.json`，以 digest 启动。记录缺失、摘要不唯一或组件不完整即失败，不假造 image manifest。

### 6.7 设置开机恢复与健康验收

```bash
ansible-playbook harbor.yml --tags verify,seed --ask-vault-pass
```

[Harbor unit](config/cnpl-harbor.service) 依赖数据盘、Docker 与专用防火墙，使用有界重试处理日志服务启动顺序。health 必须 healthy、全部组件 healthy；未登录 `/v2/` 为 401。

seed 保存本服务组件归档与校验文件，纳入第十章加密备份。恢复模式 `harbor.sh restore-images` 只使用已校验种子，比较 Image ID，生成 `pull_policy: never` overlay；不会自动启动恢复服务。

### 6.8 建立项目与最小权限账号

```bash
ansible-playbook harbor.yml --tags api --ask-vault-pass
ansible-playbook credentials.yml --limit harbor_servers --ask-vault-pass
```

[harbor-api.sh](scripts/operations/harbor-api.sh) 建立公开 bootstrap、私有 business 项目，以及 90 天期限的 publisher / reader 机器人；权限分别为 pull+push / pull。公开项目只表示读取权限，网络仍收紧到登记 VM。

已有机器人但缺少一次性秘密时停止，不偷偷创建新账号或放宽权限。秘密只受控传给 admin，不发给十节点。确认服务安装后由 admin root 执行 `04-pki.sh unstage harbor`。

### 6.9 供应引导镜像并验证拉取

**位置：admin，ops。** 本机加载 3.2 的出网代理环境，运行：

```bash
source /etc/profile.d/cnpl-proxy.sh
cd /srv/cnpl/configuration
bash scripts/run-step.sh 06-image-supply bash scripts/operations/supply-images.sh
```

入口核实 pause 3.10.2、BusyBox 1.38.0-1 和操作人选定固定版本的官方 curlimages/curl 实际上游 digest，保存后复用，使用 publisher authfile 按 digest 复制；目标 digest 必须一致；curl 诊断镜像用于第九章真实容器网络验收。reader 能拉取但不能推送，私有项目匿名读取被拒绝。

**位置：admin，ops，在 ansible 目录。** 触发真实 Trivy 扫描：

```bash
BUSYBOX_DIGEST=$(jq -r .busybox /srv/cnpl/inputs/bootstrap-images.json)
ansible harbor_servers -b -m ansible.builtin.command -a "bash /opt/cnpl/provision/scripts/operations/harbor-api.sh scan $BUSYBOX_DIGEST" --ask-vault-pass
```

扫描需完成 Success，实际下载扫描库；超时、代理错误或 AVC 不算通过。随后 Web 人工重启 harbor，复验 health、链、镜像拉取与扫描；完整配置第二次运行无非预期变化后交付。

## 7. 部署 GitLab 代码私服

### 7.1 准备 GitLab VM 与证书

现在在 Web 创建 gitlab，完成 3.5、3.6 的身份/管理/主机代理验收。**admin ops** 登记 150 GiB 数据盘并创建本机 Vault：

```bash
cd /srv/cnpl/configuration
bash scripts/prepare-inputs.sh disk gitlab
cd /srv/cnpl/inputs
ansible-vault create host_vars/gitlab.yml
```

**admin root** 执行 `04-pki.sh stage gitlab`。本服务只取得自己的叶材料。

### 7.2 先写配置，再安装官方 RPM

**位置：admin，ops。**

```bash
cd /srv/cnpl/configuration/ansible
ansible-playbook gitlab.yml --syntax-check --ask-vault-pass
ansible-playbook gitlab.yml --list-hosts --ask-vault-pass
bash ../scripts/run-step.sh 07-gitlab ansible-playbook gitlab.yml --tags configure --ask-vault-pass
```

[gitlab.yml](ansible/gitlab.yml) 先挂数据盘、安装证书、生成并保留初始口令、写 [gitlab.rb](config/gitlab.rb)，再安装锁定的 EL10 RPM。内置 PostgreSQL/Redis 与 Nexus 数据库独立。公开根 CA 同时安装到 /etc/gitlab/trusted-certs，由 reconfigure 更新内置运行时信任。Rails/Sidekiq、Workhorse、Gitaly 分别配置代理；数据留在 `/var/opt/gitlab`，不设置已移除的旧版存储字段。

### 7.3 管理 SSH 与 Git SSH 分开授权

configure 核对首次设置的 users 文件：`ops` 只来自 admin；`git` 来自 admin/build01。只增加 `.15/.160` 的 Git/HTTPS 入口，不改写 ops authorized_keys；Mac 无入口，内部数据库与其他后端不发布到 LAN。

**从 admin 登录 gitlab，root，只读核对：**

```bash
sshd -t
sshd -T -C user=ops,addr=192.168.9.15,host=gitlab.svc.internal.egon.top | grep -E '^(allowusers|permitrootlogin|passwordauthentication) '
firewall-cmd --zone=public --list-rich-rules
```

### 7.4 备份配置、限制启动依赖并验收健康

```bash
ansible-playbook gitlab.yml --tags verify --ask-vault-pass
```

必须通过 health、readiness、登录页、`gitlab-rake gitlab:check SANITIZE=true`，以及 Rails 实际 Google HTTPS 请求，结果为 `204 proxy=.10:7890`。systemd 声明 `/var/opt/gitlab` 挂载依赖；Web 人工重启后复验相同项目，再重复配置检查无非预期变化。由 admin root 清理本次 GitLab 叶材料暂存。

### 7.5 建立平台配置项目与独立 Git 密钥

**位置：admin，ops。** 生成并解锁专用 Git 密钥，与系统部署密钥分开：

```bash
if [ ! -e "$HOME/.ssh/cnpl_git" ]; then
    ssh-keygen -t ed25519 -a 100 -f "$HOME/.ssh/cnpl_git" -C cnpl-admin-git
fi
ssh-add "$HOME/.ssh/cnpl_git"
ssh -o StrictHostKeyChecking=ask ops@gitlab.svc.internal.egon.top hostname -f
cd /srv/cnpl/configuration/ansible
ansible-playbook gitlab-project.yml --tags project --ask-vault-pass
bash ../scripts/run-step.sh 07-git-project bash ../scripts/operations/gitlab-check.sh
ansible-playbook gitlab-project.yml --tags revoke --ask-vault-pass
```

首次域名连接仍与控制台核对指纹。项目入口只传公钥；[gitlab-api.sh](scripts/operations/gitlab-api.sh) 在 GitLab 本机生成 7 天短期 token，建立私有 platform/configuration、项目级可写 Deploy Key 和 main 保护（禁止直接 push，只允许维护者 merge）。

[gitlab-check.sh](scripts/operations/gitlab-check.sh) 在独立记录目录 clone，创建测试分支和小提交，验证 push 成功、main push 被保护、无授权密钥失败；随后只删除本次测试分支。测试完成立即撤销短期 token，不把秘密提交项目。已撤销的引导凭据不会在重跑时自动再生成。

## 8. 私服完成后再准备剩余 12 台 VM

### 8.1 开始条件与人工 / Ansible 的执行边界

此时 admin、OpenWrt、dns、dns02、nexus、harbor、gitlab 共 7 台通过本阶段验收；再准备 build01、backup 和十台 K8s VM。Web 创建/加盘、首次密码修改与指纹/ssh-copy-id 仍人工；后续系统配置统一由 admin Ansible 执行。无自定义 Python 或 `.j2` 文件。

### 8.2 人工准备虚拟硬件，填写磁盘与软件参数

在 Web 按 0.3 创建、放置这 12 台，完成 3.5，并逐台建立加密 host_vars。十节点每台另加 100 GiB 运行时盘；三台 storage 各另加 1 TiB 原始 OSD 盘。先不手工格式化。

**位置：admin，ops。**

```bash
export ANSIBLE_CONFIG=/srv/cnpl/inputs/ansible.cfg
ansible k8s_nodes --list-hosts --ask-vault-pass
ansible k8s_nodes -b -m ansible.builtin.command -a 'lsblk --bytes --json --paths --output PATH,TYPE,SIZE,FSTYPE,UUID,MOUNTPOINTS,SERIAL' --ask-vault-pass
ansible k8s_nodes -b -m ansible.builtin.command -a 'ls -l /dev/disk/by-id/' --ask-vault-pass
```

人工将 Web 磁盘与 by-id 对应，不凭 `/dev/sdb` 或容量猜盘。

### 8.3 在 admin 准备 Ansible 文件和公开输入

```bash
cd /srv/cnpl/configuration
bash scripts/prepare-inputs.sh nodes
```

入口从私服查询七个运行时/入群 RPM 的完整 NEVRA，从 Harbor 查询已供应镜像的真实 digest，逐台要求填写 by-id；空盘确认后生成一次 UUID，已有卷填写原 UUID。十台全部填完才保存 `/srv/cnpl/inputs/k8s-bootstrap.yml`；内容为可直接读取的 JSON/YAML，不含密码或占位值。

四角色按 5.7 的清单分组，containerd 2.x 与同一 Kubernetes minor。密码继续留在 Vault host_vars。OSD 候选盘仅记录，始终不初始化。

### 8.4 先只读预检，再单机执行，最后按角色分批

```bash
cd /srv/cnpl/configuration/ansible
ansible-playbook bootstrap-nodes.yml -e @/srv/cnpl/inputs/k8s-bootstrap.yml --syntax-check --ask-vault-pass
ansible-playbook bootstrap-nodes.yml -e @/srv/cnpl/inputs/k8s-bootstrap.yml --list-hosts --ask-vault-pass
ansible-playbook preflight-nodes.yml -e @/srv/cnpl/inputs/k8s-bootstrap.yml --ask-vault-pass
bash ../scripts/run-step.sh 08-cp01 ansible-playbook bootstrap-nodes.yml --limit cp01 -e @/srv/cnpl/inputs/k8s-bootstrap.yml --ask-vault-pass
```

cp01 完成 8.7 功能验收后再检查差异：

```bash
ansible-playbook bootstrap-nodes.yml --limit cp01 -e @/srv/cnpl/inputs/k8s-bootstrap.yml --check --diff --ask-vault-pass
```

然后按角色顺序执行，playbook 内部 `serial: 1`、遇错停止：

```bash
ansible-playbook bootstrap-nodes.yml --limit 'k8s_master_nodes:!cp01' -e @/srv/cnpl/inputs/k8s-bootstrap.yml --ask-vault-pass
ansible-playbook bootstrap-nodes.yml --limit k8s_infra_nodes -e @/srv/cnpl/inputs/k8s-bootstrap.yml --ask-vault-pass
ansible-playbook bootstrap-nodes.yml --limit k8s_storage_nodes -e @/srv/cnpl/inputs/k8s-bootstrap.yml --ask-vault-pass
ansible-playbook bootstrap-nodes.yml --limit k8s_work_nodes -e @/srv/cnpl/inputs/k8s-bootstrap.yml --ask-vault-pass
```

### 8.5 Ansible 接管内网信任、存储和系统基线

[预检](ansible/tasks/preflight.yml) 检查真实 Rocky 10.2、角色资源、IP/主机名、唯一身份、安全、SSH 来源、软件和磁盘参数；已有集群配置即停止。[信任/源](ansible/tasks/trust-repos.yml) 切双 DNS、安装根 CA/公开密钥、归档模板源，仅用内网 DNF 补包。

[存储任务](ansible/tasks/storage.yml) 只初始化已批准空盘，匹配 UUID 则复用；[disk-state.sh](ansible/files/disk-state.sh) 只读检查且不依赖 jq/Python。根盘已有运行时数据或挂载冲突均停止。

[基线](ansible/tasks/baseline.yml) 保持 SELinux/firewalld，配置内部 NTP、关闭 swap、持久 journald、overlay/br_netfilter 和 sysctl。DNS 只 reapply；VMware 时间同步设置回到 Web 人工修改。

### 8.6 Ansible 安装并配置 containerd 与入群工具

[runtime.yml](ansible/tasks/runtime.yml) 从内网按完整 NEVRA 安装 containerd.io、container-selinux、kubeadm、kubelet、kubectl、cri-tools、kubernetes-cni，核验实际版本再锁定。实际 TOML 在任务中完整定义，使用 v3、SELinux、systemd cgroup、固定 pause digest、Harbor HTTPS 信任与数据盘挂载依赖。

00 阶段 kubelet 不启动、不启用；不运行 kubeadm init/join，不安装 CNI，不创建 Ceph OSD。缺包或签名失败不回退公网/手装二进制。

### 8.7 用 Ansible 验收真实 CRI 生命周期与清理

```bash
REPORT_DIR=/srv/cnpl/records/k8s-cp01-$(date -u +%Y%m%dT%H%M%SZ)
ansible-playbook verify-nodes.yml --limit cp01 -e @/srv/cnpl/inputs/k8s-bootstrap.yml -e "cnpl_report_dir=$REPORT_DIR" --ask-vault-pass
```

[验收 playbook](ansible/verify-nodes.yml) 检查实际版本、DNS/NTP、安全、挂载、持久日志和运行时配置。[runtime-status.sh](ansible/files/runtime-status.sh) 只输出必要字段；[cri-smoke.sh](ansible/files/cri-smoke.sh) 拉取固定 Harbor digest，执行 host-network sandbox/BusyBox，使用 cnplprep.slice，验证退出 0、`CNPL_CRI_OK`、无新增 AVC，并只清理本次 ID。任何探针/审计/清理失败均失败。

RuntimeReady 必须 true。无 CNI 阶段允许 NetworkReady=false；这不替代真实 CRI 生命周期验收。汇总只保存公开字段，不读取 Vault 明文或输出完整运行时配置。

### 8.8 十节点幂等、全量记录与重启复验

```bash
ansible-playbook bootstrap-nodes.yml -e @/srv/cnpl/inputs/k8s-bootstrap.yml --ask-vault-pass
REPORT_DIR=/srv/cnpl/records/k8s-all-$(date -u +%Y%m%dT%H%M%SZ)
ansible-playbook verify-nodes.yml -e @/srv/cnpl/inputs/k8s-bootstrap.yml -e "cnpl_report_dir=$REPORT_DIR" --ask-vault-pass
jq '{count,passed:([.nodes[].passed]|all)}' "$REPORT_DIR/readiness.json"
```

配置第二次应 failed/unreachable/changed 均为 0；全量报告 count=10，身份与运行时 UUID 唯一、全部 passed。功能探针会临时创建资源，幂等以配置任务为准。

在 Web 人工逐台重启，admin 等待 SSH 恢复并对同台重新验收，每次使用新的记录目录。不能用单机结果代表十台，也不覆盖历史记录。

### 8.9 准备 build01 与 backup

在 Web 完成硬件和首次 SSH 后，**admin ops** 登记两个角色数据盘，执行：

```bash
cd /srv/cnpl/configuration
bash scripts/prepare-inputs.sh disk build01
bash scripts/prepare-inputs.sh disk backup
cd ansible
ansible-playbook build-backup.yml --syntax-check --ask-vault-pass
ansible-playbook build-backup.yml --list-hosts --ask-vault-pass
bash ../scripts/run-step.sh 08-build-backup ansible-playbook build-backup.yml --ask-vault-pass
```

[build-backup.yml](ansible/build-backup.yml) 安装 CA/内网源、DNS/NTP、安全与日志基线，准备 `/srv/build` 和 `/srv/backup`。build01 从内网 RPM 安装 Git、Java/Maven、Node/npm、pip；backup 的受限账号和仓库在第十章建立。两台均无公网代理权限。

### 8.9a build01 客户端配置与实际制品获取

[build-client.sh](scripts/operations/build-client.sh) 只接收 reader，生成 ops 专用的 Maven settings、npmrc、pip.conf 和 netrc，均位于 `~/.config/cnpl/`，不覆盖其他项目配置；全部使用 Nexus 与系统 CA，无跳过 TLS 选项。

```bash
ansible-playbook build-backup.yml --tags acceptance --ask-vault-pass
```

以 ops 身份、新空缓存取得 slf4j-api 2.0.16 JAR、is-number 7.0.0 tgz、idna 3.10 wheel，核对实际文件与 SHA-256。pip 由 RPM 提供，仅调用包客户端，不编写 Python 脚本。第九章收紧后复验，断网缓存验收见 11.3。

## 9. 收紧内网访问与出网

### 9.1 全部入站规则核对

本期不启用 VLAN。先核对 18 台 Rocky 的管理/服务白名单，OpenWrt 使用 native UCI/fw4。主机 IP 白名单还需结合 SSH 密钥、应用认证和审计，不作为二层隔离的替代证明。

| 角色 | 允许入口 |
| --- | --- |
| admin | Mac `.200` → SSH 22 |
| OpenWrt | admin → SSH；admin 与五台服务 VM → 代理 7890 |
| dns/dns02 | 登记 VM → TCP/UDP 53、UDP 123；admin SSH |
| harbor | 登记 VM → HTTPS 443，容器转发另受专用链限制 |
| gitlab | admin/build01 → HTTPS/Git SSH；ops 只接受 admin |
| nexus | 登记 VM → DNF HTTPS；Nexus 应用仅本机/admin/build01；后端只监听回环 |
| backup | admin 管理 SSH；六个客户端受限 SFTP |
| build01/十节点 | admin SSH；01 再按角色增加集群端口 |

**位置：admin，ops。**

```bash
ssh root@192.168.9.10 'sh /tmp/cnpl-openwrt.sh verify'
ansible rocky_nodes -b -m ansible.builtin.command -a 'firewall-cmd --zone=public --list-all' --ask-vault-pass
```

人工核对没有全网 SSH/HTTPS/DNS 等额外入口。**位置：Mac，本项目目录，解锁原个人密钥后：**

```bash
bash prod/scripts/operations/mac-check.sh
```

[mac-check.sh](scripts/operations/mac-check.sh) 验证 admin 公钥登录，并对其他 18 台 SSH、私服 HTTPS、DNS TCP 与代理做有界拒绝测试。所有 VM 应先由 admin 验证在线；不把 VM 关机造成的不可达当成隔离通过，不分发 Mac 密钥。

### 9.2 Rocky 的主机出站策略

[network.sh](scripts/operations/network.sh) 按正式角色生成 HOST→ANY、priority -500、target DROP 的 cnpl-egress。共用允许内部 DNS/NTP、Harbor/RPM；服务 VM 经 `.10:7890`，DNS 额外仅允许固定上游 UDP 123；admin 可管理其他 VM，build01 可访问 GitLab，六个备份客户端可到 `.16:22`。IPv6 仅保留必要回环，不留公网绕行。

应用前备份本机 firewalld，安排 **180 秒本机超时回退**。应用后由 admin 重新建立连接并执行 [network-check.sh](scripts/operations/network-check.sh)；通过后才 commit。失败停止后续节点，等待回退或使用 Web 控制台，不跳过失败。

**位置：admin，ops。先 build01：**

```bash
cd /srv/cnpl/configuration/ansible
ansible-playbook network.yml --syntax-check --ask-vault-pass
ansible-playbook network.yml --limit build_nodes --tags plan --ask-vault-pass
bash ../scripts/run-step.sh 09-build-network ansible-playbook network.yml --limit build_nodes --tags apply --ask-vault-pass
```

随后按同样方式预览、执行其他 16 台，serial=1；admin 最后单独处理：

```bash
ansible-playbook network.yml --limit 'rocky_nodes:!management:!build_nodes' --tags plan --ask-vault-pass
ansible-playbook network.yml --limit 'rocky_nodes:!management:!build_nodes' --tags apply --ask-vault-pass
ansible-playbook network.yml --limit management --tags apply -e cnpl_admin_network_window=true --ask-vault-pass
```

admin 的回退不会由 playbook 自动取消。立即从 **Mac 新终端**运行 `ssh cnpl-admin`，确认新会话成功，然后在 admin root 的 180 秒窗口内执行：

```bash
bash /opt/cnpl/provision/scripts/operations/network.sh commit
```

验收：双 DNS、时间同步、内网 DNF/Harbor、服务 VM Google 代理通过；直接公网 TCP 443、普通节点代理入口、横向 SSH 被拒绝。检查运行期与永久策略，Web 人工重启后复验。01 部署前按实际 API/CNI/Ceph 矩阵增补端口，不提前全网放行。

### 9.3 容器出站与宿主机分开验收

Harbor 固定地址池为 `172.30.0.0/16` / `172.31.0.0/24`，与 LAN/Pod/Service/VPN 地址不冲突。firewalld reload 或 Docker 重启后，脚本重新应用专用链；Nexus host network 的出站由主机策略约束。

```bash
ansible harbor_servers -b -m ansible.builtin.command -a 'iptables -S CNPL-HARBOR' --ask-vault-pass
ansible-playbook harbor.yml --tags verify,network-acceptance --ask-vault-pass
ansible-playbook gitlab.yml --tags verify --ask-vault-pass
ansible-playbook nexus.yml --tags verify --ask-vault-pass
```

[container-network-check.sh](scripts/operations/container-network-check.sh) 从真实 core 容器读取唯一 Harbor 网络，只使用已锁定摘要的 BusyBox/curl 诊断镜像。临时容器验证 UDP DNS 实际返回、TCP 53 建连、可信 HTTPS、经代理 Google 204，以及直接公网 TCP 443 未建连；只清理本次唯一名称的容器。额外协议或诊断错误不当作拒绝成功。

再执行 6.9 的实际扫描和镜像请求。容器内部组件互访、经代理的回源都须通过；直接公网新连接必须拒绝。维护窗口临时停止 OpenWrt 验证未缓存回源失败，恢复后再成功。只检查宿主机 curl 或链存在不算应用验收完成。

## 10. 建立备份与恢复流程

### 10.1 准备 backup VM

backup 已在第八章交付 500 GiB `/srv/backup`、CA/内网源、DNS/NTP、admin 管理。六个客户端为 Harbor、GitLab、Nexus、admin、dns、dns02，各自独立账号/密钥/加密仓库；不为备份账号提供 shell 或 sudo。

**位置：admin，ops。** 先从已核对的 backup 主机记录导出公开主机密钥，不使用 ssh-keyscan 自动信任：

```bash
ssh-keygen -F 192.168.9.16 -f "$HOME/.ssh/known_hosts" | awk '$2=="ssh-ed25519" {print "backup.mgmt.internal.egon.top,192.168.9.16 "$2" "$3}' > /srv/cnpl/inputs/backup-hostkey.pub
test -s /srv/cnpl/inputs/backup-hostkey.pub
cd /srv/cnpl/configuration/ansible
ansible-playbook backup.yml --syntax-check --ask-vault-pass
ansible-playbook backup.yml --list-hosts --ask-vault-pass
```

未找到已验证记录时，先按 3.5 重新比对指纹再登记，不把空文件或来源不明密钥当作可信。

### 10.2 为每个备份客户端建立独立密钥

```bash
bash ../scripts/run-step.sh 10-backup-prepare ansible-playbook backup.yml --tags prepare --ask-vault-pass
```

[backup.yml](ansible/backup.yml) 分三步：六客户端本地生成/复用专用密钥，只汇集公钥；backup 创建六个 nologin 账号和 root 拥有的独立 chroot；最后各客户端配置自己的仓库。

公钥必须六份互异；授权绑定本角色来源，管理公钥保持原样。[backup-match.conf](config/backup-match.conf) 对 bk_* 强制 internal-sftp；只有各自 `/repo` 可写。精确目录的 SELinux 标签与必要 chroot boolean 生效，全程 Enforcing。

实际验收包括 `sshd -T -C` 的 ForceCommand/chroot/密码/转发设置，以及真实 SFTP 列目录、读取 jail 外 `/etc/passwd` 被拒绝。首次 prepare 必须包含六个客户端及 backup，不能只 --limit backup 后引用未准备的公钥。

### 10.3 初始化加密仓库

同一个 prepare 阶段在服务器只读检查 repo/config；只有确为空目录才能 init。已有仓库先验证原口令，缺少原解密口令则停止，不生成新密码覆盖。

[backup.sh](scripts/operations/backup.sh) 在各客户端生成 0600 restic.env/password，使用独立 SSH 配置和经过核实的 known_hosts，不修改 root 全局 SSH 配置。密码需另存受控离线介质，不能只在本服务和 backup VM 内保存。

```bash
ansible-playbook backup.yml --tags verify --ask-vault-pass
```

必须通过真实 SFTP、chroot 拒绝与 restic check；加密仓库存在不代表已经有可恢复快照。

### 10.4 Harbor 一致性备份

Harbor 采用明确停服窗口，停止 cnpl-harbor 后备份 `/data`、配置、叶秘密、unit 和离线种子。脚本保存原状态，备份或校验失败也尝试恢复原本运行的服务；服务恢复失败仍返回非零。

**位置：admin，ops，已确认本次停服窗口后：**

```bash
ansible-playbook backup.yml --limit harbor_servers --tags first-backup -e cnpl_backup_window_confirmed=true --ask-vault-pass
```

本阶段会停服，不能在没有维护窗口时执行。结果必须为有效 snapshot_id、restic check 成功且 Harbor 已恢复健康。

### 10.5 GitLab、Nexus、DNS、admin 与 OpenWrt 备份

| 客户端 | 一致性动作与内容 |
| --- | --- |
| GitLab | gitlab-backup create；备份生成的归档、/etc/gitlab、证书、秘密与启动依赖 |
| Nexus | 停应用写入；pg_dump；备份数据库 dump、表数量/major、blob、配置、真实 RPM 快照及公开密钥；随后恢复服务 |
| dns/dns02 | named、区域、chrony、受控配置，各自独立仓库 |
| admin | 管理配置、Vault 输入、受保护 CA、个人/部署恢复材料、应用读取凭据与 OpenWrt 加密归档 |

Nexus 不备份运行中 PGDATA 冒充一致性；DNF current 先 readlink 得到真实快照目录再备份。GitLab 原生备份没有覆盖全部配置/秘密，必须与 /etc/gitlab 等一并保存。

**OpenWrt 专用备份身份，位置：admin root。**

```bash
bash /srv/cnpl/configuration/scripts/operations/openwrt-backup-key.sh
```

[正式入口](scripts/operations/openwrt-backup-key.sh) 通过已验证的部署身份查询专用公钥是否存在，仅缺失时用 `ssh-copy-id` 安装；已有私钥/公钥复用，异常重复停止。它始终引用 ops 已核对的 OpenWrt known_hosts，并显式指定部署私钥，只交互解锁、不打开密码认证。

[OpenWrt 核验脚本](scripts/operations/10-openwrt-backup.sh) 只读检查专用公钥。admin 首次生成带固定 tar 命令、关闭转发/PTY 的公钥授权行，直接通过 ssh-copy-id 追加；不会先装通用公钥再改写授权文件。已有不符的授权停止人工核对，其他部署授权保持原样。最后使用专用密钥请求一个普通 printf 命令，必须仍返回合法配置归档；不能执行普通 shell。Dropbear 不支持限制时停止，不降级成通用 root 无人值守身份。订阅等秘密只进入加密仓库。

### 10.5a 首轮备份执行与记录

**位置：admin，ops。** OpenWrt 受限身份已验证、所有停服窗口已确认后，逐台首轮：

```bash
ansible-playbook backup.yml --tags first-backup -e cnpl_backup_window_confirmed=true --ask-vault-pass
```

playbook serial=1，不同时停 Harbor/Nexus。脚本使用 flock 防重入，只有备份、仓库校验及原服务恢复均成功才写 `/var/lib/cnpl/backups/last-success.json`。失败保留非零退出与日志，不用旧快照冒充本次成功。

### 10.6 systemd 定时任务与失败告警

```bash
ansible-playbook backup.yml --tags timers --ask-vault-pass
ansible 'private_services:dns_servers:management' -b -m ansible.builtin.command -a 'systemctl list-timers --all' --ask-vault-pass
```

只有本机首轮成功记录存在才安装/启用 timer。OnCalendar 显式使用 Asia/Shanghai，依次 Harbor 02:30、GitLab 03:00、Nexus 03:30、admin 04:00、dns 04:30、dns02 04:45，带随机偏移，实际备份时长超窗时先调整排程。

失败由 systemd 保留非零退出与日志；00 至少每日检查 failed units 和最新成功快照，后续接集中告警。保留策略须依据真实容量/RPO/RTO审查，本稿不自动 forget/prune 或删除历史快照。

### 10.7 恢复演练与独立副本

**位置：对应备份客户端，root。** 使用 [restore.sh](scripts/operations/restore.sh) 选择真实快照，提取到全新专用目录：

```bash
bash /opt/cnpl/provision/scripts/operations/restore.sh list
read -r -p '本次真实快照 ID: ' SNAPSHOT_ID
RESTORE_DIR=/srv/cnpl-restore-check/$(date -u +%Y%m%dT%H%M%SZ)
bash /opt/cnpl/provision/scripts/operations/restore.sh extract "$SNAPSHOT_ID" "$RESTORE_DIR"
```

目录存在则停止，不覆盖在用配置。先检查可用恢复空间；大体量仓库需有足够暂存空间，必要资源由 Web 人工准备。校验 zone、配置/证书摘要、GitLab 归档、Nexus 成对数据库与 blob、RPM 快照及签名。

500 GiB 是初始备份预算，不保证容纳全部制品和保留点。backup 与三台 ESXi 同平台，仍须完成 10.9 的独立副本恢复，才能交付独立备份能力。

### 10.8 独立恢复实例的实际验收

**主 DNS root：**

```bash
read -r -p '本机已提取的 DNS 快照目录: ' RESTORE_DIR
bash /opt/cnpl/provision/scripts/operations/restore.sh dns "$RESTORE_DIR"
```

脚本对恢复区域做语法检查，临时 named 仅监听回环 1053，必须实际返回 Harbor `.12`。仅停止本次 PID、撤销本次新增端口映射、删除本次测试配置；不停止生产 named，不修改原快照。

**Nexus root：**

```bash
read -r -p '本机已提取的 Nexus 快照目录: ' RESTORE_DIR
bash /opt/cnpl/provision/scripts/operations/restore.sh nexus-db "$RESTORE_DIR"
```

要求 PostgreSQL major 一致，使用唯一临时数据库实际 pg_restore，核对 schema 表数；只删除本次创建的测试库，生产 nexus 库不变。

DNS/数据库校验之外，三个私服整服务恢复使用 [rebuild-service.sh](scripts/operations/rebuild-service.sh)。每次备份保存来源角色、machine-id 和 GitLab 精确 RPM；恢复脚本要求替代 VM 的 machine-id 与来源不同，拒绝原生产 VM、非空数据目录、已有 Nexus 表或已有 GitLab 项目。

**人工边界：** 在维护窗口通过 Web 停止原 VM，从 rocky-base 创建同角色替代 VM，核对容量、独立身份与新磁盘，完成 3.5 管理授权；重新人工核验该主机的 SSH 指纹，脚本不清空 known_hosts 或重建 SSH 身份。更新并保留新旧磁盘记录，原备份不变。恢复目录必须有足够暂存空间；恢复目标在验收前隔离业务流量。

Harbor：先在替代 VM 按第六章执行 runtime 阶段，保留空 `/data`；将同一快照提取到本机独立目录后，以 root 执行：

```bash
CNPL_REBUILD_CONFIRMED=yes bash /opt/cnpl/provision/scripts/operations/rebuild-service.sh application "$RESTORE_DIR"
```

脚本回填配套数据/配置/秘密，校验 Harbor 种子并生成 Image ID + pull_policy=never overlay，恢复专用防火墙/unit，启动后验证 health。继续从 admin 验证原镜像实际拉取、项目权限及扫描。

Nexus：替代 VM 先按 3.6 挂新盘，用同发行版受信任 RPM 经 OpenWrt 安装恢复引导所需 Nginx/restic，并恢复 CA；提取快照后先恢复 DNF：

```bash
CNPL_REBUILD_CONFIRMED=yes bash /opt/cnpl/provision/scripts/operations/rebuild-service.sh rpm-source "$RESTORE_DIR"
```

该模式恢复真实 RPM 快照、密钥、签名服务与 HTTPS，先按 5.6 验证。再从 admin 按第五章执行 `nexus.yml --tags pg,runtime,https`，只准备相同 major 的空数据库及运行时，不初始化 Nexus 应用数据。回到替代 VM root 运行同一个 application 命令。它核对空库，恢复逻辑数据库和 blob/秘密，校验并加载 Nexus 离线种子，以 Image ID overlay 启动；继续从 admin 运行第五章的真实读取、发布与权限验收。

GitLab：从已恢复 DNF 安装备份所记录的精确 RPM，按第七章 configure 准备空实例。提取快照后运行同一个 application 命令，选择本次配套 GitLab 归档 ID；脚本恢复 /etc/gitlab 和秘密，停止 Puma/Sidekiq，调用官方 gitlab-backup restore，再重启和检查。继续从 admin 验证原项目 clone/push、main 保护和认证拒绝。

恢复出来的 Harbor/Nexus unit 使用独立恢复 overlay，保留原始 digest/Image ID 证据。恢复验收使用 verify/真实请求入口，后续常规配置变更需明确处理该恢复模式，不能未经审核重新生成编排。完整恢复结果、所用快照、版本和耗时都进入记录；文件提取、restic check 或表数不能代替整服务恢复通过。

### 10.9 复制到独立介质并从该副本恢复

**位置：对应客户端 root，或具备同等受控凭据的恢复端。** 人工证明介质独立于三台 ESXi 后：

```bash
read -r -p '已确认的独立介质实际挂载点: ' INDEPENDENT_MOUNT
CNPL_INDEPENDENT_MEDIA_CONFIRMED=yes bash /opt/cnpl/provision/scripts/operations/restore.sh independent-copy "$INDEPENDENT_MOUNT"
```

脚本确认挂载，创建/复用独立加密仓库，通过 restic copy 复制逻辑快照并 check，避免复制正在写入的仓库目录。独立口令另存离线副本；目标非空但不属于已知仓库时停止。

从该独立仓库选择真实快照 ID，再提取到另一个新目录，重复 10.8 功能验证：

```bash
read -r -p '独立仓库中的真实快照 ID: ' INDEPENDENT_SNAPSHOT
INDEPENDENT_RESTORE=/srv/cnpl-restore-check/independent-$(date -u +%Y%m%dT%H%M%SZ)
bash /opt/cnpl/provision/scripts/operations/restore.sh independent-extract "$INDEPENDENT_MOUNT" "$INDEPENDENT_SNAPSHOT" "$INDEPENDENT_RESTORE"
```

记录源/独立快照、实际恢复结果与耗时。缺独立介质、空间、口令或完整恢复结果时保留未完成状态，不宣称满足 RPO/RTO。

## 11. 全量验收与 01 交接

### 11.1 核对全 19 台资源、身份与放置

**位置：admin。** 用 Ansible 采集 18 台 Rocky 的公开信息，OpenWrt 另用 raw；不读取用户数据、私钥或 Secret。

```bash
cd /srv/cnpl/inputs
export ANSIBLE_CONFIG=/srv/cnpl/inputs/ansible.cfg
ansible rocky_nodes -m ansible.builtin.setup -a 'gather_subset=min' --ask-vault-pass
ansible rocky_nodes -b -m ansible.builtin.command -a 'cat /etc/machine-id' --ask-vault-pass
ansible rocky_nodes -b -m ansible.builtin.command -a 'cat /sys/class/dmi/id/product_uuid' --ask-vault-pass
ansible rocky_nodes -b -m ansible.builtin.command -a 'ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub' --ask-vault-pass
ansible rocky_nodes -m ansible.builtin.command -a 'ip -j address show ens33' --ask-vault-pass
ansible rocky_nodes -m ansible.builtin.command -a 'lscpu -J' --ask-vault-pass
ansible rocky_nodes -m ansible.builtin.command -a 'free --bytes' --ask-vault-pass
ansible openwrt_hosts -m ansible.builtin.raw -a 'cat /etc/openwrt_release; ip addr; ip route'
```

把返回的主机名、IP、machine-id、BIOS UUID、MAC、SSH 指纹汇总成矩阵，逐项确认唯一；在 vSphere Web 人工核对 19 台运行 VM 的 CPU、内存、磁盘和宿主机放置。rocky-base 另作为关机模板登记，检查其无角色材料和用户授权；不列入运行节点。只运行命令但未检查唯一性不算通过。

### 11.2 服务验收矩阵

| 项目 | 正向验收 | 拒绝 / 恢复验收 |
| --- | --- | --- |
| 管理路径 | Mac → admin 公钥登录；admin → 其余 VM | Mac 到其他 VM 无可用入口；其他 VM 不能用部署密钥管理横向主机 |
| OpenWrt | admin 及五台服务 VM 经 7890 出网；五台 Google HTTPS 均为 204、代理端点为 `.10`；内网直连 | 停止代理后五台 Google 请求失败，内网源仍可读；恢复后五台重新通过 |
| DNS / NTP | 系统解析、UDP/TCP、PTR、时钟同步 | 单 DNS 服务停止仍可解析；Mac 不获得 DNS / NTP 服务 |
| DNF | 签名与 TLS 校验、内网安装实际 RPM | 禁用公共源和代理后仍可安装已同步版本；错误签名拒绝 |
| Harbor | 健康、镜像推拉、摘要一致、扫描库 | 只读推送失败、私有项目匿名失败、Mac 443 被拒绝 |
| GitLab | 私有项目 clone / push 与权限生效 | 未授权密钥失败；受保护分支拒绝未授权写入 |
| Nexus | 固定版本 Maven / npm / PyPI 请求、缓存 | 匿名失败、只读上传失败、代理停止后缓存内容可读 |
| 十节点 CRI | Harbor 镜像拉取、sandbox / 容器 / 日志 / 清理 | 无新增 AVC；重启后配置保持；不要求此时 CNI Ready |
| 备份 | 快照、完整性、隔离恢复、独立副本 | 错误口令不可解密；恢复数据与预期一致 |

拒绝路径由 admin 在已准备的未授权来源主机编排有界测试，不授予该访问权限。Mac 侧仅保留登录 admin 的命令；对其余 VM 核对实际规则不含 Mac 来源授权，不为测试增加 Mac 到其他 VM 的管理通道。

### 11.3 断网供应检查

先在 build01 预热确定的 RPM 和 Nexus 固定版本依赖，记录包名、版本、摘要与所需构建工具；再停止 OpenWrt 代理，按同样输入复测。

```bash
# admin：停止代理；本动作有临时外部供应中断
ssh cnpl-openwrt '/etc/init.d/mihomo stop'
```

代理停止期间，五台服务 VM 重复 3.6 的 Google 请求应非零失败，内网软件源请求仍应为 `HTTP=200 peer=192.168.9.14`。在 build01 使用仅内网源的 DNF 请求、Nexus 已缓存内容和 Harbor 已复制镜像；不得偷偷打开公共源作为回退。测试结束不论成功失败都恢复代理：

```bash
# admin
ssh cnpl-openwrt '/etc/init.d/mihomo start'
```

恢复后重复 2.9 及 9.1 的五台服务 VM Google 验收，记录断网开始、结束、结果与残留。只有实际取得所需安装包和制品、运行约定构建成功，才能标记离线供应通过。

### 11.4 重启与配置保持

先逐台重启服务 VM，再逐台重启十节点；保留双 DNS 至少一台在线，备份任务不与重启窗口重叠。admin 最后单独重启，由 Mac 重新连接。

每台重启后检查地址、路由、DNS、时间、挂载、SELinux、firewalld、SSH 和角色服务；五台服务 VM 在新登录会话复验 Google 与内网直连，确认代理配置持久有效；十节点重新运行 CRI 验收。OpenWrt 重启后由 procd 自动恢复 Mihomo，仍不提供 DHCP / RA。源模板保持关机，不作为本轮重启目标。

### 11.5 输出交接材料

在 admin 的 `/srv/cnpl/records/<实际批次>/` 留存脱敏材料：

1. 19 台 VM 的资源、放置、磁盘、身份矩阵。
2. RPM 完整 NEVRA、仓库快照、GPG 指纹、容器版本与摘要。
3. DNS / NTP / TLS、私服正向请求和权限拒绝结果。
4. 防火墙 INPUT、容器转发、主机 OUTPUT 的实际规则及恢复后复验结果。
5. 十节点 CRI 生命周期、重启、幂等检查与 OSD 空盘映射。
6. 备份与独立恢复结果、未完成项、明确的下一阶段输入。

未执行、失败、只做静态检查的项目分别标注。00 阶段不创建 Kubernetes 集群、不安装 CNI、不初始化 Ceph OSD；01 基于已交付的计算、网络与存储资源部署完整生产集群。

## 12. 故障处理与资料依据

### 12.1 故障处理顺序

- SSH 失败：先从保留的控制台检查地址、路由、来源规则、公钥权限和 `sshd -t`，再重载；不重新打开全网 SSH。
- 下载失败：区分 DNS、时钟、TLS、代理、上游签名与版本不存在；不关闭证书或签名校验。
- 服务失败：先查挂载、unit、容器状态和对应日志，再查 AVC；不递归修改整块盘权限或关闭 SELinux。
- 数据盘异常：先停受影响服务并保留证据，核对 UUID 与稳定设备 ID；不对未知设备执行 mkfs、wipefs 或 ceph 初始化。
- 仓库更新失败：保持旧快照入口，修复新批次并重新校验；不覆盖已验收快照。
- 恢复失败：保留独立恢复目录和错误信息，禁止覆盖在用数据来“试一下”。

### 12.2 上游资料

以下为本稿编写时核对的主要资料。其安装示例中不符合本方案限制的方法不采用；具体运行兼容性仍以实际目标环境验收为准。

- [OpenWrt 25.12 系列与官方镜像](https://openwrt.org/releases/25.12/start)
- [OpenWrt x86_64 官方 APK 仓库](https://downloads.openwrt.org/releases/packages-25.12/x86_64/packages/)
- [Mihomo v1.19.32 上游发布](https://github.com/MetaCubeX/mihomo/releases/tag/v1.19.32)
- [Mihomo 配置与代理集合](https://wiki.metacubex.one/config/proxy-providers/)
- [Ansible 的发行版与 EPEL 安装方式](https://docs.ansible.com/projects/ansible/latest/installation_guide/installation_distros.html)
- [Helm 的 EPEL RPM 版本](https://packages.fedoraproject.org/pkgs/helm/helm/)
- [vSphere Web 上传文件](https://knowledge.broadcom.com/external/article/403632/how-to-upload-or-download-files-to-or-fr.html)
- [OpenSSH ssh-copy-id 与 OpenWrt 授权路径](https://github.com/openssh/openssh-portable/blob/master/contrib/ssh-copy-id)
- [Docker RHEL RPM 安装](https://docs.docker.com/engine/install/rhel/)
- [Docker 的转发与防火墙规则](https://docs.docker.com/engine/network/packet-filtering-firewalls/)
- [Harbor 官方部署文档](https://goharbor.io/docs/edge/install-config/)
- [Harbor v2.15.4 发布](https://github.com/goharbor/harbor/releases/tag/v2.15.4)
- [GitLab 官方 Linux 软件包](https://docs.gitlab.com/install/package/)
- [Nexus 官方容器](https://help.sonatype.com/en/cloud-deployments.html)
- [Nexus PostgreSQL 部署要求](https://help.sonatype.com/en/install-nexus-repository-with-a-postgresql-database.html)
- [Nexus 官方 REST API](https://help.sonatype.com/en/api-reference.html)
- [containerd 2.x CRI 配置](https://github.com/containerd/containerd/blob/main/docs/cri/config.md)
- [Restic 的 EPEL RPM](https://packages.fedoraproject.org/pkgs/restic/restic/)
