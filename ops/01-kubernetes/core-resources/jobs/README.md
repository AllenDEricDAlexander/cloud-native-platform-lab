# 01.09 Job、CronJob 与基础 HPA

独立入口为 `scripts/stage-09.sh`，只执行 09。Job/CronJob 源码在本目录 `manifests/`，指标服务和 HPA 在 `../autoscaling/manifests/`，实际变更在 `ansible/tasks/core/stage-09*.yml`。指标准备说明见[安全指标入口](../autoscaling/README.md)。

## 一次给全的命令

```bash
# 1. 固定仓库位置。
cd /Users/mario/SelfProject/cloud-native-platform-lab
# 2. 建立 09 的独立记录目录。
CNPL09="$PWD/ops/01-kubernetes/records/core-07-10/runs/09-$(date -u +%Y%m%dT%H%M%SZ)"
# 3. 检查既有工具、编译测试应用、渲染 Job/CronJob/HPA/指标组件变体。
#    不签发 kubelet 证书、不镜像复制、不部署 Metrics Server 或实验 Pod。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-09.sh validate "$CNPL09"
# 4. 先完成安全指标准备，再执行 09 的批处理、真实分钟调度和扩缩容。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-09.sh run "$CNPL09"
```

预期先得到 `01.09 SOURCE VALIDATION PASS`，正式执行最终得到 `01.09 ACCEPTANCE PASS` 和 `01.09 CLEANUP PASS`。CronJob 使用真实分钟边界，HPA 等实际指标刷新和 30 秒稳定窗口；这一步通常需要数分钟，不能用 YAML 创建成功代替验收。

## 每组做什么

| 组 | 实际验收 |
| --- | --- |
| 可重试 Indexed Job | completions=3、parallelism=3、总时限 180 秒。每个序号先原子提交业务键到测试 ConfigMap，再主动退出 7；重试后 Complete，确认至少三次失败且三个键各只有一次效果。账本通过 resourceVersion 处理竞争，SA 只能 get/update 这一个 ConfigMap。 |
| 不可重试失败 | 退出 42，podFailurePolicy=FailJob；确认 Failed/PodFailurePolicy 和只有一个 Pod。 |
| 总时限 | sleep 超过 activeDeadlineSeconds；确认 Failed/DeadlineExceeded。 |
| 三种 CronJob | 先全部 suspend 创建，再在每分钟 35–40 秒时启用，避免顺序创建跨分钟；首次计划时间必须相同。Asia/Shanghai、每分钟一次、任务持续 90 秒；下一次同一计划时间实际观察 Allow 两个活动 Job、Forbid 仍保留原 Job、Replace 原 UID 消失并换新 UID。检查真实 owner UID 和 cronjob-scheduled-timestamp，不用手工 Job 代替调度。 |
| 暂停/错过调度 | suspend 跨过至少一个刻度；在分钟中段恢复且 startingDeadlineSeconds=20，确认超过期限的计划没有补跑，下一正常分钟恢复执行。保存历史与现场后清理调度器。 |
| CPU HPA | CPU request=50m，目标利用率 60%，1–4 副本；用 ConfigMap 切换受限 CPU 工作，确认真实扩容和就绪，再停止负载并观察稳定窗口后的缩容。 |
| 内存 HPA | memory request=32Mi，目标利用率 120%，最多四副本；每 Pod 受限分配 96Mi。持有模式不再做新工作但保留内存，指标仍支撑副本；明确释放后才验收缩容。 |
| 不可计算反例 | 独立应用明确 CPU request=0，仍有 500m 上限；先确认实际 Pod 指标存在，再确认 ScalingActive=False/FailedGetResourceMetric。该反例的 unknown 是预期失败，不混入正常 CPU/内存扩缩容 PASS。 |

测试账本不代表生产业务数据库的持久化或分布式事务保证，整个 `lab-p09` 在验收后回收。CronJob 也不提供严格恰好一次；示例通过业务键避免重试重复效果。

本集群使用 Cilium。公共 baseline 通过 namespaced CiliumNetworkPolicy 的 kube-apiserver 实体及 TCP 443/6443 放行本 run 的 API 请求；集群节点身份不能依靠默认 ipBlock 规则放行。该策略同时进入归属检查、快照和 Namespace 清理。Job 已进入与预期相反的终态时立即报告真实原因，不再等完整重试窗口。

Job 的首次退出 7、永久错误退出 42、DeadlineExceeded，以及零 CPU 请求 HPA 的 FailedGetResourceMetric 都是有意设置的反例；脚本必须确认预期原因后才通过。Ansible 的最终 `failed=0` 和两个总 PASS 才代表本阶段成功。

## 恢复与清理

```bash
# 同源码重试；原日志和 attempt 保留。本专题重做，已完成的 07/08 不重做。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-09.sh resume "$CNPL09"
# 放弃本批 Job/CronJob/HPA 时：回收 lab-p09，保留指标基础组件和已验证服务证书。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-09.sh cleanup "$CNPL09"
```

首次指标准备会串行处理十节点的 kubelet 服务证书、放行 Pod CIDR 到 10250 并安装 `cnpl-metrics`；保持 SELinux Enforcing 和 firewalld 启用。每台配置替换前有独立回退，只有实际 TLS/Ready 验证通过才提交。该基础组件是后续 HPA 的输入，成功后有意保留，区别于会被清理的实验工作负载。

正式运行会自动重启需要启用服务证书引导的节点 kubelet，逐节点进行；无需手动关闭 VM。CronJob 对齐、暂停与恢复、ConfigMap 投射和 HPA 指标刷新都包含实际等待，期间的等待重试最终必须收敛。运行日志和证据均保存在本批目录，成功后停止在 09。

证据包括 Job 退出状态/账本、CronJob 计划时间/实际 UID、HPA 的实际副本与新鲜 Pod 指标 JSONL。只有全部通过及清理后才发布 `completed/09.json`，然后可执行 01.10。

参考：[Job](https://kubernetes.io/docs/concepts/workloads/controllers/job/)、[CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)、[HPA](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/)。
