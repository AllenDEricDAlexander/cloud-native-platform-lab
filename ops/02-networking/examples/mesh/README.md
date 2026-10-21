# 02.10 完整 Istio 与 SPIFFE/SPIRE VM 实验

02.09 的真实 VM 整组验收、自动回退和清理已通过，见[正式归档](../../records/02.09-20261021T122923Z-agent-final/README.md)，提交 `7b5dbf7`。本专题使用现有 `.101–.110` 主集群；Mac 只运行 Ansible、kubectl、Helm、Go 和 crane。正式入口覆盖 02.10.01–05，共 24 步，不必逐节启动。当前交付的是脚本与执行前核验，正式运行结果由 all 的真实回执判定。

## 一次执行全部实验

在管理 Mac 的终端执行完整三行：

~~~bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
export LAB_MESH_RECORDS="$PWD/ops/02-networking/records/02.10-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/mesh.sh all "$LAB_MESH_RECORDS"
~~~

| 命令 | 作用 | 预期结果 |
| --- | --- | --- |
| `cd …` | 进入现有仓库 | 后续脚本和证据都使用该仓库路径 |
| `export LAB_MESH_RECORDS=…` | 绑定全新 UTC 时间戳批次目录 | 不覆盖既有成功、失败和恢复记录；不要复用旧目录 all |
| `bash …/mesh.sh all …` | 自动完成前置检查、离线物料传输、Cilium 兼容配置、24 步实验、恢复和汇总 | 可运行用例全部通过，清理通过，`failed/unreachable/rescued/ignored=0`；未完成项单列 BLOCKED |

无需输入 CA 口令或准备新凭据。Istio 和 SPIRE 分别生成仅供本批使用的临时根信任，原根/中间 CA 私钥不上传。每条集群或主机写命令由 Ansible 执行并保留输出；意外失败停止后续实验，进入恢复流程，末尾打印首个失败、原因、原日志及恢复入口。

## 前置条件与改动边界

- 自动读取 02.09 的通过及清理回执，校验同一 cluster UID/run 并记录原始摘要；允许外部 BGP 转发仍为 BLOCKED。十节点、Cilium、kube-proxy、CoreDNS、Operator 和主 `.201` 可信 TLS 必须健康。
- 核对所有 Node UID、现有 Cilium Helm release/原值/原 manifest/ConfigMap、控制器 UID/spec、VM 路由、安全和防火墙；两个 Worker 还检查 2Gi 可用内存、缓存/解包磁盘余量、CNI 文件和 Istiod 端口占用、kubelet 服务证书。
- 保留 `kubeProxyReplacement=false`、VXLAN、cluster-pool IPAM 和 `bpf.masquerade=false`；临时设置 `cni.exclusive=false`、`socketLB.hostNamespaceOnly=true` 和 Operator 配置滚动。恢复使用捕获的原 Helm 内容，不假定 revision 数字保持不变。
- Istio 1.31.2 的 CNI、ztunnel 和 SPIRE 1.15.4 agent 只在 worker01/02 运行。应用服务端在 worker01、客户端在 worker02，真实跨 VM。waypoint 也限定到 Worker。8 个 amd64 镜像在本地核验后，通过 Ansible 导入 VM 原 containerd，应用 `imagePullPolicy=Never`，正式执行不依赖拉取公网镜像。
- Istiod 在 worker01 使用 hostNetwork，避免 Cilium Overlay 下 API server 到准入端点的路径问题；只临时允许三台控制节点到其 15017，以及 Pod 网段/两个 Worker 到 15012。规则有有效期且总在恢复流程撤销，不改永久规则，不关闭防火墙或 SELinux。
- 六个临时 Namespace 为 `istio-system`、`spire-system`、`lab-mesh-plain`、`lab-mesh-sidecar`、`lab-mesh-ambient`、`lab-spire`，必须事先不存在。既有 Istio CRD 或同名全局对象会阻止执行，不能接管已有网格。现有 Gateway API CRD 复用；新 Istio CRD 用 server-side apply，避免 last-applied 注解上限。
- Istio 发现范围与注入 Webhook 限定到本批 run 标签；不更改既有 Namespace 的接入标签。Sidecar、Ambient 和裸应用使用不同 Namespace；Istiod 不创建默认 GatewayClass，只使用本批明确创建的 `istio-waypoint`。
- SPIRE socket 使用包含 run 的专属主机目录。agent 使用 PSAT 证明 Worker 身份，kubelet TLS 校验开启；node/proxy 权限限制到两个 Worker，Pod 查询限制在本批服务空间。工作负载通过精确 Namespace+SA selector 取得身份。Privileged/hostPID/socket 权限随实验资源回收，主机保持 Enforcing。

Cilium 兼容设置依据[锁定版本的集成说明](https://raw.githubusercontent.com/cilium/cilium/v1.20.2/Documentation/network/servicemesh/istio.rst)与[Istio Ambient 平台前置](https://istio.io/latest/docs/ambient/install/platform-prerequisites/)。SPIRE kubelet 验证依据[1.15.4 workload attestor](https://github.com/spiffe/spire/blob/v1.15.4/doc/plugin_agent_workloadattestor_k8s.md)。

## 整组过程与实际断言

| 专题/步骤 | 作用与预期证据 |
| --- | --- |
| 前置、物料、临时入口、兼容配置、Istio CRD/组件 | 同一 VM 身份、主 TLS 与原状态快照；镜像 SHA/config/平台一致，CNI/ztunnel 各 2/2，Istiod 就绪 |
| 02.10.01 applications/baseline | Sidecar 实际注入，Ambient 无 Sidecar，裸应用无代理；探针 Ready，服务端/客户端跨 VM；10 个 nonce/后端 UID 对应的裸请求与 CRI 资源计数 |
| 02.10.03 sidecar-policy/traffic | STRICT mTLS；允许指定 SA、拒绝另一 SA 的 403/RBAC；拒绝裸明文，并有恢复后正向对照；mutual_tls 指标和证书公开元数据；故障 503 的实际后端次数必须为 3，300ms 超时配置必须产生有界 504 |
| 02.10.01 sidecar-restart | 按原 UID 删除并重建本批客户端，确认旧 Pod 退出、新 UID、重新注入、Ready 与 mTLS；裸应用仍可通信 |
| 02.10.02 ambient-l4 | 先只验证 ztunnel 的 L4 身份允许/拒绝、真实 mutual_tls 指标、工作负载映射及 10 个实际样本 |
| 02.10.02/03 waypoint/ambient-l7 | waypoint 本代 Programmed、实际 Deployment 归属/Worker 就绪；Service 明确接入后验证允许 GET /allowed、拒绝其他路径和 POST，后端只接受 waypoint 身份 |
| measurements | 保存裸请求、Sidecar、Ambient L4、waypoint 的各 10 个真实串行延迟样本和可取得的 CRI 计数；不外推吞吐或 CPU 利用率结论 |
| 02.10.04 SPIRE server/bundle/agent/register | 两个真实 Worker UID 对应的 PSAT agent；公开 bundle，6 条精确 SA 注册；未注册 SA 不能取得身份 |
| 02.10.04 spire-workloads/rotation | go-spiffe 2.9.0 经 Workload API 取真实 SVID，双向 TLS 校验双方 URI、响应 nonce/UID；60 秒 SVID 观察 serial 变化并再次授权通信 |
| 02.10.04 held/revoke | 旧 SVID 只留进程内存；撤销 allowed 注册后新签发被拒绝，持有旧证书的连接在 NotAfter 后失败；verifier 仍成功。注册撤销不等于已签发证书即时全局吊销 |
| 02.10.05 handoff/恢复 | 保留结果及待办；先退出应用，再停组件、按 UID 卸载本批全局对象、恢复 Cilium、删除专属 socket、撤销临时规则并复验原主线；清理全部通过后才发布 handoff.json |

`available_cases_passed=true` 和 `cleanup_passed=true` 才表示可运行部分完成。完整 Trace/SLO、发布联动、身份联合/网格集成依赖后续适配，本批保持 BLOCKED；其他 Phase02 公网、Ceph、主出口及整 VM 压力缺口进入交接，`phase02_complete=false`。相同 `internal.egon.top` 标识域不代表 Istio 和独立 SPIRE 自动信任对方 CA。

## 全部 Ansible、YAML 与验收实现

| 文件 | 责任 |
| --- | --- |
| [mesh.sh](../../scripts/mesh.sh)、[phase02.sh](../../scripts/phase02.sh) | 整组启动、互斥批次、原始日志、末尾首错与恢复汇总 |
| [mesh.yml](../../ansible/playbooks/mesh.yml)、[公共编排](../../ansible/playbooks/phase02.yml) | prepare/validate、24 步顺序执行与 always 恢复 |
| [mesh-images.yml](../../ansible/playbooks/mesh-images.yml)、[mesh-image.yml](../../ansible/tasks/mesh-image.yml) | VM 身份、传输摘要、同名镜像保护、containerd/CRI 核验 |
| [mesh-cleanup.yml](../../ansible/tasks/mesh-cleanup.yml)、[恢复步骤](../../networking/mesh/restore-cases.yml) | 应用先退、组件后卸、原 Cilium 恢复；回退失败也撤销临时规则 |
| [istio-operator.yaml.j2](../../networking/mesh/istio-operator.yaml.j2)、[istio-namespace.yaml.j2](../../networking/mesh/istio-namespace.yaml.j2) | 固定版本、Worker 约束、CNI/ztunnel、Istiod hostNetwork、注入/发现范围 |
| [workloads.yaml.j2](../../networking/mesh/workloads.yaml.j2)、[sidecar-policy.yaml.j2](../../networking/mesh/sidecar-policy.yaml.j2) | 三种独立应用、SA、Service、STRICT mTLS、授权、超时和重试 |
| [ambient-l4.yaml.j2](../../networking/mesh/ambient-l4.yaml.j2)、[waypoint.yaml.j2](../../networking/mesh/waypoint.yaml.j2)、[ambient-l7.yaml.j2](../../networking/mesh/ambient-l7.yaml.j2) | L4 身份、受控 waypoint、Service L7 与后端身份约束 |
| [spire-server.yaml.j2](../../networking/mesh/spire-server.yaml.j2)、[server HCL](../../networking/mesh/spire-server.conf) | 临时 CA、PSAT、受限 server RBAC、SQLite 空卷 |
| [spire-agent.yaml.j2](../../networking/mesh/spire-agent.yaml.j2)、[agent HCL](../../networking/mesh/spire-agent.conf) | 两 Worker agent、受众限定投射 token、kubelet TLS 与独立 socket |
| [spire-workloads.yaml.j2](../../networking/mesh/spire-workloads.yaml.j2)、[held.yaml.j2](../../networking/mesh/held.yaml.j2) | 精确 SA 身份、双向 TLS、持有旧 SVID 的对照 |
| [cases.yml](../../networking/mesh/cases.yml)、[check.py](../../tests/integration/mesh/check.py)、[observe.py](../../tests/integration/mesh/observe.py) | 24 步计划、所有写操作归属/UID 检查、真实断言及恢复后复验 |
| [materials.py](../../tests/integration/mesh/materials.py)、[身份应用](../mesh-identity/main.go)、[版本锁](../../../versions.lock.yaml) | 无容器引擎构建、平台/归档/config 摘要、短期身份与私钥内存边界 |

底层命令的作用与预期：

- `istioctl manifest generate` 与 `kube-inject`：用同一已锁定安装包渲染清单和非部署注入，检查代理镜像以及无 istio-init 网络初始化。
- `kubectl apply --dry-run=server --validate=strict`：先作完整预览；正式安装时依赖 Namespace/SA/CRD 落地后逐对象再次执行真实准入。预览阶段替换尚不存在的 SA，原引用明确记为准入延期，不冒充已验证。
- `helm upgrade --reuse-values` / `helm rollback`：只更改兼容字段，之后还原原值、manifest 与实际 ConfigMap；不移除 kube-proxy，不换 IPAM。
- VM `ctr images import` / `crictl inspecti`：使用既有 containerd 导入公开镜像，预期实际 config digest 与版本锁一致；同名不同内容拒绝覆盖。公开内容寻址缓存和镜像保留供复跑，不全局 prune。
- `kubectl exec … /phase-lab probe`：请求从真实测试 Pod 发出，预期 nonce、后端 UID、HTTP/网络错误和前后对照都符合用例。
- `kubectl port-forward --address 127.0.0.1`：只在一次读取期间访问本批代理指标，结束关闭进程；预期有对应命名空间的 mutual_tls 计数。
- `spire-server agent list/entry create/entry delete`：确认真实 PSAT Node UID，再注册/撤销精确本批条目；只导出公开 bundle 和证书元数据。
- `/identity-lab call/watch/hold`：实际 Workload API、轮换及 mTLS；输出身份、serial、有效期和结果，不输出私钥。
- UID 前置条件的 `kubectl delete --raw`：只删除本批记录的对象；遇到外来对象、UID 变化或 CRD 中出现外来实例则停止，原失败证据保留。

## 查看结果与恢复

正常结束查看 `passed.json`、`measurements.json`、`state/closed.json`、`postcheck.json`、`handoff.json` 和 `summary-*.json`。只有 all 真正通过才生成通过回执；validate 成功仅表示准备核验通过。

如终端中断或末尾报告清理未通过，使用同一个原批次目录恢复：

~~~bash
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/02-networking/scripts/mesh.sh recover "$LAB_MESH_RECORDS"
~~~

该命令只继续恢复与清理，不重做签发/撤销/故障实验。恢复成功后，如需重跑，重新生成新目录运行完整三行。不要手动删除证据、改 passed.json 或切换 kubeconfig 来绕过检查。
