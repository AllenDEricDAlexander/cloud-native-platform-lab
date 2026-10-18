# 01.07 StatefulSet 与 DaemonSet 实际验收

用户在管理 Mac 完成执行，Codex 于 2026-10-18 只读复核原始证据与当前集群。源码提交为 `9902576`；本次归档没有修改执行脚本、清单或旧记录。

## 执行身份与结果

- run：`20261018T102324Z-2241f623`；正式 attempt：`20261018T102355Z-9b821389`。
- Namespace：`lab-p07`，原 UID `11bfa7c8-5c92-4965-ac32-be252bf39615`。
- 集群 UID：`4d3e52d7-e203-4daf-aced-9c3a666fcf5b`；版本 `v1.36.5`。
- [源码校验完整日志](ansible-validate-20261018T102322Z-73PbiL)包含 `01.07 SOURCE VALIDATION PASS`。
- [正式执行完整日志](ansible-run-20261018T102353Z-mwwmj2)包含 `01.07 ACCEPTANCE PASS`、`01.07 CLEANUP PASS`；没有 `fatal`。localhost 为 `ok=384 changed=82`，两个 worker 各为 `ok=19 changed=7`；全部主机 `failed=0 unreachable=0 rescued=0 ignored=0`。
- [成功回执](passed.json)与[完成指针](../../completed/07.json)原字节一致，可作为 08 的同集群前置凭据。

日志中的 `FAILED - RETRYING` 是等待控制器、就绪状态和删除收敛时的中间尝试，最终均通过。DaemonSet 的 `ErrImageNeverPull` 是主动注入坏镜像的预期反例，随后必须原生回滚且恢复两个就绪副本。

## 完成的实验与结论

下表路径均位于本次正式 attempt；[完整只读复核结果](acceptance-review.json)记录 23 份工作负载快照和 26 项证据断言。

| 实验 | 实际观察与学到的边界 | 关键证据 |
| --- | --- | --- |
| StatefulSet 序号、DNS 与重建 | 先有 `p07-state-0` 就绪，后创建 `-1`；删除 `-0` 后名称保持、UID 改变，原 Headless DNS 最终解析到新 Pod IP。 | [初始副本](attempts/20261018T102355Z-9b821389/observations/state-initial.json)、[重建副本](attempts/20261018T102355Z-9b821389/observations/state-recreated.json)、完整日志中的两次 DNS 断言 |
| emptyDir 生命周期 | 原 Pod 写入 UID 标记，新 Pod 的临时内容重新初始化为新 UID。稳定名称本身不提供持久化；本实验没有验证 PVC 或 Ceph。 | 完整日志中的“稳定名称不代表数据持久化”断言与同名不同 UID 快照 |
| OrderedReady 扩缩容 | `-1` NotReady 时期望扩到 3，实际仍为 2；恢复就绪后创建 `-2`。缩容先删除最高序号，再扩容得到新 UID 的 `-2`。 | [扩容阻挡](attempts/20261018T102355Z-9b821389/observations/ordered-blocked.json)、[缩容](attempts/20261018T102355Z-9b821389/observations/ordered-scaledown.json)、[再次扩容](attempts/20261018T102355Z-9b821389/observations/ordered-rescaled.json) |
| Parallel 对照 | `p07-parallel-0` NotReady 时，`-1/-2` 已创建且 Ready；解除阻挡后三个均就绪。 | [并行创建](attempts/20261018T102355Z-9b821389/observations/parallel-blocked.json)、[恢复](attempts/20261018T102355Z-9b821389/observations/parallel-restored.json) |
| StatefulSet 分区更新 | partition=1 时仅 `-1/-2` 使用 v2，`-0` 保持原 UID/v1；partition=0 后全部更新为 v2。 | [分区更新](attempts/20261018T102355Z-9b821389/observations/partition-v2.json)、[全部 v2](attempts/20261018T102355Z-9b821389/observations/state-all-v2.json) |
| StatefulSet OnDelete | 模板改为 v1 后旧 Pod 的 UID/v2 均保持；手动删除 `-2` 后仅它更新，继续手动删除 `-0/-1` 后全部为 v1。 | [保持原副本](attempts/20261018T102355Z-9b821389/observations/state-ondelete-unchanged.json)、[单序号更新](attempts/20261018T102355Z-9b821389/observations/state-ondelete-one.json)、[手动完成](attempts/20261018T102355Z-9b821389/observations/state-ondelete-complete.json) |
| DaemonSet 标签覆盖 | 标签依次只匹配 worker02、一个也不匹配、匹配两个 worker，实际就绪 Pod 数为 1→0→2。 | [一个](attempts/20261018T102355Z-9b821389/observations/daemon-one.json)、[零个](attempts/20261018T102355Z-9b821389/observations/daemon-zero.json)、[两个](attempts/20261018T102355Z-9b821389/observations/daemon-two.json) |
| 污点与精确容忍 | worker02 加本批 NoSchedule 后，删除它的实验 Pod，DaemonSet 只覆盖 worker01；增加本批 key/value/effect 的精确容忍后恢复两个。NoSchedule 本身不驱逐原有 Pod。 | [无容忍](attempts/20261018T102355Z-9b821389/observations/daemon-tainted.json)、[增加容忍](attempts/20261018T102355Z-9b821389/observations/daemon-tolerated.json) |
| DaemonSet 发布、失败回滚和 OnDelete | 滚动更新 v2；坏镜像真实进入 ErrImageNeverPull；按已验证 ControllerRevision 回滚恢复两个 v2。改 OnDelete/v1 后旧 UID/v2 保持，手动删除后变为两个新 UID/v1。 | [故障现场](attempts/20261018T102355Z-9b821389/snapshots/20261018T102708.171052Z/objects.json)、[回滚](attempts/20261018T102355Z-9b821389/observations/daemon-rollback.json)、[手动更新完成](attempts/20261018T102355Z-9b821389/observations/daemon-ondelete-complete.json) |

## 恢复、清理与当前状态

[运行中的节点恢复索引](attempts/20261018T102355Z-9b821389/observations/nodes-restored.json)保留原两个 worker UID；[Namespace 删除回执](attempts/20261018T102355Z-9b821389/observations/namespace-deleted.json)为 `gone=true`。只读复核进一步确认：

- 十节点 Ready、无 Memory/Disk/PID Pressure，系统 Pod 健康。
- `lab-p07` 已不存在；跨 Namespace 查询本 run 的公开实验资源，剩余数为 0。
- 两个 worker UID 与恢复索引相同，均可调度且无污点；所有节点都没有 `cnpl.io/core07` 实验标签或污点。`state/nodes.json` 待办已清除。
- cp01 上本 run 的独立回退 timer 为 `not-found/inactive/dead`；SELinux 为 Enforcing，firewalld 为 active。
- 264 个当前源码/版本锁摘要与原 context、passed 回执匹配；更早 1183 个原始记录按既有索引复核未改变。

## 归档范围与下一阶段

[证据 SHA-256 索引](evidence-sha256.json)覆盖归档前全部 101 个原始文件，共 30,068,814 字节。95 个公开文本证据随本次提交保存，包含原日志、回执、上下文、渲染清单、快照和观察结果。两次构建产生的 6 个应用二进制/OCI tar 继续原样保留在本地，Git 记录其路径、大小与摘要，不提交构建产物。没有改写或删除原始成功、失败或验证证据。

本目录 `.gitattributes` 仅针对本批原始证据关闭换行归一化和日志空白检查，保留 Ansible 输出原有的终端回车、行尾空格与末尾空行；归档时同时比较工作区文件与 Git 暂存内容的 SHA-256。

下一步按 [01.08 完整手册](../../../../examples/garbage-collection/README.md)建立独立 `08-...` 证据目录，先 `validate` 再 `run`。本次重新检查 08 shell 与 Ansible 入口语法均通过，且源码仍为已交付版本；08 的正式运行结果由独立阶段记录，本次没有启动它。
