# Phase 00：服务器创建、Linux 初始化与 CRI 部署

本手册展开 00.04.03、00.04.05、00.10.01、00.10.02，属于 **00 阶段必做实施**。完成后交付十台具备入群条件的服务器。01 只复验并执行 kubeadm init/join，不再承担 Linux 和 containerd 的首次安装。

当前阶段进行中，部分母机操作已有[执行记录](records/2026-10-14/README.md)，十节点尚未交付验收。下面的路径是实施时应编写的交付文件，命令在具体操作时由管理机或目标 Rocky 节点执行；本手册本身不表示已经连接服务器或完成部署。`LAB_*` 参数必须来自已核实台账和版本锁，示例中的占位值不得直接上线。

[阶段计划与验收](../../plan/00-preparation.md) · [共用输入与记录规范](../README.md)

## 1. 执行顺序与自举来源

| 批次 | 实际动作 | 完成后可用的能力 |
| --- | --- | --- |
| A | 准备离线种子、管理工具；创建 Rocky 模板；核实 CPU/EVC 与 VMXNET3 | 可以安全创建 VM 和登录客体 |
| B | 创建管理/基础服务 VM，部署 OpenWrt、DNS、CA、GitLab、Harbor、Nexus | 内部解析、信任与软件供应独立可用 |
| C | 克隆十台节点；配置身份、磁盘、网络、时间、SSH、软件源、内核、安全策略 | Linux 基线实际完成 |
| D | 安装并配置 containerd/runc/crictl、Kubernetes 工具；镜像预热与 CRI 运行测试 | 运行时可用，仍未创建 Kubernetes 集群 |
| E | 重启复验、重复执行 Ansible、断网安装/构建检查、备份和交接 | 00 验收通过，可以进入 01 |

批次 A 使用已校验 ISO、RPM/归档、工具和容器物料作为种子；不依赖尚未部署的 Nexus/Harbor。Harbor 等集群外服务按其官方部署方式准备专用运行环境，不能要求它们先使用集群 PVC，也不能把其 Docker/Compose 依赖复制到 Kubernetes 节点作为 CRI。

## 2. 准备自动化文件和输入

实施时在 `ops/00-preparation/ansible/` 建立以下文件，不将资产台账直接误当 Ansible Inventory：

| 文件 / 目录 | 具体内容 |
| --- | --- |
| `inventories/lab/hosts.yml` | `control_plane`、`infra`、`storage`、`worker`、`bootstrap_services` 主机组，IP 和远程用户 |
| `inventories/lab/group_vars/all.yml` | DNS、NTP、CA 路径、内部软件源、管理员公钥、锁定版本 |
| `inventories/lab/host_vars/<node>.yml` | FQDN、已确认网卡连接名、网关、磁盘 UUID、物理宿主机、角色预留 |
| `roles/node_base/` | 用户、SSH、网络、时间、软件源、挂载、sysctl、Swap、安全和日志 |
| `roles/container_runtime/` | containerd/runc/crictl 安装、配置、CA、systemd 和 CRI 检查 |
| `playbooks/bootstrap-nodes.yml` | 按 node_base → container_runtime 执行，串行批次和重启检查 |
| `ops/00-preparation/tests/smoke/node-readiness.sh`（仓库根目录下） | 只读主机检查与结构化结果；CRI 运行测试另加显式启用参数 |

Rocky 基础服务 VM 同样复用 `node_base`；`container_runtime` 只应用于十个 Kubernetes 节点。OpenWrt 使用自己的配置流程，Harbor 所需专用运行环境由仓库角色负责，不把它们混入节点 CRI 角色。

先从根目录运行 `ansible-inventory -i ops/00-preparation/ansible/inventories/lab/hosts.yml --graph`，检查十节点数量和分组；再对 `cp01` 运行 `ansible ... -m ping`。密码、sudo 凭据和私钥使用受控引用，不写入这些明文文件。

OpenTofu 模块在 `ops/00-preparation/opentofu/` 声明模板、Datastore、Port Group、CPU、内存与磁盘；先 `tofu init`、`tofu validate`、`tofu plan -out=...`，逐项核对计划仅创建本项目 VM，再执行保存的 Plan。既有资源未明确纳管前不 import、不替换、不 destroy。State 单独安全备份，Git 不提交 State 和含秘密的 Plan 文件。

## 3. 创建 Rocky 模板与克隆身份

1. 使用锁定 ISO，核对 SHA256/签名；在每类宿主机/EVC 配置上启动试装 VM。Rocky 10 的 x86_64 基线要求 x86-64-v3，必须检查客体实际暴露的能力，不能只看 CPU 型号。[Rocky 官方发布说明](https://docs.rockylinux.org/latest/releases/release_notes/10_0/)
2. 采用最小安装，确认 UEFI/启动盘和目标磁盘；OS 盘与未来运行时/OSD 盘分开。安装 `open-vm-tools`、NetworkManager、chrony、SSH 和所需诊断工具。
3. 网卡选择 VMXNET3；执行 `ip -br link`、`ethtool -i <实际网卡>`、`systemctl is-active vmtoolsd`，检查驱动、速率和管理端看到的客体信息。
4. 模板仅保留公共基线。封装过程处理 machine-id、SSH host key、DHCP/连接身份和日志；首次启动再生成唯一标识，不在每次 Ansible 执行时删除身份。
5. 连续创建两个临时克隆，比较 `cat /etc/machine-id`、`cat /sys/class/dmi/id/product_uuid`、网卡 MAC 与 `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`；验证不同身份后才复制十台节点。
6. cp01/storage01、cp02/storage02、cp03/storage03 分别放在三台 ESXi，其他节点按物理拓扑放置。保存克隆参数与 vSphere Task 结果，失败只清理本次创建且无数据的对象。

验收：模板能冷启动和重启；克隆身份唯一；Mac/管理机能够经已验证主机密钥登录。模板不含业务凭据、VPN 私钥或长期管理员 kubeconfig。

## 4. 磁盘、目录与文件系统

先执行只读检查：

```bash
lsblk -e7 -o NAME,PATH,SIZE,TYPE,FSTYPE,UUID,MOUNTPOINTS,MODEL,SERIAL
findmnt --verify --verbose
df -hT
```

按设备稳定 ID 对照台账，再为新建且已确认用途的系统/运行时盘创建文件系统和挂载；不对所有“未挂载盘”自动格式化。运行时数据规划挂载到 `/var/lib/containerd`，kubelet 与构建临时空间分别核算，记录 inode 与容量。

`/etc/fstab` 使用 UUID 等稳定标识；专用运行时盘应配置挂载依赖和检查，盘丢失时阻止 containerd 悄悄写入系统根盘。启用服务前用 `mountpoint`/`findmnt` 验证实际挂载。

storage01–03 的候选 OSD 保持未使用，不创建分区、LVM、文件系统或通用挂载；00 仅记录稳定 ID 和物理来源，03 才执行 cephadm 初始化。磁盘尚未核实时，该节点不能通过磁盘验收。

## 5. 网络、主机名和 DNS

1. 每台设置与台账一致的 FQDN，例如 `cp01.k8s.internal.egon.top`；先以 `nmcli connection show` 获取实际连接名，禁止假定都叫 `eth0`。
2. 用 NetworkManager 配置静态 IP、掩码、已核实的默认网关、DNS `.11` 和内部搜索域。保持原 LAN 默认网关，不能统一指向 OpenWrt 旁路由。
3. 网络变更前保留控制台或第二管理连接；先更改一个节点并验证 SSH 回连，再小批量执行。持久配置由 Ansible 模板/任务保存，不能只运行临时 `ip addr add`。
4. 配置完成检查实际路由和系统解析，不用 `/etc/hosts` 长期替代 DNS：

```bash
hostnamectl --static
ip -br address
ip route
nmcli device show
getent hosts cp01.k8s.internal.egon.top
getent hosts harbor.k8s.internal.egon.top
getent hosts gitlab.svc.internal.egon.top
```

从不同 ESXi 上的节点互相访问，并检查 MTU；失败时先定位 Port Group、vSwitch、上联、客体防火墙与回程路由。一次 ping 不能代替后续 TCP/TLS、Overlay 和 VIP 检查。

## 6. 软件源、账户、时间与 CA

- 将经过校验的 Rocky BaseOS/AppStream、工具 RPM 和 Kubernetes 版本仓库映射到受控内网源；保留 GPG 校验。安装所需 `curl`、`jq`、`tar`、`ethtool`、`bind-utils`、`iproute`、诊断工具及 runtime 依赖，固定来源和包版本；不执行来源不明的在线安装脚本。
- 创建专用管理账户、分发公钥、配置有限 sudo；用 `sshd -t` 检查后 reload，并从第二会话确认登录，再收紧 root/密码登录。不要提前关闭唯一可用登录方式。
- 配置 `/etc/chrony.conf` 指向核实过的时间源；确定 VMware 客体时间同步和 chrony 的职责，避免两套持续纠偏互相干扰。检查 `chronyc sources -v`、`chronyc tracking`、`timedatectl`；无有效时间源不能通过。
- 将公开 CA 证书写入 `/etc/pki/ca-trust/source/anchors/` 并执行 `update-ca-trust`。先校验 CA 指纹，再验证 Harbor/GitLab/Nexus 的 TLS，不使用 `curl -k` 或 `skip_verify` 作为验收。
- 为 journald/系统日志配置明确的占用上限和保留；检查 `/var/log`、系统盘与 runtime 盘水位。实际大小来自容量预算，不能套一个无限保留配置。

```bash
sudo sshd -t
chronyc tracking
sudo update-ca-trust
curl -I https://gitlab.svc.internal.egon.top
curl -I https://nexus.svc.internal.egon.top
curl -sS -o /dev/null -w '%{http_code}\n' https://harbor.k8s.internal.egon.top/v2/
```

Harbor `/v2/` 未认证返回 `401` 可用于证明 TLS 和 Registry 端点可达，不代表已拥有拉取权限；实际镜像拉取在第 10 节验收。

## 7. cgroup、Swap、内核与主机安全

本次实验的安全约束（2026-10-14 用户明确要求）：SELinux 必须保持 Enforcing，firewalld 必须保持启用；不得通过 permissive、disabled 或停止防火墙绕过兼容性问题。运行时、CNI 和存储组件需验证相应策略、标签及来源受限规则；缺少支持时保留阻塞项并排查，不降低安全模式。

00 必须把以下配置实际写入主机并在重启后验证，不能只登记“待 01 处理”。

| 配置位置 | 本阶段动作 | 检查结果 |
| --- | --- | --- |
| `/sys/fs/cgroup` 与启动参数 | 确认 cgroup v2，containerd 采用 systemd cgroup | `stat -fc %T /sys/fs/cgroup` 为 `cgroup2fs` |
| `/etc/fstab`、Swap unit / zram 来源 | 起步关闭 Swap，并移除对应持久启用项；保留原配置 | `swapon --show` 无激活项，重启后仍一致 |
| `/etc/modules-load.d/` | 按所选运行时加载 overlay；桥接路径需要时再加载 br_netfilter | `lsmod` 和内核能力检查符合所选数据面 |
| `/etc/sysctl.d/90-kubernetes.conf` | 持久配置 `net.ipv4.ip_forward=1`；桥接 netfilter 参数按实际模式核对 | `sysctl net.ipv4.ip_forward` 返回 1，无未知键错误 |
| firewalld/nftables | 按下表配置来源受限规则，保存原规则与回退入口 | 允许与拒绝用例都通过 |
| `/etc/selinux/config` 与策略包 | 明确实际模式、runtime 支持和必要文件标签；检查 AVC | `getenforce` 与文档一致，CRI 测试无未处理拒绝 |
| 主机变量 / kubelet 规划 | 填写按角色的 OS、kubelet、Ceph 预留预算 | 01 将预算写入 kubelet 并复验 Allocatable |

不要盲目设置 `rp_filter`、关闭 IPv6、修改全局文件句柄或套用“性能优化参数包”。有具体 CNI/存储需求时再加参数和对应验证。SELinux 不能直接照抄其他发行版配置；官方 kubeadm RPM 示例采用 permissive，本次不能照做，必须在 Enforcing 下验证实际支持和策略。[运行时文档](https://kubernetes.io/docs/setup/production-environment/container-runtimes/)；[安装前置](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/)

| 访问目标 | 来源与端口设计 |
| --- | --- |
| SSH | 授权管理终端 → 节点 TCP 22 |
| DNS / 时间 | 节点 → 基础 DNS TCP/UDP 53；节点 → 时间源 UDP 123 |
| 仓库 | 节点 → 基础服务 HTTPS 443，其他端口按实际配置登记 |
| API | 授权管理端与节点 → 控制平面/VIP TCP 6443 |
| etcd | 三控制平面之间 TCP 2379–2380，不向普通 LAN 开放 |
| kubelet | 授权控制平面及后续监控来源 → 节点 TCP 10250 |
| Cilium 基础 Overlay | 节点之间所选 VXLAN UDP 8472 或 Geneve UDP 6081；只启用实际选定模式 |
| Cilium 健康检查 | 节点之间 TCP 4240 与所需 ICMP，按锁定版本核对 |
| Ceph / Hubble / NodePort / 网关 | 仅预留来源和用途，03/02 启用时落实具体规则，不提前放开整网全部端口 |

00 检查主机规则持久性与节点路径；01 部署真实 CNI/API 后验证数据面。`ss -lntup` 在 00 看不到 kube-apiserver 属于正常现象，不应为了通过检查提前 init。

## 8. 安装 containerd、runc、crictl 与入群工具

1. 从版本锁读取 containerd 2.x、runc、crictl 的精确版本、体系结构、来源和校验值。选择已经在 Rocky 10 验证过的 RPM 或官方二进制安装路线，不假设系统仓库天然提供全部组件。
2. 使用种子或内网源安装，保留包清单；归档路线需同时交付 systemd unit、runc 和必要 CNI 工具，不能只复制一个 containerd 二进制。`containerd --version`、`runc --version`、`crictl --version` 均与锁定集合一致。
3. 按锁定版本的默认配置生成受控模板，配置 `/etc/containerd/config.toml`、registry hosts、CA 与 systemd。runtime 数据盘先挂载，再启用服务。
4. 安装锁定 kubeadm、kubelet、kubectl 工具包并防止未经计划的次版本升级；00 不执行 init/join。kubelet 在配置生成前不作为健康服务验收，具体启动由 01 的 kubeadm 流程接管。
5. `containerd config dump` 检查最终配置；启动后检查 `systemctl is-enabled containerd`、`systemctl is-active containerd`、`journalctl -u containerd -b` 和 CRI 插件状态。不要在已有业务节点上无条件覆盖配置/重启。

containerd 2.x 配置 v3 的关键项如下，实施时合并到该版本生成的完整配置。下面的 `pinned_images.sandbox` 与 `certs.d` 是 Harbor（00.09.02）和内部 DNS（00.07.01）就绪后的目标形态，`<PAUSE_DIGEST>` 必须替换为已同步镜像的实际 Digest：

```toml
version = 3
root = "/var/lib/containerd"
state = "/run/containerd"

[plugins."io.containerd.cri.v1.runtime".containerd.runtimes.runc]
  runtime_type = "io.containerd.runc.v2"
[plugins."io.containerd.cri.v1.runtime".containerd.runtimes.runc.options]
  SystemdCgroup = true

[plugins."io.containerd.cri.v1.images".pinned_images]
  sandbox = "harbor.k8s.internal.egon.top/bootstrap/pause@sha256:<PAUSE_DIGEST>"
[plugins."io.containerd.cri.v1.images".registry]
  config_path = "/etc/containerd/certs.d"
```

不能继续写 1.x 的 `io.containerd.grpc.v1.cri` 配置路径，也不能让 CRI 留在禁用插件列表。字段以锁定发行版配置为准。[containerd CRI 配置](https://github.com/containerd/containerd/blob/main/docs/cri/config.md)

**Harbor 与 DNS 就绪前不要写入上面的 `pinned_images.sandbox`。** 指向一个不存在的仓库会让 `RunPodSandbox` 在拉取阶段直接失败，并且无法通过 `--noproxy` 或信任配置绕过。此时保留锁定版本生成的默认 sandbox 引用，按第 10.1 节把该引用的镜像以种子物料导入本地；`certs.d` 目录可以先建立但保持为空，不预写任何主机条目。Harbor 投产后再改为固定 Digest，并重新执行一次第 10 节自测确认引用切换成功。配置里出现内部域名不代表该域名已可解析。

## 9. Registry、CA 与 crictl 配置

计划交付 `roles/container_runtime/templates/config.toml.j2`、`hosts.toml.j2`、`crictl.yaml.j2`。本节的 `/etc/crictl.yaml` 在母机阶段即可写入；`hosts.toml` 属于 Harbor 就绪后的交付物，Harbor 未部署时不写该文件。Harbor 示例 hosts 文件保存到 `/etc/containerd/certs.d/harbor.k8s.internal.egon.top/hosts.toml`：

```toml
server = "https://harbor.k8s.internal.egon.top"
[host."https://harbor.k8s.internal.egon.top"]
  capabilities = ["pull", "resolve"]
  ca = "/etc/pki/ca-trust/source/anchors/lab-root-ca.crt"
```

这只配置端点和信任，不会自动提供认证。引导镜像必须采用已经验证的节点只读认证或内网受限的只读引导项目；不能依赖尚不存在的 Kubernetes Secret。临时用人工凭据拉一次镜像，也不能证明之后静态 Pod 能自行拉取。

`/etc/crictl.yaml`：

```yaml
runtime-endpoint: unix:///run/containerd/containerd.sock
image-endpoint: unix:///run/containerd/containerd.sock
timeout: 20
debug: false
```

分别通过系统 HTTPS 客户端和 CRI 拉取验证；`ctr images pull` 成功不能替代 CRI 配置验收。`NO_PROXY` 覆盖内部域、回环、节点/Pod/Service 网段，逐个客户端核对匹配行为。上述拉取验证以 Harbor 可达为前提；Harbor 之前的镜像供应按第 10.1 节的种子导入路线执行，此时没有 registry 拉取结果可供验收，也不能因为缺少仓库就改用未核实的公共镜像源。

crictl 属于 cri-tools，与 containerd 分开发布，版本锁中 `cri_tools` 仍为 `null`。执行第 10 节前先按 00.02.02 锁定与锁定 Kubernetes 次版本对应的 cri-tools 版本、架构、来源和 SHA256，再按第 1 节批次 A 的种子物料路线安装；`policy.exact_versions_required` 不允许凭 latest 或系统仓库顺带提供的版本进入节点。[cri-tools 发布与版本对应说明](https://github.com/kubernetes-sigs/cri-tools/blob/master/README.md)

## 10. 无 Kubernetes、无 CNI 的 CRI 自测

先验证 `sudo crictl info` 的 RuntimeReady。00 尚未安装 Cilium，NetworkReady 可因 CNI 未安装为 false，这是明确的阶段边界；不能把它说成 Pod 网络已经通过。用 host-network sandbox 测试 runtime，01 再验收普通 Pod 网络。

本节有两条镜像来源路线，验收标准相同，前置不同。Harbor（00.09.02）和内部 DNS（00.07.01）尚未部署时执行 10.1；两者投产后按 10.2 重做一次，确认引用切换成功。两条路线都不改变 SELinux Enforcing 与 firewalld 启用的要求。

| 路线 | 适用时机 | 镜像来源 | 本阶段能证明什么 |
| --- | --- | --- | --- |
| 10.1 种子导入 | Harbor/DNS 之前，含母机 | 管理端已校验归档，scp 后导入本地 | runtime、cgroup、SELinux 标签和容器执行链路可用 |
| 10.2 内网仓库 | Harbor/DNS 就绪后 | Harbor 引导项目的固定 Digest | 追加证明 CRI 的 registry 配置、CA 信任和只读认证可用 |

10.1 通过不代表仓库拉取路径已验收；10.2 未执行前，第 12 节的「CRI」行只能记为部分通过。

### 10.1 种子导入路线（Harbor 之前）

沿用第 1 节批次 A 的自举方式：管理端取得并校验镜像归档，scp 到目标机，再导入 containerd。关键点是 **CRI 只查看 `k8s.io` 命名空间**，导入时必须显式指定，否则 `crictl images` 看不到镜像，而 `ctr images ls` 却显示存在。

先在管理端确定要导入哪个 sandbox 引用——不要假定具体 tag，从目标机实际生效的配置读取：

```bash
sudo containerd config dump | grep -A3 'pinned_images'
sudo crictl info | jq -r '.config.sandboxImage'
```

按该引用和一个含 `/bin/sh` 的测试镜像（busybox 一类）在管理端导出归档。Mac 多为 arm64，必须强制 `linux/amd64`，否则导入后容器以 `exec format error` 失败：

```bash
# 管理端；<SANDBOX_REF> 用上一步的实际输出，<SMOKE_REF> 为已在版本锁登记的测试镜像
crane pull --platform linux/amd64 <SANDBOX_REF> sandbox-image.tar
crane pull --platform linux/amd64 <SMOKE_REF>  cri-smoke.tar
shasum -a 256 sandbox-image.tar cri-smoke.tar
```

两份归档的来源、Digest 和 SHA256 按 00.02.03 登记后再传输；`crane`/`skopeo` 自身也是需要锁定的工具。导入与核对：

```bash
# 目标机
sudo ctr -n k8s.io images import --platform linux/amd64 sandbox-image.tar
sudo ctr -n k8s.io images import --platform linux/amd64 cri-smoke.tar
sudo crictl images
```

镜像必须出现在 `crictl images` 中才算导入成功。此路线下 **不执行 `crictl pull`**，第 10.3 节的 `LAB_SMOKE_IMAGE` 直接使用已导入的本地引用。

### 10.2 内网仓库路线（Harbor 之后）

Harbor、DNS 和 CA 就绪后，把同两个镜像按 Digest 复制到只读引导项目，按第 8 节写入 `pinned_images.sandbox`、按第 9 节写入 `hosts.toml`，重启 containerd，再执行 10.3 并在其中保留 `crictl pull` 一步。此时才产生 registry 配置、CA 信任与只读认证的验收证据。

### 10.3 共用的自测流程

在专用临时工作目录准备 `sandbox.json`（CRI 的 namespace enum 中 NODE 为 2，实施前对照锁定 cri-tools 版本）：

```json
{
  "metadata": {"name": "phase00-cri-smoke", "namespace": "phase00", "uid": "phase00-cri-smoke", "attempt": 1},
  "log_directory": "/var/log/phase00-cri",
  "linux": {"security_context": {"namespace_options": {"network": 2}}}
}
```

准备 `container.json`，镜像须含 `/bin/sh`。`<SMOKE_REF>` 在 10.1 下是已导入的本地引用，在 10.2 下是 Harbor 引导项目的固定 Digest：

```json
{
  "metadata": {"name": "smoke", "attempt": 1},
  "image": {"image": "<SMOKE_REF>"},
  "command": ["/bin/sh", "-c", "echo phase00-cri-ok"],
  "log_path": "smoke.log",
  "linux": {}
}
```

替换占位值、创建日志目录、确认仅针对新建实验节点后执行。先只读确认 RuntimeReady 和镜像已就位，再创建对象：

```bash
set -euo pipefail
sudo install -d -m 0755 /var/log/phase00-cri
sudo crictl info
LAB_SMOKE_IMAGE=$(jq -r '.image.image' container.json)
# 10.2 内网仓库路线才执行下一行；10.1 的镜像已由 ctr 导入，pull 会因无仓库而失败
# sudo crictl pull "$LAB_SMOKE_IMAGE"
sudo crictl images | grep -F "${LAB_SMOKE_IMAGE%@*}"
LAB_SANDBOX_ID=$(sudo crictl runp sandbox.json)
LAB_CONTAINER_ID=$(sudo crictl create "$LAB_SANDBOX_ID" container.json sandbox.json)
sudo crictl start "$LAB_CONTAINER_ID"
sudo crictl logs "$LAB_CONTAINER_ID"
sudo crictl inspect "$LAB_CONTAINER_ID"
```

等待容器终止，检查日志含 `phase00-cri-ok`、退出码为 0，再对本次记录的 ID 执行 `crictl rm`、`crictl stopp`、`crictl rmp`。失败时先保存 CRI/containerd/SELinux 证据，清理仅限本次对象；禁止清空整个 runtime 数据目录。

`runp` 阶段失败时先区分三类原因，不要先改安全配置：sandbox 镜像不在 `k8s.io` 命名空间（`crictl images` 为空而 `ctr -n default images ls` 有内容）、配置里的 `pinned_images.sandbox` 指向不可达仓库、或 Enforcing 下的真实拒绝。第三类用 `sudo ausearch -m AVC -ts recent` 取证并按策略处理，不通过 permissive 或停防火墙绕过。架构不符会表现为容器启动后立即以 `exec format error` 退出，属于导入时未锁定 `linux/amd64`，不是 runtime 缺陷。

随后将 kubeadm 控制面、etcd、CoreDNS、kube-vip、Cilium 镜像与 Chart 缓存到内网。使用 `kubeadm config images list --kubernetes-version <锁定版本>` 核对列表；镜像映射、认证和 Digest 落入物料清单。00 能取回引导镜像，01 才实际启动它们。

## 11. 批量执行、幂等与重启复验

以已经编写并语法验证的 Playbook 为前提，先 `cp01`，再每批一台扩展到其余角色；storage 组单独检查磁盘保护和资源预留。

```bash
ansible-playbook -i ops/00-preparation/ansible/inventories/lab/hosts.yml ops/00-preparation/ansible/playbooks/bootstrap-nodes.yml --syntax-check
ansible-playbook -i ops/00-preparation/ansible/inventories/lab/hosts.yml ops/00-preparation/ansible/playbooks/bootstrap-nodes.yml --check --limit cp01
ansible-playbook -i ops/00-preparation/ansible/inventories/lab/hosts.yml ops/00-preparation/ansible/playbooks/bootstrap-nodes.yml --limit cp01
```

Check mode 不能代替实际安装验收。完成一台后检查本手册各项结果，再执行下一台。第二次真实执行应无非预期变更，尤其不得重建 machine-id、SSH host key、格式化数据盘或重写已有密钥。

在阶段实施窗口逐台重启，复查 SSH、网卡地址、DNS、chrony、挂载、Swap、sysctl、firewall/SELinux、containerd 自启与 CRI 自测。不能仅凭重启前的输出交接。结果按主机写入 `ops/00-preparation/records/<执行批次>/`，命令日志必须脱敏。

## 12. 十节点交接清单与失败处理

| 验收项 | 预期结果 | 失败后处理 |
| --- | --- | --- |
| VM/身份/放置 | 十节点身份唯一，三 cp 分散三 ESXi | 修正模板/放置，再重新核验受影响节点 |
| 网络/DNS/时间 | 静态配置持久、系统解析正确、时间源有效 | 通过控制台恢复原网络，修复角色任务 |
| 软件源/CA/仓库 | 指定物料可内网获取，TLS 无绕过 | 补同步缺失包/证书链，不能转用不可信源 |
| OS/cgroup/Swap/安全 | 配置与预算一致，重启仍生效 | 修复持久配置与策略，记录明确例外 |
| CRI | containerd 自启，RuntimeReady，运行/日志/清理通过；镜像来源按 10.2 完成仓库拉取，仅完成 10.1 时标注为种子导入、仓库拉取待验 | 排查版本、socket、cgroup、证书、mount、AVC |
| 幂等 | 第二次执行无非预期变更 | 修复 Playbook，禁止用手工结果掩盖重复破坏 |
| 保护范围 | OSD 候选盘未被初始化，既有 VM/数据未受影响 | 阻止后续步骤并处理偏差 |
| 离线/备份 | 新客户端可完成指定安装/构建，基础服务可从独立备份恢复 | 补齐物料和恢复材料后重测 |

以上全部通过后填写阶段验收，01 才开始 kubeadm 配置与 init/join。主机缺陷回到 00 的对应配置修复；不通过 `kubeadm --ignore-preflight-errors=all` 绕过，也不把本阶段问题拖到 01 临时处理。
