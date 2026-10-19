# Phase 02 实验操作手册

与 [阶段正文](../../plan/02-networking.md) 配合执行，下面按原专题编号展开。02.01 正式实验与清理均已通过，详见[实际验收与交接](records/02.01-20261018T142346Z/README.md)；当前进入 02.02.01 的准备。后续示例命令不表示已经具备部署实现。

每个专题沿“确认输入 → 编写和校验配置 → 单项执行 → 正常/失败验证 → 恢复与归档”推进。报告放 `ops/02-networking/records/<执行批次>/`，引用原步骤号、参数、版本和实际结果；修改范围只限本实验对象。

## 命令与示例的使用方式

以下写明实验时大概要执行的命令、目的和预期变化，不是现在就能整段运行的一键脚本。`LAB_*`、`<...>`、版本、资源名和文件路径在开始实验时按实际环境填写；文件须先根据示例补齐，凭据通过受控配置注入。YAML 标为“片段”时应合并到完整对象，不能单独 apply；示例值不是性能或容量承诺。

`kubectl` 在选定集群的管理终端执行，`kubeadm`/主机命令在文中指定节点执行。每次变更前用 `kubectl config current-context` 核对目标。`--dry-run=server` 用于已经存在的集群/API；CRD 尚未安装时先安装匹配版本。`kubectl diff` 返回 1 通常表示有差异，应阅读差异后再 apply。故障、恢复和清理命令分段执行并观察结果，当前不执行任何部署。

测试 Namespace、样例应用、Chart/CRD 和引用文件应先创建到就绪；已由 GitOps 托管的对象通过仓库变更和同步更新，文中的直接 patch/scale/apply 用于隔离实验对象或受控诊断。

<a id="02-01"></a>

## 02.01 固定网络诊断基准

本专题完整实施入口为 [02.01 网络路径与诊断基准](examples/network-baseline/README.md)，包括所有执行命令、逐条作用/预期结果、完整 YAML、Ansible、离线物料、失败处理、清理与回退。当前状态见 [2026-10-18 实际验收与交接](records/02.01-20261018T142346Z/README.md)，前期只读及源码验证另见[准备记录](records/02.01-20261018-source-review/README.md)。

- **输入**：Phase 01 原集群交接回执、十台 VM `.101–.110`、已有 Mac 工具链和原恢复管理员身份。
- **02.01.01**：记录 Mac/API/业务、Pod/Pod、Pod/Service、Pod/Harbor 与节点/外网的 DNS、路由、TLS、代理和实际 SNAT 路径。
- **02.01.02**：11 个普通诊断 Pod，覆盖 100 个 VM 有向对的 HTTP/TCP、UDP、跨空间、双协议 DNS、接口 MTU、大包、样本丢失与延迟。用户已明确屏蔽物理层感知，不依赖 ESXi 放置。
- **02.01.03**：沿用 Cilium 1.20.2，增加有界 Hubble 缓冲、mTLS Relay 与受限查询入口；正常放行、应用超时、策略拒绝各有真实请求和 Flow 断言。
- **交付与边界**：`examples/network-baseline/`、`networking/`、`ansible/`、`scripts/baseline.sh` 和 `tests/integration/network-baseline/`。保留 Overlay、kube-proxy、Enforcing 与 firewalld；源码校验不能代替正式运行验收。

先运行 `preflight`、`validate`，再由用户执行 `run`；看到 `02.01 ACCEPTANCE PASS` 后执行 `cleanup`，核对 `02.01 CLEANUP PASS`。本轮完成后再进入 02.02。

<a id="02-02"></a>

## 02.02 Service、CoreDNS 与 EndpointSlice

**02.02 整组已验收并清理**，见[实际结果与交接](records/02.02-20261018T225144Z/README.md)。[整组 Ansible、YAML、命令与预期结果](examples/services/README.md)保留作复现；真实 NodePort、VIP 回收再分配、Headless、手工 EndpointSlice、ExternalName 和 DNS 缓存均通过。MetalLB controller 1/1、两个 worker speaker 2/2 保留供 02.03。以下示例仅供概念查阅。

输入：稳定的 HTTP/gRPC 测试后端。

1. 分别编写 ClusterIP、NodePort、Headless、ExternalName、无 selector Service，明确端点来源；无 selector 场景显式管理 EndpointSlice。
2. 变化后端副本和 Readiness，watch EndpointSlice，同时从 Pod、节点和外部客户端发请求；检查 externalTrafficPolicy/sessionAffinity 对路径和源 IP 的影响。
3. 查看 CoreDNS ConfigMap，测试 cluster.local、内部域、外部域、负缓存与后端恢复，避免环路。

### 操作命令与目的

```bash
kubectl -n lab-net apply -f services-demo.yaml
kubectl -n lab-net get service,endpointslice -o wide
kubectl -n lab-net exec "$LAB_CLIENT_POD" -- nslookup echo.lab-net.svc.cluster.local
kubectl -n lab-net exec "$LAB_CLIENT_POD" -- curl -fsS http://echo:8080/
kubectl -n lab-net scale deployment/echo --replicas=3
kubectl -n lab-net get endpointslice -l kubernetes.io/service-name=echo -w
kubectl -n kube-system get configmap coredns -o yaml  # 查看域与转发方向
```

NodePort 再从 LAN 请求 `http://<节点 IP>:<实际 NodePort>`；Headless 查返回的 Pod 地址；ExternalName 查 CNAME；无 selector Service 使用明确的 EndpointSlice 变体分别验收。

### 配置示例

选择 `app=echo`、后端 8080 端口的基础 Service；其他类型另存文件，不在同一个对象上混写互斥字段：

```yaml
apiVersion: v1
kind: Service
metadata: {name: echo, namespace: lab-net}
spec:
  type: ClusterIP
  selector: {app: echo}
  ports:
    - name: http
      port: 8080
      targetPort: 8080
```

### 预期结果

Service 选择器匹配实际 Pod，扩容/Readiness 变化带来 EndpointSlice 变化，客户端只能命中就绪端点。DNS 错误、Service 无端点和端口不匹配是不同失败，分别保存解析、端点和请求结果。

交付：`ops/02-networking/networking/services/`、`dns/`；服务类型请求矩阵。

检查与失败处理：Service/域名和实际端点一致；失败检查 selector、端口映射、策略与 DNS，不只反复重启 CoreDNS。

<a id="02-03"></a>

## 02.03 MetalLB 与地址宣告

状态：[完整02.03实际验收及清理通过](records/02.03-20261019T000211Z/README.md)，已生成02.04交接；主池与两个speaker保留。

使用[完整 Ansible、YAML、命令与预期结果](examples/metallb/README.md)，统一入口 `scripts/metallb.sh all <记录目录>` 一次完成全部三项；[02.02 交接](records/02.02-20261018T225144Z/README.md)中的 MetalLB 0.16.1 controller1/1、worker speaker2/2 直接复用。

1. **02.03.01**：持久主池 `.201–.210` 禁止自动分配，声明 Service 分配标签、ens33 和两个候选 VM；从 Mac、infra01 与 ServiceL2Status 核对 `.202` 的实际 HTTP/唯一 ARP 宣告。
2. **02.03.02**：从实际 ARP 判断入口 VM，先预热原有 TCP 连接，再精确停止该 VM 的 speaker；记录 VIP 接管、新连接恢复和原连接断开/重连；任何结果都恢复原始 speaker spec 和两个 Ready 实例。
3. **02.03.03**：旧 Service UID/宣告撤销、HTTP/ARP 不再响应后，以新 Service UID 重新申请同 VIP，实测后再次撤销，生成地址分配/撤销台账。

只感知 VM，不操作 ESXi 或物理宿主机。SELinux Enforcing、firewalld、API `.100`、CNI/CoreDNS/控制台均保持原配置。`.201` 预留网关，`.211–.220` 对比池不启用。完整主池及宣告保留供02.04；实验 Namespace、VIP Service 和观测进程清理。

执行前严格 dry-run 全部 YAML、已有 CRD/Webhook 及两种维护补丁；实际故障和业务验收由用户执行。观察结果和清理回执分别保存，不能把只读检查或离线替身演练当作正式漂移通过。

<a id="02-04"></a>

## 02.04 Gateway API 与 Ingress 对照

状态：[完整 02.04 实际验收及清理通过](records/02.04-20261019T105544Z/README.md)，63 份源码输入匹配；保留 .201 的 80/443 与双副本数据面，供 02.05 接管证书自动化。

完整交付：[逐项作用、预期结果、全部剧本和 YAML](examples/gateway/README.md)；[JSONPath 修复与真实前检记录](records/02.04-20261019-jsonpath-review/README.md)。在管理 Mac 的交互终端一次运行：

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
export LAB_GATEWAY_RECORDS="$PWD/ops/02-networking/records/02.04-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/gateway.sh all "$LAB_GATEWAY_RECORDS"
```

第一行进入仓库，第二行绑定全新证据目录，第三行统一核对前置、部署、验证七项与清理。启动时安全输入一次既有中间 CA 口令，不回显、不保存；不在聊天或命令行写口令。预期 02.04 ALL PASS，PLAY RECAP failed/unreachable/rescued/ignored 为 0，passed.json 和 state/closed.json 均通过。

锁定 Gateway API 1.6.1 Standard、Envoy Gateway 1.9.2、Envoy 1.39.1，以及临时 Traefik 3.7.14 / Chart 42.0.0。主入口 .201 的 80/443 保留，数据面只跨 worker01/02 两台 VM；临时对照 .203、9000/TCP、9001/UDP、实验路由/授权/空间统一回收。实际验证 DNS、前后端 TLS、Host/Path/Header/重写/超时、RBAC/跨空间授权、真实 gRPC/TCP/UDP、同应用 Ingress 对照、200 个独立连接权重与新 Pod 的 HTTP/gRPC/xDS 配置。

原有 MetalLB 主池及 speaker、Headlamp/Hubble/metrics、CNI/CoreDNS、SELinux Enforcing 和 firewalld 保持。任一实际协议或分项结果缺失均不能通过。失败后仅使用原目录 recover，具体边界及命令见完整说明。

<a id="02-05"></a>

## 02.05 TLS、cert-manager 与公网边界

状态：[完整 02.05 内部验收及清理通过](records/02.05-20261019T125941Z/README.md)，49 份执行输入匹配，13 项内部结果通过；主入口保留稳定周期自动证书。按操作者确认，02.05.03 公网项 BLOCKED，阶段不宣称完整通过；已生成 02.06 内部实验交接。

[全部 Ansible、YAML、每条命令与预期结果](examples/certificates/README.md)；[执行前核验](records/02.05-20261019-source-review/README.md)。管理 Mac 一次执行：

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
export LAB_TLS_RECORDS="$PWD/ops/02-networking/records/02.05-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/certificates.sh all "$LAB_TLS_RECORDS"
```

依次进入仓库、绑定全新证据目录、统一前检及执行全部内部实验和清理。首次安全输入一次根 CA 口令，在 Mac 签发独立受限中间 CA；根和原中间 CA 私钥不上传，新签发器只允许既有两个网关域名。cert-manager 1.21.2、五个镜像和 Go 标准库 TLS 客户端均已锁定并准备。

定时器实际更新证书和密钥、Secret UID 保持、网关 TLS 热加载后恢复七天证书/提前四十八小时续期。四类错误材料仅放在 lab-tls 后端，主入口保持有效证书；Python/Go 检查真实拒绝类型，网关上游验证失败计数必须增加。成功保留自动化组件和 .201，回收实验空间，原入口非证书字段及原 Pod UID/spec 不变。

预期 02.05 INTERNAL PASS、02.05.03 BLOCKED、CLEANUP PASS 和 failed/unreachable=0；不打印完整 ALL PASS，不把公网标成通过。恢复命令、权限边界及 CA 有效期维护见完整说明。

<a id="02-06"></a>

## 02.06 网络策略与出口治理

完整剧本、YAML、逐条作用/预期、52 个正反向用例、5 组实际源与回程以及恢复说明见 [完整操作指南](examples/policies/README.md)；[执行前核验记录](records/02.06-20261019-source-review/README.md)。02.05 内部验收已归档，公网 BLOCKED 保留。

在管理 Mac 一次运行整组：

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
export LAB_POLICY_RECORDS="$PWD/ops/02-networking/records/02.06-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/policies.sh all "$LAB_POLICY_RECORDS"
```

第一行进入仓库，第二行绑定全新证据目录，第三行完成前置、全部配置预览、默认拒绝、标准/Cilium/FQDN/HTTP 对照、Harbor/存储 VM/代理的实际源与回程、实验 Pod 的代理入口不可达与恢复、汇总和清理。无需分节执行或输入口令。只有操作者启动正式部署。

预期 AVAILABLE CASES PASS、CLEANUP PASS、failed/unreachable/rescued/ignored=0。当前模式保留 kube-proxy，02.06.04 Egress Gateway 模式、CRD 和真实 VPN/出口 VM 故障项 BLOCKED；Ceph 服务属于 Phase03，02.06.03 只完成存储 VM 路径验证，记 PARTIAL_CEPH_BLOCKED。passed=false、phase_complete=false，不把实验代理入口故障冒充真实 VPN 故障。

本轮只创建三个 restricted 临时 Namespace，按原 UID 清理；保持 .101–.110 VM、SELinux/firewalld、原 CNI/路由/代理与主 .201 的可信 TLS。完整指南提供原批 recover 命令与每类底层命令解释。

<a id="02-07"></a>

## 02.07 节点约束与物理故障域

输入：hosts.yaml 的实际放置与容量。

1. 写入角色与 `lab.egon.top/esxi-host` 标签；核对真实宿主机后配置 nodeSelector/NodeAffinity 的硬、软约束。
2. 对单个实验节点施加 NoSchedule/PreferNoSchedule/NoExecute，验证容忍期限；检查系统 DaemonSet 不被 storage 污点误伤。
3. 测试 PodAffinity/AntiAffinity、TopologySpread 的 maxSkew 与不可调度行为；改变容量或标签，记录 Pending 的具体原因和修复。

### 操作命令与目的

```bash
kubectl label node "$LAB_NODE" lab.egon.top/esxi-host=esxi01 --overwrite
kubectl get nodes -L lab.egon.top/esxi-host
kubectl -n lab-net apply -f placement-demo.yaml
kubectl -n lab-net get pods -o wide
kubectl taint node "$LAB_TEST_NODE" lab-purpose=isolated:NoSchedule
kubectl -n lab-net describe pod "$LAB_PENDING_POD"   # 解释无法调度原因
kubectl taint node "$LAB_TEST_NODE" lab-purpose:NoSchedule-  # 结束后撤销本次污点
```

### 配置示例

Deployment 的 PodSpec 片段，展示真实物理故障域分散和存储污点容忍；是否允许业务进入 storage 节点按场景决定：

```yaml
topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: lab.egon.top/esxi-host
    whenUnsatisfiable: DoNotSchedule
    labelSelector:
      matchLabels: {app: placement-demo}
affinity:
  nodeAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 50
        preference:
          matchExpressions:
            - key: lab.egon.top/role
              operator: In
              values: [worker]
```

### 预期结果

副本按真实 ESXi 标签分散；硬约束不可满足时 Pending，事件说明具体约束。Preferred 是偏好，Toleration 只是解除排斥，不会自动选择节点。NoExecute 与容忍时间另存变体观察逐出和恢复。

交付：`ops/02-networking/networking/scheduling/`；节点位置和调度结果矩阵。

检查与失败处理：关键副本分散到真实故障域；条件不足时 Pending 可解释，不偷偷放宽全部硬约束。

<a id="02-08"></a>

## 02.08 配额、QoS、驱逐与 PDB

输入：独立压力 Namespace，保留节点与管理资源余量。

1. 声明 ResourceQuota/LimitRange，测试缺失或超限 requests/limits 的拒绝；创建三类 QoS 工作负载并记录实际 qosClass。
2. 在受限负载下观察资源压力和 Eviction，设置 PriorityClass 对照抢占；不把压力施加到控制平面或唯一数据副本。
3. 配置 PDB，再对单 Worker 使用受控 drain 场景观察允许/阻止；说明 PDB 约束自愿驱逐，不能当作物理故障或所有直接删除的保护。

### 操作命令与目的

```bash
kubectl -n lab-net apply -f quota-demo.yaml -f limits-demo.yaml -f pdb-demo.yaml
kubectl -n lab-net describe resourcequota lab-budget
kubectl -n lab-net apply -f over-budget-demo.yaml  # 故意请求超配额资源
kubectl -n lab-net get pod "$LAB_POD" -o jsonpath='{.status.qosClass}'
kubectl -n lab-net get pdb
kubectl drain "$LAB_TEST_WORKER" --ignore-daemonsets --timeout=120s
# 观察 PDB 阻止/允许后，完成实验恢复调度
kubectl uncordon "$LAB_TEST_WORKER"
```

drain 可能因 PDB 或本地数据保护停止，这本身可作为实验结果；不额外加 `--force` 绕过。压力和抢占先限制在有余量的测试 Worker。

### 配置示例

```yaml
apiVersion: v1
kind: ResourceQuota
metadata: {name: lab-budget, namespace: lab-net}
spec:
  hard:
    requests.cpu: "2"
    requests.memory: 2Gi
    limits.cpu: "4"
    limits.memory: 4Gi
    pods: "12"
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata: {name: echo-budget, namespace: lab-net}
spec:
  minAvailable: 1
  selector:
    matchLabels: {app: echo}
```

### 预期结果

超配额创建被拒绝；QoS 与 requests/limits 组合一致；drain 尊重 PDB，恢复后节点可调度。PDB 约束自愿驱逐，不保证物理故障时仍有足够副本；节点压力实验另记录 Evicted/抢占原因。

交付：`ops/02-networking/networking/resource-governance/`；配额与驱逐用例。

检查与失败处理：拒绝、驱逐和分布符合预期；触达停止阈值立即撤销压力并恢复节点调度。

<a id="02-09"></a>

## 02.09 Cilium 数据面、L2 与 BGP 对照

输入：独立实验窗口/范围、已验证主线配置和回退通道。

1. 保存主线 values，在隔离环境切换 kube-proxy replacement，逐项跑 Service/NodePort/Gateway/API 回归；先确认特性要求再实验 L2。
2. 使用 .211–.220 的独立选择器与池测试 LB IPAM/L2，不宣告 MetalLB 或 API 地址；测试节点失效与地址撤回。
3. Native Routing 先具备 Pod CIDR 回程路由；BGP 先准备可控邻居、ASN、过滤与允许前缀，再测试建邻、宣告、撤回和故障，不把家庭默认路由纳入宣告。

### 操作命令与目的

本节在独立实验环境或有回退入口的维护窗口执行，每次只变一种数据面能力：

```bash
helm get values cilium -n kube-system -o yaml > cilium-before.yaml
helm history cilium -n kube-system
helm upgrade cilium "$LAB_CILIUM_CHART" -n kube-system \
  --version "$LAB_CILIUM_VERSION" -f cilium-comparison-values.yaml --wait
cilium status --wait
cilium connectivity test --test-namespace lab-connectivity
kubectl apply -f cilium-lb-pool.yaml -f cilium-l2-policy.yaml
cilium bgp peers                         # BGP 场景检查邻居
cilium bgp routes advertised ipv4 unicast # 检查实际宣告的 IPv4 单播路由
# 对照结束后按实际迁移流程恢复；Helm 回退不是 kube-proxy 重建的完整替代
helm rollback cilium "$LAB_GOOD_HELM_REVISION" -n kube-system --wait
```

### 配置示例

Cilium Helm values 的特性片段；L2/BGP 分开启用，具体 Kubernetes API 地址和设备按实验填写：

```yaml
kubeProxyReplacement: true
k8sServiceHost: 192.168.9.100
k8sServicePort: 6443
l2announcements:
  enabled: true
```

隔离的 LB IPAM 地址池示例，CRD API 版本在实验时核对：

```yaml
apiVersion: cilium.io/v2
kind: CiliumLoadBalancerIPPool
metadata: {name: comparison-pool}
spec:
  blocks:
    - start: 192.168.9.211
      stop: 192.168.9.220
  serviceSelector:
    matchLabels: {lab.egon.top/lb: cilium-comparison}
```

对照 Service 还需设置该 Cilium 模式支持的 `loadBalancerClass`，并让 MetalLB 只处理其自己的 class 或互斥服务分配范围。地址池不重叠本身不能阻止两个控制器同时处理同一个 Service。

### 预期结果

切换前后同一通信集可对比，实验 VIP 与 MetalLB/API 不重叠；BGP 邻居 Established、前缀受过滤且故障后撤回。Native Routing 必须有 Pod CIDR 回程路由。恢复主线时再次验证 API、Service、DNS 和网关，不能只看 Helm 状态。

交付：`ops/02-networking/examples/` 模式 values、网络测试和回退配置。

检查与失败处理：同一测试集给出前后对照；缺少路由/BGP 条件单独阻塞；回退后原入口和 DNS 仍通过。

<a id="02-10"></a>

## 02.10 Istio、SPIFFE/SPIRE 与交接

输入：隔离 Namespace、兼容矩阵和已验证应用基准。

1. 分别在不同工作负载上启用 Sidecar 与 Ambient；Ambient 按所需 L7 功能配置 waypoint，比较注入/ztunnel/waypoint 的实际责任。
2. 实施 mTLS、授权、超时和有界重试，测试未授权服务与故障后端；记录资源和延迟变化，不给同一工作负载重复启用冲突模式。
3. 部署隔离 SPIRE 注册/证明流程，验证 SVID 签发、续期和不满足身份条件时拒绝；internal.egon.top 信任域不替代 DNS 或 RBAC。
4. 撤除闲置网格/Ingress/实验 VIP，保留主线并跑基准回归；需要 05/06 的观测与联合信任扩展写入回访。

### 操作命令与目的

```bash
istioctl install -f istio-sidecar.yaml --skip-confirmation
kubectl label namespace mesh-sidecar istio-injection=enabled --overwrite
kubectl -n mesh-sidecar rollout restart deployment/mesh-demo
istioctl proxy-status
# Ambient 工作负载放到另一个 Namespace，控制面先安装匹配 Ambient profile
kubectl label namespace mesh-ambient istio.io/dataplane-mode=ambient --overwrite
istioctl waypoint apply -n mesh-ambient --enroll-namespace
kubectl -n mesh-sidecar apply -f mesh-auth.yaml
kubectl -n mesh-sidecar exec "$LAB_ALLOWED_CLIENT" -- curl -fsS http://mesh-demo:8080/
```

SPIRE 部署后，在 server 管理环境使用 `spire-server agent list`、`spire-server entry show`，再以 `spire-server entry create` 声明实际 parent ID、SPIFFE ID 和 `k8s:ns`/`k8s:sa` selectors；通过实验工作负载检查 SVID 获取、续期及不匹配身份拒绝。

### 配置示例

在单一实验 Namespace 强制 mTLS，随后配套最小 AuthorizationPolicy；Sidecar 与 Ambient 使用各自独立对象：

```yaml
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata: {name: default, namespace: mesh-sidecar}
spec:
  mtls:
    mode: STRICT
```

超时/重试示例字段放进实际 VirtualService 或该实现支持的 Route；不要在网关、网格和 SDK 同时设置无界重试。

### 预期结果

选定工作负载接入对应网格，允许身份可调用，未授权身份被拒绝；Ambient 的 L4 与 waypoint 的 L7 行为分别验证。SPIRE 的短期身份能续期，不合 selectors 的工作负载不能取得目标身份。退出实验后主线网络回归通过。

交付：`ops/02-networking/networking/mesh/` 与身份实验；完整网络交接表。

检查与失败处理：跨节点、HTTPS/gRPC、策略、调度和网格基础能力有证据；未满足高级条件不计为已完成。

## 命令参考

[Gateway API HTTP 路由](https://gateway-api.sigs.k8s.io/guides/user-guides/http-routing/) · [Cilium L2 前置](https://docs.cilium.io/en/stable/network/l2-announcements/) · [原官方资料入口](../../arch/references.md)
