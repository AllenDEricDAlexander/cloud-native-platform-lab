# 02.08 整组交付复核

02.07 的真实验收与清理已归档并提交后，为完整 02.08 重新执行全部前检、配置预览和定向验证。正式资源实验由用户运行 `resource-governance.sh all`；本记录不代表实际 CPU/OOM/卷驱逐/抢占/PDB 已通过。

| 核验 | 结果 |
| --- | --- |
| 前序与 VM | 自动识别 02.07 的同集群 run 和两份回执摘要；十 VM Ready 且无压力；两 Worker 的 MemAvailable 大于 2Gi、kubelet 可用磁盘大于 10Gi |
| Ansible/YAML | 完整 validate 为 ok=5、changed=0、failed/unreachable/rescued/ignored=0；29 个对象严格服务端预览通过，未落地 |
| PriorityClass 引用 | 两个非默认负优先级类及 Pod 引用结构匹配；预览不创建类，引用的准入在正式 all 创建类后再次严格校验 |
| 诊断物料 | amd64/arm64 从锁定源码重建；二进制、源、公开 CA 和 OCI 摘要全部匹配，Harbor 匿名摘要读取通过 |
| 定向测试 | 资源验收器 4 项、共享框架 4 项通过；Go test -race、go vet、Shell 语法均通过 |
| 编排模型 | 真实 Ansible 的正常、观察失败、单命令失败和显式 recover 四种离线分支通过；两种注入失败均按预期返回失败并清理，后续命令没有误执行 |
| 范围和恢复 | 19 步串行、17 项实际验收；五临时 Namespace、两个负 PriorityClass、原 Node UID/字段/维护标记及 Pod 后代链保护；只按本批 run+app 标签 drain |
| 前检后复核 | 五个测试空间和两个测试 PriorityClass 均不存在；worker02 可调度且无维护标记，两 Worker Ready 且无压力 |

完整结果见 [delivery-review.json](delivery-review.json)，45 份一致输入快照见 `reviewed-source/`，逐项摘要见 [evidence-sha256.json](evidence-sha256.json)。原始预览、镜像重建和模型细节全部保留；`attempts/` 依仓库规则只保留本地。

本次核查未发现需要更改现有 Ansible/YAML 或验收代码的问题。复用已有 Session、声明式 cases 与 Ansible always 恢复路径，不新增依赖或编排层。

正式入口见 [完整操作指南](../../examples/resource-governance/README.md)：单条 all 覆盖配额/默认值/预期准入拒绝、QoS、CPU 限流、64Mi Pod OOM、32Mi 空卷驱逐、限定抢占和 PDB 驱逐/直接删除对照，并自动恢复。整 VM 压力下的 QoS 驱逐顺序保持 BLOCKED，`available_cases_passed` 与 `phase_complete` 分开判断。
