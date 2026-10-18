# 01.05 探针、连接与优雅终止完整实验

前置：01.04 已全部验收并清理。使用原 `lab-core` restricted 命名空间和 `lab-primary-lab-ops`，只在 worker01/02 创建实验资源；普通命令不需要扩大 RBAC。SELinux Enforcing、firewalld 和 kubelet 配置保持现状。本批 `01.05-20261017-224949` 的五组真实实验、总验收和清理均已通过，见 [验收与实验小结](../../records/2026-10-17-restart/acceptance.md#6-0105-实验小结)。以下入口保留供新批次复现。

## 一次执行的完整命令

以下三条都在管理 Mac 执行，不要同时运行两批：

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
CNPL05="$PWD/ops/01-kubernetes/records/2026-10-17-restart/evidence/01.05-$(date +%Y%m%d-%H%M%S)"
bash ops/01-kubernetes/core-resources/probes/run.sh "$CNPL05"
```

1. `cd`：固定仓库位置，后续配置和 Ansible inventory 都从该仓库读取。预期无错误返回。
2. `CNPL05=…`：给本次实验生成独立证据目录名；赋值本身不创建集群资源。预期变量类似 `…/evidence/01.05-20261017-223000`。
3. `bash …/run.sh "$CNPL05"`：执行下表全部步骤，保存脚本快照、物料摘要、清单、输出和实际回执；真正错误立即停止，预期故障必须被断言证实。预期约 6–12 分钟，最终出现验收和清理两个总 PASS。

源码在 [main.go](main.go)，本机测试在 [main_test.go](main_test.go)，编排在 [lab.py](lab.py)，完整执行顺序在 [run.sh](run.sh)，镜像准备在 [Ansible playbook](../../ansible/playbooks/prepare-probe-image.yml)。无需另填配置或复制不存在的示例 YAML。

## 每条内部命令的作用与预期结果

下表 `PY` 为 `$HOME/.venvs/cnpl-ansible/bin/python`，`LAB` 为本目录，`R` 为 `$CNPL05`。所有命令已在 run.sh 中完整展开，主命令会依次执行，表格用于理解，不要再重复执行一遍。

| 步骤 / 命令 | 做什么 | 预期结果及证据 |
| --- | --- | --- |
| 00 `PY LAB/build.py --output …/artifact.json` | 核对隔离 Go 编译器下载包 SHA；运行有限本机单测，交叉编译 linux/amd64 静态应用，生成 OCI 归档和精确 Digest。 | `PROBE BUILD PASS`。只有标准库，无第三方 Go 包；不依赖 Docker。源码/二进制/归档/manifest 各有 SHA。 |
| 01 `PY LAB/lab.py check --records R` | 只读检查两份 kubeconfig 的目标、集群 UID、1.36.5、十节点 Ready/无压力、worker 可调度、restricted、实际权限和两个 worker 已有 etcd 镜像。 | `PROBE PREFLIGHT PASS`；不满足则在部署前停止。 |
| 02 `ansible-playbook …/prepare-probe-image.yml -e probe_artifact_file=…` | 仅向 worker01/02 复制 OCI，使用 Python hashlib 校验，导入 containerd 的 k8s.io 命名空间，核对 manifest 和 CRI 可见性。 | 两主机 `failed=0 unreachable=0`。再次执行应不再导入同一 Digest。不安装节点包，不调用 openssl，不启动容器。 |
| 03 `PY LAB/lab.py render --artifact … --records …/manifests` | 输出全部完整 YAML，并逐份使用实际受限身份进行 API server dry-run。 | `PROBE MANIFEST SERVER DRY-RUN PASS`；这是 API 准入核验，不部署 Pod。 |
| 04 `PY LAB/lab.py prepare --artifact … --records R` | 绑定集群 UID、批次和应用物料，建立本批 NetworkPolicy；已有其他批次或同名对象会拒绝覆盖。 | `PROBE PREPARE PASS`，生成原子写入的 state.json。策略允许同批 Pod、DNS 和两个 worker 的受控健康端口。 |
| 05 `PY LAB/lab.py startup --records R` | 依次运行 6/12/20 秒慢启动；读取真实 kubelet 调用计数，证明 startup 成功前未执行 live/ready；再让 45 秒启动超过约 8 秒容忍窗口。 | `STARTUP PASS`。三个慢启动零重启，另一个有 startup 失败事件及真实 restartCount 增长；保存采样和失败现场后回收本组。 |
| 06 `PY LAB/lab.py liveness --records R` | 独立依赖服务保留端口，但把响应拖到 2 秒；两个业务副本的真实 HTTP 依赖请求在 500ms 超时。再冻结一个副本的本地 worker 心跳。 | `LIVENESS PASS`。依赖中断期间两个副本 NotReady，但连续 14 秒零重启；恢复依赖后 Ready。本地心跳停止后出现 liveness 失败、重启及恢复，对照副本不重启。 |
| 07 `PY LAB/lab.py readiness --records R` | 两副本 Service 持续发起新 TCP 连接，同时保留一条连到 a 的 HTTP/1.1 连接；将 a 的 readiness 切为失败，核对 EndpointSlice。 | `READINESS PASS`。端点更新及数据平面等待后，新连接只到 b；原连接仍到 a，连接 ID 和客户端端口均未变；a 没有重启，恢复后重回就绪端点。 |
| 08 `PY LAB/lab.py termination --records R` | 同时处理 12 秒长请求、短请求和 12 秒消息；删除主副本，运行 PreStop 5 秒和总宽限 25 秒。随后用 PreStop 4 秒、总宽限 6 秒处理更长请求/消息，故意制造失败并补偿。 | `TERMINATION PASS`。正常场景长请求完整返回、短请求无失败、消息提交一次、TERM/UID/排空回执匹配。失败场景观察非 OOM 的 137、长请求中断、未提交消息；租约到期由新消费者重领，重复提交后效果次数仍为 1。 |
| 09 `PY LAB/lab.py protocols --records R` | HTTP/TCP/Exec 使用同一应用，注入端口仍开但业务失败；原生 gRPC 使用已有 etcd 镜像，对比空 service 和故意不存在的 service。 | `PROTOCOLS PASS`。HTTP/Exec 识别 503，TCP 仍 Ready；正常 gRPC Ready，错误 service NotReady 且有 kubelet NotFound 事件，但 etcdctl 仍证明业务健康；不把配置错配当作进程死亡。 |
| 10 `PY LAB/lab.py verify --records R` | 核对五组回执的批次、真实终止 Pod、消息重领/去重证据，再只读检查集群健康。 | `VERIFY PASS`、`PROBE LIFECYCLE ACCEPTANCE PASS`。仅文件存在或退出 0 不足以通过。 |
| 11 `PY LAB/lab.py cleanup --records R` | 按本批标签清理 Pod/Service/NetworkPolicy；再次查询对象及派生 EndpointSlice，保留证据、Namespace 和身份。 | `CLEANUP PASS`、`PROBE LAB CLEANUP PASS`，cleanup-confirm.json 中 items=[] 且 endpointslices.items=[]。物料缓存供复现，不算运行中的 Kubernetes 资源。 |

## 怎么理解探针和阈值

`startupProbe` 只负责“这次启动是否完成”。本应用启动期间 `/startup` 和 `/live` 都失败，启动成功后才由 kubelet执行运行期 live/ready。若没有 startup 保护，20 秒初始化可能被更短的 liveness 失败阈值反复打断。三次受控启动使用 period=2 秒、failureThreshold=30，得到约 60 秒窗口；45 秒坏例故意缩成 period=2、threshold=4。乘积是配置预算，真实探测时刻还受 kubelet 调度、首次探测和超时影响，不能当作毫秒精确期限。[官方探针语义](https://v1-36.docs.kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)

`receipts/startup.json` 保存每次配置延迟、实际观察到 Ready 的 uptime、Pod UID、全过程采样。60 秒预算为实验最大初始化 20 秒加观察/探测余量；这三个受控样本用于学习测量方法，不能冒充生产启动分位数。生产阈值还需用真实冷启动、数据量和资源竞争下的分布推导。

`livenessProbe` 回答“本地 worker 是否还能工作”，检查三秒内是否有心跳。`hang` 控制冻结该 worker 的心跳，HTTP 监听进程仍在，kubelet 观察本地失活后重启容器。依赖超时不会停止本地心跳，因而不会把所有副本同时重启。`readinessProbe` 还考虑依赖、业务开关及排空状态，决定该副本此时是否参与服务。

依赖 fixture 的 readiness 故意检查 `/live`，保留其 Service 端点，让业务响应持续超时。它用于精确制造外部依赖故障；两个业务副本的 readiness 仍正确反映业务可用性。采样必须出现实际依赖超时计数及接近 500ms 的耗时，才能通过。

Readiness 改变的是后续流量选择，不会自动撤销应用中已经建立的会话。Mac 经 worker SSH 连接同节点的实验客户端 Pod，由该 Pod 发起真实 ClusterIP 连接；透明 TCP 转发对每条连接保持一对一，不解析 HTTP、不合并连接。这样 Service 流量具备真正的 Pod 身份，不受宿主机网络身份影响；未使用 `kubectl port-forward service` 充当负载均衡证明。每个新请求主动新建连接，旧连接额外核对服务端连接 ID，避免客户端重连造成假象。EndpointSlice 按当前 Service UID 过滤，旧对象残留不能冒充新 Service 的状态。[EndpointSlice 条件](https://v1-36.docs.kubernetes.io/docs/concepts/services-networking/endpoint-slices/)

## 终止与消息补偿是怎么工作的

正常主副本的 PreStop 先调用本地控制接口：readiness 变为失败、消费者停止领取下一条消息，然后等 5 秒给端点传播留出时间。这期间保留 HTTP 处理能力。钩子结束后，应用收到 SIGTERM，停止接受新连接，等待已经进入的 HTTP 请求及当前消息完成，在 `/dev/termination-log` 写入包含 Pod UID、信号、PreStop/TERM/完成时间和已提交消息 ID 的回执，再退出 0。

总宽限期从终止流程开始计时，PreStop 的 5 秒包含在 25 秒中；并非先等 5 秒，再额外获得 25 秒。脚本还会留取 `terminating=true`、`ready=false` 的 EndpointSlice；`serving` 单独记录观察值。finalizer 只为保留 API 终态，删除后不再依赖 CRI 日志。[官方终止流程](https://v1-36.docs.kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination-flow)

反例把总宽限缩为 6 秒、PreStop 占 4 秒，长请求 30 秒、消息处理 20 秒，剩余时间不足，所以必须看到真实强杀和未完成工作。队列为独立 broker Pod：按租约分配消息，消费者成功后提交；被杀且未提交的消息租约到期后重新投递，旧租约不能覆盖新消费者。提交按消息 ID 去重，脚本会真实重复提交两次核对效果计数。

这是本实验 broker 内部的租约及幂等提交演示，状态保存在其 emptyDir；不代表已经部署生产消息平台，也不保证任意外部数据库副作用恰好一次。若 broker Pod 被删除，卷内队列也会丢失；因此脚本先把强杀后的未提交状态及最终队列保存到 Mac，再回收整组。生产消费者须将业务效果与幂等记录放在相应事务边界内。

## 四种协议的含义和成本

| 协议 | 此次真实判定 | 容易漏掉或误判什么 | 成本与选用 |
| --- | --- | --- | --- |
| HTTP | 返回明确的 200/503 | 检查路径若不代表本地健康，会把业务故障误当死进程 | 轻量专用接口；避免大响应及阻塞操作。 |
| TCP | 只尝试建立端口连接 | 端口开着，业务仍可能返回 503 | 无需业务处理，语义最弱。 |
| Exec | 执行 `/probe-lab probe …/ready`，按退出码判定 | 缺程序/权限/超时也会失败，不一定是主进程死亡 | 每次创建探测进程；本镜像没有 sh/curl，不依赖它们。 |
| 原生 gRPC | 调用标准 Health Check，要求 SERVING | service 配错会 NotFound；本实验 etcd 的空 service 也不代表你的全部外部业务依赖 | 使用数字端口、配置正确的 service；原生探针不提供 TLS/认证参数。 |

etcd 的 gRPC 服务注册及空 service 行为已对照 [v3.6.8 源码](https://github.com/etcd-io/etcd/blob/v3.6.8/server/etcdserver/api/v3rpc/health.go)。四种协议成本在这里定性比较，不编造尚未测量的 CPU 百分比。

## 中断后继续、查看及清理

同一终端保留 CNPL05；换终端时先将它设回末尾打印的实际证据目录。继续只需：

```bash
bash ops/01-kubernetes/core-resources/probes/run.sh "$CNPL05" --resume
```

作用：重新核对物料、目标和准入，跳过已 PASS 的组。首个未完成组会先保存旧对象/事件/可读日志，再仅重建本组资源；重建的 Pod UID 和 emptyDir 会变化。上一组回执、原始输出及源码快照不覆盖，新输出存入新的 attempt-*。失败发生在 prepare 前也能这样继续；应用物料与旧批不一致则拒绝混用。已完成 cleanup 的批次不应再续跑。

查看当前实验对象：

```bash
"$HOME/.cnpl/bin/kubectl" --kubeconfig "$HOME/.cnpl-secrets/access/lab-primary/mac.conf" \
  --context lab-primary-lab-ops -n lab-core get pods -l app.kubernetes.io/part-of=cnpl-probe-lab -o wide
```

作用：只读观察所有实验 Pod 的 Ready、重启和位置；有意失败阶段出现 NotReady、重启或强杀属于待验证现象，不能直接判断整批失败。详细原因见 `attempt-*/步骤.txt`、`failure-*.json`、`snapshots/` 和 `receipts/`。

如果决定结束未完成批次：

```bash
"$HOME/.venvs/cnpl-ansible/bin/python" ops/01-kubernetes/core-resources/probes/lab.py cleanup --records "$CNPL05"
```

作用：核对集群 UID 和归属后清理本批 Kubernetes 资源，验证零残留。失败批次会额外写 cleanup-without-acceptance.json，不补写不存在的实验 PASS。没有 state.json 时尚未创建本批 Kubernetes 资源，无需运行此清理命令；已缓存镜像和公开证据保留。

## 交付前验证边界

使用现有原生命令编排与 Pod/Service/NetworkPolicy；应用只用 Go 标准库，未引入通用策略/工厂或外部消息依赖。Go 1.27.2 管理 Mac arm64 下载包按 [官方物料](https://go.dev/dl/?mode=json) SHA256 `76812b213b1b2302c978d28fa52fa92d541704b9e7d9d5db8002c50e4018c4c5` 核验，隔离于 `~/.cnpl/toolchains/`，不替换系统环境。应用按 OCI manifest Digest 引用，Never 拉取；源码、编译器及归档信息写入 artifact.json。gRPC 复用两个 worker 已缓存的 etcd 精确 Digest。

本机测试通过 Recorder 和有界 net.Pipe 执行真实 HTTP 超时/连接/长请求排空及队列提交逻辑，未监听端口；编排回归运行真实 run.sh 的失败续跑分支，但将外部操作替换为替身。另做 API server dry-run、镜像真实导入与幂等性验证。它们不证明真实 kubelet 探针、Cilium 端点传播、CRI 信号和强杀实验已经通过；运行这些场景的入口由用户启动。具体输出见本次交付记录。
