# 01.06 RC、ReplicaSet 与 Deployment 完整实验

前置检查点为 `812f2c9`：01.05 五组实验、总验收和清理通过。[实际验收](../../records/2026-10-17-restart/acceptance.md#6-0105-实验小结)已归档。本专题脚本已准备，真实六组实验由用户启动。

使用原 `lab-core` restricted 命名空间及 `lab-primary-lab-ops`。应用只调度到 worker01/02，保持 SELinux Enforcing、firewalld 和 kubelet 配置；容量反例通过 Pod 资源请求制造，不修改节点。本专题采用原生控制器及顺序编排，复用已验收的客户端、SSH 转发、流量记录和 Go 工具链，没有增加框架或业务依赖。

## 一次执行的完整命令

管理 Mac 执行三条，不要并行运行两批：

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
CNPL06="$PWD/ops/01-kubernetes/records/2026-10-17-restart/evidence/01.06-$(date +%Y%m%d-%H%M%S)"
bash ops/01-kubernetes/core-resources/controllers/run.sh "$CNPL06"
```

1. `cd`：固定仓库位置，读取既有 inventory、受限身份和相邻脚本。预期正常返回。
2. `CNPL06=…`：指定本次独立证据目录；赋值不创建集群资源。预期变量类似 `…/evidence/01.06-20261017-235000`。
3. `bash …/run.sh "$CNPL06"`：按下表执行全部命令，每步成功才继续；阶段内部也会打印当前子实验。预计约 8–18 分钟，错误镜像一组会特意等待 45 秒进度期限。日志、源码快照、完整清单、流量、控制器时间线及回执都会保存。

最后必须同时看到：

```text
CONTROLLER ACCEPTANCE PASS
CONTROLLER LAB CLEANUP PASS
```

核心源码：[main.go](main.go)、[build.py](build.py)、[lab.py](lab.py)、[run.sh](run.sh)；镜像导入：[playbook](../../ansible/playbooks/prepare-controller-images.yml)、[导入任务](../../ansible/tasks/import-controller-image.yml)。下表为解释，不要在主脚本之后再重复执行一遍。

## 每条内部命令做什么

`PY` 为 `$HOME/.venvs/cnpl-ansible/bin/python`，`LAB` 为本目录，`R` 为 `$CNPL06`；完整参数均在 run.sh 中展开。

| 步骤 / 命令 | 作用 | 预期结果 |
| --- | --- | --- |
| 00 `PY LAB/build.py --output …/bundle.json` | 复用隔离 Go 工具链，核验其 SHA，运行有限单测，构建 v1/v2/bad 三个不可变 OCI 镜像。 | `CONTROLLER BUILD PASS`。固定 linux/amd64、标准库、Digest；不依赖 Docker、不启动应用。 |
| 01 `PY LAB/lab.py check --records R` | 只读核对目标集群、1.36.5、十节点健康/无压力、两 worker 可调度、restricted、控制器/scale/exec 权限，以及同集群 01.05 真实通过与清理记录。 | `CONTROLLER PREFLIGHT PASS`。前置不满足时停止。 |
| 02 `ansible-playbook …/prepare-controller-images.yml -e controller_bundle_file=…` | 仅向两个 worker 复制归档，Python 核对 SHA，containerd 导入/展开，显式建立完整仓库名的 Digest 引用并查询 CRI。 | 两主机 failed=0、unreachable=0；相同物料重复执行应 changed=0。节点不依赖 openssl。 |
| 03 `PY LAB/lab.py render --bundle … --records …/manifests` | 输出 33 份完整清单，包括 RC/RS、孤儿、Deployment、两种策略、坏镜像/探针、8 核反例和双入口；逐份真实 API server dry-run。 | `CONTROLLER MANIFEST SERVER DRY-RUN PASS`；准入检查不创建运行对象。 |
| 04 `PY LAB/lab.py prepare --bundle … --records R` | 保存集群 UID、前置批次、镜像物料和初始 Git 检查点，建立本批网络策略。 | `CONTROLLER PREPARE PASS`。已有其他批次拒绝覆盖；续跑核对物料并恢复缺失的本批策略。 |
| 05 `PY LAB/lab.py replicas --records R` | 分别创建匹配/不匹配孤儿和独立 RC/RS；观察接管、补足两个副本，再删除一个受控 Pod。 | `REPLICAS PASS`。匹配孤儿保留 UID 并获得正确 ownerReference；不匹配 Pod 保持无控制器；删除后出现新 UID，副本恢复为 2。 |
| 06 `PY LAB/lab.py history --records R` | 发布 v1→v2，记录 Deployment→RS→Pod；再只把 replicas 改成 3。 | `HISTORY PASS`。改 Pod 模板产生新 RS/revision；仅 scale 不新增 RS、不改变 revision；真实业务返回 v2。 |
| 07 `PY LAB/lab.py scale --records R` | 正常扩到 3，为每个副本写临时数据并同时发 12 秒请求，缩到 1，再扩到 3。另建 8 核请求的容量控制器，从 0 扩到 1。 | `SCALE PASS`。被删两个副本在 TERM 后完成请求并留下 UID 回执；幸存者数据保留，新 Pod 得到新 emptyDir；8 核副本 Pending/Insufficient cpu，缩回 0 后正常业务仍健康。 |
| 08 `PY LAB/lab.py strategies --records R` | 持续新连接下分别执行 RollingUpdate 与 Recreate；记录错误率、耗时、RS 副本预算、实际 Pod 峰值和声明的 CPU 请求；另验证 surge 新 Pod 因 8 核请求阻塞。 | `STRATEGIES PASS`。滚动更新本次采样零错误，Recreate 观察到不可用窗口；surge 阻塞时旧两副本继续服务，回滚请求配置后恢复。 |
| 09 `PY LAB/lab.py rollbacks --records R` | 暂停时批量修改并修正模板，再恢复；依次制造错误镜像、失败 readiness、探针健康但业务错误，动态选择已知 revision 回滚。 | `ROLLBACKS PASS`。暂停时无新 RS；坏镜像出现 ErrImageNeverPull 和 ProgressDeadlineExceeded；坏探针不重启容器；坏业务即使 rollout 完成也返回 500。三次回滚均还原完整模板并连续 6 次返回 v2。 |
| 10 `PY LAB/lab.py split --records R` | 建 stable=v1 两副本、canary=v2 一副本，使用独立 Deployment selector 和 Service 入口。 | `SPLIT PASS`。稳定入口只返回 v1，候选入口只返回 v2；仅验证入口分离，不宣称已经实现带权灰度。 |
| 11 `PY LAB/lab.py verify --records R` | 复核六组回执的批次、接管/替换 UID、缩容终态、流量差异、容量阻塞及完整模板/业务回滚，再检查集群健康。 | `VERIFY PASS`、`CONTROLLER ACCEPTANCE PASS`。只有配置存在或退出 0 不足以通过。 |
| 12 `PY LAB/lab.py cleanup --records R` | 先停止本批父控制器，再前台级联回收子对象及孤儿，删除 Service/策略，查询派生 EndpointSlice。 | `CLEANUP PASS`、`CONTROLLER LAB CLEANUP PASS`；cleanup-confirm.json 的对象及 EndpointSlice 均为空。Namespace、RBAC、公开证据和物料缓存保留。 |

## 六组实验应该学到什么

### RC / RS：副本控制依赖 selector 和 ownerReferences

RC 使用等值 selector，RS 还可使用集合表达式；本实验 RS 的 track 使用 `In: [stable]`，不匹配孤儿为 track=other。两种控制器使用不同 pool，整个批次还带唯一 run 标签；不会让两个控制器争抢相同 Pod。

控制器接管的是满足 selector、没有其他 controller owner 的 Pod。验收比较原孤儿 UID 和新的 ownerReference；补副本时要求原删除 UID 消失、出现新 UID，不能只凭数量仍为 2 就判成功。RC 仅作历史对照，后续正式模板继续使用 Deployment。[ReplicaSet 语义](https://kubernetes.io/docs/concepts/workloads/controllers/replicaset/)

### Deployment：模板版本和副本数是不同字段

Deployment 管理 RS，RS 管理 Pod。`set image` 修改 `spec.template`，因此会有新 RS/revision；`scale` 修改 `spec.replicas`，只改变已有版本的副本数量。`history.json` 保存各层 ownerReferences、镜像和 UID；`history-*.txt` 是原生 rollout history 输出。

v1/v2/bad 使用同一标准库二进制、不同的不可变镜像配置。v1 和 v2 返回不同 version，并分别模拟 2/4 秒初始化；bad 故意在探针健康时让业务返回 500。镜像配置也属于镜像内容，因此三个 Digest 不同，模板确实发生镜像变更；这不是用可变标签冒充更新。

### 扩缩容：3 个副本不需要 3 台节点

应用仅可调度到两个 worker，使用软分散约束；三个副本可以共享节点。缩容前为三个副本都发请求，因为不能预先猜测控制器会删除哪个。受控 finalizer 保留两个终止 Pod 的 API 终态，校验 Completed/0、TERM/UID/排空消息和请求完成时间，再释放 finalizer。

emptyDir 跟随 Pod UID：幸存副本保留写入的数据，被删除副本的数据不会自动复制给新副本。脚本先把原值及现场保存到 Mac，再验证重扩的两个 Pod 是新 UID、新卷。本实验不交付业务持久化。

8 核反例的前提是每个 worker Allocatable=7 核，由前检确认。Pod 的请求必须放进单个节点，不能把两台节点的余量拼给一个 Pod。这里正常主应用保持三副本；容量控制器从 0→1 出现 FailedScheduling 后缩回 0，Pending 对象被回收。

### 更新策略：测实际流量，同时看预算和瞬时对象数

RollingUpdate 设置 maxSurge=1、maxUnavailable=0、minReadySeconds=3。新版本就绪并稳定后才替换旧副本；应用 PreStop 等 5 秒给端点传播留出时间。脚本核对 RS 期望副本预算不超过 3，并单独记录非终止 Pod、全部 Pod 对象及 CPU 请求总量。

控制器异步收敛和终止过程会造成实际 Pod 峰值与预算不同；不能把 replicas+maxSurge 当成任意瞬间的对象总数上限。CPU 字段记录的是声明请求，未冒充实测 CPU 使用率。新 surge Pod 请求 8 核时，旧两副本仍服务，发布会阻塞；增加 maxSurge 不会让单 Pod 跨节点调度。

Recreate 先停旧版再建新版，应用启动延迟使不可用窗口可观测。两种策略的 traffic-*.jsonl 都保存每次请求时间及结果，strategy-*.json 保存采样错误率、发布观察耗时和峰值。滚动更新的零错误结论仅覆盖本次采样，不是生产可用性保证。[Deployment 更新与资源语义](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)

### 发布失败：控制器完成状态和业务正确性分别验收

暂停期间的模板修改不会立即发布；先修正错误配置，再 resume。本实验之后依次观察：

- 镜像不存在且 Never 拉取：新 Pod 出现 ErrImageNeverPull，保留旧副本；45 秒进度期限后出现 ProgressDeadlineExceeded。脚本再读取模板确认仍是失败版本，证明控制器没有自动回滚。
- readiness 失败：新容器已经启动，返回 503、不进入服务端点，restartCount 仍为 0；旧版本继续服务。
- 业务失败：bad 的健康接口返回成功，所以控制器可能报告发布完成；真实 `/work` 返回 500，因此业务验收仍失败。

每个反例都先保存原生 history、对象、事件和流量证据，再执行 `rollout undo --to-revision=当时的已知版本`。回滚后比较完整 Pod 模板，包括镜像、环境变量、资源和注解，并等待真实入口连续六次返回 v2；不只看 rollout status。revision 会随着回滚变化，脚本每轮重新读取，不写死为 1 或 2。

回滚恢复的是 Pod 模板，外部数据和数据库变更需要各自的恢复设计；副本数也不是 Pod 模板的一部分。实验镜像和原有 RS 历史被保留，避免回滚时已无可用物料。[进度失败与暂停/回滚](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)

### 双版本入口：为后续灰度实验建立边界

stable 和 canary 各有独立 selector/Service，两个客户端从各自入口取样。这里没有按权重切流、指标分析或自动回退；这些留在 Phase 02、04。本节通过只代表版本和入口能独立管理，普通滚动更新中短暂共存的两版本也不能直接当作带权灰度。

## 如何续跑、查看和清理

保持原来的 CNPL06；换终端时先将它赋回真实证据目录。继续执行：

```bash
bash ops/01-kubernetes/core-resources/controllers/run.sh "$CNPL06" --resume
```

作用：重核目标/物料和准入，跳过已通过组，对未完成组先保存旧对象、事件、可读日志、应用指标及临时数据，再重建本组。新 Pod UID/emptyDir 会变化；原通过回执和旧 attempt 输出不覆盖。若准备阶段尚无 state.json，也可以重试此入口；应用物料改变则拒绝混用。

只读查看现场：

```bash
"$HOME/.cnpl/bin/kubectl" --kubeconfig "$HOME/.cnpl-secrets/access/lab-primary/mac.conf" \
  --context lab-primary-lab-ops -n lab-core get deploy,rs,rc,pods,svc \
  -l app.kubernetes.io/part-of=cnpl-controller-lab -o wide
```

作用：观察 desired/current/ready、Pod Pending、版本 RS 和 Service。反例中 Pending、NotReady、ProgressDeadlineExceeded 是待验证现象；以脚本断言和组 PASS 判断结果。步骤日志位于 attempt-*/，详细对象位于 snapshots/，发布采样位于 rollout-*.jsonl，最终结果位于 receipts/。

结束未完成批次并清理：

```bash
"$HOME/.venvs/cnpl-ansible/bin/python" ops/01-kubernetes/core-resources/controllers/lab.py cleanup --records "$CNPL06"
```

作用：核对集群 UID 和整组归属，处理本实验自己的 finalizer，先删父控制器再级联回收，最后验证零残留。外来 finalizer 会在删除任何对象前中止；失败批次会写 cleanup-without-acceptance.json，不补写不存在的验收 PASS。没有 state.json 时尚未创建本批资源，无需运行此清理命令。

## 交付前核验与真实验收的边界

当前已做有限本机行为/竞态测试、编排与真实 Shell 续跑回归、33 份真实 API server dry-run、两 worker 镜像导入及幂等复验。测试只使用 Recorder/net.Pipe，不监听端口；没有自动创建 01.06 实验 Pod。具体输出见 [交付核验](../../records/2026-10-17-restart/evidence/01.06-delivery-20261017/README.md)。实际调度、控制器补副本、Cilium 流量、缩容信号和回滚由用户运行后另行验收。
