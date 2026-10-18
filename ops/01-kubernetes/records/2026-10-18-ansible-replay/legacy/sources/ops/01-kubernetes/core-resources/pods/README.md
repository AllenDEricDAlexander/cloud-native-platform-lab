# 01.04 Pod 生命周期完整实验

前置检查点为 `03f7094`：01.03 完整备份/取回、离线快照展开、单 VM HA 与清理通过。原短名 DNS 补测失败已保留，修正后的矩阵已在本批次通过；新批次仍按脚本先验证矩阵。[阶段验收记录](../../records/2026-10-17-restart/acceptance.md)保留 .15 分发及在线灾难恢复的未完成边界。


本批最新进度：01.04.01–05、14/15/16 的最终验收和清理全部通过，结果见 [验收与实验小结](../../records/2026-10-17-restart/acceptance.md#5-0104-实验小结)。以下 09/13/14 小节保留故障处理与复现说明，当前无需再重试。

本目录复用 `lab-core` restricted 命名空间、Mac 运维身份、已缓存 BusyBox Digest，以及现有 CoreDNS 镜像的实际运行 Digest（仅充当无 Shell 应用）。不增加镜像、包或业务依赖。正常场景固定 worker01；OOM 和驱逐固定 worker02。SELinux Enforcing 与 firewalld 保持开启。

## 一次执行的完整命令

以下三条在管理 Mac 执行。脚本内每一组成功后才进入下一组；不要同时运行两批：

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
CNPL04="$PWD/ops/01-kubernetes/records/2026-10-17-restart/evidence/01.04-$(date +%Y%m%d-%H%M%S)"
bash ops/01-kubernetes/core-resources/pods/run.sh "$CNPL04"
```

第一条固定仓库路径；第二条生成本次独立证据目录名称；第三条执行下表的全部命令。`run.sh` 自己开启 `set -euo pipefail`，不会更改你终端的默认身份或 shell 设置。每步 stdout/stderr 都保存；预期故障由断言确认后算成功，真正命令错误立即停止。预计 5–15 分钟，取决于容器重启退避和节点状态更新时间。

全部完成应出现 `POD LIFECYCLE ACCEPTANCE PASS`、`POD LAB CLEANUP PASS`，以及最终证据目录。文件存在不代表验收通过，最终还需核对各组状态。

## 第 09 步中断后继续原批次

`01.04-20261017-204751` 的 DNS 补测已通过，prepare 已完成，09 因脚本争抢两秒 exec 窗口而中断。现场容器重启退避已到五分钟，原来的 150 秒重试无法保证命中；10 的 Init 原实现有同类问题，两处均已改为保存失败证据后以正确 command 重建。

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
CNPL04="$PWD/ops/01-kubernetes/records/2026-10-17-restart/evidence/01.04-20261017-204751"
bash ops/01-kubernetes/core-resources/pods/run.sh "$CNPL04" --resume
```

三条分别固定仓库、选回原批次、从首个未通过步骤继续。`--resume` 先核对集群 UID、顺序检查点、基准与资源归属；本批跳过 00–08，重新执行未完成的 09，再继续 10–16。09 重试前对旧的五个状态实验 Pod 留证，再仅回收本批对应 Pod，不重建基准应用、Namespace 或身份配置；过期的实验 Pod 也可以这样恢复。

修正 command 需要重建独立 Pod，因此失败和修复对应不同 UID；不宣称旧 emptyDir 仍然保留。普通 Sidecar 的 stop 文件仍在稳定运行的 Sidecar 内写入，不依赖短命容器窗口。取证保存的是实际观测到的 CrashLoopBackOff 状态，不会被稍后的 Running 窗口替换。

原始日志不覆盖；新执行日志位于 `resume-时间-随机值/`，同名 Pod 观测增加唯一后缀，当前实现源文件及 SHA 保存在 `script-revisions/` 并追加 resume_history，原始 implementation_sha256 保留。若后面再次中断，同一命令会跳过新通过的步骤。压力阶段有单独恢复规则：未 armed、未 cordon 且已恢复的准备失败可用下节 retry 留证回收后继续；已经进入阈值修改的失败仍需 restore，再 cleanup 后新建批次。

## 第 13 步准备阶段超时后继续

该批首次运行到 13 时，09–12 均已 PASS，13 停在等待负载 Ready：原探针每两秒用 wc 扫描 96Mi 文件，在 200m CPU 上超过默认一秒超时。进程已经完成写入并输出 pressure-ready；当时 armed=false、cordoned=false，还没有修改驱逐阈值。

现改为写完后 stat 校验一次体积，再生成 `/work/loaded`；readiness 只判断完成标记，显式 timeoutSeconds=5。保留 96Mi 负载、160Mi 容器上限和原节点预算，压力判定仍要求真实 MemoryPressure/Evicted。

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
CNPL04="$PWD/ops/01-kubernetes/records/2026-10-17-restart/evidence/01.04-20261017-204751"
"$HOME/.venvs/cnpl-ansible/bin/python" ops/01-kubernetes/core-resources/pods/pressure.py retry --records "$CNPL04"
bash ops/01-kubernetes/core-resources/pods/run.sh "$CNPL04" --resume
```

四条分别固定仓库、选择原批次、准备第 13 步重试、继续到 14–16。retry 要求记录明确为未 armed、未 cordon、已恢复，并重新核对集群/节点 UID、原 kubelet SHA、节点及系统健康；然后将旧 pressure.json 和测试 Pod 证据存入 pressure-attempts 子目录，仅回收本批 p04-pressure，解除失败准备记录的门禁。该命令不创建新负载、不修改 kubelet，也不改变 09–12 的通过标记。

随后 --resume 跳过已通过阶段，从 13 创建修正探针的 Pod，按原计划验证驱逐和恢复，再执行正常终止、总验收和清理。已有 armed 或配置/身份不匹配时 retry 会拒绝，不能手工删除 pressure.json 绕过检查。后续失败会自动补存 Pod、事件、日志与失败阶段；WORKER02 HEALTH/RESTORE PASS 只说明恢复检查，不表示压力实验通过。

## 第 14 步终止证据读取失败后继续

历史排障时，13 已实际观察 MemoryPressure、memory 驱逐及恢复，状态记录包含 PRESSURE PASS。14 的旧证据显示 Completed/0，但删除后再读日志得到 unable to retrieve container logs。finalizer 只能保留 API 对象，不保证运行时容器/日志仍在；旧验收错误地依赖删除后的日志。

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
CNPL04="$PWD/ops/01-kubernetes/records/2026-10-17-restart/evidence/01.04-20261017-204751"
bash ops/01-kubernetes/core-resources/pods/run.sh "$CNPL04" --resume
```

三条分别固定仓库、选回原批次、从未通过的 14 继续到 15–16，09–13 的结果保持。此次不调用 pressure.py retry，也不重新修改 worker02。

14 会建立本批专用 p04-term-app ConfigMap 并挂载到新测试 Pod，确保旧批次运行修正后的应用；现有 p04-app 和基准 Pod 保留。等待 HTTP ready（在 trap 安装及服务启动之后）再删除，信号处理函数先回收 httpd 子进程，再向 `/dev/termination-log` 写入带 signal=TERM、Pod UID、child_reaped=true 的短消息，并退出 0。Kubernetes 将这段文本保存到 containerStatuses[].state.terminated.message，日志回收不影响读取此状态。[官方终止消息机制](https://v1-36.docs.kubernetes.io/docs/tasks/debug/debug-application/determine-reason-pod-failure/)

验收同时要求 deletionTimestamp、Succeeded、Completed/0 和匹配 UID 的 TERM 消息；只退出 0、缺消息、UID 错误或不同信号均拒绝通过。成功后保存 termination-receipt-UID.json，再释放 finalizer。15 重读回执及压力记录；16 删除后再查询本批标签，确认零残留才输出清理 PASS。旧失败文件保留，新快照使用唯一后缀。

## 每一组实际做什么

脚本中的 `p04` 显式使用平台管理员；`lab.py` 内普通资源使用 `lab-primary-lab-ops`，仅 quota/limitrange、节点 cordon/uncordon、统计和 ServiceAccount 权限核验使用管理员。日常默认 Context 继续只读。`PY` 表示 `$HOME/.venvs/cnpl-ansible/bin/python`，`LAB` 表示本目录，`R` 表示 `$CNPL04`；完整展开命令均已写在 [run.sh](run.sh)，无需手工创建配置文件。

| 序号 / 命令 | 目的、预期结果与证据 |
| --- | --- |
| 00 `PY LAB/lab.py check --records R` | 在任何变更前核对两份 kubeconfig 的目标及十节点健康；选错集群立即停止，不会先部署 DNS 测试。 |
| 01 `p04 apply -f …/network-smoke.yaml` | 重建独立十节点诊断 Namespace/DaemonSet/Service，补测原短名问题。 |
| 02 `p04 … rollout status daemonset/network-smoke` | 等十个普通 Pod 就绪；未 Ready 不开始矩阵。 |
| 03 `PY …/check-network.py --short-name` | 100 条 Pod HTTP、50 次 DNS、30 次 Service HTTP 均成功才继续。额外 DNS 查询检查实际搜索域展开；wget 短名访问验证应用解析器。BusyBox 指定 DNS 服务器时会跳过 search，不能用原命令测短名。 |
| 04 `p04 delete -f …/network-smoke.yaml` | 删除本次独立诊断资源，保留原始失败和补测输出。 |
| 05 `PY LAB/lab.py render --records R/manifests` | 只在本地输出全部 19 份完整 YAML（含终止实验专用 ConfigMap），供复现和查看；不部署。 |
| 06 `PY LAB/lab.py check --records R` | 只读核验集群目标、1.36.5、十节点 Ready、无节点压力、两 worker 可调度及 restricted Namespace。 |
| 07 `PY LAB/pressure.py check --records R` | 只读检查 worker02 只有系统关键负载、原 kubelet 没有自定义 soft 驱逐策略、硬阈值仍 500Mi。发现其他负载或策略时拒绝覆盖。 |
| 08 `PY LAB/lab.py prepare --records R` | 建 quota/limitrange、只允许同实验 Pod 与 DNS 通信的 NetworkPolicy、ConfigMap、普通基准 Pod/ClusterIP。验证响应与健康 503/恢复。已有 Pod 或同名对象时拒绝覆盖。 |
| 09 `PY LAB/lab.py states --records R` | 制造完成、退出 7、反复退出、错误镜像和 CPU 请求过大；保存 phase/state/事件/当前与 previous 日志。恢复镜像、将 Crash 命令修正后重建 Pod、降低 CPU 请求并重建，确认恢复后清理这些 Pod。 |
| 10 `PY LAB/lab.py sidecars --records R` | 先观察 Init 退出 11 阻止主容器，修正初始化命令并重建 Pod；再比较普通并列容器与 `initContainers[].restartPolicy: Always` 原生 Sidecar。校验共享卷轨迹中的启动、主容器结束、Sidecar 结束顺序。 |
| 11 `PY LAB/lab.py debug --records R` | 无 Shell 的 CoreDNS Pod 不能 exec `/bin/sh`；通过 restricted 临时 BusyBox 加入目标进程命名空间，检查同 Pod 网络、目标进程、正常 DNS、NXDOMAIN 和关闭端口。另用基准应用的 2 秒延迟区分慢请求与 1 秒客户端超时，最后还原延迟。检查应用默认 SA 没有调试授权。 |
| 12 `PY LAB/lab.py memory --records R` | worker02 上给容器 32Mi 内存上限、向内存 emptyDir 写 96Mi，验证 `OOMKilled`/137 后删除。实际触及容器内存上限，节点其他内存预算不变。 |
| 13 `PY LAB/pressure.py run --records R` | 见下一节。观察真实 MemoryPressure 与 memory 原因 Evicted，恢复配置 SHA、节点可调度/无压力及系统 Pod，再删除测试 Pod。 |
| 14 `PY LAB/lab.py termination --records R` | 先等待服务 Ready，再正常删除 Pod；校验 Completed/0 与 API 中绑定 Pod UID 的 TERM 终止消息，留存回执后释放 finalizer。删除后不依赖 CRI 日志。 |
| 15 `PY LAB/lab.py verify --records R` | 复核各阶段标记、压力恢复记录和终止回执，确认十节点健康、基准响应正常后输出验收 PASS。 |
| 16 `PY LAB/lab.py cleanup --records R` | 按本批 run 标签删除实验资源，再查询确认零残留并保存 cleanup-confirm.json；保留 lab-core、RBAC、其他对象和证据。 |

## 状态应该怎样理解

| 场景 | Pod phase | 容器 state / reason | 根因与修复 |
| --- | --- | --- | --- |
| 正常 HTTP | Running | Running | 进程在运行；本阶段只有最小 HTTP readiness。 |
| 正常一次性退出 | Succeeded | Terminated / Completed / 0 | `restartPolicy: Never`，任务正常完成。 |
| 主动退出 7 | Failed | Terminated / Error / 7 | 应用错误；应修正命令/配置，保留退出码和日志。 |
| 反复退出 7 | Running | Waiting / CrashLoopBackOff，lastState 为 Terminated | CrashLoopBackOff 是重启等待原因，不是 Pod phase；保存失败后修正 command 并重建。新 Pod UID 和 emptyDir 都会变化。 |
| 缺失镜像 | Pending | Waiting / ErrImageNeverPull | 故意使用不存在的镜像及 Never 拉取策略，稳定制造镜像错误而不访问仓库；修复为本地已有 Digest。它与尝试拉取后的 ImagePullBackOff 同属镜像层问题，但原因不同。 |
| CPU 请求 8 核 | Pending | 尚未创建容器，PodScheduled=False | worker01 Allocatable 为 7 核，调度器拒绝；降低 request 后重建 Pod。Pod 的 requests/command 通常不能像 image 一样原地更新。 |
| 容器超出 32Mi | Failed | Terminated / OOMKilled / 137 | 内核在 cgroup 上限内杀死进程，不能仅凭 137 就推断 OOM，必须同时看 reason。 |
| 节点软阈值触发 | Failed / Evicted | 退出状态由 kubelet 驱逐流程产生 | kubelet 主动回收资源；事件/Pod message 指向 memory。不是应用主动退出，也不是 API eviction/delete。 |
| 正常删除 | Terminating 为 CLI 展示；最后保存终态 | Terminated / Completed / 0 | TERM 处理完成并写入匹配 UID 的终止回执后退出；finalizer 只保留 API 对象。 |

Init 按顺序运行且成功后才能进入下一阶段。普通并列 Sidecar 尚未结束时，即使主容器退出，Pod 仍 Running；本实验通过共享 stop 文件让它协作退出。原生 Sidecar 使用 restartable init container，startupProbe 确认准备完成后主容器才启动，主容器结束后 kubelet 再终止 Sidecar；它不阻挡一次性 Pod 完成。资源预算必须同时考虑应用与并行 Sidecar，以及 Init 阶段的峰值。[Kubernetes 1.36 Sidecar 文档](https://v1-36.docs.kubernetes.io/docs/concepts/workloads/pods/sidecar-containers/)

临时容器使用专用子资源追加，结束后不能单独移除；本实验最终删除专用 Pod。API 不允许为它单独设置 resources，因此只运行固定、短时的诊断命令，使用非 root、drop ALL、RuntimeDefault，既不给 SYS_PTRACE/privileged，也不给应用 SA 权限。进程可见性依赖 containerd 对 target 的支持，本脚本必须实际看到 `/coredns` 才判通过。[临时容器文档](https://kubernetes.io/docs/concepts/workloads/pods/ephemeral-containers/)

无 Shell 应用的 `/coredns` 二进制带 NET_BIND_SERVICE 文件能力，沿用本集群 CoreDNS 的 drop ALL + add NET_BIND_SERVICE 配置；该项符合 restricted 标准，诊断容器本身仍 drop ALL。[该版本官方镜像定义](https://github.com/coredns/coredns/blob/v1.14.2/Dockerfile)

## worker02 驱逐是怎样触发和恢复的

这是**临时提高阈值的节点压力实验**，并未真实耗尽节点内存。只有 `pressure.py run` 才会修改 worker02 和重启它的 kubelet，其他阶段只创建受限 Pod；控制平面、infra、storage 不参与故障注入。

1. 确认 worker02 除系统关键 Pod 外没有其他负载，在其中运行有 160Mi 上限、实际写入 96Mi 内存卷的低优先级 Pod；一次 stat 校验后创建完成标记，探针仅检查标记，再 cordon 阻止新调度。
2. 读取 kubelet stats/summary 的 memory.available；真实余量至少 4GiB 才继续。临时软阈值取当时 available+16Mi，45 秒宽限，Pod 最大终止宽限 5 秒。保留全部原硬阈值与角色预留；不更改 Node Allocatable 的硬驱逐预算。
3. root 原配置以私有字节副本保存。先建立 150 秒 systemd 独立回退，再以 JSON（YAML 的兼容形式）写入临时 kubelet 配置并重启。不依赖节点安装 PyYAML/OpenSSL。
4. 记录 MemoryPressure=True、Pod Failed/Evicted 及 memory message；只出现删除/超时不判通过。kubelet 以真实 available 信号比较阈值，驱逐路径与资源耗尽时一致；本方法的通过范围不包括真实宿主机 OOM。
5. 正常结束、异常或 Ctrl-C 都进入恢复：逐字节还原并比对原 SHA，重启 kubelet，取消独立定时器，等待 Ready、压力消除，再 uncordon 和核对系统 Pod。发现配置被第三方改动时拒绝覆盖，保持 cordon 供检查。远端原配置副本和小型恢复脚本保留用于复盘，不存在持续压力进程。

Mac 断线时，定时器还原配置并恢复 kubelet，**保留 cordon**；恢复连接后执行下方 restore 完成健康核验/解除维护。实验记录同时包含节点 UID，防止把旧恢复材料写入重建后的同名节点。[节点压力驱逐机制](https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction/)

## 出错后如何查看、恢复和清理

已完成 prepare 的批次可以使用上面的 --resume 继续；先查看失败步骤的日志、对应 `*-observed*.json`、`*.events.json`、容器日志及 `pressure.json`。默认的 check/render 均不会启动实验。

```bash
# 只观察当前批次；不会删除 Pod。
"$HOME/.cnpl/bin/kubectl" --kubeconfig "$HOME/.cnpl-secrets/access/lab-primary/mac.conf" \
  --context lab-primary-lab-ops -n lab-core get pods -l app.kubernetes.io/part-of=cnpl-pod-lab -o wide
# 压力实验失败或 Mac 中断时先恢复。仅当本目录确有 pressure.json 时执行。
"$HOME/.venvs/cnpl-ansible/bin/python" ops/01-kubernetes/core-resources/pods/pressure.py restore --records "$CNPL04"
# 确认节点恢复后，只清理本批对象；失败批次也允许清理，不伪造验收 PASS。
"$HOME/.venvs/cnpl-ansible/bin/python" ops/01-kubernetes/core-resources/pods/lab.py cleanup --records "$CNPL04"
```

若停在 DNS 补测、还没有 state.json，先保留失败矩阵；确认后使用 `run.sh` 第 04 步的 delete 清理独立诊断 Namespace，不执行 lab cleanup。若换终端，先把 CNPL04 设回实际证据目录，不能把旧阶段目录当作本批。

## 交付验证与边界

脚本使用既有原生 Pod/ConfigMap/NetworkPolicy/配额和顺序编排，公共 Pod 字段只由一个模板生成；没有引入策略/工厂等额外架构。最初 18 份资源已做 server dry-run；本次增加终止专用 ConfigMap 后重新验证当前 19 份清单。没有自动部署新负载。离线回归覆盖资源边界、外来对象拒删、Crash/Init 无 exec 窗口恢复、过期 Pod 重试、继续入口跳过已通过步骤和原证据保留、压力轻量探针/准备失败安全重试、压力前检/失败回退、独立定时器先于变更、配置逐字节恢复和第三方漂移拒绝；本批 OOM、驱逐、CRI 临时容器、Sidecar 和修复后的 14–16 均已由用户实际执行通过；最终回执与清理记录已核验。有限信号测试和模拟 API 回归保留其验证边界，不代替实际证据。

app.sh 的 START_DELAY、健康标记和 0–5 秒 CGI 延迟保留用于复现本专题。下一专题需要真正的 HTTP/1.1 连接保留、长请求及消息排空，已另交付标准库 Go 应用与 [01.05 完整入口](../probes/README.md)，不把本 BusyBox 示例当作完整探针矩阵。
