# 01.09 执行前脚本核验

08 的实际验收已归档提交 `9211eb3`，见[08 归档](../core-07-10/runs/08-20261018T105000Z/README.md)。本次在该提交上核验并修正 09；实际执行源码以[源码 SHA](source-hashes.json)和[最终 validate 上下文](validation-context.json)为准。没有启动 09 的正式 Job、CronJob、HPA 或 Metrics Server，也没有批准节点 CSR。

## 修正的时序问题

原流程顺序创建三个已启用的 CronJob，接近分钟边界时，首次调度可能落在不同分钟，随后并发策略比较会错位。现在复用源码已有的 `cron_suspend` 参数：

1. Ansible 先全部暂停创建；在每分钟 35–40 秒、超过原 30 秒错过期限后统一启用，等下一分钟真实调度。
2. 只读检查器要求首次三个计划时间一致；下一次对照时，Allow/Replace 的最新计划时间必须相同且已向前推进，同时保留 Forbid 原 UID、核验 Replace 原 UID 实际消失。
3. 校验目录增加 suspend 变体并传递参数；测试同时检查目录参数全部接入原生渲染入口，防止参数被静默忽略。

继续使用既有 YAML 源码、Ansible 编排和 Python 只读断言；没有增加依赖或新的执行框架。

## 已实际完成的核验

| 核验 | 结果与原始输出 |
| --- | --- |
| 原问题负向样本 | [修正前回归输出](cron-regression-before.txt)重现旧检查器未拒绝跨分钟样本；这是有限测试的预期失败，不是集群执行失败。 |
| Python 与原生证书测试 | [12 项最终测试](core-tests.txt)全部通过，覆盖计划时间错位、旧时间换新 UID 的假替换、目录参数转发、Job 终态原因、HPA 指标与实际副本、CSR 身份/SAN/用途/时效，以及真实 Ansible/OpenSSL 证书链、密钥匹配、权限与复用。私钥只在临时目录。 |
| Shell / Ansible 语法 | stage-09.sh、core-stage.sh 的 bash 语法及 [09 主入口语法](syntax-09.txt)通过。 |
| 最终真实 validate | [完整日志](validate-09.txt)包含 `01.09 SOURCE VALIDATION PASS`；20 个本专题公开变体实际渲染并通过严格结构校验，包含 [suspend=true 的真实渲染](cron-suspended-render.yaml)。应用有限 Go 测试、静态构建与 OCI 打包通过，264 个源码/版本锁摘要与最终上下文一致。全部主机 failed=0/unreachable=0。 |
| 真实服务端准入 | [完整日志](server-schema.txt)包含 `CORE SERVER SCHEMA AND CLEANUP PASS`；51 个公开变体做 server dry-run，控制器 PodTemplate 在实际 ResourceQuota/LimitRange 下做 Pod 准入。只实际创建临时 Namespace、SA、预算和模拟 ConfigMap，不运行工作负载；精确 Finalizer 清理后两个验证空间都消失。localhost 为 ok=798 changed=118 failed=0/unreachable=0。 |
| Linux 独立回退 | [worker02 夹具](recovery-fixture.txt)通过原字节回退、拒绝第三方修改、成功提交后不回退、timer 先回退后拒绝假提交；真实 kubelet 配置 SHA 和 PID 前后相同。systemctl 在夹具内部被替身拦截。 |
| 当前环境只读前检 | [十节点前置状态](prerequisites.json)确认服务证书引导尚未启用、无外来 Pending CSR、没有资源指标 API，SELinux Enforcing、firewalld active。Harbor 的 TLS 读取及固定 busybox 摘要已验证，管理员凭据文件存在且权限私有，未读取或输出其内容。 |

## 正式执行与清理边界

[09 完整手册](../../core-resources/jobs/README.md)给出四条完整命令。run 核对 08 的同集群成功回执后，按需串行准备十节点 kubelet 服务证书、精确放行 Pod CIDR 到 10250、镜像固定摘要并部署安全 Metrics Server，然后执行 Job、真实分钟调度与 CPU/内存 HPA。

每台节点配置变更前有 300 秒独立回退；只有精确 CSR 审核、真正 TLS 链/IP SAN 和 Ready 验证通过后才提交。实验 cleanup 删除 lab-p09；安全指标服务、服务证书与精确防火墙规则作为基础组件保留。仅在真实实验与清理均通过后发布 completed/09.json。本次有限核验没有写此回执。

07/08 原始日志、成功回执、完成指针和旧执行记录均保留，未因新源码修正改写历史。旧交付校验结果也保持原字节；新 09 使用独立目录绑定当前源码。

参考：[CronJob 计划时间、暂停及错过期限](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)、[Metrics Server v0.9.0 兼容与安全要求](https://github.com/kubernetes-sigs/metrics-server/blob/v0.9.0/README.md)、[官方最小采集授权](https://github.com/kubernetes-sigs/metrics-server/blob/v0.9.0/manifests/base/rbac.yaml)。
