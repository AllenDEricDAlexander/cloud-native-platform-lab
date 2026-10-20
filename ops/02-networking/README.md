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

[实际执行归档](records/02.06-20261020T004459Z-agent-r4/README.md)：52 个行为用例、5 组抓包和清理通过，Ansible failed=0；Ceph 与主集群 Egress Gateway 缺口仍保留。该批结束后按要求暂停，后续由用户自行运行；02.07 的实际结果见下一节。

在管理 Mac 一次运行整组：

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
export LAB_POLICY_RECORDS="$PWD/ops/02-networking/records/02.06-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/policies.sh all "$LAB_POLICY_RECORDS"
```

第一行进入仓库，第二行绑定全新证据目录，第三行完成前置、全部配置预览、默认拒绝、标准/Cilium/FQDN/HTTP 对照、Harbor/存储 VM/代理的实际源与回程、实验 Pod 的代理入口不可达与恢复、汇总和清理。无需分节执行或输入口令。只有操作者启动正式部署。

预期 AVAILABLE CASES PASS、CLEANUP PASS、failed/unreachable/rescued/ignored=0。当前模式保留 kube-proxy，02.06.04 Egress Gateway 模式、CRD 和真实 VPN/出口 VM 故障项 BLOCKED；Ceph 服务属于 Phase03，02.06.03 只完成存储 VM 路径验证，记 PARTIAL_CEPH_BLOCKED。passed=false、phase_complete=false，不把实验代理入口故障冒充真实 VPN 故障。

本轮创建三个 restricted 临时 Namespace，并在 worker01 添加本批精确 HTTP/DNS 透明代理即时规则；结束按原 UID 清理空间并撤销规则，核对原即时/永久规则恢复。保持 .101–.110 VM、SELinux/firewalld、原 CNI/路由/代理与主 .201 的可信 TLS。完整指南提供原批 recover 命令与每类底层命令解释。

<a id="02-07"></a>

## 02.07 VM 调度与分布

[完整 Ansible/YAML、逐项作用、预期与恢复](examples/scheduling/README.md)。只使用 VM hostname；包含 Required/Preferred、标签变化、NoSchedule/PreferNoSchedule/NoExecute、Pod 亲和/反亲和和 TopologySpread。每次先核对现有 Pod 的 NoExecute 容忍，结束精确恢复原标签/污点。

[实际执行归档](records/02.07-20261020T132429Z/README.md)：16 项结果全部通过，Ansible failed=0；原节点标签/污点、实验空间清理和既有资源保护基线一致，主 .201 可信 TLS 正常。已生成 [02.08 交接](records/completed/02.07.json)。

```bash
export LAB_SCHEDULING_RECORDS="$PWD/ops/02-networking/records/02.07-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/scheduling.sh all "$LAB_SCHEDULING_RECORDS"
```

第一行绑定新批次，第二行一次完成全部用例、证据与恢复；要求 02.06 已实际运行并清理。预期 passed=true、cleanup_passed=true、failed/unreachable/rescued/ignored=0。

<a id="02-08"></a>

## 02.08 配额、QoS、限流、抢占与 PDB

[完整 Ansible/YAML、作用/预期与恢复](examples/resource-governance/README.md)。三个预算空间、QoS分类、Pod OOM、CPU真实限流、32Mi空卷限额驱逐、只针对本批低优先级 Pod 的抢占、PDB 阻止/允许的标签限定 drain、直接删除对照在同一个入口完成。

[实际执行归档](records/02.08-20261020T133923Z/README.md)：17 项可运行结果和清理通过，Ansible failed=0；五个实验空间、两个 PriorityClass 与维护字段均已回收，主 .201 可信 TLS 正常。整 VM 压力排序保持 BLOCKED，已生成 [02.09 交接](records/completed/02.08.json)。

[02.07 交接后的整组复核](records/02.08-20261020T133203Z-delivery-review/README.md)：29 个对象严格服务端预览、两个架构物料重建与匿名摘要、8 项 Python 测试、Go race/vet，以及 Ansible 正常/故意失败/恢复的四种模型分支通过。正式 all 共 19 步、17 项实际验收，由操作者一次启动；前检不代表实际资源实验通过。

```bash
export LAB_RESOURCE_RECORDS="$PWD/ops/02-networking/records/02.08-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/resource-governance.sh all "$LAB_RESOURCE_RECORDS"
```

第一行绑定新目录，第二行运行全组并恢复 cordon/实验资源。前置为 02.07 已实际通过并清理；两 Worker 内存/文件系统余量预检。整 VM 耗尽与节点压力下的 QoS 驱逐顺序保留 BLOCKED，其余可运行结果单列通过，phase_complete=false。

<a id="02-09"></a>

## 02.09 隔离数据面、L2 与 BGP 对照

[完整 Ansible/YAML、21步作用/预期与恢复](examples/dataplane/README.md)。管理 Mac 上临时kind，固定Kubernetes1.36.4/Cilium1.20.2，实际比较kube-proxy/eBPF与VXLAN/Native，独立Envoy Gateway、L2/ARP/暂停容器故障与FRR BGP前缀宣告/撤回，最后恢复基准并删除本批环境。

[02.08 交接后的整组复核](records/02.09-20261020T135236Z-delivery-review/README.md)：五种 Cilium profile、网关模板、6 个内置对象和5个 CRD预览、9个自定义实例 schema、离线物料摘要、11项 Python测试与四种 Ansible模型分支通过。已修正 FRR公开配置目录权限和 EndpointSlice空值处理；Docker保持停止，正式kind实验由用户启动。

```bash
export DOCKER_CONTEXT=desktop-linux
export LAB_DATAPLANE_RECORDS="$PWD/ops/02-networking/records/02.09-$(date -u +%Y%m%dT%H%M%SZ)"
docker desktop start && bash ops/02-networking/scripts/dataplane.sh all "$LAB_DATAPLANE_RECORDS"
```

当前终端固定 Docker Desktop context、绑定新批次，最后等待Docker启动成功再运行整组；脚本本身不启动它。Docker要求linux/arm64、cgroup v2、至少4CPU/6Gi，建议8Gi。前置为02.08已实际完成与清理。全部物料已锁定并导出离线归档；主十VM、Cilium和.201保持。BGP仅使用专属Docker网络软件邻居，不接家庭路由器。

<a id="02-10"></a>

## 02.10 Istio、SPIFFE/SPIRE 与交接

[全部 Ansible/YAML、21步作用/预期与恢复](examples/mesh/README.md)。另一套临时kind内演练Sidecar、Ambient/waypoint，mTLS精确身份授权、超时/有界重试、SPIRE PSAT注册/真实SVID与轮换、注册撤销和旧证书TTL。独立CA/bundle不自动联合信任。清理后才写正式handoff。

```bash
export LAB_MESH_RECORDS="$PWD/ops/02-networking/records/02.10-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/mesh.sh all "$LAB_MESH_RECORDS"
```

第一行绑定新目录，第二行一次完成身份/网格实验并删除本批环境。前置为02.09实际通过与清理，本机Docker保持运行。主集群Cilium/证书/入口保持；全部私钥仅在隔离环境/进程内，私有kubeconfig不入Git。

## 02.06–10 分步与整批执行

五个专题各有独立all/validate/recover入口，按顺序执行。每个脚本自动查找前一步真实通过及清理回执。[总操作指南](examples/06-10/README.md)提供五条独立命令、作用、预期、失败恢复和可选顺序入口。

```bash
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/02-networking/scripts/run-06-10.sh all
```

可选整批入口调用相同五个独立脚本；意外失败即停止，保留失败专题原目录并打印recover入口。BLOCKED保持单列，不声称完整Phase02已验收。准备阶段未启动Docker/kind或部署本批工作负载；实际数据面由操作者启动all。
