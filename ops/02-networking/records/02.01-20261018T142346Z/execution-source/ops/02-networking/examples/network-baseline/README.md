# 02.01 网络路径与诊断基准

本轮从 Phase 01 的原集群交接开始，范围是 `.101–.110` 十台 VM。用户已明确由 VMware 关注物理放置，本专题不读取、不依赖 ESXi 标签。当前只读前检和源码准入已经执行；正式实验、Hubble 启用和清理待用户运行。

## 前置条件与文件

前检逐项核对原集群 UID、01.03–01.10 的真实通过/清理回执、十节点名称/IP/版本、Ready/压力/调度状态、API、Cilium、Envoy、kube-proxy、CoreDNS、operator，以及每台 VM 的 SELinux、firewalld、CRI、chrony、接口和路由。`chronyc waitsync 1 0.1` 只读确认已同步且剩余时钟修正不超过 100 ms，使按时间匹配 Hubble Flow 有可靠前提。`.15` 管理机实际分发与持久存储未验收，不是管理 Mac 执行本网络专题的依赖。

管理端沿用 `~/.venvs/cnpl-ansible`、`~/.cnpl/bin/`、Go 1.27.2 和 00 的 Ansible inventory/SSH 配置。所有 Kubernetes 命令显式使用 `~/.cnpl-secrets/kubeconfig-lab-primary`，开头同时检查 API 地址和 kube-system UID。本专题需要在 kube-system 调整已有 Cilium Helm release，因此使用原恢复管理员配置，不扩大 Mac 日常身份或 Pod 的权限。

| 文件 | 用途 |
| --- | --- |
| [baseline.yml](../../ansible/playbooks/baseline.yml) | 完整 Ansible 入口，串联前检、校验、物料、实验、清理和回退 |
| [vars/main.yml](../../ansible/vars/main.yml) | 复用工具、原集群身份和两个受控 4244 防火墙规则 |
| [fixtures.yaml.j2](fixtures.yaml.j2) | 完整 Namespace、公开 CA、DaemonSet 和 Service；两个空间共 8 个对象 |
| [deny.yaml.j2](deny.yaml.j2) | 仅作用于 peer 测试 Pod 的拒绝策略 |
| [hubble-values.yaml](../../networking/hubble-values.yaml) | 对现有 Cilium 1.20.2 release 的 Hubble 叠加配置 |
| [hubble-access.yaml](../../networking/hubble-access.yaml) | 仅允许节点实体访问 Relay；不提供公网、LAN、NodePort 或 UI 入口 |
| [main.go](main.go) | 非特权 HTTP/UDP 服务端及有界探测程序，只用 Go 标准库 |
| [check.py](../../tests/integration/network-baseline/check.py) | 版本、交接、OCI 完整性、请求、地址与 Flow 的断言和证据保存 |
| [baseline.sh](../../scripts/baseline.sh) | 管理 Mac 执行入口，固定 inventory、模式与记录目录，保存完整日志 |

诊断镜像按现有项目方式离线构建为 Linux/amd64 静态 OCI 包，再按 SHA-256 导入节点，不需要 Docker、额外依赖或外网镜像拉取。Relay 已按 [版本锁](../../../versions.lock.yaml)下载到管理 Mac 种子目录，逐个核验 manifest/config/layer；原来源名配合完整摘要和 `imagePullPolicy: Never` 使用，节点只取本地已验物料。完整生成 YAML 保存在各次 `attempts/*/fixtures.yaml`、`deny.yaml` 中，没有待手填的镜像或节点占位符。

采用直接的 Ansible 顺序编排和标准库探测，不引入 Strategy 等额外模式：本专题只有固定协议矩阵和三个明确故障场景，额外接口/工厂不会简化这些步骤。

## 02.01.01 理解实际路径

| 流量 | 本轮路径与验证方法 | 信任和代理 |
| --- | --- | --- |
| Mac → API | 内部 DNS → `api.k8s.internal.egon.top` / `.100:6443` → kube-vip → 原控制平面；读 readyz 并核对 UID | 原 kubeconfig CA 与客户端身份；直连内网 |
| Mac → 测试业务 | 临时 `127.0.0.1` 随机端口 → API port-forward → kubelet → 测试 Pod；请求后立即关闭通道 | 沿用 API TLS 和授权；这不代表 LAN 业务 VIP 已验证 |
| 同 VM / 跨 VM Pod | `10.244.0.0/16` 普通 Pod → Cilium；跨 VM 使用 VXLAN `8472/udp` | 沿用 Overlay，不改变 IPAM、CNI 模式或 kube-proxy |
| Pod → Service | CoreDNS `.20.10` 解析 `cluster.local` → `192.168.20.0/24` ClusterIP → 后端 Pod | HTTP 响应回传实际后端和源地址，不把 Service IP 当作 LAN 地址 |
| Pod → Harbor | Pod DNS → 内部 DNS `.11` → `.12:443`；从 Pod 验 TLS，并在该源 VM 的 ens33 上采集五个 SYN 的地址元数据 | 公开内部根 CA；不注入登录凭据、不绕过证书校验；对照 Pod 本地地址与线上节点 SNAT 地址 |
| 节点 → 外网 | 每台 VM 显式使用 `.10:7890` HTTP CONNECT 代理访问 `https://kubernetes.io/` | TLS 保持校验；内网 Harbor/API/DNS 不经过代理；记录默认网关 `.1` 及实际代理连接地址 |
| 后续 Ceph 地址 | `.106–.108` 已进入十 VM 的普通 Pod 通信矩阵 | 没有开放或声称验证尚未安装的 Ceph 守护进程端口 |

`192.168.20.10` 是集群 DNS，`192.168.9.11` 是内部基础 DNS。前者解析 `cluster.local` 并转发企业内网域，不能混用。每个测试 Pod 的 `/etc/resolv.conf`、接口 MTU、Pod 路由与每台 VM 的接口、主机路由都入证据。预计底层 MTU 为 1500、VXLAN Pod MTU 为 1450，以本次实际输出为准。

## 完整执行命令

在管理 Mac 的同一个终端按顺序执行以下命令。无需 SSH 到节点逐条手工改配置，也不需要先 source 日常 kubeconfig。下列命令已给全，本轮操作停在 02.01；`run` 由用户发起。

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
export LAB_NET_RECORDS="$PWD/ops/02-networking/records/02.01-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/baseline.sh preflight "$LAB_NET_RECORDS" &&
bash ops/02-networking/scripts/baseline.sh validate "$LAB_NET_RECORDS" &&
bash ops/02-networking/scripts/baseline.sh run "$LAB_NET_RECORDS" &&
bash ops/02-networking/scripts/baseline.sh cleanup "$LAB_NET_RECORDS"
```

| 命令 | 作用 | 预期结果 |
| --- | --- | --- |
| `cd ...` | 固定仓库根目录，使相对脚本路径有确定含义 | 当前目录为本仓库 |
| `export LAB_NET_RECORDS=...` | 生成 UTC 时间命名的独立证据批次；后续命令共用此路径 | 只设置本终端变量，不改系统环境或 kubeconfig |
| `preflight` | 只读复验 01 交接、集群和十台 VM，并保存本机证据 | 集群前检 PASS、所有主机 failed/unreachable=0；SELinux Enforcing，服务 active，CRI 两项 Ready 为 true，代理 HTTP 200、TLS 校验为 0 |
| `validate` | 再检前置、离线交叉编译、生成 8+1 个完整 YAML，严格服务端 dry-run、原 Chart 摘要与 Helm 4 服务端渲染、Relay 全部 blob 校验 | `02.01 SOURCE VALIDATION PASS`；没有创建测试 Pod、启用 Hubble 或变更防火墙 |
| `run` | 导入两种精确镜像、记录原防火墙/Helm 状态、按来源启用 4244、滚动启用 Hubble、运行测试和三个观测场景 | `02.01 ACCEPTANCE PASS`；`passed.json` 指向成功 attempt；本次按五次样本运行约 1,365 条普通矩阵请求，另有管理端与观测请求 |
| `cleanup` | 核对归属标签、Namespace UID 和空间内没有外来资源，再删除两个测试空间 | `02.01 CLEANUP PASS` 和 `state/closed.json`；两个空间消失，Hubble、受限入口和 4244 保留给后续网络专题 |

`&&` 保证前一命令成功才进入下一条；任一失败都会停止该命令链，并保留现场，不会自动执行后面的 cleanup。每条入口命令遇错即返回非零，`tee` 保存完整输出，包装器的 `pipefail` 不让日志写入成功掩盖 Ansible 失败。Ansible 的 `changed` 包括 Mac 本机创建证据文件，不能据此推断前检改了 VM。每次调用生成独立 attempt，不覆盖前一次输出。

`validate` 的业务对象准入会在既有 `lab-core` restricted 空间进行同规格 dry-run，因为新空间尚未创建；`run` 会先顺序创建实际 Namespace，再逐对象在实际目标空间做 dry-run 和 apply。Helm dry-run 会调用 Kubernetes 的 lookup，但不提交 release；包含私钥的渲染内容由 `no_log` 隐藏，绝不写入公开证据。

## 02.01.02 通信矩阵与预期

`lab-net` 的 DaemonSet 在十台 VM 各运行一个普通 Pod；另一个 DaemonSet 只在 worker02 的 `lab-net-peer` 中运行一个 Pod，共 11 个。只为诊断 Pod 容忍现有控制平面和存储污点，不改节点污点。所有 Pod 为 restricted、非 root、只读根文件系统、不挂默认 Token，不使用 hostNetwork、hostPath、额外 capability 或持久卷。

| 用例 | 验证与预期 |
| --- | --- |
| 100 个 Pod 有向对（含 10 个同 VM、90 个跨 VM） | 每对 5 次 HTTP/TCP 和 5 次 UDP；HTTP 上传 128 KiB，UDP 上传 1200 字节；回传后端 VM、服务端所见源地址、长度与 SHA-256，逐项匹配 |
| UDP 大包 | 每个主空间源对 peer 发送 1400 与 4096 字节，各 5 次；回包验证摘要和长度，记录样本丢失。成功可能经过 IP 分片，不能声称已测得无分片 PMTU |
| Service | 每源分别请求 ClusterIP、Service FQDN、跨空间 FQDN；peer 再反向请求主空间 Service；记录实际后端和实际源地址 |
| DNS | 每源通过 UDP、TCP 分别查询测试 Service、Kubernetes Service 和 Harbor，核对固定/实际 IP；共 60 个解析用例 |
| 出集群 TLS / SNAT | 每源 5 次 Harbor TLS；该 VM 的短时 tcpdump 只记录 SYN 元数据，检查出接口源地址等于本 VM `.101–.110` 地址；不采集 HTTPS 内容 |
| Mac 业务访问 | 只监听 loopback 的临时 port-forward；HTTP 200 且返回目标 Pod，完成后关闭进程；LAN VIP 待后续 MetalLB 专题 |

请求在 Pod 内计时，不把 `kubectl exec` 的控制通道耗时当作数据面延迟。每条 JSONL 包含时间、目标、协议、状态码、耗时、本地源地址、服务端 peer 和验证结果。`matrix.json` 分协议/场景汇总样本数和耗时；任一样本错误或丢失都停止，不生成通过回执。本实验不设未经测量的毫秒性能承诺。

## 02.01.03 Hubble 观测与预期

Hubble 与现有 Cilium 同为 1.20.2；使用 4095 条/节点环形事件缓冲和 8192 事件队列，不启用 L7 重定向、UI、磁盘 Flow 导出或 metrics ServiceMonitor。Relay 固定到 worker01，避免增加调度不确定性。Relay → Agent 的 4244 使用 Chart 自带 Helm 签发的 mTLS，证书保存在集群 Secret 中；证书有效期 365 天，后续维护需在到期前通过受控 Helm 更新。

4244 仅对现有节点 ipset 和规划 Pod CIDR 放行，不对整个 LAN 开放；节点 Enforcing/firewalld 始终保留。查询 Relay 的 4245 仅允许 host/remote-node 实体，健康检查端口 4222 也明确列出。通过已有管理员对 worker01 的 Cilium 容器执行自带 `hubble`，无需在 Mac 安装新 CLI、取出 TLS 私钥或暴露长期端口。官方说明：[Hubble 安装及 4244 前提](https://docs.cilium.io/en/v1.20/observability/hubble/setup/)。

三个场景都要求 Relay 连接 **10/10 节点**，按本次开始时间、源 Pod、目的 Pod IP、TCP/8080 过滤 Flow：

1. **正常请求**：客户端 HTTP 成功，Hubble 有 `FORWARDED`。
2. **应用超时**：`/delay` 延迟 3 秒，客户端 1 秒截止并实际报告 timeout；Hubble 仍有这段请求的 `FORWARDED`，说明链路放行而响应未按时完成。
3. **策略拒绝**：只在 peer 测试 Pod 启用 ingress deny；等到数据面确实超时，并必须找到 `DROPPED / POLICY_DENIED`。Ansible 的 `always` 撤销该策略，随后同一路径必须恢复成功。

没有符合过滤条件的 Flow、Relay 只连接部分节点或报告丢事件，均不能算观测通过。失败时保留 Pod 与证据以供诊断，拒绝策略仍执行撤销；若 API 当时不可用导致撤销未完成，可在恢复后用原批次 `cleanup` 或原样重跑完成恢复。

## 清理、重跑和完整回退

`cleanup` 是正常收尾：删除本批两个空间，保留 Hubble 和物料缓存；不会移除共享镜像、关闭安全机制或改动其他空间。`passed.json` 与 `state/closed.json` 必须属于同一 run/集群，且各自通过，才算本轮实验与清理全部完成。仅执行 cleanup 不会凭空产生实验通过回执。

需要恢复到本轮开启 Hubble 前的配置时，在同一个终端执行这一条替代/追加清理命令：

```bash
bash ops/02-networking/scripts/baseline.sh rollback "$LAB_NET_RECORDS"
```

作用：先清理本批实验，再确认当前 Helm revision 仍属于本批或已经由 Helm 自动回退；恢复先前 revision、等待 Cilium 健康，按 UID 撤销本批首次创建的 Relay 策略，最后分别恢复原 runtime/permanent 防火墙规则。预期：原 CNI 配置健康，本批新增端口被撤销，原有规则不受影响。Hubble 若在本批之前已经启用，则保留它及其访问规则；有其他人后续变更 Helm release 时会停止回退，避免覆盖新配置。

运行中断且尚未清理时，可以用同一目录重新执行 `run`；它要求源码完全一致并验证已有对象属于原 run。清理过的目录已关闭，新实验使用新 `LAB_NET_RECORDS`。若只是查看结果，阅读原 attempt 和日志，无需重复启动实验。

本次只读和源码校验记录见 [2026-10-18 前置复验](../../records/02.01-20261018-source-review/README.md)。静态、dry-run 和离线构建不能代替正式网络/Relay/清理运行结果；02.02 在本轮实际验收后继续。
