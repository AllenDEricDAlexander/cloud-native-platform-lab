# Phase 01 实验操作手册

与 [阶段正文](../../plan/01-kubernetes.md) 配合执行，下面按原专题编号展开实施参考。配置和脚本应在本轮实施时编写、校验；示例命令只提供操作/检查入口，实际进度以本轮执行记录为准。

当前按 [2026-10-17 从头重做批次](records/2026-10-17-restart/README.md)推进；已编写并执行的 [cp01 旧残留清理剧本](ansible/playbooks/cleanup-cp01.yml)复用 00 的 Ansible 配置，后续部署与核心资源实验按本轮证据逐项验收。

01.02 十节点基础健康、普通 Pod 网络、Mac 受限身份与恢复文件备份/取回已通过；01.03 完整备份、取回、单 VM HA 与清理也已通过，准备 01.04；DNS 短名修正待补测。.15 管理机实际分发仍待交付。[身份手册](bootstrap/access/README.md)、[基础验收命令](bootstrap/acceptance/README.md)和 [引导配置](bootstrap/README.md)保留复现入口；下面的“本轮第一至第三步”仅保留教学过程，不对完整文件重复执行旧追加命令。

每个专题沿“确认输入 → 编写和校验配置 → 单项执行 → 正常/失败验证 → 恢复与归档”推进。报告放 `ops/01-kubernetes/records/<执行批次>/`，引用原步骤号、参数、版本和实际结果；修改范围只限本实验对象。

## 命令与示例的使用方式

以下写明实验时大概要执行的命令、目的和预期变化，不是现在就能整段运行的一键脚本。`LAB_*`、`<...>`、版本、资源名和文件路径在开始实验时按实际环境填写；文件须先根据示例补齐，凭据通过受控配置注入。YAML 标为“片段”时应合并到完整对象，不能单独 apply；示例值不是性能或容量承诺。

`kubectl` 在选定集群的管理终端执行，`kubeadm`/主机命令在文中指定节点执行。每次变更前用 `kubectl config current-context` 核对目标。`--dry-run=server` 用于已经存在的集群/API；CRD 尚未安装时先安装匹配版本。`kubectl diff` 返回 1 通常表示有差异，应阅读差异后再 apply。故障、恢复和清理命令分段执行并观察结果，当前不执行任何部署。

测试 Namespace、样例应用、Chart/CRD 和引用文件应先创建到就绪；已由 GitOps 托管的对象通过仓库变更和同步更新，文中的直接 patch/scale/apply 用于隔离实验对象或受控诊断。

<a id="01-01"></a>

## 01.01 入群前复验

输入：00 的十节点验收报告、锁定版本、可访问的引导镜像和主机配置。

1. 逐台执行 node-readiness 的只读模式，核对身份、IP、DNS、chrony、挂载、Swap、sysctl、SELinux/规则与版本；比较 00 重启后的报告，先定位漂移。
2. 检查 `systemctl is-active containerd`、`crictl info` 与内网镜像拉取；此时只要求 RuntimeReady，不把尚未安装 CNI 的 NetworkReady 当作失败。
3. 把按角色的 OS/kubelet/Ceph 预留、Pod PID/驱逐预算写入待用 kubelet 配置；禁止重新安装另一版本 CRI 或临时关闭安全机制。

### 操作命令与目的

在每台新节点执行只读复验；发现差异先回到 00 修复：

```bash
hostnamectl --static                 # 确认节点身份
stat -fc %T /sys/fs/cgroup            # 确认 cgroup v2
swapon --show                        # 确认起步无激活 Swap
findmnt /var/lib/containerd          # 确认运行时数据挂载位置
chronyc tracking                     # 确认时间同步状态
sudo systemctl is-active containerd  # 确认运行时已由 00 启动
sudo crictl info                     # 通过 CRI 检查 RuntimeReady
sudo crictl pull "$LAB_BOOTSTRAP_IMAGE"  # 检查内网镜像与认证
```

### 配置示例

后续 `KubeletConfiguration` 的关键字段；预算按角色填写，storage 节点另计 Ceph 预留：

```yaml
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
cgroupDriver: systemd
clusterDomain: cluster.local
clusterDNS: [192.168.20.10]
systemReserved:
  cpu: "500m"
  memory: "1Gi"
kubeReserved:
  cpu: "500m"
  memory: "1Gi"
```

### 预期结果

输出身份与台账一致，cgroup 类型为 `cgroup2fs`，Swap 无激活项，containerd 为 active，CRI 的 RuntimeReady 为 true。未安装 CNI 时 NetworkReady 可以为 false；此时不要求十节点 Ready。预留示例只是写法，不能直接作为所有角色的最终数值。

交付：`ops/01-kubernetes/bootstrap/` 的入群输入与 `ops/01-kubernetes/records/` 前置检查。

检查与失败处理：十台节点均符合 00 基线；缺陷回到 00 的 Ansible 角色修复并重验，禁止忽略全部 kubeadm preflight 错误。

<a id="01-02"></a>

## 01.02 创建高可用集群

输入：已通过 01.01；明确 kube-vip 与锁定 kubeadm 版本的静态 Pod 引导流程。

1. 编写 `kubeadm-init.yaml`、各节点 JoinConfiguration 和 kubelet 角色配置：API FQDN/VIP、SAN、CRI socket、Pod/Service CIDR、cluster.local、192.168.20.10；验证配置 API 与锁定 kubeadm 一致。
2. 生成 kube-vip 静态 Pod 配置并核对启动时 kubeconfig 来源；按锁定版本引导说明解决首节点凭据依赖，不把需要尚不存在 kubeconfig 的清单直接当作已就绪入口。
3. 先执行 `kubeadm init --config <初始化配置> --dry-run`，检查预期对象和前置；真实 init 后检查本地静态 Pod、etcd 和 API，再验证 VIP。短时 join/certificate key 通过受控通道传递。
4. 编写并安装 Cilium 基础 values：Overlay、kube-proxy 共存、cluster-pool IPAM 与每节点 /24、内网镜像；用 `cilium status --wait` 检查，再顺序 join cp02/cp03 和七 Worker。
5. 配置控制平面审计/Secret 加密，所有 API Server 使用一致配置；设置 storage 污点、节点角色和物理宿主机标签，检查必要 DaemonSet 仍可调度。

### 01.02.01 本轮第一步：生成并理解默认配置

目的：先看 cp01 当前安装的 kubeadm 支持哪些配置字段，再按台账逐段编写实际初始化配置。模板打印只输出参考内容，不生成真实入群令牌，也不初始化集群。[官方命令说明](https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-config/#kubeadm-config-print-init-defaults)

| 配置对象 | 负责什么 |
| --- | --- |
| `InitConfiguration` | 本次初始化及首节点的信息，例如本机 API 地址、节点名称与 CRI 端点 |
| `ClusterConfiguration` | 集群公共参数，例如 Kubernetes 版本、统一 API 入口、网段与镜像仓库 |
| `KubeletConfiguration` | kubelet 的工作参数，例如 cgroup、集群 DNS 与资源预留 |

在管理 Mac 执行。先切换到仓库根目录，使输出路径明确；`pipefail` 让 SSH 命令失败时整条管道也返回失败，避免只看到 tee 成功写文件。

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
set -o pipefail
ssh -i ~/.ssh/cnpl_lab_ed25519 -o IdentitiesOnly=yes root@192.168.9.101 \
  'kubeadm config print init-defaults --component-configs KubeletConfiguration' \
  | tee ops/01-kubernetes/records/2026-10-17-restart/evidence/01.02.01-kubeadm-defaults.yaml
```

SSH 将引号内的命令交给 cp01 执行；`print init-defaults` 打印默认初始化模板，`--component-configs KubeletConfiguration` 额外输出 kubelet 配置；tee 在 Mac 上同时显示并保存标准输出。

预期看到 `InitConfiguration`、`ClusterConfiguration`、`KubeletConfiguration` 三个 kind。`---` 是同一 YAML 文件内不同文档的分隔符。默认值不是本实验室的最终参数，这份文件仅作为参考；下一步再区分首节点的本机 API 地址（`.101`）与全局 API 入口（域名指向 VIP `.100`），并逐项填入实际配置。

### 01.02.01 本轮第二步：首节点地址与集群入口

`.101` 是 cp01 的固定节点地址；`.100` 是控制平面的统一入口 VIP。API 域名始终解析到 `.100`，kube-vip 的 ARP 模式通过选举让一个控制平面持有 VIP，切换持有者时更新网络中的 IP/MAC 映射。三台控制平面的固定节点地址仍各自保留。[kube-vip ARP 说明](https://kube-vip.io/docs/modes/arp/)

| 字段 | 本轮值与含义 |
| --- | --- |
| `localAPIEndpoint.advertiseAddress` | `192.168.9.101`，cp01 的 API Server 对外通告的本机地址 |
| `localAPIEndpoint.bindPort` | `6443`，API Server 端口 |
| `controlPlaneEndpoint` | `api.k8s.internal.egon.top:6443`，全体节点与客户端共用的入口 |
| `nodeRegistration.kubeletExtraArgs / node-ip` | `192.168.9.101`，明确 kubelet 注册的节点 IP，避免误用 VIP |
| `apiServer.certSANs` | API 域名与 `.100`，将这些访问身份列入 API Server 证书 |

`localAPIEndpoint` 与 `controlPlaneEndpoint` 分别描述本机 API 地址和集群全局入口；字段语义见 [kubeadm 配置 API](https://kubernetes.io/docs/reference/config-api/kubeadm-config.v1beta4/)。本步仅写入地址、节点身份、锁定版本与镜像仓库；Pod/Service 网段、kubelet 公共配置、审计/加密与 SELinux 访问方案仍待补齐。

在管理 Mac 执行：第一条进入仓库；第二条创建本轮 kubeadm 配置目录（`-p` 会创建缺少的上级目录）；第三条把两段 YAML 写入草稿。`>` 创建或覆盖指定文件，`<<'YAML'` 表示原样读取后面的多行文本，最后一行 `YAML` 结束输入。

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
mkdir -p ops/01-kubernetes/bootstrap/kubeadm
cat > ops/01-kubernetes/bootstrap/kubeadm/kubeadm-init-cp01.yaml <<'YAML'
# 01.02.01 分步草稿：网络、kubelet、审计/加密及 SELinux 配置待补齐。
apiVersion: kubeadm.k8s.io/v1beta4
kind: InitConfiguration
localAPIEndpoint:
  advertiseAddress: 192.168.9.101
  bindPort: 6443
nodeRegistration:
  name: cp01.k8s.internal.egon.top
  criSocket: unix:///run/containerd/containerd.sock
  kubeletExtraArgs:
    - name: node-ip
      value: 192.168.9.101
---
apiVersion: kubeadm.k8s.io/v1beta4
kind: ClusterConfiguration
clusterName: lab-primary
kubernetesVersion: v1.36.5
controlPlaneEndpoint: api.k8s.internal.egon.top:6443
imageRepository: harbor.k8s.internal.egon.top/bootstrap
apiServer:
  certSANs:
    - api.k8s.internal.egon.top
    - 192.168.9.100
YAML
```

`nodeRegistration.name` 使用已核验的 cp01 FQDN；`criSocket` 指向现有 containerd CRI 端点。版本 `v1.36.5` 与镜像仓库均来自本轮已复验的版本锁和镜像准备结果。保留原始默认模板作为对照，不把其中 `1.2.3.4`、`node`、`1.36.0` 等默认值直接用于本轮。

此时写入的是 Mac 仓库里的文件，尚未部署至 cp01。本段草稿已用 cp01 当前 kubeadm 做字段校验（见本轮记录），这不代表整个初始化配置完成或运行验收通过。写入后继续讲解网络与 kubelet 参数，再做完整配置校验与 dry-run。

### 01.02.01 本轮第三步：Pod、Service 网段与集群 DNS

目的：在本轮地址草稿之后追加集群网络范围和 kubelet 的 DNS 参数。当前草稿末尾仍是 ClusterConfiguration，因此顶格的 `networking`、`controllerManager` 会属于集群配置；`---` 之后才开始第三个对象 KubeletConfiguration。

| 地址类别 | 本轮规划 | 用途 |
| --- | --- | --- |
| 节点网络 | `192.168.9.0/24` | VM 的网卡地址，包含节点 IP 和 API VIP |
| Pod 网络 | `10.244.0.0/16` | 分配给普通 Pod，由后续的 Cilium 管理 |
| Service 网络 | `192.168.20.0/24` | 为 ClusterIP Service 分配稳定的虚拟入口 |
| 集群 DNS | `192.168.20.10` | 规划的 CoreDNS Service IP，位于 Service 网段内 |

Pod IP 对应具体运行实例，Service IP 对应服务入口，后端 Pod 更换时入口可保持。节点 DNS 仍使用内部 DNS `192.168.9.11`，Pod 的默认集群 DNS 使用 `192.168.20.10`；`cluster.local` 是集群内部域，与节点和 Harbor 使用的 `internal.egon.top` 分工不同。[Service 说明](https://kubernetes.io/docs/concepts/services-networking/service/) · [Kubelet DNS 字段](https://v1-36.docs.kubernetes.io/docs/reference/config-api/kubelet-config.v1beta1/)

在之前已启用 `pipefail` 的 Mac 终端执行。第一条切换到仓库；第二条以 `>>` 追加，保留已填写的地址配置，本步追加执行一次即可；第三条将本地文件通过标准输入交给 cp01 的 kubeadm 校验，并保存输出。它不会在节点写入部署配置或初始化集群。

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
cat >> ops/01-kubernetes/bootstrap/kubeadm/kubeadm-init-cp01.yaml <<'YAML'

networking:
  podSubnet: 10.244.0.0/16
  serviceSubnet: 192.168.20.0/24
  dnsDomain: cluster.local
controllerManager:
  extraArgs:
    - name: allocate-node-cidrs
      value: "false"
---
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
cgroupDriver: systemd
clusterDNS:
  - 192.168.20.10
clusterDomain: cluster.local
YAML
ssh -i ~/.ssh/cnpl_lab_ed25519 -o IdentitiesOnly=yes root@192.168.9.101 \
  'kubeadm config validate --config /dev/stdin' \
  < ops/01-kubernetes/bootstrap/kubeadm/kubeadm-init-cp01.yaml \
  2>&1 | tee ops/01-kubernetes/records/2026-10-17-restart/evidence/01.02.01-network-user-validate.txt
```

字段解释：

- `podSubnet`、`serviceSubnet` 分别确定 Pod 与 Service 地址范围；`dnsDomain` 保留集群内部域。
- 本项目选择 Cilium cluster-pool 管理每节点 Pod CIDR，因此显式关闭 kube-controller-manager 的 `allocate-node-cidrs`。后续 Cilium values 仍须明确写入 `10.244.0.0/16` 与每节点 `/24`，本步不会安装 Cilium。[Cluster-pool IPAM](https://docs.cilium.io/en/stable/network/concepts/ipam/cluster-pool/)
- `extraArgs` 的 `value` 是字符串，因此写成 `"false"`。
- `cgroupDriver: systemd` 与已复验的 containerd 配置保持一致；`clusterDNS` 告诉 kubelet 为使用 ClusterFirst 策略的 Pod 配置哪个 DNS 地址，`clusterDomain` 与上面的 `dnsDomain` 一致。

预期校验返回 `ok`。这是配置校验；Pod 网络与 CoreDNS 的实际访问能力要在对应组件就绪后验证。资源预留、审计/加密及 SELinux 访问方案尚待补齐，下一步继续讲节点资源预算。

### 操作命令与目的

先在管理目录准备 kubeadm、kube-vip 和 Cilium 配置。以下命令分别在 cp01、其他待加入节点和管理终端执行：

```bash
# cp01：生成/校验配置，再预演初始化
kubeadm config print init-defaults > kubeadm-defaults.yaml
kubeadm config validate --config kubeadm-init.yaml
sudo kubeadm init --config kubeadm-init.yaml --dry-run

# cp01：在核对 kube-vip 首节点凭据与静态 Pod 引导顺序后初始化
sudo kubeadm init --config kubeadm-init.yaml
sudo crictl ps                       # 检查 API/etcd 等静态 Pod 的容器

# 管理端：安装基础 Cilium；Chart 和镜像使用已同步版本
helm upgrade --install cilium "$LAB_CILIUM_CHART" -n kube-system \
  --version "$LAB_CILIUM_VERSION" -f cilium-values.yaml --wait
cilium status --wait

# 各待加入节点：使用其自己的短时、受控 JoinConfiguration
sudo kubeadm join --config node-join.yaml

# 管理端：检查集群就绪
kubectl get nodes -o wide
kubectl get pods -n kube-system -o wide
kubectl get --raw='/readyz?verbose'
```

kube-vip 清单可用锁定版本的 `kube-vip manifest pod --interface "$LAB_INTERFACE" --address 192.168.9.100 --controlplane --arp --leaderElection` 生成到工作目录；再按该版本要求处理首节点 kubeconfig 并放入静态 Pod 目录。不要把这条生成命令等同于已完成 VIP 自举。

### 配置示例

`kubeadm-init.yaml` 的基本结构，API 版本在实验时与 kubeadm 核对；还需合并审计、加密、镜像映射和角色预留：

```yaml
apiVersion: kubeadm.k8s.io/v1beta4
kind: InitConfiguration
localAPIEndpoint:
  advertiseAddress: 192.168.9.101
  bindPort: 6443
nodeRegistration:
  name: cp01.k8s.internal.egon.top
  criSocket: unix:///run/containerd/containerd.sock
---
apiVersion: kubeadm.k8s.io/v1beta4
kind: ClusterConfiguration
kubernetesVersion: "<锁定的 Kubernetes 版本>"
controlPlaneEndpoint: api.k8s.internal.egon.top:6443
networking:
  podSubnet: 10.244.0.0/16
  serviceSubnet: 192.168.20.0/24
  dnsDomain: cluster.local
apiServer:
  certSANs: [api.k8s.internal.egon.top, 192.168.9.100]
```

`cilium-values.yaml` 的网络部分，完整文件还要指定离线镜像、资源和必要容忍：

```yaml
kubeProxyReplacement: false
routingMode: tunnel
tunnelProtocol: vxlan
ipam:
  mode: cluster-pool
  operator:
    clusterPoolIPv4PodCIDRList: [10.244.0.0/16]
    clusterPoolIPv4MaskSize: 24
```

### 预期结果

初始 CNI 未部署时节点可暂时 NotReady；Cilium 和 CoreDNS 健康后节点转为 Ready。顺序加入另外两个控制平面和七 Worker 后应看到 10 个 Ready，API 经 VIP 可访问。Join 所需 token/证书材料只在受控路径传递，不能写入报告。

交付：`ops/01-kubernetes/bootstrap/{kubeadm,kube-vip,cilium}/` 配置；敏感 Join 材料不入 Git。

检查与失败处理：`kubectl get nodes -o wide` 为 10 个 Ready；`kubectl get --raw='/readyz?verbose'`、Cilium/CoreDNS 和三 etcd 成员健康。失败先检查具体节点与 kubeadm 日志，不能对全部节点统一 reset。

<a id="01-03"></a>

## 01.03 验证 DNS、API 故障切换与备份

输入：主集群健康，已选定非业务测试应用与独立备份位置。

本轮直接使用 [01.03 完整脚本与逐条解释](operations/README.md)：先滚动分散 CoreDNS 并补 Service 短名测试，再进行完整备份/取回验证，最后由用户在 ESXi 控制台关/开单台 VM，脚本独立观测 API、应用、Service 和 etcd。下方 govc 命令仅为通用示意，本轮不新增 vSphere CLI 或凭据依赖。

1. 在不同节点放置 DNS/HTTP 测试 Pod，分别解析 Service 全名、kubernetes.default、Harbor 和外部域；保存请求、CoreDNS 配置与实际上游。
2. 使用匹配版本的 etcdctl 保存 snapshot，配合 etcdutl snapshot status 校验，连同 PKI、加密配置和密钥恢复索引复制到独立介质；在隔离位置验证可读取。
3. 持续请求 API 和测试应用，记录基线；每次只停止一个控制平面，观察 kube-vip 接管、etcd 两成员多数派、新建/调度对象能力；恢复并确认三成员健康才结束。

### 操作命令与目的

```bash
# 管理端：从已有诊断 Pod 检查集群内外名称
kubectl -n lab-core exec dns-client -- nslookup kubernetes.default.svc.cluster.local
kubectl -n lab-core exec dns-client -- nslookup harbor.k8s.internal.egon.top

# 控制平面：检查 etcd 多数派，并把快照写到受控备份路径
sudo etcdctl --endpoints="$LAB_ETCD_ENDPOINTS" --cacert="$LAB_ETCD_CA" \
  --cert="$LAB_ETCD_CERT" --key="$LAB_ETCD_KEY" endpoint health --cluster
sudo etcdctl --endpoints=https://127.0.0.1:2379 --cacert="$LAB_ETCD_CA" \
  --cert="$LAB_ETCD_CERT" --key="$LAB_ETCD_KEY" snapshot save "$LAB_SNAPSHOT"
etcdutl snapshot status "$LAB_SNAPSHOT" -w table

# 有可用 vSphere CLI 时：只停止选定的一个控制平面 VM
# 在另一个终端持续观察 API/应用；观测完成后才运行恢复命令
govc vm.power -off "$LAB_FAILED_CP_VM"
kubectl get --raw='/readyz?verbose'
govc vm.power -on "$LAB_FAILED_CP_VM"
```

没有 `govc` 的环境在实验时确定等价 VM 停机入口。单独停止 kubelet 不会自动停止其已运行的静态 Pod，不能据此声称完成控制平面故障实验。

### 配置示例

给故障测试脚本使用的实验参数示意，属于项目约定，不能当 Kubernetes YAML apply：

```yaml
experiment: single-control-plane-failure
failed_vm: cp01
max_failed_control_planes: 1
probes:
  - api-vip-readyz
  - create-and-schedule-test-pod
  - application-http
recovery_check:
  - three-etcd-members-healthy
  - ten-nodes-ready
```

### 预期结果

DNS 分别返回集群 Service 和内网仓库地址；etcd 初始三成员健康，失去一个后仍有多数派；API 恢复访问且能够创建/调度测试对象。记录真实失败窗口，不预填“零中断”。节点恢复后再确认三个 etcd 成员及 VIP；快照另行复制到独立介质并校验。

交付：`ops/01-kubernetes/tests/failover/` 控制平面用例；etcd 备份入口；DNS/切换时间线及恢复材料索引。

检查与失败处理：单控制平面不可用时 API 可继续提供服务并能调度；数据/PKI/加密材料完整。失去预期多数派时停止实验并恢复原节点，不继续停第二台。

<a id="01-04"></a>

## 01.04 建立可控制的 Pod 实验基准

输入：轻量内网镜像；独立 Namespace 和明确的资源上限。

1. 在 `ops/01-kubernetes/core-resources/pods/` 编写正常、错误镜像、进程退出、Init Container、Sidecar、临时容器等清单；所有对象带本实验标签。
2. 测试应用提供可控制的启动延迟、健康状态、退出信号和请求耗时；每种场景先保存正常状态，再仅改变一个变量。
3. 分别查看 `kubectl get pod`、`describe`、`logs --previous` 和 Events，区分 Pod phase、容器 state、reason、restartCount；修复同一对象并观察恢复。

### 操作命令与目的

```bash
kubectl create namespace lab-core --dry-run=client -o yaml | kubectl apply -f -
kubectl -n lab-core apply -f pod-state.yaml       # 建立可观察 Pod
kubectl -n lab-core get pods -o wide
kubectl -n lab-core describe pod state-demo      # 查看调度/拉取/启动事件
kubectl -n lab-core logs state-demo -c app
kubectl -n lab-core set image pod/state-demo app="$LAB_BAD_IMAGE"  # 注入错误镜像
kubectl -n lab-core get events --sort-by=.metadata.creationTimestamp
# 另一个“进程主动退出”的场景用下面命令读取上一次容器日志
kubectl -n lab-core logs state-demo -c app --previous
kubectl -n lab-core apply -f pod-state.yaml       # 恢复正确镜像
```

### 配置示例

`pod-state.yaml`；镜像需有 shell。Init/Sidecar/临时容器使用同一基准另存变体，不在一次实验中同时修改所有条件：

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: state-demo
  namespace: lab-core
  labels: {app: state-demo}
spec:
  initContainers:
    - name: prepare
      image: "<内网诊断镜像>"
      command: [sh, -c, "echo init-ok; sleep 2"]
  containers:
    - name: app
      image: "<内网诊断镜像>"
      command: [sh, -c, "while true; do date; sleep 5; done"]
      resources:
        requests: {cpu: 20m, memory: 32Mi}
        limits: {cpu: 100m, memory: 64Mi}
```

### 预期结果

Init 先完成，主容器持续输出日志；错误镜像产生明确拉取事件，主动退出变体展示重启次数和 previous 日志。Pod phase、容器 state、reason 分别记录；没有 previous 容器时该日志命令报不存在是预期边界。

交付：`ops/01-kubernetes/examples/pods/` 操作说明；清单与失败/修复对照记录。

检查与失败处理：能解释 Pending、Running、Succeeded、Failed 和 CrashLoopBackOff 的不同层次；测试结束只清理该 Namespace 内的实验对象。

<a id="01-05"></a>

## 01.05 三类探针与优雅终止

输入：01.04 的可控应用及持续请求脚本。

1. 创建 Startup/Liveness/Readiness 独立变体，明确 path、period、timeout、failureThreshold；启动慢场景验证 Startup 窗口而非无限重试。
2. 让 Liveness 失败并观察重启；让 Readiness 失败并同时 watch EndpointSlice 和持续请求，证明流量摘除而非容器一定重启。
3. 为应用添加 SIGTERM 处理和 PreStop，设置 terminationGracePeriodSeconds；在长请求执行中删除测试 Pod，记录钩子、信号、端点变化、请求完成或中断。

### 操作命令与目的

约定实验镜像提供 `/startup`、`/live`、`/ready`，并将 `/tmp/not-ready` 解释为 Readiness 失败；这是测试应用需要实现的控制入口。

```bash
kubectl -n lab-core apply -f probe-demo.yaml
kubectl -n lab-core rollout status deployment/probe-demo
kubectl -n lab-core get endpointslice -l kubernetes.io/service-name=probe-demo -w
# 在另一终端选择一个 Pod，让其暂时退出服务端点，再恢复
kubectl -n lab-core exec "$LAB_PROBE_POD" -- touch /tmp/not-ready
kubectl -n lab-core exec "$LAB_PROBE_POD" -- rm /tmp/not-ready
# 持续请求期间删除这个 Pod，观察 PreStop、SIGTERM 和请求结束
kubectl -n lab-core delete pod "$LAB_PROBE_POD" --wait=false
kubectl -n lab-core get pods -w
```

### 配置示例

Deployment 的 `spec.template.spec` 片段；应用须处理 SIGTERM，`sleep` 仅用于观察端点传播窗口：

```yaml
terminationGracePeriodSeconds: 40
containers:
  - name: app
    image: "<内网探针实验镜像>"
    ports: [{name: http, containerPort: 8080}]
    startupProbe:
      httpGet: {path: /startup, port: http}
      periodSeconds: 2
      failureThreshold: 30
    livenessProbe:
      httpGet: {path: /live, port: http}
      periodSeconds: 5
    readinessProbe:
      httpGet: {path: /ready, port: http}
      periodSeconds: 2
    lifecycle:
      preStop:
        exec: {command: [sh, -c, "sleep 5"]}
```

### 预期结果

Readiness 失败后 EndpointSlice 中该端点变为不就绪，容器不必重启；Liveness 失败才触发重启。Startup 阶段保护慢启动。删除时观测钩子、信号和请求结果，超过终止期限的长请求可能被中断，不能把 PreStop 等同于绝对无损。

交付：`ops/01-kubernetes/core-resources/probes/`、`lifecycle/`；探针阈值与终止时间线。

检查与失败处理：分别证明启动保护、自愈、流量可用性和终止期限；失败修正应用或阈值，不能用取消探针掩盖。

<a id="01-06"></a>

## 01.06 RC、ReplicaSet 与 Deployment

输入：具有 v1/v2 和可控坏版本的相同测试应用。

1. 建立 RC 和 ReplicaSet 对照，变更副本数、删除 Pod、创建匹配 selector 的孤儿 Pod，观察 ownerReferences 与接管；避免 selector 重叠影响其他工作负载。
2. 建立 Deployment，固定镜像 Digest，调整 maxSurge/maxUnavailable，持续请求并观察新旧 RS、Pod 和 EndpointSlice；对照 RollingUpdate/Recreate。
3. 发布坏版本后检查 `kubectl rollout status`、`rollout history`，回滚到明确 revision；扩缩容并记录 Desired/Current/Ready/Available。

### 操作命令与目的

```bash
kubectl -n lab-core apply -f rc-demo.yaml -f rs-demo.yaml  # 对照两类副本控制器
kubectl -n lab-core get rc,rs,pods
kubectl -n lab-core delete pod "$LAB_REPLICA_POD"         # 观察控制器补副本
kubectl -n lab-core apply -f deployment-demo.yaml
kubectl -n lab-core set image deployment/controller-demo app="$LAB_IMAGE_V2"
kubectl -n lab-core rollout status deployment/controller-demo --timeout=120s
kubectl -n lab-core rollout history deployment/controller-demo
kubectl -n lab-core rollout undo deployment/controller-demo --to-revision="$LAB_GOOD_REVISION"
kubectl -n lab-core scale deployment/controller-demo --replicas=3
```

### 配置示例

Deployment 的策略与选择器；RC/RS 分别使用独立 selector，避免互相接管：

```yaml
apiVersion: apps/v1
kind: Deployment
metadata: {name: controller-demo, namespace: lab-core}
spec:
  replicas: 2
  selector:
    matchLabels: {app: controller-demo}
  strategy:
    type: RollingUpdate
    rollingUpdate: {maxSurge: 1, maxUnavailable: 0}
  template:
    metadata:
      labels: {app: controller-demo}
    spec:
      containers:
        - name: app
          image: "<内网应用 v1 Digest>"
          ports: [{containerPort: 8080}]
```

### 预期结果

删除一个副本后会补齐；升级创建新 RS，正常版本收敛到目标副本，坏版本出现明确 rollout 超时/未就绪。回滚后镜像和真实响应回到已知版本。孤儿接管实验要同时比较 ownerReferences，不能只数 Pod。

交付：`ops/01-kubernetes/core-resources/controllers/` 清单与 `ops/01-kubernetes/tests/integration/` 更新回退场景。

检查与失败处理：能证明期望状态收敛、孤儿接管及实际版本回退；失败检查 selector/ownerReferences 和就绪状态，不删除所有 RS 重新开始。

<a id="01-07"></a>

## 01.07 StatefulSet 与 DaemonSet

输入：不依赖 Ceph 的身份实验；明确数据暂不持久的限制。

1. 编写 Headless Service + StatefulSet，比较有序/并行策略、扩缩容和分区更新；删除单 Pod 后比较名称、序号、DNS 与 UID。
2. 用 DaemonSet 记录各节点覆盖，测试 nodeSelector/污点兼容；升级一个可观察版本并回滚，比较 ControllerRevision 和实际日志。
3. 为 03 的 PVC 数据实验预留独立变体，明确本阶段 emptyDir/无卷结果不证明数据持久化。

### 操作命令与目的

```bash
kubectl -n lab-core apply -f statefulset-demo.yaml
kubectl -n lab-core get statefulset,pod,service -o wide
kubectl -n lab-core get pod state-demo-0 -o jsonpath='{.metadata.uid}'
kubectl -n lab-core delete pod state-demo-0      # 观察名称不变而 UID 重建
kubectl -n lab-core scale statefulset/state-demo --replicas=3
kubectl -n lab-core apply -f daemonset-demo.yaml
kubectl -n lab-core set image daemonset/node-demo agent="$LAB_IMAGE_V2"
kubectl -n lab-core rollout status daemonset/node-demo
kubectl -n lab-core rollout undo daemonset/node-demo
```

### 配置示例

StatefulSet 与 Headless Service；本阶段不加 PVC，后续再增加持久化变体：

```yaml
apiVersion: v1
kind: Service
metadata: {name: state-headless, namespace: lab-core}
spec:
  clusterIP: None
  selector: {app: state-demo}
  ports: [{name: http, port: 8080, targetPort: 8080}]
---
apiVersion: apps/v1
kind: StatefulSet
metadata: {name: state-demo, namespace: lab-core}
spec:
  serviceName: state-headless
  replicas: 2
  selector:
    matchLabels: {app: state-demo}
  template:
    metadata:
      labels: {app: state-demo}
    spec:
      containers:
        - name: app
          image: "<内网应用镜像>"
          ports: [{containerPort: 8080}]
```

### 预期结果

Pod 重建后名称/序号与 Service DNS 稳定，UID 改变；这不证明本地数据持久化。DaemonSet 在符合节点约束的每个节点各有一个 Pod，更新/回退后实际镜像和 ControllerRevision 对应。节点污点不满足时缺少 Pod 应能从事件解释。

交付：`ops/01-kubernetes/core-resources/statefulset/`、`daemonset/`；身份和覆盖矩阵。

检查与失败处理：StatefulSet 稳定身份、DaemonSet 更新/回滚得到验证；失败检查更新策略和节点约束，保留原 ControllerRevision。

<a id="01-08"></a>

## 01.08 删除传播、垃圾回收与 Finalizer

输入：只有实验资源的隔离命名空间。

1. 为同一小型父子资源分别执行 foreground/background/orphan 删除，保存父子 UID、ownerReferences 和删除时间；Orphan 后观察子对象继续存在。
2. 创建带实验 Finalizer 的对象，删除后观察 deletionTimestamp；按设计清理外部模拟资源再移除 Finalizer，不把强删所有 Finalizer 当成通用修复。
3. 核对垃圾回收后的孤儿 Service/ConfigMap/PVC，区别 Kubernetes 对象删除和外部数据释放。

### 操作命令与目的

下面三种传播策略分别在重新创建的实验对象上运行：

```bash
kubectl -n lab-core apply -f gc-demo.yaml
kubectl -n lab-core delete deployment/gc-demo --cascade=foreground
# 重建后比较后台删除
kubectl -n lab-core apply -f gc-demo.yaml
kubectl -n lab-core delete deployment/gc-demo --cascade=background
# 再重建后比较孤儿保留
kubectl -n lab-core apply -f gc-demo.yaml
kubectl -n lab-core delete deployment/gc-demo --cascade=orphan
kubectl -n lab-core get rs,pods -o yaml          # 比较 ownerReferences
kubectl -n lab-core apply -f finalizer-demo.yaml
kubectl -n lab-core delete configmap/finalizer-demo --wait=false
kubectl -n lab-core get configmap/finalizer-demo -o yaml
```

### 配置示例

专用 ConfigMap 模拟 Finalizer 阻塞；它没有生产数据或真实控制器副作用：

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: finalizer-demo
  namespace: lab-core
  finalizers: [lab.egon.top/cleanup]
data:
  external-resource: simulated
```

### 预期结果

foreground 等待依赖删除，background 异步清理，orphan 保留子对象；Finalizer 对象出现 deletionTimestamp 并等待清理。在模拟外部资源已经清理、且对象仅含该实验 Finalizer 后，可用 `kubectl patch configmap/finalizer-demo -n lab-core --type=merge -p '{"metadata":{"finalizers":[]}}'` 完成演示。正常控制器的 Finalizer 应由其流程解除。

交付：`ops/01-kubernetes/examples/garbage-collection/`；删除前后资源关系及清理检查。

检查与失败处理：三种传播行为和 Finalizer 阻塞/完成均可解释，清理完成后无本次遗留对象。

<a id="01-09"></a>

## 01.09 Job、CronJob 与基础 HPA

输入：独立实验资源；HPA 需要实际可用的资源指标 API。

1. 编写成功/失败 Job，指定 backoffLimit、activeDeadlineSeconds 和完成条件；对照串行/并行及重试，任务写入带业务键避免重复副作用。
2. 配置 CronJob 的 schedule/timeZone/concurrencyPolicy/deadline/history，测试重叠、暂停和恢复；查看实际创建 Job 的时刻和去重结果。
3. 部署所选资源指标组件并验证 API，再给应用设置 requests 与 HPA；施加受控负载，记录扩缩容、稳定窗口和资源限制。

### 操作命令与目的

```bash
kubectl -n lab-core apply -f job-demo.yaml -f cronjob-demo.yaml
kubectl -n lab-core wait --for=condition=complete job/job-demo --timeout=120s
kubectl -n lab-core logs job/job-demo
kubectl -n lab-core create job cronjob-manual --from=cronjob/cron-demo
kubectl -n lab-core get jobs,cronjobs
kubectl -n lab-core patch cronjob/cron-demo --type=merge -p '{"spec":{"suspend":true}}'
kubectl top pods -n lab-core                      # 先确认指标 API 可用
kubectl -n lab-core apply -f hpa-demo.yaml
kubectl -n lab-core get hpa -w                    # 配合受控负载观察扩缩容
```

### 配置示例

CronJob 的执行策略：

```yaml
apiVersion: batch/v1
kind: CronJob
metadata: {name: cron-demo, namespace: lab-core}
spec:
  schedule: "*/2 * * * *"
  timeZone: Asia/Shanghai
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 60
  jobTemplate:
    spec:
      backoffLimit: 2
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: job
              image: "<内网诊断镜像>"
              command: [sh, -c, "date; sleep 20"]
```

HPA 的 `spec` 片段，CPU 利用率依赖目标容器配置 requests：

```yaml
scaleTargetRef: {apiVersion: apps/v1, kind: Deployment, name: controller-demo}
minReplicas: 1
maxReplicas: 4
metrics:
  - type: Resource
    resource:
      name: cpu
      target: {type: Utilization, averageUtilization: 60}
```

### 预期结果

正常 Job 为 Complete，失败变体按 backoffLimit 重试后失败；CronJob 遵守时区/并发/暂停约定。HPA 的 TARGETS 应为有效指标，负载上升后扩容、负载恢复后按窗口缩容；`<unknown>` 不是通过结果。

交付：`ops/01-kubernetes/core-resources/jobs/`、`autoscaling/`；执行次数和副本曲线。

检查与失败处理：可区分调度、重试和业务幂等；无指标时不把 HPA YAML 创建成功算扩缩容通过。

<a id="01-10"></a>

## 01.10 配置、身份与阶段交接

输入：核心资源实验完成，具备受控管理身份。

1. 对比 ConfigMap/Secret 以环境变量与卷注入后的更新行为，说明 subPath 等限制；以实际应用读取结果验证，不在日志输出秘密。
2. 创建最小 RBAC/ServiceAccount 与镜像拉取身份，通过 `kubectl auth can-i` 和实际允许/拒绝请求检查，区分身份认证与资源授权。
3. 执行阶段 smoke、HA 和资源实验回归，归档可复用清单、测试、备份与未完成项；撤销临时管理员和故障资源。

### 操作命令与目的

```bash
kubectl -n lab-core apply -f config-demo.yaml -f config-consumer.yaml
kubectl -n lab-core exec deployment/config-consumer -- cat /etc/demo/config.yaml
kubectl -n lab-core apply -f config-demo-v2.yaml    # 对比卷更新与环境变量不自动更新
kubectl -n lab-core apply -f reader-rbac.yaml
kubectl auth can-i get pods -n lab-core --as=system:serviceaccount:lab-core:reader
kubectl auth can-i delete pods -n lab-core --as=system:serviceaccount:lab-core:reader
kubectl -n lab-core get pods --as=system:serviceaccount:lab-core:reader
kubectl get nodes
```

### 配置示例

读取 Pod 的 Role；`reader-rbac.yaml` 还应包含对应 ServiceAccount 与 RoleBinding：

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata: {name: pod-reader, namespace: lab-core}
rules:
  - apiGroups: [""]
    resources: [pods]
    verbs: [get, list, watch]
```

配置消费者的 PodSpec 片段，用同一 ConfigMap 对比两种注入方式：

```yaml
containers:
  - name: app
    image: "<内网诊断镜像>"
    envFrom: [{configMapRef: {name: config-demo}}]
    volumeMounts: [{name: config, mountPath: /etc/demo, readOnly: true}]
volumes:
  - name: config
    configMap: {name: config-demo}
```

### 预期结果

非 subPath 的配置卷最终更新，环境变量需重新创建容器才能改变；记录传播延迟。reader 可以读取 Pod 而不能删除，实际请求与 `can-i` 一致。Secret 用相同注入方式测试，但只检查可用性和元数据，不输出秘密正文。最后集群恢复 10 个 Ready。

交付：`ops/01-kubernetes/core-resources/config/`、`rbac/`；阶段 acceptance 与清理结果。

检查与失败处理：全部核心资源要求有证据，十节点健康并有恢复入口；保留 03 持久化衔接，不误记为未部署的能力已通过。

## 命令参考

[kubeadm 配置](https://kubernetes.io/docs/reference/config-api/kubeadm-config.v1beta4/) · [kube-vip 静态 Pod 引导](https://kube-vip.io/docs/installation/static/) · [原官方资料入口](../../arch/references.md)
