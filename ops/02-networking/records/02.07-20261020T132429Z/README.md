# 完整 02.07 VM 调度验收与 02.08 交接

批次 `02.07-20261020T132429Z`，run `20261020T132431Z-95a3a4f1`。用户执行完整 all 后，16 项结果全部通过，`passed=true`、`phase_complete=true`，原节点字段和临时资源清理通过。

| 步骤 | 实际结果 |
| --- | --- |
| 02.07.01 | worker01/02 的 VM 标签和 hostname 拓扑验证通过；没有使用物理宿主机放置 |
| 02.07.02 | Required/Preferred、错误选择器、单 VM CPU 请求不足、标签变化后原 Pod 保留/新 Pod Pending，以及恢复调度通过 |
| 02.07.03 | NoSchedule、PreferNoSchedule、NoExecute 与无/5 秒/无限期容忍验证通过；原有 Pod 保持 |
| 02.07.04 | Required PodAffinity 同 VM；硬反亲和在两 VM 上两份 Ready、一份 Pending；软反亲和三份 Ready |
| 02.07.05 | maxSkew=1/minDomains=2 实际分布 2:1；单域限制与 ScheduleAnyway 对照通过 |
| 清理 | lab-scheduling 已删除；两个 Worker 和 storage03 的原 UID、标签、污点复核一致；既有资源 UID/spec 一致；主 .201 可信 TLS 返回预期 404 |

[完整原始日志](ansible-all-20261020T132429Z-zpeOnW)：localhost `ok=303 changed=82 unreachable=0 failed=0 skipped=2 rescued=0 ignored=0`。[原始验收](passed.json)、[清理回执](state/closed.json)、[归档复核](acceptance-review.json)和[额外只读复核](archive-live-review.json)相互一致。

36 份执行源码输入全部匹配，原样副本保存在 `execution-source/`。逐项 SHA256 见 [证据清单](evidence-sha256.json)。`attempts/` 的原始命令、对象、事件和 UID 证据按仓库规则保留本地，不改写、不删除；归档未重跑调度或改变节点。

[02.08 交接](handoff.json)允许同集群继续完整资源治理实验。02.08 正式 all 由用户启动；整 VM 资源压力排序的既有 BLOCKED 保留，不影响本阶段已经通过的调度验收。
