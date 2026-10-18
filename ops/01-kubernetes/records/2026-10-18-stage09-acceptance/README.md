# 01.09 完成复核与零请求原因补证

正式实验、来源修订及清理结果见[原目录验收归档](../core-07-10/runs/09-20261018T113437Z/README.md)。本目录补充归档复核时发现的反例原因时序问题，用户原始回执与旧源码绑定保持原字节。

原 `zero-request-observed.json` 的 ScalingActive=False/FailedGetResourceMetric 消息仍为目标 Pod 指标尚未收到。即使当时只读采样已经获得新鲜指标，HPA 控制器自己的上一轮状态仍可能落后，不能直接归因为 request=0。

检查器现要求 Kubernetes v1.36.5 的零分母分支消息 `no metrics returned matched known pods`，同时继续核对真实 Pod CPU request=0 和新鲜 Pod 指标。[控制器源码](https://github.com/kubernetes/kubernetes/blob/v1.36.5/pkg/controller/podautoscaler/metrics/utilization.go)说明 requestsTotal=0 的此分支；[副本计算源码](https://github.com/kubernetes/kubernetes/blob/v1.36.5/pkg/controller/podautoscaler/replica_calculator.go)区分了尚未收到目标指标的分支。

[15 项最终测试](core-tests.txt)通过，新增拒绝临时缺指标假阳性的用例。[有限补证夹具](../../tests/core-zero-request-smoke.yml)复用实际 baseline、资源预算及零请求 HPA，容器只执行 `/core-lab sleep 180`，无需 HTTP 服务；结束始终取证并精确清理。

[最终实际补证日志](zero-request-smoke.txt)包含 `ZERO CPU EXACT CAUSE PASS`；[精确原因与真实指标](zero-evidence/attempt/observations/zero-exact-cause.json)同时记录 CPU request=0 的应用、PodMetrics 和 HPA 的零分母消息。临时空间已回收，见[删除回执](zero-evidence/attempt/observations/namespace-deleted.json)。初轮夹具使用 240 秒超过应用既定 180 秒上限而被拒绝，原日志与现场保留在 `*-initial`；修正夹具后完成上述实际补证，未放宽验收。

该补证只修正检查器并补足一项原因证据；09 的原始全阶段 PASS、失败现场、成功 attempt 和 Namespace UID 历史均保留。版本锁仅登记 Metrics Server 已部署实测的事实，未更换版本或摘要。01.10 尚未开始正式实验。
