# 完整 02.03｜MetalLB 主池、故障漂移与地址生命周期

状态：全部三项正式验收及清理通过，见[实际结果与02.04交接](../../records/02.03-20261019T000211Z/README.md)。执行时的原始源码保存在归档execution-source/；以下保留为复现说明。

前序：[02.02 整组验收与清理](../../records/02.02-20261018T225144Z/README.md)已通过，MetalLB 0.16.1 controller1/1、两个 worker speaker2/2 保留。本批直接复用其 UID、锁定镜像和 L2 配置，完成 02.03.01–03，统一校验、执行及清理。无需逐小节运行。

## 一次执行的完整命令

在管理 Mac 执行三条：

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
export LAB_METALLB_RECORDS="$PWD/ops/02-networking/records/02.03-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/metallb.sh all "$LAB_METALLB_RECORDS"
```

| 命令 | 作用 | 预期结果 |
| --- | --- | --- |
| `cd ...` | 进入已核验仓库 | 当前路径为仓库根目录 |
| `export LAB_METALLB_RECORDS=...` | 给完整 02.03 分配唯一证据目录 | 路径为 `records/02.03-<UTC时间>`，不会覆盖旧批次 |
| `bash .../metallb.sh all ...` | 前检全部配置，执行主池、故障与恢复、撤销再分配，汇总及清理 | `SOURCE VALIDATION PASS`、`02.03.01 PASS`、`02.03.02 PASS`、`02.03.03 PASS`、`CLEANUP PASS`、`02.03 ALL PASS`；所有 recap 的 `failed=0 unreachable=0` |

不需要手动挑 speaker、改 IP、删除 Pod、改防火墙或分多次执行。正常预计数分钟，取决于镜像拉取和 speaker 停止/恢复。等待就绪期间的 `FAILED - RETRYING` 表示有界轮询，最终以 PASS 和 recap 为准；无显式申请的 Service 保持 Pending、地址撤销后的 HTTP 超时是需要验证的预期行为，由检查器处理。

## 一次包含的全部剧本和 YAML

| 剧本 | 完整配置与检查 | 作用和预期结果 |
| --- | --- | --- |
| [总入口](../../ansible/playbooks/metallb.yml) / [包装命令](../../scripts/metallb.sh) | 模式及全局批次互斥锁 | 同批完成全部步骤，保留原始日志和独立 attempt |
| [统一准备](../../ansible/playbooks/metallb-prepare.yml) | 全部模板、已有 [MetalLB values](../../networking/metallb/values.yaml)、[变量](../../ansible/vars/metallb.yml) | 核对原十 VM、API UID、02.02 原始回执摘要、controller/speaker UID、镜像、确定性构建、Chart/CRD/Webhook；严格服务端 dry-run 全部 YAML 和两个可能的维护补丁；核对三个 VM 安全状态及十个 VIP 的 ARP 冲突 |
| [主池与真实访问](../../ansible/playbooks/metallb-primary.yml) | [primary-pool.yaml.j2](../../networking/metallb/primary-pool.yaml.j2)、[l2-fixtures.yaml.j2](../../networking/metallb/l2-fixtures.yaml.j2)、[l2-unallocated.yaml.j2](../../networking/metallb/l2-unallocated.yaml.j2)、[l2-service.yaml.j2](../../networking/metallb/l2-service.yaml.j2) | 创建 `.201–.210` 持久主池；不自动分配；两个 VM 各有一后端；显式申请 `.202`，Mac 实际 HTTP200 和 Pod UID、Mac ARP、ServiceL2Status、独立 VM 广播 ARP 的唯一应答者必须一致 |
| [故障、连接观测与恢复](../../ansible/playbooks/metallb-failover.yml) | 根据实际 ARP 入口生成 JSON Patch，按原 UID/spec 保存恢复意图 | 先建立原有 TCP 长连接，再停止当前宣告 VM 上的 speaker；幸存 speaker UID 不变，VIP 进入另一 VM，新连接实际恢复；无论成功失败均恢复完整原始 speaker 配置及两个 Ready 实例 |
| [撤销、再分配与台账](../../ansible/playbooks/metallb-lifecycle.yml) | 同一 Service 模板生成不同名称/UID；[VIP 用途台账](../../../inventory/vips.yaml) | 删除旧 Service 后，分配记录、ServiceL2Status、HTTP 和 ARP 宣告消失；新 Service 使用相同 `.202` 并可达；再次撤销；生成每次 Service UID、用途、时间和撤销记录 |
| [汇总与清理](../../ansible/playbooks/metallb-finish.yml) | 完整必需用例、源码摘要、原有资源 UID/spec、观测进程状态 | 缺项不能通过；测试空间及 VIP 分配清空、观测退出、两个 speaker Ready；主池及宣告保留供 02.04 |

[检查器](../../tests/integration/metallb/check.py)负责校验与精确变更计划；[HTTP/ARP 观测程序](../../tests/integration/metallb/monitor.py)仅发有界请求和读取邻居表。沿用现有 Ansible、Python 标准库/已有 PyYAML 和诊断镜像，不增加依赖、不修改诊断应用。

全部生成 YAML、正向/负向用例、原始流量 JSONL、ARP 输出和补丁位于 `attempts/<本次身份>/`。`state/source.json`、`state/protected.json`、`state/speaker-original.json` 首次写入后不覆盖。

## 故障方法与结果解释

只感知 VM `.101–.110`。候选宣告 VM 固定为 worker01 `.109`、worker02 `.110`，均使用 ens33；infra01 `.104` 仅作为独立 LAN ARP 观察者。不会访问 ESXi/vCenter。

若主池内已有其他业务的 VIP 分配，前检会停止，防止 speaker 故障实验影响现有入口。

故障时临时将 speaker DaemonSet 更新策略切到 `OnDelete`，调度范围收窄到另一 VM。DaemonSet 会停止不再匹配节点的原 speaker；`OnDelete` 保留幸存实例。脚本核对原 speaker Pod UID 已消失、幸存 UID 没变、实际 ARP 和业务入口已改变。结束后只恢复本批修改的 `nodeSelector`/`updateStrategy`，补丁包含 UID 与字段原值测试；并复核整个 spec 回到原值、两个 speaker Ready。该实验验证宣告进程退出与入口接管，不代表 VM 断电、交换机故障或物理故障域验收。

观测分别记录：

- 每次新建 TCP 连接的 HTTP 状态、后端 UID、耗时、实际源端口及当时 ARP 入口。
- 故障前连续复用的同一 TCP 连接及其后续成功、断开和重连；重连会递增 epoch，不能当作原连接继续存活。
- 从维护请求时间到首次观测到另一 VM ARP 入口且 HTTP 成功的时间。至少三个迁移后成功样本才通过；观察上限90秒。

采样请求数和失败数不是网络包丢失率；可能没有观察到失败，也可能原有连接断开，结果按实际记录，不承诺无感切换。恢复两个 speaker 后再次核对业务和独立 VM 的广播 ARP，要求只有一个预期 MAC 应答。

## 主池、地址所有权和保留资源

| 资源 | 规则 | 结束后的状态 |
| --- | --- | --- |
| `metallb-system/cnpl-primary` IPAddressPool | `.201–.210`，`autoAssign:false`；Service 必须有 `cnpl.io/vip-policy: primary`；业务显式声明池和 IP | 保留，UID/spec 登记在 `records/components/metallb-primary.json` |
| 同名 L2Advertisement | 仅该池、ens33、两个 worker；拒绝未核对的其他 L2Advertisement 合并扩大范围 | 保留供后续网关使用 |
| `.201` | 预留给主网关，静态台账登记负责人 `lab-platform` | 本批不分配 |
| `.202` | 本批临时测试 VIP，只允许管理 Mac `/32`；不分配 NodePort | 测试后无 Service 占用、无 ARP 应答 |
| `.203–.210` | 后续业务按同样的显式申请流程登记 | 本批不分配 |
| `.100` / `.211–.220` | API kube-vip / 关闭的对比池 | 不纳入主池 |
| `lab-metallb`、两个 echo 后端 | restricted PSA、非 root、只读根、无 ServiceAccount token，镜像按摘要从现有 Harbor 拉取 | 清理 |
| controller、两个 speaker、已有7946规则 | 复用02.02已验收组件；本批不升级、不改主机防火墙 | 恢复原配置并保留 |
| Headlamp、Hubble UI、Cilium、CoreDNS、kube-proxy | 受 UID/spec/关键配置摘要保护 | 保持原配置 |

地址台账是使用约定，Service label 和地址池选择器用于分配范围控制，不是独立的租户授权系统。网关 `.201` 的正式申请和 DNS 配置在后续步骤实施。

本批直接使用 IP，不创建 DNS 记录；`vip-ledger.json` 的空 DNS 引用只表示本批没有创建 DNS 记录，不声称已经审计整个外部 DNS 区域。后续带域名入口撤销时，流程是先撤销 DNS 引用，再删 Service，核对地址/宣告释放后方可给不同身份使用。

SELinux 始终 Enforcing，firewalld 保持开启。不会重启 VM、停止 kubelet/containerd、改变 Cilium/kube-proxy 或 API `.100`。

## 完成证据与失败恢复

正常 `all` 生成：

- `passed.json`：三个步骤所有必需用例通过，包括故障漂移、原有连接记录与再分配。
- `vip-ledger.json`：Service 名称/UID、用途、分配/撤销时间及最终无活动分配。
- `state/closed.json`：临时 Namespace/VIP 已清理、观测停止、speaker 完整恢复、原有资源配置不变、持久主池保留。

两份通过/清理回执联合判定完整结束；单独 `passed.json` 中的 `cleanup_passed:false` 是清理前快照。执行前核验记录与真实业务验收分开保存，离线替身演练不能替代实际故障结果。

正常只运行前面的 `all`。其他入口完整列出，供只读预检或失败恢复：

| 命令 | 作用 | 预期结果 |
| --- | --- | --- |
| `bash ops/02-networking/scripts/metallb.sh validate "$LAB_METALLB_RECORDS"` | 全部只读前检、镜像/构建、渲染及严格服务端 dry-run；含两种维护补丁 | `SOURCE VALIDATION PASS`；不建立主池、不停止 speaker、不部署负载、不改防火墙 |
| `bash ops/02-networking/scripts/metallb.sh recover "$LAB_METALLB_RECORDS"` | 对原集群和 UID 恢复 speaker、停止原批观测、撤销原批 Service 并清理 Namespace | `CLEANUP PASS`；保留完整主池及控制器；首次创建且只有一半的主池按原 UID 撤回，完整但登记中断的主池补登记；不能据此认为故障验收通过 |
| `bash ops/02-networking/scripts/metallb.sh run "$LAB_METALLB_RECORDS"` | 完成全部三个步骤并恢复 speaker，保留实验空间便于查看 | 写 `passed.json`/`vip-ledger.json`；之后需 cleanup |
| `bash ops/02-networking/scripts/metallb.sh cleanup "$LAB_METALLB_RECORDS"` | 与 recover 相同的显式清理 | 写 `state/closed.json` |

如失败，先保留完整日志。原 UID 或维护字段被其他操作改变时拒绝覆盖；脚本变更后先 recover 旧记录，再给新批次运行 all。不要手动清理原始证据、改标签冒充归属或删除持久地址池。管理 Mac 若被强制退出，观测窗口为210秒且单次 I/O 也设有超时；recover 会先恢复 speaker 并停止属于本批的观测。

依据：[MetalLB L2 行为](https://metallb.io/concepts/layer2/)、[地址池策略](https://metallb.io/configuration/_advanced_ipaddresspool_configuration/)、[L2 选择器及接口](https://metallb.io/configuration/_advanced_l2_configuration/)、[Kubernetes DaemonSet](https://kubernetes.io/docs/concepts/workloads/controllers/daemonset/)。
