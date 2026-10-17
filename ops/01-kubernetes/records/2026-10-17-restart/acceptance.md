# Phase 01 验收记录（进行中）

## 1. 范围与输入

执行日期：2026-10-17（管理 Mac）；执行批次 2026-10-17-restart。输入为 [版本锁](../../../versions.lock.yaml)、[引导配置](../../bootstrap/README.md)及用户实际入群输出。01.01–01.02 的配置、测试和脱敏证据随本次检查点归档；执行时使用对应工作区版本，不能用更早的 Git HEAD 代替执行输入。物理宿主机目前只登记 planned-hypervisor，实际故障域尚未独立核实。

本次先验收十节点基础健康、实际 kubelet/安全基线及普通 Pod 网络/Service/DNS；完整 Phase 01 的其余要求保留未执行。

## 2. 交付与用例

| 要求 / 步骤号 | 配置或脚本路径 | 测试入口与参数 | 预期结果 | 实际结果与证据 | 状态 |
| --- | --- | --- | --- | --- | --- |
| 01.02.06–07 十节点入群 | [Join 入口](../../ansible/playbooks/join-control-plane.yml) | 用户运行两个 join playbook | 全部 Ready、入群无失败 | [控制平面](evidence/01.02-join-control-plane-retry-20261017-123053.txt)、[七节点](evidence/01.02-join-workers-20261017-123816.txt)、[只读现场](evidence/01.02-cluster-baseline-readonly.txt) | 通过 |
| 01.02.01 实际角色预算、DNS/cgroup/PID | [verify-hosts.yml](../../ansible/playbooks/verify-hosts.yml) | 只读检查实际 kubelet 配置 | 与台账一致 | [十节点实际配置](evidence/01.02-ten-node-effective-config.txt) 全部 changed=0/failed=0/unreachable=0 | 通过 |
| 安全基线与 CRI 网络状态 | 同上 | Enforcing、服务 active、CRI 两 Ready=true | 十节点全部满足 | 同上 | 通过 |
| Cilium/CoreDNS/系统组件 | [Cilium 配置](../../bootstrap/cilium/cilium-values.yaml) | status、workload/Pod 状态 | DS 各 10/10，operator/DNS 各 2/2 | [只读现场](evidence/01.02-cluster-baseline-readonly.txt) | 通过 |
| 正常态三 API/VIP 与 etcd | [基础验收手册](../../bootstrap/acceptance/README.md) | 各端点 readyz、etcd health/status | 四 API 可用，三 etcd healthy，单 leader/无 learner | [只读现场](evidence/01.02-cluster-baseline-readonly.txt) | 通过 |
| 普通 Pod 十节点双向 HTTP | [临时清单](../../bootstrap/acceptance/network-smoke.yaml)、[检查入口](../../bootstrap/acceptance/check-network.py) | 用户部署后执行 | 100 条路径成功，其中 90 跨节点 | [真实网络矩阵](evidence/01.02-acceptance-20261017-125334/14-network-matrix.txt) NETWORK ACCEPTANCE PASS | 通过 |
| 01.03.01 Service 与内外 DNS | 同上 | 每个节点四 DNS、两 Service HTTP | 地址正确且 HTTP 后端身份正确 | 同一矩阵：40 DNS 检查、20 Service HTTP 全通过 | 通过 |
| 临时资源清理 | 同上 | 成功后 delete、查询 Namespace | 专用 Namespace 和测试资源清理 | [删除记录](evidence/01.02-acceptance-20261017-125334/17-network-cleanup.txt)、[空查询](evidence/01.02-acceptance-20261017-125334/18-cleanup-confirm.txt) | 通过 |
| 01.02.04 加密/审计恢复材料完整性 | [配置职责](../../bootstrap/README.md) | 共享策略已准备；补密钥备份和恢复验收 | 共享配置一致，恢复材料可用 | 既有配置前检不代表备份/恢复已验收 | 未完成 |
| 01.02.08 受限身份与恢复管理员 | [身份配置手册](../../bootstrap/access/README.md) | configure-access / verify-access / backup-access | 身份、默认 Context、恢复与备份可用 | [真实权限](evidence/01.02-access-20261017-131508/02-access-verification.txt)、[恢复入口](evidence/01.02-access-20261017-131508/04-recovery-direct-api.txt)、[.16 取回](evidence/01.02-access-20261017-131508/05-access-backup-restore.txt)均 PASS；Mac 默认只读 | Mac/证书包通过；.15 分发待交付 |
| 01.03.02–03 HA 与完整备份/隔离恢复 | 同上 | 备份验证后单控制平面停机 | 故障期间 API/调度可用并恢复 | 正常态健康不替代故障实验 | 未执行 |
| 01.04–01.10 其余核心资源实验 | 同上 | 按 47 步逐项实施 | 全部要求有真实证据 | 当前仅推进基础集群 | 未执行 |

## 3. 恢复与清理

用户已完成普通 Pod 网络验收并清理临时 Namespace；真实身份验收的临时 ConfigMap 也已清理。五份独立证书、默认只读配置、恢复直连和集群外加密备份取回均通过。没有执行控制平面停机实验；恢复文件备份不等同于完整 etcd/PKI/Secret 加密密钥备份。

## 4. 未完成项与结论

主线：十节点基础健康、普通 Pod 网络、Service/DNS、Mac 受限身份及恢复入口通过，可进入 01.03 完整控制平面备份和 HA 实验。规划中的 .15 管理机实际分发/登录保留待办。Phase 01 **未完整完成**；不宣称物理故障域、HA 或完整控制平面数据恢复验收通过。
