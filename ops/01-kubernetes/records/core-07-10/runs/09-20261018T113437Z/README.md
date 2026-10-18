# 01.09 Job、CronJob 与 HPA 实际验收

用户在原目录完成 resume。run 为 `20261018T113444Z-f130c045`，成功 attempt 为 `20261018T121140Z-99aca522`；执行源码为 `c5a0ffd`。集群 UID 为 `4d3e52d7-e203-4daf-aced-9c3a666fcf5b`，版本 `v1.36.5`。

[完整成功日志](ansible-run-20261018T121137Z-9KykT9)包含 `01.09 ACCEPTANCE PASS`、`01.09 CLEANUP PASS`；localhost 为 ok=436 changed=83，两个 worker 各为 ok=15 changed=0，十节点指标准备直接复用。全部主机 failed=0/unreachable=0/rescued=0/ignored=0。[成功回执](passed.json)与[完成指针](../../completed/09.json)原字节一致。

## 实验与证据

[33 项完整复核](acceptance-review.json)核对下列结果；下表文件均位于成功 attempt。

| 实验 | 实际结果 | 关键证据 |
| --- | --- | --- |
| Indexed Job 幂等重试 | 三个序号各有退出 7 与重试退出 0；succeeded=3、failed=3、completedIndexes=0-2。账本的三个业务键各为 1，区分了尝试次数和业务效果次数。 | [Job/退出码](attempts/20261018T121140Z-99aca522/observations/job-retry-complete.json)、[账本快照](attempts/20261018T121140Z-99aca522/snapshots/20261018T121327.603728Z/objects.json) |
| 不可重试失败 | 退出 42 命中 podFailurePolicy，只有一个 Pod，Failed 原因为 PodFailurePolicy。 | [不可重试结果](attempts/20261018T121140Z-99aca522/observations/job-permanent.json) |
| 总时限 | Job 进入 Failed/DeadlineExceeded，未把调度、镜像或一般错误当作超时通过。 | [总时限结果](attempts/20261018T121140Z-99aca522/observations/job-deadline.json) |
| 三种 CronJob | Asia/Shanghai，首次计划均为 20:15；20:16 时 Allow 两个活动 Job，Forbid 保留首次 UID，Replace 原 UID 消失并产生新 UID。 | [首次调度](attempts/20261018T121140Z-99aca522/observations/cron-first.json)、[并发对照](attempts/20261018T121140Z-99aca522/observations/cron-overlap.json) |
| 暂停与错过期限 | suspend 跨分钟；以 20 秒 startingDeadline 在分钟中段恢复，未补跑超期计划，下一正常分钟继续调度。 | 成功日志中的原生断言、[恢复后的 CronJob](attempts/20261018T121140Z-99aca522/observations/cron-resumed.json) |
| CPU HPA | 实际就绪副本 1→3→1，当前 CPU 指标可用，HPA desired、Deployment spec 和 Ready 副本一致，最大值为 4。 | [扩容](attempts/20261018T121140Z-99aca522/observations/cpu-scaleup.json)、[缩容](attempts/20261018T121140Z-99aca522/observations/cpu-scaledown.json)及同名 JSONL |
| 内存 HPA | 1→3；应用进入 hold 后仍保留内存，实际为 4 个就绪副本；释放后回到 1。停止新工作不等于释放内存。 | [扩容](attempts/20261018T121140Z-99aca522/observations/memory-scaleup.json)、[持有](attempts/20261018T121140Z-99aca522/observations/memory-held.json)、[释放缩容](attempts/20261018T121140Z-99aca522/observations/memory-scaledown.json) |
| 零 CPU 请求反例 | 原记录观察到指标失败，但 HPA 消息尚停留在临时缺指标；复核后收紧检查并独立补证 request=0 的零分母分支，补测已清理。 | [原因修正、15 项测试及实际补证](../../../2026-10-18-stage09-acceptance/README.md) |

## 清理与当前健康

`lab-p09` 已实际消失，[删除回执](attempts/20261018T121140Z-99aca522/observations/namespace-deleted.json)为 gone=true。十节点 Ready，无 Memory/Disk/PID Pressure，两个 worker 可调度且无污点，系统 Pod 健康。

Metrics Server 的两个副本、信任链、服务证书引导和精确防火墙规则作为基础组件保留；[清理后指标](attempts/20261018T121140Z-99aca522/observations/metrics-after-cleanup.json)和归档时只读检查均确认十节点新鲜指标。版本锁已登记 deployed_verified，版本及镜像摘要保持原值。

## 历史与归档范围

首次 API 请求超时的失败现场、[修复与有限真实 Job 验证](../../../2026-10-18-stage09-api-egress-fix/README.md)、来源修订和成功 attempt 都保留。执行时的 264 个来源摘要与 c5a0ffd 的 Git 原字节一致；完成后增加的反例原因检查有独立补证，没有改写原 passed/context 的源码绑定。

首次失败前 57 个原件全部可按修复前索引追溯：旧 context 在 `origin/api-egress-fix-0001/context.json`；resume 更新过的 Namespace UID 指针，其原字节从已有 Git 提交恢复到 `origin/pre-resume-09/state/namespace.json`。当前 `state/namespace.json` 记录成功 attempt 实际创建、随后已删除的新 Namespace UID。

[归档前证据索引](evidence-sha256.json)覆盖 198 个文件，共 59,376,745 字节，其中 186 个公开文本文件入库；四次构建产生的 12 个应用二进制/OCI tar 原样保留在本地，仅提交其路径、大小与摘要。原始终端日志换行和空白保留。

下一专题为 [01.10 配置、Secret、身份与交接](../../../../core-resources/config/README.md)，使用独立 10-... 目录及 09 完成指针作为前置条件。
