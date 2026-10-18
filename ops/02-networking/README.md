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

输入：00 已验证 L2/VIP，.201–.210 已排除 DHCP。

1. 安装锁定 MetalLB，声明 IPAddressPool 和 L2Advertisement，限制作用域；API .100 和对照池不纳入该池。
2. 为测试 LoadBalancer Service 申请地址，从不同客户端检查 ARP、访问和实际宣告节点；记录节点失效后的迁移时间。
3. 恢复节点后再次检测重复宣告，清理临时 Service 并核对 IP 释放。

### 操作命令与目的

```bash
helm upgrade --install metallb "$LAB_METALLB_CHART" -n metallb-system \
  --create-namespace --version "$LAB_METALLB_VERSION" -f metallb-values.yaml --wait
kubectl apply -f metallb-pool.yaml
kubectl -n lab-net apply -f loadbalancer-demo.yaml
kubectl -n lab-net get service echo-lb -w          # 等待外部 IP 分配
curl -fsS "http://$LAB_SERVICE_VIP:8080/"          # 从 LAN 请求真实 VIP
ip neigh show "$LAB_SERVICE_VIP"                 # Linux 客户端观察邻居项
kubectl -n metallb-system get pods -o wide
```

故障实验时再对当前宣告节点执行约定的单节点停机/隔离动作；持续请求并观察邻居项改变，恢复后再清理测试 Service。

### 配置示例

```yaml
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata: {name: lab-business, namespace: metallb-system}
spec:
  addresses: [192.168.9.201-192.168.9.210]
---
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata: {name: lab-business, namespace: metallb-system}
spec:
  ipAddressPools: [lab-business]
```

LoadBalancer Service 使用 `type: LoadBalancer`，按需用 `metallb.io/address-pool: lab-business` 注解指定池；selector 和端口复用 echo 服务。

### 预期结果

EXTERNAL-IP 从规划池产生；LAN 可访问；停一个宣告节点后其他节点接管并记录实际切换时间。不得占用 API `.100` 或对照池 `.211–.220`，长期 Pending 应检查池、选择器和控制器事件。

交付：`ops/02-networking/networking/metallb/` 配置与 VIP 故障用例。

检查与失败处理：无冲突且客户端可达；失败先检查 L2/端口组/池选择，撤回本次宣告而非改全部网络。

<a id="02-04"></a>

## 02.04 Gateway API 与 Ingress 对照

输入：MetalLB、HTTP/gRPC 后端与所需域名。

1. 锁定 Gateway API CRD channel、Envoy Gateway 版本和 Route 支持；依次安装 CRD、控制器、GatewayClass、Gateway、HTTPRoute/GRPCRoute。
2. 检查 Accepted/Programmed/ResolvedRefs 等条件；用 Host/SNI、path/header、权重请求验证路由，不把 CRD 创建成功当作流量通过。
3. 在独立 IngressClass/入口部署 Ingress 对照，测相同应用；测试无效引用、后端失效和跨 Namespace 引用边界。

### 操作命令与目的

```bash
kubectl apply --server-side -f "$LAB_GATEWAY_API_CRDS"  # 使用锁定版本本地清单
helm upgrade --install envoy-gateway "$LAB_ENVOY_CHART" -n envoy-gateway-system \
  --create-namespace --version "$LAB_ENVOY_VERSION" -f envoy-values.yaml --wait
kubectl -n lab-net apply -f gateway-demo.yaml -f route-demo.yaml
kubectl -n lab-net get gateway,httproute -o yaml       # 检查 Accepted/Programmed/ResolvedRefs
curl -H 'Host: demo.svc.internal.egon.top' "http://$LAB_GATEWAY_VIP/"
# 单独部署 Ingress 对照；使用不同 IngressClass/入口，参数按选定控制器填写
helm upgrade --install ingress-compare "$LAB_INGRESS_CHART" -n ingress-compare \
  --create-namespace --version "$LAB_INGRESS_VERSION" -f ingress-values.yaml --wait
```

gRPC 场景补充 GRPCRoute，并用 `grpcurl` 的 `-authority` 和实际 proto/方法发请求；`list` 依赖服务启用反射，反射关闭不等于 gRPC 不通。

### 配置示例

HTTPRoute 关联已建立的 `lab-gateway` 和 echo 后端：

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata: {name: echo, namespace: lab-net}
spec:
  parentRefs: [{name: lab-gateway}]
  hostnames: [demo.svc.internal.egon.top]
  rules:
    - matches:
        - path: {type: PathPrefix, value: /}
      backendRefs:
        - name: echo
          port: 8080
```

Gateway 另行声明 `gatewayClassName` 和 HTTP/HTTPS listener；跨 Namespace 的后端引用按实际关系配置 ReferenceGrant，不能默认允许所有引用。

### 预期结果

Route 条件为接受且引用已解析，访问指定 Host 命中对应后端；错误 Host/路径、失效后端和未授权跨域引用产生可解释的失败。最终用实际 HTTP/gRPC 请求验证，不只检查资源存在。

交付：`ops/02-networking/networking/gateway/`、`ingress/`；Route 与请求记录。

检查与失败处理：HTTPS/gRPC 和路由策略有数据面证据；适配缺失标注阻塞，不伪造控制器能力。

<a id="02-05"></a>

## 02.05 TLS、cert-manager 与公网边界

输入：内部 CA 签发方式及明确的公开白名单。

1. 部署 cert-manager，声明受限 Issuer/Certificate，根 CA 私钥保持离线；把证书 Secret 引用接到 Gateway，校验实际返回的 SAN/链/有效期。
2. 缩短实验叶证书周期或执行可控续期测试，观察更新后的 TLS；测试错误 SAN、未受信 CA、过期证书的拒绝行为。
3. 公网入口只对已列白名单配置 DNS/入站和 ACME；内部 GitLab/Harbor/API 不因统一网关而公开。

### 操作命令与目的

```bash
helm upgrade --install cert-manager "$LAB_CERT_MANAGER_CHART" -n cert-manager \
  --create-namespace --version "$LAB_CERT_MANAGER_VERSION" -f cert-manager-values.yaml --wait
kubectl -n lab-net apply -f issuer-demo.yaml -f certificate-demo.yaml
kubectl -n lab-net get certificate,certificaterequest
kubectl -n lab-net wait --for=condition=Ready certificate/demo-tls --timeout=120s
openssl s_client -connect "$LAB_GATEWAY_VIP:443" -servername "$LAB_HOST" \
  -CAfile "$LAB_CA_FILE" -verify_return_error </dev/null
curl --cacert "$LAB_CA_FILE" --resolve "$LAB_HOST:443:$LAB_GATEWAY_VIP" "https://$LAB_HOST/"
cmctl renew demo-tls -n lab-net                   # 对实验叶证书测试续期
```

cert-manager CRD 的安装开关按锁定 Chart 确认；Issuer 仅引用受限签发身份。根 CA 私钥不放到集群中。

### 配置示例

`lab-issuer` 已经配置为受限内部签发端，Certificate 生成的 Secret 由 Gateway HTTPS listener 引用：

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata: {name: demo-tls, namespace: lab-net}
spec:
  secretName: demo-tls
  dnsNames: [demo.svc.internal.egon.top]
  issuerRef:
    kind: Issuer
    name: lab-issuer
```

### 预期结果

Certificate Ready，TLS SAN/链/有效期正确，客户端不跳过校验即可访问。续期后 Secret 和实际返回证书更新；错误 SAN、未知 CA 和过期叶证书应被客户端拒绝。公网 ACME 单独使用白名单域名和受限 DNS 身份。

交付：`ops/02-networking/networking/certificates/`；TLS 正反用例与续期结果。

检查与失败处理：客户端无需跳过校验，续期后服务可用；失败恢复原可用叶证书和 Route，不公开根密钥。

<a id="02-06"></a>

## 02.06 网络策略与出口治理

输入：Hubble、确定的 DNS/仓库/数据库依赖清单。

1. 先为实验 Namespace 建 default-deny，再逐项允许 DNS、入口、依赖服务；分别执行应允许和应拒绝的请求。
2. 用相同流量对比标准 NetworkPolicy 与 Cilium 策略的 L3/L4/FQDN/适用 L7；保留 Flow 与源身份，检查 Ceph/仓库实际可见源。
3. 隔离测试 Egress Gateway→OpenWrt 的出口节点/地址和回程路由；断 VPN 时验证受限出口停止、LAN 保持，记录出口节点故障后的会话变化。

### 操作命令与目的

```bash
kubectl -n lab-net apply -f default-deny.yaml
kubectl -n lab-net exec "$LAB_CLIENT_POD" -- curl --max-time 5 http://echo:8080/
kubectl -n lab-net apply -f allow-dns.yaml -f allow-echo.yaml
kubectl -n lab-net exec "$LAB_CLIENT_POD" -- nslookup echo.lab-net.svc.cluster.local
kubectl -n lab-net exec "$LAB_CLIENT_POD" -- curl --max-time 5 http://echo:8080/
hubble observe --namespace lab-net --verdict DROPPED --last 20
kubectl apply -f cilium-egress-demo.yaml          # 独立的出口策略实验
```

Egress Gateway 实验再配合出口节点的 `ip rule`、`ip route show table <实验路由表>`、OpenWrt 的路由/防火墙检查；请求自有的出口回显服务，比较源 IP。断隧道与恢复使用 00 已验证流程。

### 配置示例

默认拒绝策略；DNS、echo 服务及实际依赖使用另一个允许策略文件，不在主业务 Namespace 直接试验：

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: default-deny, namespace: lab-net}
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
```

允许 DNS 的 egress 片段；同一 peer 内同时匹配 kube-system 和 DNS Pod：

```yaml
egress:
  - to:
      - namespaceSelector:
          matchLabels: {kubernetes.io/metadata.name: kube-system}
        podSelector:
          matchLabels: {k8s-app: kube-dns}
    ports:
      - {protocol: UDP, port: 53}
      - {protocol: TCP, port: 53}
```

### 预期结果

施加默认拒绝后请求失败，添加最小允许规则后仅指定通路恢复；Hubble 给出允许/拒绝证据。VPN 断开时受限出口停止，LAN/DNS/仓库保持可达。Cilium 扩展策略只在确认当前模式支持后启用。

交付：`ops/02-networking/networking/policies/`、`egress/`；双向允许/拒绝和断链结果。

检查与失败处理：策略控制实际流量且不切断 DNS/恢复通道；失败回退本次策略版本，不删全体 NetworkPolicy。

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
