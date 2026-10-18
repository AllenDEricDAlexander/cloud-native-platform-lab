# Phase 01 实验操作手册

与 [阶段正文](../../plan/01-kubernetes.md) 配合执行，下面按原专题编号展开实施参考。配置和脚本应在本轮实施时编写、校验；示例命令只提供操作/检查入口，实际进度以本轮执行记录为准。

当前按 [2026-10-17 从头重做批次](records/2026-10-17-restart/README.md)推进；已编写并执行的 [cp01 旧残留清理剧本](ansible/playbooks/cleanup-cp01.yml)复用 00 的 Ansible 配置，后续部署与核心资源实验按本轮证据逐项验收。

01.02 十节点基础健康、普通 Pod 网络、Mac 受限身份与恢复文件备份/取回已通过；01.03–01.06 已完成源码 YAML + Ansible 的真实重跑验收，26 个成功断点与验收、清理两个总 PASS 齐全，详见[重跑完成记录](records/2026-10-18-ansible-replay/repairs/20261018-observer-and-completion/README.md)。01.07 StatefulSet/DaemonSet、01.08 删除传播/所有权/Finalizer 实验与清理均已实际通过，详见[07 验收归档](records/core-07-10/runs/07-20261018T102322Z/README.md)、[08 验收归档](records/core-07-10/runs/08-20261018T105000Z/README.md)；下一专题为 01.09。.15 管理机实际分发仍待交付。[身份手册](bootstrap/access/README.md)、[基础验收命令](bootstrap/acceptance/README.md)和 [引导配置](bootstrap/README.md)保留复现入口；下面的“本轮第一至第三步”仅保留教学过程，不对完整文件重复执行旧追加命令。

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

原始运行已验收并清理，见 [原始逐项验收](records/2026-10-17-restart/acceptance.md)。资源 YAML 位于 [源码清单](core-resources/pods/manifests/)，Ansible 执行顺序与说明见 [专题手册](core-resources/pods/README.md)。

01.03–01.06 已完成源码 YAML、Ansible 执行、Python 必要检查的真实重跑验收，26 个成功断点和两个总 PASS 齐全，原始记录与旧源码保留。详见[重跑完成记录](records/2026-10-18-ansible-replay/repairs/20261018-observer-and-completion/README.md)。

<a id="01-05"></a>

## 01.05 三类探针与优雅终止

原始运行已验收并清理，见 [原始逐项验收](records/2026-10-17-restart/acceptance.md)。资源 YAML 位于 [源码清单](core-resources/probes/manifests/)，Ansible 执行顺序与说明见 [专题手册](core-resources/probes/README.md)。

01.03–01.06 已完成源码 YAML、Ansible 执行、Python 必要检查的真实重跑验收，26 个成功断点和两个总 PASS 齐全，原始记录与旧源码保留。详见[重跑完成记录](records/2026-10-18-ansible-replay/repairs/20261018-observer-and-completion/README.md)。

<a id="01-06"></a>

## 01.06 RC、ReplicaSet 与 Deployment

原始运行已验收并清理，见 [原始逐项验收](records/2026-10-17-restart/acceptance.md)。资源 YAML 位于 [源码清单](core-resources/controllers/manifests/)，Ansible 执行顺序与说明见 [专题手册](core-resources/controllers/README.md)。

01.03–01.06 已完成源码 YAML、Ansible 执行、Python 必要检查的真实重跑验收，26 个成功断点和两个总 PASS 齐全，原始记录与旧源码保留。详见[重跑完成记录](records/2026-10-18-ansible-replay/repairs/20261018-observer-and-completion/README.md)。

<a id="01-07"></a>

## 01.07 StatefulSet 与 DaemonSet

稳定序号、DNS/UID、emptyDir 边界、有序/并行、分区/OnDelete；DaemonSet 标签、精确污点容忍、发布与回滚。

本轮已实际验收并完成清理：两个总 PASS、全部主机失败数为零；十节点健康，实验空间、节点标签与污点均已清除，详见[07 验收归档](records/core-07-10/runs/07-20261018T102322Z/README.md)。以下命令保留为复现入口，当前继续 01.08 即可。

独立源码、逐条命令解释、预期结果和恢复说明见 [01.07 完整手册](core-resources/statefulset/README.md)。每阶段只执行自己；正式运行前检查上一阶段的真实回执。

```bash
# 进入管理 Mac 的仓库。
cd /Users/mario/SelfProject/cloud-native-platform-lab
# 为本阶段建立独立证据目录；不要复用其他阶段 context。
CNPL07="$PWD/ops/01-kubernetes/records/core-07-10/runs/07-$(date -u +%Y%m%dT%H%M%SZ)"
# 先编译/有限测试并渲染清单校验；这不是实际实验验收。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-07.sh validate "$CNPL07"
# 只执行当前阶段，完成后停止。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-07.sh run "$CNPL07"
```

预期 `01.07 SOURCE VALIDATION PASS`，随后正式运行必须同时出现 `01.07 ACCEPTANCE PASS`、`01.07 CLEANUP PASS`。失败后同源码用 `resume`；放弃时用原目录 `cleanup`。已有证据保留，未通过时不发布下一阶段进度。

<a id="01-08"></a>

## 01.08 删除传播、所有权与 Finalizer

分别实测 foreground/background/orphan、原 Pod 接管和模拟外部清理顺序，按 UID 验收。

本轮已实际验收并完成清理：五组快照证明传播顺序、原 Pod UID 接管与 Finalizer 清理顺序；两个总 PASS、全部主机失败数为零，十节点健康且实验空间已删除，详见[08 验收归档](records/core-07-10/runs/08-20261018T105000Z/README.md)。以下命令保留为复现入口，当前继续 01.09 即可。

独立源码、逐条命令解释、预期结果和恢复说明见 [01.08 完整手册](examples/garbage-collection/README.md)。每阶段只执行自己；正式运行前检查上一阶段的真实回执。

```bash
# 进入管理 Mac 的仓库。
cd /Users/mario/SelfProject/cloud-native-platform-lab
# 为本阶段建立独立证据目录；不要复用其他阶段 context。
CNPL08="$PWD/ops/01-kubernetes/records/core-07-10/runs/08-$(date -u +%Y%m%dT%H%M%SZ)"
# 先编译/有限测试并渲染清单校验；这不是实际实验验收。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-08.sh validate "$CNPL08"
# 只执行当前阶段，完成后停止。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-08.sh run "$CNPL08"
```

预期 `01.08 SOURCE VALIDATION PASS`，随后正式运行必须同时出现 `01.08 ACCEPTANCE PASS`、`01.08 CLEANUP PASS`。失败后同源码用 `resume`；放弃时用原目录 `cleanup`。已有证据保留，未通过时不发布下一阶段进度。

<a id="01-09"></a>

## 01.09 Job、CronJob 与基础 HPA

Indexed Job 重试幂等、失败/超时、真实分钟调度、时区/并发/暂停；先建立安全资源指标，再实测 CPU/内存 HPA。

执行前已补齐 CronJob 暂停创建、统一启用和同一计划时间检查，并完成有限测试、真实 validate、服务端准入及 Linux 回退夹具，详见[09 执行前核验](records/2026-10-18-stage09-review/README.md)。09 正式实验仍由下面的 run 开始；其清理回收 lab-p09，保留安全指标基础组件。

当前实际执行在 Job API 请求处发现 Cilium 节点身份与 ipBlock 不匹配，已改为本 run 的 kube-apiserver 实体精确放行；两个 worker 均完成真实 Indexed Job 的 7→0 重试和幂等账本验证，原批次已登记修复来源并通过同目录 validate。详见[API 出口修复与原批次恢复](records/2026-10-18-stage09-api-egress-fix/README.md)，当前使用原目录 resume 完成后续实验。

独立源码、逐条命令解释、预期结果和恢复说明见 [01.09 完整手册](core-resources/jobs/README.md)。每阶段只执行自己；正式运行前检查上一阶段的真实回执。

```bash
# 进入管理 Mac 的仓库。
cd /Users/mario/SelfProject/cloud-native-platform-lab
# 为本阶段建立独立证据目录；不要复用其他阶段 context。
CNPL09="$PWD/ops/01-kubernetes/records/core-07-10/runs/09-$(date -u +%Y%m%dT%H%M%SZ)"
# 先编译/有限测试并渲染清单校验；这不是实际实验验收。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-09.sh validate "$CNPL09"
# 只执行当前阶段，完成后停止。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-09.sh run "$CNPL09"
```

预期 `01.09 SOURCE VALIDATION PASS`，随后正式运行必须同时出现 `01.09 ACCEPTANCE PASS`、`01.09 CLEANUP PASS`。失败后同源码用 `resume`；放弃时用原目录 `cleanup`。已有证据保留，未通过时不发布下一阶段进度。

<a id="01-10"></a>

## 01.10 配置、身份与阶段交接

配置注入/刷新、Secret 轮换和实际认证、私有 Registry 拉取及凭据轮换、SA/RBAC/audience/Bound Token，最后清理交接。

独立源码、逐条命令解释、预期结果和恢复说明见 [01.10 完整手册](core-resources/config/README.md)。每阶段只执行自己；正式运行前检查上一阶段的真实回执。

```bash
# 进入管理 Mac 的仓库。
cd /Users/mario/SelfProject/cloud-native-platform-lab
# 为本阶段建立独立证据目录；不要复用其他阶段 context。
CNPL10="$PWD/ops/01-kubernetes/records/core-07-10/runs/10-$(date -u +%Y%m%dT%H%M%SZ)"
# 先编译/有限测试并渲染清单校验；这不是实际实验验收。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-10.sh validate "$CNPL10"
# 只执行当前阶段，完成后停止。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-10.sh run "$CNPL10"
```

预期 `01.10 SOURCE VALIDATION PASS`，随后正式运行必须同时出现 `01.10 ACCEPTANCE PASS`、`01.10 CLEANUP PASS`。失败后同源码用 `resume`；放弃时用原目录 `cleanup`。已有证据保留，未通过时不发布下一阶段进度。

## 命令参考

[kubeadm 配置](https://kubernetes.io/docs/reference/config-api/kubeadm-config.v1beta4/) · [kube-vip 静态 Pod 引导](https://kube-vip.io/docs/installation/static/) · [原官方资料入口](../../arch/references.md)
