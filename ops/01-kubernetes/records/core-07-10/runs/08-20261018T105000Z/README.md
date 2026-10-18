# 01.08 删除传播、所有权与 Finalizer 实际验收

用户完成正式执行，Codex 于 2026-10-18 只读复核原始证据与当前集群。执行时源码提交为 `278e9bf`。本次归档保留原始日志、回执、清单和快照，不修改实验源码或旧记录。

## 执行身份与结果

- run：`20261018T105012Z-db7abb6a`；正式 attempt：`20261018T105042Z-a53720ec`。
- 集群 UID：`4d3e52d7-e203-4daf-aced-9c3a666fcf5b`，版本 `v1.36.5`。
- [源码校验日志](ansible-validate-20261018T105009Z-JAY2OP)包含 `01.08 SOURCE VALIDATION PASS`。
- [正式执行日志](ansible-run-20261018T105039Z-L2nmSJ)包含 `01.08 ACCEPTANCE PASS`、`01.08 CLEANUP PASS`，没有 `fatal`。localhost 为 `ok=229 changed=43`，两个 worker 各为 `ok=15 changed=0`；全部主机 `failed=0 unreachable=0 rescued=0 ignored=0`。
- [成功回执](passed.json)与[完成指针](../../completed/08.json)原字节一致，可作为 09 的同集群前置凭据。

## 实验与证据

完整证据位于本次正式 attempt；[复核结果](acceptance-review.json)记录五组现场快照与 18 项断言。

| 实验 | 实际观察与结论 | 关键证据 |
| --- | --- | --- |
| Foreground | Deployment 与 RS 都带删除时间和 foregroundDeletion；被本实验 Finalizer 阻挡的原 Pod 尚在，owner UID 链保持一致。释放自己的标记后整组对象消失。父对象等待阻挡删除的子对象。 | [删除过程快照](attempts/20261018T105042Z-a53720ec/snapshots/20261018T105118.014014Z/objects.json)、[整组清理](attempts/20261018T105042Z-a53720ec/observations/p08-foreground-gone.json) |
| Background | Deployment 已实际消失，原来的子 Pod 带删除时间且被自己的 Finalizer 暂时保留；解除标记后整组清理完成。父对象消失不等于后代已清理。 | [父对象消失](attempts/20261018T105042Z-a53720ec/observations/background-parent-gone.json)、[后代仍在](attempts/20261018T105042Z-a53720ec/snapshots/20261018T105129.350428Z/objects.json)、[整组清理](attempts/20261018T105042Z-a53720ec/observations/p08-background-gone.json) |
| Orphan 与接管 | Orphan 删除 Deployment 后 RS 留存并解除原父引用，Pod 仍由原 RS 控制。再 Orphan 删除 RS，确认无 owner 后由 p08-adopter 接管，两个原 Pod UID 从始至终保持相同。所有权处理沿直接引用关系进行，新建同名对象不能替代 UID 证明。 | [原父子链](attempts/20261018T105042Z-a53720ec/observations/orphan-before.json)、[RS 留存](attempts/20261018T105042Z-a53720ec/observations/orphan-rs-preserved.json)、[原 Pod 接管](attempts/20261018T105042Z-a53720ec/observations/orphan-adopted.json) |
| Finalizer 顺序 | p08-external 模拟外部资源先被删除，p08-finalizer 仍带删除时间与本实验标记；之后才解除该标记并确认对象消失。保护标记需要清理逻辑配合，不会自行执行外部清理。 | [先完成外部清理](attempts/20261018T105042Z-a53720ec/observations/external-gone.json)、[仍受保护现场](attempts/20261018T105042Z-a53720ec/snapshots/20261018T105149.240139Z/objects.json)、[最终删除](attempts/20261018T105042Z-a53720ec/observations/finalizer-gone.json) |

## 清理与只读复核

[Namespace 删除回执](attempts/20261018T105042Z-a53720ec/observations/namespace-deleted.json)为 `gone=true`。当前 `lab-p08` 已不存在，跨 Namespace 查询本 run 的公开实验资源为 0，无节点或临时集群授权恢复待办。十节点 Ready、无 Memory/Disk/PID Pressure，两个 worker 可调度且无污点，系统 Pod 健康。

264 个当前源码/版本锁摘要与原 context、passed 回执一致；07 的 101 个原始文件及更早 1183 个执行文件均按既有摘要复核未改变。本实验只使用自己的 Namespace 和模拟 ConfigMap，没有真实云资源或持久存储清理副作用。

## 归档范围

[证据 SHA-256 索引](evidence-sha256.json)覆盖归档前全部 57 个原始文件，共 28,419,131 字节。51 个公开文本证据入库；两次构建产生的 6 个应用二进制/OCI tar 原样留在本地，Git 仅记录其路径、大小与摘要。本目录 `.gitattributes` 防止 Git 归一化原始日志的换行和空白，入库内容须与原文件 SHA-256 一致。

下一专题为 [01.09 Job、CronJob 与 HPA](../../../../core-resources/jobs/README.md)。本次 08 归档没有启动 09 的正式实验。
