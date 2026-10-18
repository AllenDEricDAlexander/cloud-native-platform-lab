# 02.02.01 ClusterIP 与 EndpointSlice 实际验收

正式 run 为 `20261018T152116Z-641876dc`，成功 attempt 为 `20261018T152127Z-477adbe2-run`，清理 attempt 为 `20261018T153013Z-bea0ee50-cleanup`。原集群 UID 为 `4d3e52d7-e203-4daf-aced-9c3a666fcf5b`。

[正式运行日志](ansible-run-20261018T152125Z-r8y3Sr)和[清理日志](ansible-cleanup-20261018T153012Z-uxp20g)分别包含 ACCEPTANCE PASS、CLEANUP PASS；具体文件名及完整 recap 以 [acceptance-review.json](acceptance-review.json)中的索引为准。Mac 与两台 worker 的 failed/unreachable/rescued/ignored 均为 0。

## 五阶段实际结果

| 阶段 | Pod / Ready 端点 | 请求 |
| --- | --- | --- |
| initial | 2 / 2 | 30 次全部通过 |
| expanded | 3 / 3 | 30 次全部通过 |
| not-ready | 3 / 2 | 30 次全部命中仍就绪的端点 |
| restored | 3 / 3 | 30 次全部通过 |
| scaled-down | 2 / 2 | 30 次全部命中当前端点 |

两台客户端分别通过 ClusterIP、FQDN 和短名发起共 150 次请求，HTTP 状态与真实后端 UID 均通过。Service UID 始终为 `dfc255e2-6a6a-4f4e-bfdc-e31ab671a8f8`，ClusterIP 始终为 `192.168.20.216`。

Readiness 目标为 `svc-echo-679df6d569-97k5w`，UID 为 `dac94ba6-e59b-4c7a-98b2-76d0659376df`。摘除与恢复期间 Pod 保持 Running，UID 和容器重启计数保持不变。

原 [passed.json](passed.json)记录实验通过，原 [state/closed.json](state/closed.json)独立记录清理通过；不改写原实验回执中的 `cleanup_passed=false`。归档时只读确认十节点仍 Ready，`lab-service-clusterip` 已不存在。Hubble、管理控制台、原主机规则与缓存均保留。

## 源码、原件与下一批

运行时 18 个源码/输入摘要与整理前工作区逐一匹配，代码当时尚未提交，Git 基线为 `f7b0811`；本次提交首次收录这套实际运行代码。将更新的操作说明原字节保存在 `execution-source/`，其余源码随本提交保留。

[evidence-sha256.json](evidence-sha256.json)登记整理前的 64 个原件，原字节全部保持不变。`attempts/` 按现有 ignore 规则保留本地，公开验收摘要、日志、回执、交接和校验索引入库。初次失败批次与修复证据仍分别保留，不覆盖为本次成功。

[handoff.json](handoff.json)与[完成指针](../completed/02.02.01.json)原字节一致。按用户要求，后续 **02.02.02–02.02.06 合并为统一批次**，剧本分开，但整组一次校验、执行和清理。
