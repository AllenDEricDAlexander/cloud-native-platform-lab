# 02.02 Service 与 DNS 整组验证

状态：整组正式执行和清理通过，见[实际归档与 02.03 交接](../../records/02.02-20261018T225144Z/README.md)。以下为原执行说明；执行时源码另存归档 `execution-source/`。

02.02.01 已于 `02.02.01-fixed-20261018T152113Z` 完整执行并清理，五个状态、150 次 HTTP 请求均通过，见[原始验收归档](../../records/02.02.01-fixed-20261018T152113Z/README.md)。本入口校验其回执摘要和集群 UID，将它作为整组第一项的证据；一次执行全部剩余 02.02.02–06。

## 一次执行的完整命令

在管理 Mac 的终端执行下面三条。每次新验收使用新记录目录；不要复用已通过或已关闭的批次。

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
export LAB_SERVICES_RECORDS="$PWD/ops/02-networking/records/02.02-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/services.sh all "$LAB_SERVICES_RECORDS"
```

| 命令 | 作用 | 预期结果 |
| --- | --- | --- |
| `cd ...` | 切换到核验过的仓库 | 当前目录为仓库根目录 |
| `export LAB_SERVICES_RECORDS=...` | 为整组分配唯一证据目录 | 环境变量指向 `records/02.02-<UTC 时间>` |
| `bash .../services.sh all ...` | 统一前检、生成和准入全部 YAML，再依次运行五个专题、汇总验收及清理 | `SOURCE VALIDATION PASS`、`02.02.02` 至 `02.02.06 PASS`、`CLEANUP PASS`、`02.02 ALL PASS`；recap 各主机 `failed=0 unreachable=0` |

不需要逐项运行 kubectl、拷贝镜像或手动改端口。预计数分钟；首次安装控制器和拉取镜像可能较慢。Ansible 输出中的 HTTPS 别名证书不匹配、Local 无本地端点访问不通、DNS 的 NXDOMAIN 都由脚本作为明确的预期断言处理，不应产生 Ansible failed。

## 前置条件与变更边界

前检逐一核对：原集群 UID、API VIP `.100`、`.101–.110` 十台 VM 的 IP/版本/Ready/污点、Cilium/kube-proxy/CoreDNS/Hubble 健康、已归档 02.02.01 的原始通过与清理回执、管理 Mac `.200`、两台 worker 的 SSH/Enforcing/firewalld/public 区域、内网 Harbor TLS、四个完整镜像摘要、Chart SHA256、候选 VIP 的 ARP 冲突、Cilium L2/地址池是否冲突、kube-proxy 模式兼容性，以及全部配置准入。

只感知 VM，不依赖 ESXi 或物理宿主机标签。测试 VIP `192.168.9.202/32` 属于既有 `.201–.210` 主方案范围；测试池 `autoAssign: false`，Service 显式申请地址。`.201` 和 API `.100` 不作测试。诊断镜像及 MetalLB 镜像已按 linux/amd64 摘要准备在现有 Harbor，使用 `IfNotPresent`，不会要求节点用公网仓库。

| 配置/资源 | 作用和预期结果 | 生命周期 |
| --- | --- | --- |
| `lab-services` Namespace | restricted PSA；两个 echo 后端固定在 worker02，两台 worker 各有一个诊断客户端；所有 HTTP 回包核对 Pod UID | 整批清理 |
| `nodeport-cluster` / `nodeport-local` | API 自动分配 NodePort；仅对管理 Mac `/32` 添加精确端口规则；两台 VM 原运行/永久规则分别记录与恢复 | 临时；该专题 `always` 恢复防火墙 |
| `metallb-system`、`cnpl-metallb` release | MetalLB 0.16.1 controller + 两个 worker speaker，仅 L2，关闭 FRR/frrk8s；Namespace 需 privileged PSA 才能准入 hostNetwork/NET_RAW 的 speaker | 保留供 02.03；不等于 02.03 故障漂移已通过 |
| worker 的 7946 TCP/UDP 规则 | 仅来源 `k8s-nodes` ipset 的 speaker 成员通信，保留原始回执 | 随保留的 MetalLB 保留 |
| `cnpl-services-test` IPAddressPool / L2Advertisement | 仅 `.202/32`、ens33、两个 worker；先安装匹配 CRD/Webhook，再逐对象严格准入 | 整批清理 |
| 两个依次创建的 LoadBalancer Service | 无 NodePort，来源限制为管理 Mac `/32`；同 VIP 在不同 Service UID 间回收再分配 | 测试后立即删除 |
| CoreDNS/Cilium/kube-proxy、Headlamp/Hubble UI | 读取原 UID/spec/关键配置摘要，整组通过和清理时再次对比 | 保持原配置 |

主机 SELinux 和 firewalld 始终开启。保留 MetalLB 后，后续 02.03 直接接续地址池管理与故障漂移；本批不进行节点停机、不切换 CNI、不改 API kube-vip。

## 剧本、YAML 与每项预期

总入口为 [services.sh](../../scripts/services.sh) → [services.yml](../../ansible/playbooks/services.yml)。沿用现有 inventory、SSH、管理端 Python 和 kubeconfig。没有额外框架或依赖；检查器沿用已有标准库 Go 探测程序并加入 Host/UID 和 CNAME 观测。

| 专题和独立剧本 | 完整 YAML / 检查项 | 预期结果 |
| --- | --- | --- |
| [统一准备](../../ansible/playbooks/services-prepare.yml) | [suite-fixtures.yaml.j2](../../networking/services/suite-fixtures.yaml.j2)、[MetalLB values](../../networking/metallb/values.yaml)、[Namespace](../../networking/metallb/namespace.yaml.j2) | 基础应用和 MetalLB 的配置、镜像、资源范围全部统一核验；前检失败即停止变更 |
| [02.02.02 NodePort](../../ansible/playbooks/services-nodeport.yml) | [nodeport.yaml.j2](../../networking/services/nodeport.yaml.j2)；Cluster、Local、源 IP、ClientIP affinity | Mac→worker01 Cluster 成功并跨节点 SNAT；Mac→worker02 Local 成功且保留源 IP；worker01 Local 无本地后端而拒绝；同一 Mac 十次新连接绑定同一 UID；原防火墙恢复 |
| [02.02.03 LoadBalancer](../../ansible/playbooks/services-loadbalancer.yml) | [test-pool.yaml.j2](../../networking/metallb/test-pool.yaml.j2)、[loadbalancer.yaml.j2](../../networking/services/loadbalancer.yaml.j2) | MetalLB controller 1/1、speaker 2/2；Mac 实际 HTTP200 + 当前 Pod UID + ARP 邻居；删除后另一 Service 获得相同 VIP 并仍能访问 |
| [02.02.04 Headless/手工端点](../../ansible/playbooks/services-discovery.yml) | [discovery.yaml.j2](../../networking/services/discovery.yaml.j2)、[manual-endpoints.yaml.j2](../../networking/services/manual-endpoints.yaml.j2) | Headless UDP/TCP DNS 返回两 Pod IP；无 selector Service 保有 ClusterIP，通过手工 Slice 访问所选的真实 Pod UID |
| [02.02.05 ExternalName](../../ansible/playbooks/services-externalname.yml) | discovery 中两个 ExternalName；CNAME、HTTP Host、TLS SNI | 别名解析为目标；HTTP Host 保留别名；原 Harbor 名称的可信 HTTPS 成功，别名因证书主机名不匹配被准确识别 |
| [02.02.06 DNS](../../ansible/playbooks/services-dns.yml) | [late-service.yaml.j2](../../networking/services/late-service.yaml.j2)、现有 CoreDNS 的只读观测 | cluster.local、短名、搜索域、内网域、外网域均可用；固定同一 CoreDNS Pod 观测正/负缓存命中计数增加、延迟记录；创建此前 NXDOMAIN 的 Service 后恢复解析并成功 HTTP |
| [整组验收与清理](../../ansible/playbooks/services-finish.yml) | 全部专题回执、现有工作负载摘要、防火墙原始回执 | 必须所有专题真实通过；临时对象清空、集群健康、原控制台和配置未变 |

完整生成 YAML 保存在 `attempts/<本次身份>/`。预览手工 EndpointSlice 使用示例 UID/IP，仅用于 dry-run；实际执行前会从当前 API 重取 Service/Pod UID/IP，重新渲染、严格准入并保存创建回执，预览值不会部署。NodePort 由 API 分配，脚本随后读取实际值；不占用 Headlamp/Hubble UI 已有端口。

现有 CoreDNS 对 `cluster.local` 禁用了正负缓存。因此缓存命中实验直接向同一 CoreDNS Pod 查询外网 A 记录和唯一 `.invalid` 名称，并比较其 Prometheus 成功/拒绝缓存计数；另用集群 Service 的 NXDOMAIN→创建→恢复观测 Kubernetes 记录变化。不会为了实验改变 CoreDNS 配置。NodeLocal DNSCache 是计划中的可选对照，本批不部署。

## 证据、清理和恢复命令

每次入口生成独立 Ansible 日志与 `attempts/`，保留生成 YAML、dry-run、原始 HTTP/DNS 结果、轮询快照和后端 UID。`state/source.json`/`protected.json` 首次绑定后不覆盖；脚本变更后不允许对旧的未清理批次继续正式运行。通过后生成 `passed.json`，清理成功生成 `state/closed.json`；只有两者结合才代表本批完整结束。归档时保留原始失败和成功证据，不将未执行项记为通过。

下面是替代或恢复入口，正常验收只需要前述 `all`：

| 命令 | 作用 | 预期结果 |
| --- | --- | --- |
| `bash ops/02-networking/scripts/services.sh validate "$LAB_SERVICES_RECORDS"` | 只读检查集群/VM、镜像、构建、全部渲染和服务端 dry-run | `SOURCE VALIDATION PASS`；不部署负载、不改防火墙；首次不存在的 MetalLB CR 先本地严格核对，真正准入在运行时 CRD/Webhook 建立后执行 |
| `bash ops/02-networking/scripts/services.sh recover "$LAB_SERVICES_RECORDS"` | 失败后校验原集群/运行标签/UID，恢复临时防火墙并清理本批实验对象 | `CLEANUP PASS`；若控制器安装未完成，保留 MetalLB 并在 closed 回执报告其状态，不能据此声称整组通过 |
| `bash ops/02-networking/scripts/services.sh cleanup "$LAB_SERVICES_RECORDS"` | 与 recover 相同的显式清理，适用于 `run` 模式通过后 | 同上；不自动删除保留的 MetalLB |
| `bash ops/02-networking/scripts/services.sh run "$LAB_SERVICES_RECORDS"` | 完成所有专题验收，保留实验 Namespace 便于观察 | 生成 `passed.json`；之后需要 cleanup；通常直接用 all 即可 |

失败时先保留完整日志；若需要换新版脚本，先对原记录执行 recover，再用新记录运行 all。脚本拒绝删除其他运行的对象或 UID 已被替换的对象。无需重新执行 02.02.01。

依据：[Kubernetes Service](https://kubernetes.io/docs/concepts/services-networking/service/)、[MetalLB 安装](https://metallb.io/installation/)、[L2 配置](https://metallb.io/configuration/_advanced_l2_configuration/)、[CoreDNS cache](https://coredns.io/plugins/cache/)。
