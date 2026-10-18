# 01.10 配置、身份与阶段交接实际验收

用户已完成正式运行。run 为 `20261018T132021Z-f5b9bd22`，成功 attempt 为 `20261018T132117Z-297e2f6a`；执行源码为 `4d7a3da`。集群 UID 为 `4d3e52d7-e203-4daf-aced-9c3a666fcf5b`，版本 `v1.36.5`。

[完整运行日志](ansible-run-20261018T132113Z-koUsto)包含 `01.10 ACCEPTANCE PASS`、`01.10 CLEANUP PASS`；localhost 为 ok=620 changed=137，两个 worker 各为 ok=15 changed=0。全部主机 failed=0/unreachable=0/rescued=0/ignored=0。[源码校验日志](ansible-validate-20261018T132018Z-hgCDdT)包含 SOURCE VALIDATION PASS。[成功回执](passed.json)与[完成指针](../../completed/10.json)原字节一致。

## 实验与证据

[76 项归档复核](acceptance-review.json)核对源码、实际结果、清理和当前健康；下表文件均来自正式成功 attempt。

| 实验 | 实际结果 | 关键证据 |
| --- | --- | --- |
| ConfigMap 注入与传播 | 初始 env、普通卷、subPath 均为 v1；更新后普通卷变为 v2，原 Pod 的 env/subPath 仍为 v1；重建 Pod 后三者均为 v2，UID 改变。 | [普通卷刷新结果](attempts/20261018T132117Z-297e2f6a/observations/config-volume-refreshed.json)、[重建后 Pod](attempts/20261018T132117Z-297e2f6a/observations/config-after-recreate.json)及运行日志断言 |
| 不可变配置 | 更新不可变 ConfigMap 的服务端准入被明确拒绝；最终配置仍为 immutable=true、value=v1。 | 运行日志中的 immutable 断言、[最终公开对象](attempts/20261018T132117Z-297e2f6a/snapshots/20261018T132740.697468Z/objects.json) |
| Secret、TLS 与轮换 | 应用认证允许/拒绝对照通过，TLS 私钥对、CA 和 DNS SAN 校验通过；轮换后卷中凭据更新而旧 env 保留，重建后重新匹配。消费者关闭默认 Token 挂载。 | 运行日志中的 Secret/TLS 检查、[最终消费者](attempts/20261018T132117Z-297e2f6a/observations/secret-after-recreate.json)；未归档凭据正文 |
| 私有镜像认证与轮换 | 错误凭据实际触发 ErrImagePull 和 401 Unauthorized；第一代拉取成功，撤销旧账号后第二代在新 repository scope 拉取成功，两次均使用完整摘要且在 worker01 执行完成。 | [认证失败事件](attempts/20261018T132117Z-297e2f6a/snapshots/20261018T132553.063221Z/events.json)、[第一代成功](attempts/20261018T132117Z-297e2f6a/observations/pull-v1-complete.json)、[第二代成功](attempts/20261018T132117Z-297e2f6a/observations/pull-v2-complete.json) |
| 最小 SA/RBAC 边界 | 九次真实 API 请求符合预期：允许读取 Pod、节点和本空间配置；拒绝 Secret 读取、越权删除及跨空间访问；授权删除成功；匿名返回 403，错误 audience 返回 401。拒绝删除的对象 UID 保持不变。 | [HTTP 状态汇总](acceptance-review.json)、成功 attempt 的 `observations/rbac-*.json` 和运行日志 UID 断言 |
| 显式 Token 与对象绑定 | 四种有 Token 的消费者显式指定 audience 和 600 秒期限；匿名消费者无 Token。绑定 reader Pod 的 Token 在删除前认证通过，删除原 Pod 后同一 Token 失效。 | [Bound Token 生命周期](attempts/20261018T132117Z-297e2f6a/observations/bound-token-lifecycle.json)及身份 Pod 观测 |
| 核心阶段交接 | 03–06 的 26 个断点、07/08/09 同集群回执齐全；三个 API 返回 ok，三个 etcd 端点健康，指标 API 正常。引用既有 HA 证据，本次没有重复关机实验。 | [交接前检查](attempts/20261018T132117Z-297e2f6a/observations/handoff-before-cleanup.json)、[清理后的交接索引](handoff.json) |

## 清理与当前健康

归档时再次只读确认：十节点 Ready，无 Memory/Disk/PID Pressure，两个 worker 可调度且无污点，系统 Pod 健康；三个 API 均返回 ok。安全指标组件 `cnpl-metrics` 保留，两个副本就绪，十节点指标新鲜，未开启不安全 TLS 参数。

`lab-p10` 已消失，所有 Namespace 中按本 run 标签查询的公开资源为 0；两个临时 ClusterRole 和一个 ClusterRoleBinding 均不存在。Harbor 测试项目和最终撤销的机器人账号查询均返回 404；第一代账号在轮换步骤已明确撤销。[Harbor 清理回执](attempts/20261018T132117Z-297e2f6a/observations/harbor-cleaned.json)和[集群授权清理索引](attempts/20261018T132117Z-297e2f6a/observations/cluster-objects-cleaned.json)保留公开归属信息。

两台 worker 的两个本次私有镜像别名均已移除，共享 bootstrap/busybox 摘要引用保留；本 run 的私有凭据目录和待清理状态索引已不存在。公开证据未包含 Secret 正文、私钥或 JWT。

## 归档范围与进度

[证据 SHA-256 索引](evidence-sha256.json)覆盖归档前的 98 个原件，共 28,703,798 字节，其中 92 个公开文本文件入库。两次构建产生的 6 个二进制/OCI tar 原样保留在本地，仅登记路径、大小与摘要。原始日志的换行和空白保留，执行时 264 个来源摘要与 `4d7a3da` 的 Git 原字节一致。

另外复核了 1,183 个旧批次原始文件，以及 07/08/09 的 101/57/198 个归档原件，摘要全部保持不变。执行前的[独立核验记录](../../../2026-10-18-stage10-review/README.md)保留原有结论，与本次完整正式运行分别追溯。

01.03–01.10 核心实验现已全部验收并清理。[交接索引](handoff.json)将后续阶段记为 02，同时明确 `persistent_storage_verified=false`；本次归档未启动下一阶段，01.02.15 管理机实际分发仍待交付。
