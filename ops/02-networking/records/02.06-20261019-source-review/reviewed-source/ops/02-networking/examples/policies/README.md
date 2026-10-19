# 完整 02.06：网络隔离、策略对照与出站路径

在管理 Mac 一次运行下面三行。Ansible 内部顺序处理 02.06.01–04，无须分节启动。正式集群运行由操作者启动。

~~~bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
export LAB_POLICY_RECORDS="$PWD/ops/02-networking/records/02.06-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/policies.sh all "$LAB_POLICY_RECORDS"
~~~

| 命令 | 作用、执行位置及预期 |
| --- | --- |
| cd | 管理 Mac 进入本仓库，后面的相对入口可直接解析 |
| export LAB_POLICY_RECORDS | 绑定全新 UTC 批次目录；所有原始记录、失败和清理回执存入该目录；不复用已经执行或关闭的目录 |
| bash policies.sh all | 锁定同一网络批次；前检、全部 YAML 预览、八个 Pod、两组策略对比、实际出站源地址、代理故障与恢复、汇总、清理一次完成；无需口令或额外手工 kubectl |

正常预期：AVAILABLE CASES PASS、CLEANUP PASS，PLAY RECAP 的 failed/unreachable/rescued/ignored 均为 0。**这不表示完整 02.06 全通过**：02.06.03 的 Ceph 服务与 02.06.04 的 Egress Gateway 联动仍有前提缺口，回执保留 passed=false、phase_complete=false。

## 前置条件与可执行边界

- [02.05 原始交接](../../records/completed/02.05.json)的内部验收、清理回执、run、集群 UID 和 SHA256 全部匹配；公网 BLOCKED 允许继续内部实验。
- 原十台 VM .101–.110 Ready；只使用 VM hostname，不读取或使用 ESXi 放置。Cilium 1.20.2 VXLAN、保留 kube-proxy，Cilium/Envoy/kube-proxy 10/10，CoreDNS 2/2；Hubble mTLS Relay 连通十个节点，L7 代理已经启用。
- worker01/02、storage01/02/03 保持 SELinux Enforcing、firewalld/chronyd 活跃、时间同步；不修改 VM 的路由、防火墙或代理服务。
- Harbor .12 与现有 OpenWrt .10:7890 可用；外网探测复用 00.06.02 的 https://www.google.com/generate_204，需可信 TLS + 204。公网入站能力与这个出站前提无关。
- Mac 已有 kubectl、Ansible venv、Go 1.27.2、crane、SSH 密钥和 OpenWrt SSH 别名；均复用既有工具，不安装新依赖。
- 三个专用 Namespace lab-policy、lab-policy-peer、lab-egress 不能被其他批次占用。标准库 Go 诊断镜像已经推送 Harbor 并锁定摘要；公开 CA bundle 保存在版本锁指定的本地 seed 路径。

本轮只新增这三个空间及其中对象；不向 kube-system 或既有业务空间下发默认拒绝，不修改主 .201 入口或既有自动签发器。入口/监控使用有明确身份标签的模拟 Pod；既有入口的授权不能直接照抄这组教学标签。

## 一次执行的全部实验

| 步骤 | 实际操作 | 通过证据与预期 |
| --- | --- | --- |
| 前检 | 原集群和 02.05 交接；只读 SSH/路由/服务状态；确定性重建镜像并查 Harbor 摘要；全部 YAML strict server dry-run | YAML、CRD、准入、工具、VM、代理前提一次校验；dry-run 不落地。每个实际目标空间仍在 apply 前再次预览 |
| 02.06.01 初始拒绝 | 三空间先建立双向 default-deny，再创建八 Pod；等待 Ready、实际镜像、身份及双向策略收敛 | client→api HTTP 与 client→DNS 都被策略拒绝；超时和 POLICY_DENIED 流量必须同时存在 |
| 标准 NetworkPolicy | 放行 UDP/TCP DNS、client→api/dependency、入口→api:8080、monitor→api:9090 | Service DNS/IP、Pod IP、依赖、入口、监控成功；陌生入口、错误端口、越权依赖失败；相同的 /blocked 与 POST 请求仍成功，展示标准 L3/L4 边界 |
| 02.06.02 Cilium 对照 | 删除标准“允许”策略，始终保留默认拒绝，再应用 CNP | 同一批原 Pod/UID 对照。GET /allowed 成功，GET /blocked 和 POST /allowed 返回代理 403；FQDN 允许 Harbor，Nexus DNS 返回 REFUSED、Nexus IP 和 Harbor 错误端口被拒绝 |
| 02.06.03 内网与出站 | egress Pod 直连可信 Harbor /v2/，无凭据 TCP 握手 storage01/02/03:10250，经显式代理访问外网；禁止公网直连与 API:6443 | Harbor 401 是未携带仓库登录的正常认证响应；存储 VM TCP 成功；代理 TLS 204；直连拒绝有 Hubble 证据 |
| 实际源与回程 | Harbor 的 ens33、三个存储 VM 的 any 抓取有界 TCP SYN；代理使用 worker01 ens33 出站 SYN；与本次 Pod socket 端口关联 | 记录 Pod IP、实际源、是否 SNAT、接口及真实源回程 ip route get；内网目标和 .10 的 VM 路由必须为 ens33 直连；存储 VM 的 any 同时覆盖隧道解封后流量，不假设 PodCIDR 回程或固定 SNAT |
| 代理入口不可达 | 仅给 egress Pod 增加到 .10:7890 的拒绝，再移除 | 外网访问失败、没有公网直连后路；Harbor 与三个存储 VM 继续；撤销后代理重新返回 204。不会停止 mihomo 或真实 VPN |
| 02.06.04 能力门禁 | 校验当前 Cilium 配置；官方 1.20.2 CRD 自身服务端预览，参考 CR 按锁定 schema 校验，不安装 CRD | 缺少 kube-proxy replacement/BPF masquerade/Egress Gateway 使能，当前也无该 CRD；实例准入、运行和故障项均 BLOCKED |
| 汇总与清理 | 校验本批策略 UID/spec、全部行为结果和来源输入；成功或失败均 always 清理 | 按本批 Namespace UID 前置条件删除三空间；保护主入口、原 Pod、既有策略、工作负载及网络配置；单独写 closed.json |

共 52 个行为用例，每项要求连续三次符合预期；另有 5 组实际 SYN/socket/回程证据。未收敛的早期样本同样保留。端口关闭、证书错误、NXDOMAIN、kubectl/探测器自身故障不能冒充策略拒绝。Hubble 空白或丢失事件也会失败。

remote-node:10250 规则按 Cilium 身份匹配所有远端 Kubernetes 节点，只用于无凭据 TCP 握手；它不授予 kubelet API 权限，也不是限定为三个 IP 的规则。普通 ipBlock 不一定匹配集群节点身份，不能将其写成假定生效的节点 CIDR 白名单。

显式代理的网络策略约束的是 .10:7890；CONNECT 内目标由现有 OpenWrt 策略决定。本轮只验证上表目标，不宣称具备每应用独立代理域名 ACL，也不以 204 推断公网源 IP 或 VPN 节点身份。

## Ceph 与 Egress Gateway 为什么保留 BLOCKED

Ceph 安装与服务验收在 Phase03。这里记录三个存储 VM 上 3300/6789 的监听状态，验证既有 10250 TCP、真实源和回程；这些证据不等于 Ceph MON/OSD/认证/客户端成功。02.06.03 因此记 PARTIAL_CEPH_BLOCKED。

[Cilium 1.20.2 原版说明](https://github.com/cilium/cilium/blob/v1.20.2/Documentation/network/egress-gateway/egress-gateway.rst)要求 Egress Gateway 同时启用 BPF masquerading 与 kube-proxy replacement。当前主集群保留 kube-proxy；本轮不自动 Helm 升级、重启 Cilium、切换默认网关或操作真实 VPN。

[参考 CR](../../networking/policies/egress-gateway-reference.yaml)限定 lab-egress/role=egress，目标公网 CIDR 排除私网，后续可选 worker02 已有 .110 作为源。当前没有该 CRD，只按 SHA256 锁定的官方 1.20.2 schema 校验参考实例结构；CRD 自身做 server dry-run，实例 CEL/服务端准入保留 BLOCKED，不安装 CRD。**单独应用该 CR 不会启用功能，也不会建立 VPN。** 后续须先完成独立 CNI 迁移审阅、接口/源地址/路由与 OpenWrt 防火墙回程准备，再验证指定出口、真实 VPN 中断、出口 VM 故障和已有会话变化；本次全部列在 BLOCKED 中，不以代理入口故障替代。

## 全部文件与职责

| 文件 | 职责 |
| --- | --- |
| [统一脚本](../../scripts/policies.sh)、[带锁入口](../../tests/integration/policies/entry.py) | 参数与路径约束、完整日志、共享网络批次锁、拒绝覆盖旧批次；不读取口令 |
| [总剧本](../../ansible/playbooks/policies.yml)、[前检](../../ansible/playbooks/policies-prepare.yml)、[整组执行](../../ansible/playbooks/policies-run.yml)、[变量](../../ansible/vars/policies.yml) | 一次完成所有步骤；block/always 负责异常回收 |
| [逐份应用](../../ansible/tasks/policies-apply.yml)、[逐对象边界/预览/应用/记录](../../ansible/tasks/policies-document.yml) | 模板→JSON→原集群与 UID 检查→server dry-run→apply→UID 回执；不接管外来对象 |
| [收敛](../../ansible/tasks/policies-ready.yml)、[观察](../../ansible/tasks/policies-observe.yml)、[移除](../../ansible/tasks/policies-remove.yml)、[清理](../../ansible/tasks/policies-cleanup.yml) | 原 Pod/镜像/Cilium 双向策略版本；行为及 Hubble；DeleteOptions UID 原子前置条件；清理后复核 |
| [Namespace](../../networking/policies/namespaces.yaml.j2)、[default-deny](../../networking/policies/default-deny.yaml.j2)、[工作负载/公开根/Service](../../networking/policies/workloads.yaml.j2) | restricted、无 ServiceAccount token、无特权/主机挂载、固定 VM、资源上限、Ready 探针；公开根用于验证 Harbor |
| [标准策略](../../networking/policies/standard.yaml.j2)、[Cilium 策略](../../networking/policies/cilium.yaml.j2) | DNS/入口/依赖/监控；相同 Pod 上完成 L3/L4、身份、FQDN、HTTP 对照 |
| [内网与代理](../../networking/policies/egress.yaml.j2)、[代理故障](../../networking/policies/proxy-unreachable.yaml.j2)、[能力边界](../../networking/policies/capabilities.yaml) | 只允许必要地址/端口；故障只作用于本批 Pod；保留能力缺口 |
| [验收器](../../tests/integration/policies/check.py)、[物料](../../tests/integration/policies/materials.py)、[Python 回归](../../tests/integration/policies/test_check.py)、[离线 Ansible 演练](../../tests/integration/policies/offline.py) | 只读前检与断言；Hubble/有界 SYN；确定性镜像；故障与恢复流程核验 |
| [Go 服务/探测器](main.go)、[Go 测试](main_test.go)、[go.mod](go.mod) | 回显 UID/nonce；原始 DNS RCODE；可信 TLS/显式 CONNECT；新连接、有界超时；仅标准库 |

剧本执行的每类命令及预期：

- kubectl get/config view/get --raw=/readyz：只读确认集群、原身份、健康、策略、Pod 与公开配置；不导出 Secret 或 kubeconfig。
- ssh 中的 hostname/getenforce/systemctl/timedatectl/ip/ss/command -v：只读核对 VM、直连、时间、监听器及工具；OpenWrt 只检查进程与 LAN 路由，不读取订阅/代理配置。
- go build 与 crane digest：本机重建锁定的 Linux/amd64 镜像，核对来源、公开 CA、二进制与 Harbor 摘要；正式入口不推送新镜像。
- kubectl apply --dry-run=server --validate=strict：全部实际执行清单服务端预览；前检用已有 restricted 的 lab-core，不创建测试空间；另预览官方出口 CRD 自身。未安装 CRD 的参考实例只做锁定 schema 结构校验，准入仍为 BLOCKED。
- kubectl apply --validate=strict ... -o json：应用已经校验、有创建意图的本批对象，记录实际 UID；写入由 Ansible 负责。
- kubectl exec cilium-dbg endpoint list 与 kubectl get ciliumendpoint：只读观察身份、policy-enabled=both 与 spec/realized 版本收敛，不修改 agent。
- kubectl exec -i /policy-lab probe：固定目标单次 nonce 请求，保留结果；预期网络失败与探测命令失败区分。
- kubectl exec hubble status/observe：读取既有 Relay，验证 10/10、双向流量、身份、POLICY_DENIED/DNS REFUSED/HTTP403；保留 JSONL。
- ssh timeout 8 tcpdump：仅限定源/目标/端口的 SYN 元信息，无 -A/-X/-w，不抓取正文；最多 8 秒退出。随后 ip -j route get 记录真实源回程。
- kubectl delete --raw ... -f DeleteOptions.json：API 原子校验原 UID 后删除；kubectl wait --for=delete 等待清理。外来对象、Secret 或 UID 漂移会停止删除并保留证据。

## 失败恢复与证据

正常模式自动清理；中断或清理失败时，保持终端打印的**原证据目录**：

~~~bash
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/02-networking/scripts/policies.sh recover "$LAB_POLICY_RECORDS"
~~~

该命令按原 context/Namespace UID 清理并复核基线，不重新运行故障，不启动代理，不修改真实 VM 路由。恢复后选择全新目录运行 all。

仅复核物料时，可用全新目录执行 validate；只做前检、重建/摘要检查、模板与 dry-run，不部署 Pod 或策略。正常首次运行直接 all，无需先单独 validate。

批次保留完整 ansible-all-* 日志、context.json、state/source.json、state/protected.json、逐对象意图/UID、attempts 中的原始请求/Hubble/SYN/回程、passed.json 和 state/closed.json。passed.json 沿用既有文件命名，必须读取 available_cases_passed 与各步骤状态，不能凭文件存在或 failed=0 宣称阶段完成。
