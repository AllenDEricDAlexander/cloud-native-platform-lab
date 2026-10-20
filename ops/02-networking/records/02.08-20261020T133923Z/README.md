# 02.08 可执行项验收与 02.09 交接

批次 `02.08-20261020T133923Z`，run `20261020T133924Z-c6b62b72`。用户完整 all 的 17 项可运行结果及清理通过。整 VM 压力下的 QoS 驱逐顺序保持 BLOCKED，`available_cases_passed=true`、`passed=false`、`phase_complete=false`。

| 步骤 | 实际结果 |
| --- | --- |
| 02.08.01 | 三个预算空间的 Quota/LimitRange、默认值注入、配额超限与 LimitRange 超限的具体拒绝原因验证通过 |
| 02.08.02 | 实际 Guaranteed/Burstable/BestEffort 分类通过；受控内存负载触发 OOMKilled/137，VM 无内存压力 |
| 02.08.03 | 100m CPU 限流的 nr_throttled 增加 80，throttled_usec 增加 7897282；32Mi 空卷写入触发 scratch 超出16Mi限额的 Evicted，VM 无磁盘压力 |
| 02.08.04 | 两个负 PriorityClass 的实际抢占仅移除本批低优先级 reserve Pod，并记录原 UID 与抢占事件 |
| 02.08.05 | minAvailable=2 阻止限定标签的 drain；改为1后允许驱逐，服务探测成功；恢复调度及双副本；直接删除对照通过 |
| 清理 | 五个临时 Namespace、两个实验 PriorityClass 已删除；worker02 原 UID/cordon 字段恢复、维护标记撤销；既有资源基线一致；主 .201 可信 TLS 返回预期404 |

[完整原始日志](ansible-all-20261020T133923Z-XdXaNY)：localhost `ok=308 changed=82 unreachable=0 failed=0 skipped=3 rescued=0 ignored=0`。[原始验收](passed.json)、[清理回执](state/closed.json)、[归档复核](acceptance-review.json)和[额外只读复核](archive-live-review.json)一致。

45 份执行输入摘要全部匹配，原样副本保存在 `execution-source/`；逐项 SHA256 见 [证据清单](evidence-sha256.json)。`attempts/` 的 cgroup 计数、原始命令、事件、对象和 UID 证据按仓库规则保留本地，不改写、不删除。归档未重跑压力、抢占或驱逐。

[02.09 交接](handoff.json)允许在同一主集群基线上继续独立 kind 数据面对照；Docker Desktop 的启动和完整 02.09 all 由用户执行。该隔离实验不补全主集群 Egress Gateway 或整 VM 压力的既有缺口。
