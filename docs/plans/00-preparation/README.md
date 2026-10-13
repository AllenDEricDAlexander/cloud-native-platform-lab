# Phase 00｜基础设施、服务器初始化与软件供应准备

文档版本：V3.0。状态：未执行。步骤数：43。

本阶段实际创建 VM、部署基础服务，并完成十台 Rocky Linux 的系统初始化、containerd/runc/crictl 安装、镜像预热、CRI 自测和重启复验，交付可以直接进入 kubeadm init/join 的节点。资产统计只是开头，不是阶段成果。

前置条件：能够从 Mac 访问三台 ESXi 与 iDRAC；拥有虚拟机创建权限。公网域名 egon.top 的 DNS 管理权限、上游网关、DHCP 范围和 VPN 服务端参数都须通过实际环境核实。

实施边界：本阶段安装 Linux、CRI 和锁定的入群工具，运行 containerd 并验证 CRI；不执行 kubeadm init/join、不安装集群 CNI、不初始化 Ceph OSD。基础服务使用集群外本地存储，未知盘和既有 RAID 不改动。

[返回七阶段目录](../README.md) · [统一架构与域名约定](../../architecture/v3.0-baseline.md) · [执行记录模板](../../templates/execution-record.md)

技术复核入口：[R01](../../reference/official-sources.md#r01)、[K01](../../reference/official-sources.md#k01)、[K02](../../reference/official-sources.md#k02)、[N01](../../reference/official-sources.md#n01)、[S01](../../reference/official-sources.md#s01)、[D03](../../reference/official-sources.md#d03)。

## 阶段实施与验收

目标：独立于 Kubernetes 完成基础设施部署与恢复，十台 Rocky 节点具备入群条件。

| 项目 | 具体要求 |
| --- | --- |
| 建设范围 | ESXi 模板/批量 VM、Rocky Linux 10、VMXNET3、Linux 基线与 containerd/runc/crictl、OpenWrt/VPN、IP/DNS/CA/NTP、Harbor/Nexus/GitLab、Ansible/OpenTofu、离线镜像和依赖。 |
| 实际顺序 | 资产与版本核实 → 集群外管理工具/种子 → 模板和基础 VM → 网络/DNS/CA/仓库 → 十节点 Linux/CRI 初始化 → 重启/幂等/离线/备份验收。00.10.01 的工具准备在创建 VM 前执行，编号用于追溯而非强制逐号执行。 |
| 重点实验 | 批量克隆唯一身份、VMXNET3、VPN 分流与断链、代理缓存、CRI 容器运行、重启保持配置、离线安装/构建、基础服务恢复。 |
| 交付物 | inventory 三份台账；OpenTofu 模块；Ansible Inventory/角色/Playbook；模板制作记录；OpenWrt/DNS/PKI/仓库配置；物料同步和预热入口；十节点 Linux/CRI 检查结果。 |
| 验收用例 | 十台节点通过 node-readiness 和 host-network CRI smoke；关键服务不依赖 K8s/Ceph；VPN 故障下内网可用；干净客户端断网后完成指定物料的安装及七类最小构建；独立备份恢复一个基础服务。 |

实施细节：[打开具体操作、配置位置和检查方法](node-bootstrap.md)。

阶段交接：基础服务与十台服务器已实际就绪；OS/CRI 初始化不能延后到 01。

验收结果保存为 `reports/00-preparation/<执行批次>/acceptance.md`，逐项链接配置、测试入口和真实输出。使用 [阶段验收模板](../../templates/phase-acceptance.md)；没有运行证据的条目保持未执行。

## 00.01 确认建设边界与资产

先确定什么可以修改，再建立软件与虚拟机；所有地址和磁盘操作都以现场核实为前提。

### 00.01.01 登记三台物理宿主机与现有数据

实施内容：登记 ESXi01/02/03 的型号、内存、CPU、版本、许可证、物理网卡、PERC 模式、磁盘和现有虚拟机。保留 ESXi .61–.63 与 iDRAC .51–.53。

过程安排：逐台确认 Datastore 的物理来源、RAID 状态、剩余容量和已有数据用途；把可用磁盘与禁止操作磁盘分别标记。

具体操作：导出现有 VM/Datastore/物理盘映射，逐项写入 inventory/hosts.yaml；在 resources.yaml 填实际可用容量，把禁止改动对象作为执行输入。

交付位置：`inventory/hosts.yaml、inventory/resources.yaml`；reports/00-preparation/<批次>/assets.md。

完成判定：形成资产台账与禁止操作清单；所有后续 OSD 设备都能追溯到具体宿主机和磁盘。

### 00.01.02 检查网络设备与 DHCP 可控程度

实施内容：核实实际默认网关，不把 192.168.9.1 当作已经确认的值；识别交换机是否真正具备 VLAN 管理能力。

过程安排：检查主路由分配范围和已占用地址。无法管理 DHCP 时，由网络管理员保留实验地址，或先确认一个不会被分配的可用范围。

具体操作：从主路由取得 DHCP 池和保留地址；检查管理机路由、VPN 远端网段及已用静态 IP；为节点和 VIP 留出地址，未确认前禁止批量克隆配置网络。

交付位置：`inventory/networks.yaml`；地址占用与 DHCP 排除记录。

完成判定：节点、基础服务和 VIP 不与 DHCP 或现有设备冲突；未确认前不批量分配静态地址。

### 00.01.03 制定内存和磁盘预算

实施内容：十个 Kubernetes 节点按 64 vCPU、128GB 内存起步；所有基础服务 VM、ESXi 和 vCenter 开销另外计入。

过程安排：将节点分别分布到三台宿主机；计算 ESXi01/02/03 的剩余内存和实际磁盘占用，设置不可突破的容量水位。

具体操作：按每台 ESXi 计算现有占用 + 新增 VM + 管理/恢复余量；列出 OS、runtime、OSD 与备份设备，先确定本批能开的 VM，不把所有高级组件一起启动。

交付位置：`inventory/resources.yaml`；docs/architecture/resource-capacity.md 的实测补充。

完成判定：预算能够在现有硬件上启动基础平台；不把虚拟磁盘标称容量当成 Ceph 可用容量或物理空闲容量。

### 00.01.04 固定主方案与对比实验的管理权

实施内容：确定 kubeadm 主集群、cephadm 外部 Ceph、Argo CD 主 GitOps，以及 GitLab CI/Jenkins 两条对等流水线。

过程安排：把 Rook 自管理、Flux、Tekton、Cilium 替代负载均衡、多集群和 GPU 划为独立模块，注明负责人、启用条件与清理范围。

具体操作：为 VM、主机、外部 Ceph、VIP、GitOps 对象分别指定唯一控制者；建立对照实验的 Namespace、IP 池、独立盘和清理范围。

交付位置：`docs/adr/ 的决策记录`；实验作用域表。

完成判定：同一虚拟机、磁盘、VIP 或 Kubernetes 资源没有两个相互竞争的主管工具。

## 00.02 建立项目和软件版本基线

### 00.02.01 建立项目目录与变更记录

实施内容：以 cloud-native-platform-lab 为项目根目录，按根 README 使用 docs、inventory、infrastructure、kubernetes、gitops、ci、platform-engineering、labs、tests、scripts 和 reports 分层，建立 versions.lock.yaml。

过程安排：检查仓库骨架与目录职责；将当前草案台账核实为实际输入，补充配置清单、架构决策和实验编号。不得把占位目录或未锁定版本标记成实施完成。

具体操作：检查根 README 的全部目录是否存在；将手工资产确认、配置代码、实验场景、测试用例和执行报告放入各自目录，敏感 State/密钥只保存受控引用。

交付位置：`README.md、inventory/、versions.lock.yaml 与目录骨架`。

完成判定：每项计划都能找到对应目录；本阶段之后补充的脚本与配置不混入聊天记录充当唯一副本。

### 00.02.02 复核并锁定兼容版本

实施内容：以 Kubernetes 1.36.5 为本次文档候选基线，Cilium 1.20 系列、containerd 2.x、Rocky Linux 10.x 逐项核对兼容矩阵。

过程安排：Ceph Tentacle 使用实施时已修复安全问题的维护补丁，不只满足最低版本。记录 Rook、CSI、Gateway 和各 Operator 的准确版本、镜像 Digest 与核对日期。

具体操作：核对 OS/内核/CPU、containerd/runc、kubeadm/kubelet、Cilium/kube-vip、Ceph/CSI 组合；填准确包版本、Chart 版本、镜像 Digest、资料日期及测试状态，先在一台新 VM 安装验证。

交付位置：`versions.lock.yaml`；兼容性与单节点安装记录。

完成判定：得到一个经过核对的版本集合；不能只记录 latest，也不能把文档编写日版本当作永久最新版本。

### 00.02.03 建立软件来源和离线物料清单

实施内容：登记 OS ISO、OpenWrt 镜像、容器镜像、Helm Chart、RPM、构建工具和依赖仓库来源。

过程安排：核对签名或校验值；将安装介质、校验文件及版本说明存入受控目录，并准备可离线访问的副本。

具体操作：在管理端建立种子物料目录，下载并校验 ISO、工具、RPM 依赖树、容器镜像和 Chart；把清单和校验值入库，二进制存受控离线介质。

交付位置：`infrastructure/registry/ 的物料清单`；离线介质索引。

完成判定：下载内容有来源、版本和完整性记录；执行者无需临时到处寻找未经核实的镜像。

本节行为核对：[K01](../../reference/official-sources.md#k01)、[N01](../../reference/official-sources.md#n01)、[S01](../../reference/official-sources.md#s01)。

## 00.03 规划网络、内部域名与公网域名

企业内部根域名使用 internal.egon.top，公网服务使用 egon.top；基础设施、云原生平台与内部服务分别使用 mgmt、k8s、svc 子域，完整约定见架构基线。

### 00.03.01 固定节点、Pod、Service 与 VIP 地址

实施内容：节点网络使用 192.168.9.0/24，Pod 使用 10.244.0.0/16，Service 使用 192.168.20.0/24；API VIP 为 .100，业务 VIP 池为 .201–.220。

过程安排：检查家庭网络、VPN 远端、容器桥接与将来第二集群的 CIDR；Service 网段不建立物理 VLAN，也不配置家用路由器 DHCP。

具体操作：核对 .100 API VIP、.101–.110 节点、.201–.220 业务池不冲突；登记 Pod/Service CIDR，生成节点静态配置输入和 DNS 记录输入。

交付位置：`inventory/networks.yaml、inventory/hosts.yaml`。

完成判定：所有地址池互不冲突；保留 Service .1 给 Kubernetes API Service、.10 给 CoreDNS，其他 Service 默认自动分配。

### 00.03.02 确定域名层级和 Kubernetes 集群域

实施内容：基础设施使用 esxi01.mgmt.internal.egon.top、vcsa.mgmt.internal.egon.top、idrac01.mgmt.internal.egon.top 等管理入口；平台使用 argocd.k8s.internal.egon.top、grafana.k8s.internal.egon.top、harbor.k8s.internal.egon.top；内部服务使用 gitlab.svc.internal.egon.top、mysql.svc.internal.egon.top、nexus.svc.internal.egon.top。主集群 API 使用 api.k8s.internal.egon.top，内部业务使用各服务.svc.internal.egon.top。

过程安排：Kubernetes 保留默认 cluster.local，kubeadm networking.dnsDomain 与 kubelet clusterDomain 保持一致；服务全名采用 service.namespace.svc.cluster.local，例如 kubernetes.default.svc.cluster.local。企业内网域名只用于节点、管理与应用入口。

具体操作：列出所有节点、仓库与管理服务的 FQDN→目标 IP；把 cluster.local 写进后续 kubeadm 模板的设计值，不把内部企业域写为 Service DNS 域。

交付位置：`infrastructure/dns/ 的记录源`；kubernetes/bootstrap/ 的配置设计。

完成判定：记录内部域名层级、集群域、上游 DNS 和名称模板；所有 Chart、Istio、Operator 和客户端与 cluster.local 一致，企业域名调整不改变集群内部 Service DNS。

### 00.03.03 建立公网发布白名单

实施内容：egon.top 只承载主动批准公开的站点或 API；内部 GitLab、Harbor、Ceph、Kubernetes API 和监控管理入口默认不公开。

过程安排：核实域名 DNS 权限、公网 IP、CGNAT、端口转发及隧道选择；先登记所需主机名，再决定是否建立记录。

具体操作：列出要公开的具体域名、后端、端口和身份要求；默认清单为空。检查路由器端口映射和 DNS 是否意外包含管理服务，清理仅限本项目错误配置。

交付位置：`infrastructure/dns/ 的公开入口清单`；公网连通前置记录。

完成判定：拥有公网域名不被等同于已具备公网连通性；没有因通配记录或端口转发而误暴露管理界面。

### 00.03.04 确定内部 DNS 与集群 DNS 的职责

实施内容：外部于 Kubernetes 的 DNS VM 管理 internal.egon.top 及其子域；CoreDNS 只对 cluster.local 的集群服务记录负责，其余请求转交基础 DNS。

过程安排：规划单向转发和负缓存，避免基础 DNS 把 internal.egon.top 再转回 CoreDNS；egon.top 的其他公网名称使用正常上游解析，同名应用确有需要时采用明确的分视图记录。

具体操作：画出客户端→基础 DNS、Pod→CoreDNS→基础 DNS 的单向查询路径；列出内部权威区、外部转发器、允许递归的来源和负缓存策略。

交付位置：`infrastructure/dns/ 的服务配置与查询用例`。

完成判定：基础 DNS 不依赖集群 API，不接管整个 egon.top；不存在递归转发环路，证书 SAN 与实际访问主机名匹配。

本节行为核对：[R01](../../reference/official-sources.md#r01)、[K02](../../reference/official-sources.md#k02)、[K07](../../reference/official-sources.md#k07)。

## 00.04 准备 ESXi 网络和虚拟机模板

### 00.04.01 检查虚拟交换机和 Port Group

实施内容：将基础服务和十个节点接入现有可用管理网络；第一版不假定物理交换机支持 Trunk。

过程安排：验证三台宿主机的端口组、MTU、上联与网卡一致性；保留 Mac 到 ESXi/iDRAC 的独立管理路径。

具体操作：先比较三台 ESXi 的 Port Group 名称、VLAN、MTU 与上联；创建或复用已批准端口组，用两个跨宿主机临时 VM 验证连通，再挂载基础 VM。

交付位置：`infrastructure/opentofu/ 的网络引用`；跨宿主机测试记录。

完成判定：跨宿主机虚拟机可以互通；网络变更不会切断唯一管理通道。

### 00.04.02 验证 VIP 的二层可达性

实施内容：为 kube-vip 和 MetalLB 的 ARP 宣告预留测试条件，不盲目关闭整个 vSwitch 的安全检查。

过程安排：用临时 VIP 验证地址漂移、ARP 更新和跨宿主机访问；仅在定位到实际限制后调整对应 Port Group。

具体操作：从未使用的实验地址临时分配 VIP，在两台测试 VM 之间迁移并观察 ARP/客户端恢复；逐项验证 Port Group 限制，完成后释放临时地址。

交付位置：`tests/smoke/ 的二层/VIP 场景`；原设置与恢复记录。

完成判定：能够观察 VIP 切换后的连通性；有原网络设置记录和恢复路径。

### 00.04.03 制作 Rocky Linux 10 虚拟机模板

实施内容：使用与宿主机虚拟 CPU 指令集匹配的 Rocky Linux 10 安装介质，检查 x86-64-v3 需求与 EVC 暴露能力。

过程安排：完成最小化安装、VMware Guest 工具、网络适配器、时间同步和基础安全配置；封装前清理机器标识和主机专属凭据。

具体操作：按节点手册第 3 节实际安装 Rocky、open-vm-tools 和 VMXNET3；验证启动、网卡和系统基线，封装首次启动身份生成，再用两个克隆证明身份唯一。

交付位置：`infrastructure/opentofu/ 的模板输入`；模板制作与克隆验证记录。

完成判定：模板克隆后不会出现重复 machine-id、SSH 主机密钥或静态 IP；客体能稳定启动和重启。

### 00.04.04 部署集群外管理与基础服务虚拟机

实施内容：规划 OpenWrt .10、DNS .11、Harbor .12、GitLab .13、Nexus .14、管理机 .15 和独立备份入口 .16。

过程安排：按依赖顺序先部署管理机、DNS 和网络，再部署仓库；服务 VM 数据盘独立规划，避免把十节点 128GB 预算重复占满。

具体操作：先执行 00.10.01 准备管理工具，再创建管理/DNS/仓库 VM；种子环境通过已知 IP 和控制台引导，DNS/CA 可用后切换正式名称和信任，随后安装仓库服务。

交付位置：`infrastructure/opentofu/ 模块和已核对 Plan`；基础 VM 清单。

完成判定：Kubernetes 尚未建立时，管理工具和软件供应服务已有可用宿主环境。

### 00.04.05 分散控制平面和存储节点

实施内容：让 cp01/storage01、cp02/storage02、cp03/storage03 分别位于三台不同 ESXi；基础服务优先使用 ESXi01 的内存余量。

过程安排：记录节点到物理宿主机的映射和本地 Datastore 位置；迁移虚拟机时同步更新故障域台账。

具体操作：按 hosts.yaml 创建十台节点并逐台核对宿主机、Datastore 和专用盘；检查三控制平面没有共置，记录 VM 迁移后必须更新的标签。

交付位置：`VM 放置导出`；十节点身份与盘位映射。

完成判定：任何一台 ESXi 故障不会同时丢失两个 etcd 成员；不假定本地 Datastore 支持自动跨宿主机重启。

## 00.05 在 ESXi 部署 OpenWrt 旁路由

### 00.05.01 准备 OpenWrt 虚拟机

实施内容：使用可信的 x86-64 OpenWrt 镜像和匹配的启动方式，配置 2 vCPU、2GB 内存、32GB 系统盘及一张虚拟网卡。

过程安排：核对镜像完整性、磁盘导入格式与网卡驱动支持；通过 ESXi 控制台完成第一次启动和管理账户设置。

具体操作：校验 OpenWrt 镜像，按 ESXi 支持格式导入并创建单网卡 VM；从控制台设置管理账户、LAN 静态地址，保存可恢复配置副本。

交付位置：`infrastructure/openwrt/ 的非敏感配置与镜像校验记录`。

完成判定：OpenWrt 可独立重启，控制台可登录；即使网络配置错误仍能回到控制台修复。

### 00.05.02 接入现有局域网

实施内容：将 OpenWrt 固定为 192.168.9.10，默认路由指向核实后的主路由，关闭面向现有 LAN 的 DHCP 服务。

过程安排：保持 Mac、ESXi 和节点的原默认网关不变；先只验证管理页面、DNS 上游、外网连接和内网互访。

具体操作：用 UCI 配置实际网络接口、.10 地址和已核实上游；关闭该 LAN 的 DHCP 发放，验证现有客户端租约来源未改变，再测试内外网。

交付位置：`OpenWrt network/dhcp 配置模板`；DHCP 与路由验证。

完成判定：不存在第二个 DHCP 服务抢答；关停 OpenWrt 不影响普通 LAN 通信。

### 00.05.03 配置旁路由访问控制

实施内容：只允许指定管理终端访问 OpenWrt 管理界面，仅允许指定源地址使用后续代理服务。

过程安排：启用最小化防火墙规则、独立管理密码和配置备份；限制监听接口，避免把服务暴露到不可信网络。

具体操作：限定 LuCI/SSH/代理监听与来源；分别从授权和非授权测试端访问；导出脱敏规则，真实密码和 VPN 材料单独加密备份。

交付位置：`infrastructure/openwrt/ 防火墙模板`；允许/拒绝证据。

完成判定：未经授权的终端无法借用代理或修改网关设置；备份不包含公开存储的 VPN 私钥。

### 00.05.04 保留双接口路由的升级路径

实施内容：透明接管全量出口只作为后续实验；需要时建立不同于上游 LAN 的下游网段。

过程安排：登记独立 Port Group/VLAN、DHCP 和 NAT 的前提；不得将 WAN 与 LAN 两侧都配置成同一个 192.168.9.0/24。

具体操作：编写双接口实验拓扑，明确新下游 CIDR、端口组和迁移对象；当前不启用第二 DHCP。只有隔离网络具备条件才实施并验证回退。

交付位置：`双接口实验方案、启用前置和回退步骤`。

完成判定：当前单网卡方案不依赖未拥有的 VLAN 功能；未来切换有明确的地址迁移与回退边界。

## 00.06 接入 VPN、代理和出口分流

### 00.06.01 建立 VPN 隧道与凭据管理

实施内容：优先选择已有服务端支持的 WireGuard；不支持时使用相应 OpenVPN 配置，不凭空假定服务端可用。

过程安排：记录服务端端点、认证材料、路由、DNS、MTU 和重连策略；秘密信息单独加密，先从 OpenWrt 测试隧道。

具体操作：导入已有 VPN 服务端提供的受控参数，先从 OpenWrt 建连；检查握手、路由、DNS、实际出口和重连，公钥/端点与私钥分开保存。

交付位置：`infrastructure/openwrt/ VPN 模板`；脱敏握手与出口记录。

完成判定：隧道能建立并重连，连通性和出口地址经过实际验证。

### 00.06.02 部署受控的显式 HTTP/HTTPS 代理

实施内容：为 Harbor、Nexus 和下载同步任务提供显式代理；HTTPS 默认使用 CONNECT 转发，不引入未经说明的 TLS 解密。

过程安排：先用单个同步客户端测试，区分代理进程的流量如何进入 VPN；VPN 本身不会自动提供 HTTP 代理服务。

具体操作：安装选定显式代理并限定来源，配置仅代理进程或指定源走隧道；分别用 curl 的直连和代理请求确认实际路径，检查 CONNECT 与证书未被替换。

交付位置：`代理安装/配置任务`；直连和代理路径对照。

完成判定：指定客户端通过代理获取外部资源；局域网服务和 API 访问仍为直连。

### 00.06.03 建立分流与故障策略

实施内容：对必须走 VPN 的流量采用隧道断开即停止的策略；允许直连的下载任务可使用明确的备用出口。

过程安排：覆盖 IPv4、IPv6、DNS 和 VPN 远端路由。仅给确有需要的进程配置代理，避免向所有系统服务全局注入。

具体操作：实现指定流量的路由表、策略规则、NAT/防火墙及失败关闭；覆盖 IPv4/IPv6/DNS，再断开隧道验证无泄漏，LAN 连接持续成功。

交付位置：`策略路由与规则备份`；断隧道测试记录。

完成判定：停用隧道后，受限流量不静默直连；授权的 LAN、DNS 和本地仓库继续工作。

### 00.06.04 设计代理绕行清单

实施内容：将 internal.egon.top 及其子域、cluster.local 及其集群服务名称、内部仓库、节点网络、Pod CIDR、Service CIDR 和回环地址加入绕行设计。

过程安排：逐种语言和运行时检查代理变量及 CIDR 支持差异；无法识别 CIDR 的客户端使用域名规则或明确地址排除。

具体操作：为下载进程、容器运行时和各语言客户端分别设置代理及绕行；实际请求 Harbor、Nexus、GitLab 和外部测试地址，记录每种客户端的匹配差异。

交付位置：`infrastructure/ansible/ 代理变量`；语言绕行测试表。

完成判定：Java、Python、Node、Rust 构建和 containerd 访问内网不被错误送往 VPN。

### 00.06.05 演练网络出口故障

实施内容：分别测试隧道中断、上游 DNS 不可用、OpenWrt VM 关机和代理拒绝连接。

过程安排：保持一台 Mac 和一个节点持续访问本地 DNS、GitLab、Harbor；记录下载任务的失败、重试和恢复行为。

具体操作：逐个注入隧道、代理、上游 DNS、OpenWrt 故障，不同时破坏所有路径；持续探测内网 DNS/仓库并记录失败窗口，逐项恢复后再下一项。

交付位置：`tests/failover/ 网络出口用例`；reports 中的恢复时间线。

完成判定：确认网络出口故障只影响需要外网的请求；形成故障现象与恢复顺序记录。

## 00.07 建立内部 DNS 与客户端解析

### 00.07.01 部署集群外 DNS 服务

实施内容：在 192.168.9.11 建立 internal.egon.top 内部权威记录与上游递归能力，记录 mgmt、k8s、svc 下的节点、管理、仓库、API 和应用入口主机名。

过程安排：先建立精确记录，再按需为统一应用网关建立 svc.internal.egon.top 下的通配记录，数据库和其他独立服务保留精确记录；为第二 DNS 保留 192.168.9.17 地址，不预设已经部署。

具体操作：基线使用集群外 BIND：安装包，编写 named 配置、内部 zone 和允许递归 ACL；运行 named-checkconf 与 named-checkzone 后启动，分别测试内部权威和外部递归。

交付位置：`infrastructure/dns/ 配置、zone 模板与检查入口`。

完成判定：从节点能够解析内部服务；Kubernetes 和 OpenWrt 停止时，基础服务域名仍可解析。

### 00.07.02 配置 macOS 的内网域名解析路径

实施内容：使 Mac 在 LAN 或授权 VPN 中通过内部 DNS 解析 internal.egon.top 及其 mgmt、k8s、svc 子域。

过程安排：通过网络/VPN DNS 设置或分域解析配置建立内部查询路径；测试系统解析器、浏览器、Git、IDE 与 VPN 客户端，不只测试直接指定 DNS 的查询，并验证其他 egon.top 公网名称仍正常解析。

具体操作：给 Mac 配置内网 DNS 或 /etc/resolver/internal.egon.top 分域解析；用 scutil --dns、dscacheutil 查询和实际 Git/HTTPS 请求验证，VPN 切换后再测。

交付位置：`macOS 分域解析操作说明`；客户端验收记录。

完成判定：Mac 的实际应用均通过内部 DNS 访问内网入口，公网解析正常；没有长时间等待或仅部分软件能解析的情况。

### 00.07.03 处理 Rocky、构建镜像和浏览器的 DNS 差异

实施内容：检查 NetworkManager、解析顺序、容器内 DNS、浏览器安全 DNS和客户端缓存。

过程安排：逐类验证 internal.egon.top 及其子域；对 DoH 或 VPN 覆盖 DNS 的客户端设置内部域例外，不能靠永久 hosts 列表代替 DNS 管理。

具体操作：通过 NetworkManager 配置 Rocky DNS；为 Builder 镜像和浏览器/DoH 设置一致路径；分别清缓存、重启客户端和用系统解析器测试，不靠永久 hosts 补丁。

交付位置：`Ansible DNS 任务`；客户端 DNS 回归用例。

完成判定：不同系统和语言运行时的名称解析结果一致；客户端设置能够随模板或文档重复应用。

### 00.07.04 建立 DNS 故障与恢复流程

实施内容：备份正向记录、上游、访问控制和客户端分域配置，保留已知 IP 的紧急管理路径。

过程安排：在恢复演练中先还原 DNS，再启动依赖域名的仓库；验证负缓存和记录变更传播。

具体操作：备份 BIND 配置/zone/客户端规则，在隔离副本校验并恢复；测试错误记录、负缓存和 DNS 中断；第二 DNS 只有实际部署到另一故障域后才计为冗余。

交付位置：`docs/runbooks/ 的 DNS 恢复规程`；独立恢复证据。

完成判定：DNS 单点风险被明确记录；需要常驻冗余时，第二 DNS 部署于另一台宿主机并经过一致性检查。

本节行为核对：[R01](../../reference/official-sources.md#r01)。

## 00.08 建立内部 CA 与证书信任

### 00.08.01 建立内部 PKI 信任链

实施内容：内部 internal.egon.top 及其子域使用私有 CA；根私钥离线保存，签发权限与日常管理权限分离。

过程安排：定义证书主体、SAN、有效期、吊销或替换流程；为基础服务签发各自证书，不共享一个无范围限制的私钥。

具体操作：准备离线根与受限签发流程；为 DNS 外的 HTTPS 基础服务分别签发含实际 SAN 的证书，校验链、期限和私钥权限，再加载服务。

交付位置：`infrastructure/pki/ 的证书模板与签发说明`；不含私钥。

完成判定：浏览器和服务端能够验证完整链；根密钥未进入 Git、普通 Secret 或通用 CI Job。

### 00.08.02 分发各语言和系统的 CA 信任

实施内容：将 CA 信任分发给 Mac、Rocky、containerd、GitLab Runner、Jenkins Agent 和语言构建镜像。

过程安排：分别检查 Java Truststore、.NET、Python、Node、Rust 工具链和系统证书库；不以长期关闭证书校验替代信任配置。

具体操作：分发公开根/中间证书；分别配置系统 CA、Java Truststore 和所需语言信任；通过实际 Git clone、依赖下载和 CRI 拉取验收，不使用跳过校验参数。

交付位置：`Ansible 信任任务、Builder CA 配置、客户端结果矩阵`。

完成判定：镜像拉取、Git 操作、依赖下载和 HTTPS API 均无需不安全跳过验证。

### 00.08.03 规划公网证书与内部证书隔离

实施内容：egon.top 下批准公开的应用使用公有 CA 或适用的 ACME 流程；internal.egon.top 内部入口按本方案使用私有 CA。

过程安排：通配证书使用受支持的 DNS 验证方式；限定 DNS API 凭据权限，按 mgmt、k8s、svc 的实际主机名检查 SAN，*.egon.top 不覆盖这些多层内部入口。

具体操作：列出每个公开入口采用的签发方式及 DNS API 权限；先在适用的测试环境验证签发/续期和 SAN，内部服务继续使用内部 CA。

交付位置：`证书用途、续期、权限与过期检查表`。

完成判定：内外证书签发来源、使用范围和续期方法清楚；一个域名的证书不会误用于另一个域名。

## 00.09 建立 GitLab、Harbor 与依赖仓库

### 00.09.01 部署集群外 GitLab CE

实施内容：在 gitlab.svc.internal.egon.top 建立源码仓库、管理员、团队和项目空间，配置备份、存储保留及外部访问地址。

过程安排：先使用内置或同 VM 的受控数据库方案，不依赖阶段 03 的数据库；后续 Keycloak 接入前保留本地恢复管理员。

具体操作：使用锁定安装物料部署 GitLab，设置 external_url、TLS、数据/备份目录；创建实验仓库并实际 clone/push，再把备份恢复到隔离实例核对仓库。

交付位置：`infrastructure/registry/gitlab/ 配置`；仓库与恢复测试。

完成判定：能够创建仓库、推送文档、审核变更并从备份恢复测试仓库。

### 00.09.02 部署 Harbor 与项目权限

实施内容：在 harbor.k8s.internal.egon.top 建立基础镜像、平台、构建器、中间件、业务和代理缓存项目。

过程安排：启用 TLS、机器人账号、推拉权限、保留策略和容量管理；基础平台镜像与随时可回收的缓存分开。

具体操作：按锁定版本的官方单机方式安装 Harbor；配置域名、TLS、持久目录和项目权限，创建只读/构建机器人并分别测试允许与拒绝，设置保留规则。

交付位置：`infrastructure/registry/harbor/ 配置`；推拉权限和保留验证。

完成判定：普通构建任务只能推送授权项目；节点能拉取内网镜像，关键版本不被清理规则误删。

### 00.09.03 建立上游代理缓存和引导镜像库

实施内容：为实际使用的外部 Registry 建立相应缓存项目；将 kubeadm、CNI、CSI 和 Operator 必需镜像预先复制到自有项目。

过程安排：验证代理项目的路径规则、认证与离线命中；按需缓存不等于完整离线镜像库，关键内容使用可控保留和 Digest。

具体操作：区分代理项目与固定引导项目；将镜像按 Digest 复制、记录来源与内部映射；断外网后从空客户端缓存拉取，验证真实内网命中及多架构清单。

交付位置：`镜像同步/预热入口、Digest 清单、离线拉取报告`。

完成判定：上游不可达时已固定镜像仍可获取；没有假定所有原始镜像路径都能自动透明替换。

### 00.09.04 部署 Nexus 和语言依赖代理

实施内容：在 nexus.svc.internal.egon.top 规划 Maven、npm、PyPI、NuGet、Cargo、RPM 和通用制品。

过程安排：核对选定 Nexus 版本、版本授权与各仓库格式实际支持；不支持的生态使用对应独立缓存，不把 Raw 当通用协议转换器。

具体操作：实际部署 Nexus，创建其支持的 Maven/npm/PyPI/NuGet 等仓库；逐生态配置客户端并解析固定依赖；Cargo/RPM 等若无适用支持则部署对应缓存或镜像源，保留协议验证。

交付位置：`infrastructure/registry/nexus/ 及生态客户端配置`；依赖命中表。

完成判定：每种语言都能解析固定依赖；上游、内部发布和组合仓库的权限与路径有明确约定。

### 00.09.05 补充 C/C++ 与构建工具缓存

实施内容：为 Conan、vcpkg、编译器工具链、Rust 工具链和 .NET SDK 安排制品或二进制缓存。

过程安排：保留来源与许可证信息；验证全新构建环境能仅从内网取回工具和依赖，避免只依赖管理员机器上的暖缓存。

具体操作：为 Conan/vcpkg、编译器、Rust 工具链、.NET SDK 建立固定物料；用新建干净环境执行七类语言的最小编译，不使用个人工作站已缓存依赖。

交付位置：`工具链物料、七类最小构建输入、内网重建记录`。

完成判定：C/C++ 不因缺少依赖代理而成为离线构建的盲点；工具链版本可重现。

### 00.09.06 建立镜像扫描与数据库同步起点

实施内容：规划 Trivy 数据库、漏洞源和扫描日志的本地同步位置；正式签名与准入在阶段 04 和 06 完成。

过程安排：对仓库基础镜像进行一次扫描并记录数据库时间；离线扫描结果必须注明情报更新时间。

具体操作：同步 Trivy 程序、所需 DB/Java DB 等物料；扫描固定引导镜像，记录数据库更新时间、漏洞结果和同步失败行为，验证断网时不尝试遗漏的下载。

交付位置：`扫描数据库同步入口、脱敏扫描结果与新鲜度信息`。

完成判定：扫描任务不会因为数据库未缓存而临时联网失败，也不会把旧情报扫描误当实时安全结论。

本节行为核对：[D03](../../reference/official-sources.md#d03)。

## 00.10 建立自动化、备份与阶段验收

### 00.10.01 部署独立管理工具环境

实施内容：在管理 VM 或 Mac 准备 Ansible、OpenTofu、Git 和必要客户端，形成不依赖 K8s 的引导执行入口。

过程安排：使用最小权限服务账号，分离 vCenter、ESXi、DNS、仓库和 Ceph 凭据；受控保存初始本地状态，后续再迁移远端 State。

具体操作：本步在批量 VM 创建前先执行：准备 OpenTofu/Provider、Ansible/集合与客户端种子；校验版本，配置作用域受限的凭据引用，测试主机连通和 IaC Plan。

交付位置：`infrastructure/opentofu/、infrastructure/ansible/ 与集群外管理工具清单`。

完成判定：主集群完全未建立或损坏时，仍然有可用的管理和恢复工具。

### 00.10.02 初始化十台节点并验证幂等性

实施内容：按 [节点初始化实施手册](node-bootstrap.md) 完成十台节点的唯一身份、磁盘挂载、静态网络、DNS/NTP/CA、账户/SSH、软件源、cgroup v2、Swap、内核、防火墙/SELinux，以及 containerd/runc/crictl 安装和配置。

过程安排：先处理 cp01，再按角色逐台推广；执行 CRI 拉取/运行/日志/清理测试，重启后重新检查持久配置和 runtime 自启，再重复执行 Playbook 检查幂等。候选 OSD 盘不格式化。

具体操作：逐项执行节点初始化实施手册第 4–11 节：系统基线→CRI→镜像→host-network sandbox→重启→幂等；为每台输出主机检查结果，不接受只填台账。

交付位置：`node_base/container_runtime 角色、bootstrap-nodes.yml、十节点验收记录`。

完成判定：十台节点的主机检查和 RuntimeReady 均通过，内网镜像能够通过 CRI 运行，重启后结果一致；没有被初始化的 OSD 或被重置的身份。未装 CNI 的 NetworkReady 不在 00 验收范围。

### 00.10.03 建立独立备份位置和恢复清单

实施内容：重要备份复制到三台 ESXi 本地 Datastore 与未来 Ceph 故障域之外，例如独立 NAS 或外置存储。

过程安排：备份 GitLab、Harbor、Nexus、DNS、OpenWrt、CA、状态文件和管理配置；加密密钥另存，抽样恢复一个基础服务。

具体操作：把基础服务配置/数据、模板参数、State、证书恢复材料复制到独立介质；校验哈希和解密能力，至少恢复一个服务并验证数据；密钥另存。

交付位置：`独立备份索引、恢复 Runbook 与实际抽样恢复记录`。

完成判定：备份文件可读取且恢复路径经过试验；同一物理存储中的另一个 VM 不被称为独立灾备。

### 00.10.04 执行指定物料的断网验收

实施内容：选择已同步的安装介质、镜像和各语言固定依赖，临时限制互联网访问。

过程安排：从干净客户端验证内部解析、证书、源码、镜像和依赖；记录任何未缓存下载并补充物料，不宣称任意新依赖可离线。

具体操作：限制测试客户端互联网访问，清理该客户端测试缓存；依次验证 DNS/TLS、Git、镜像、RPM 和七类固定语言依赖，执行指定安装与构建，并恢复网络限制。

交付位置：`tests/smoke/ 离线用例`；物料缺口和通过结果。

完成判定：得到一份可复用的离线物料清单和验收记录；本地管理不依赖 VPN 正常运行。

### 00.10.05 完成 Phase 00 交接

实施内容：归档资产、地址、域名、证书、版本、物料、备份和虚拟机模板的实际结果。

过程安排：逐项标记已完成、阻塞、待补充命令与未启用模块；交接十节点主机/CRI 检查结果、自动化配置、已锁定入群工具和镜像。01 只复验，不再首次配置 Linux 或安装 CRI。

具体操作：逐台检查 Linux/CRI/重启/幂等证据；核对基础服务、离线和恢复证据；把未解决条件列为阻塞，交付操作入口和回退文件给 01。

交付位置：`reports/00-preparation/<批次>/acceptance.md`；阶段交接清单。

完成判定：本阶段交付及验收清单全部满足；十台服务器已经完成 Linux/CRI 初始化，基础服务与指定离线物料可用，恢复副本已验证，才允许开始 Kubernetes 初始化。
