# Phase 01 验收记录（进行中）

## 1. 范围与输入

执行日期：2026-10-17（管理 Mac）；执行批次 2026-10-17-restart。输入为 [版本锁](../../../versions.lock.yaml)、[引导配置](../../bootstrap/README.md)及用户实际入群输出。01.01–01.03 的配置、测试和脱敏证据随检查点归档；执行时使用对应工作区版本，不能用更早的 Git HEAD 代替执行输入。物理宿主机目前只登记 planned-hypervisor，实际故障域尚未独立核实。

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
| 01.03.01 Service 与内外 DNS | 同上 | 每个节点四 DNS、两 Service HTTP | 地址正确且 HTTP 后端身份正确 | 01.02 矩阵：40 DNS、20 Service HTTP 通过；[01.03 短名补测](evidence/01.03-20261017-183105/06-dns-smoke.txt)失败，BusyBox 指定服务器会跳过 search，修正后待补测 | 原矩阵通过；短名待补测 |
| 临时资源清理 | 同上 | 成功后 delete、查询 Namespace | 专用 Namespace 和测试资源清理 | [删除记录](evidence/01.02-acceptance-20261017-125334/17-network-cleanup.txt)、[空查询](evidence/01.02-acceptance-20261017-125334/18-cleanup-confirm.txt) | 通过 |
| 01.02.04 加密/审计恢复材料完整性 | [配置职责](../../bootstrap/README.md) | 完整控制平面备份/取回 | 共享配置一致，恢复材料可用 | [真实凭据](evidence/01.03-20261017-183105/backup/backup-receipt.json)：三节点配置/PKI、加密密钥及审计策略归档并整包取回；离线快照展开通过。未验证在线重建后的审计/Secret 解密行为 | 恢复材料通过；在线恢复待后续 |
| 01.02.08 受限身份与恢复管理员 | [身份配置手册](../../bootstrap/access/README.md) | configure-access / verify-access / backup-access | 身份、默认 Context、恢复与备份可用 | [真实权限](evidence/01.02-access-20261017-131508/02-access-verification.txt)、[恢复入口](evidence/01.02-access-20261017-131508/04-recovery-direct-api.txt)、[.16 取回](evidence/01.02-access-20261017-131508/05-access-backup-restore.txt)均 PASS；Mac 默认只读 | Mac/证书包通过；.15 分发待交付 |
| 01.03.02–03 HA 与完整备份/隔离恢复 | [操作脚本](../../operations/README.md) | 完整备份/离线展开/取回后，观测单 VM 停机 | 故障期间 API/调度可用并恢复 | [备份凭据](evidence/01.03-20261017-183105/backup/backup-receipt.json)、[HA 输出](evidence/01.03-20261017-183105/09-ha-watch.txt)、[观测状态](evidence/01.03-20261017-183105/ha/state.json)：cp01 停机、cp03 接管、新 Pod 调度通过；应用失败 0，API 失败采样 1/97；恢复/清理 PASS | 通过（单 VM/离线展开范围） |
| 01.04–01.10 其余核心资源实验 | 同上 | 按 47 步逐项实施 | 全部要求有真实证据 | 当前仅推进基础集群 | 未执行 |

## 3. 恢复与清理

用户完成普通网络与身份临时资源清理；01.03 的 [诊断资源](evidence/01.03-20261017-183105/07-dns-smoke-cleanup.txt)和 [HA 资源](evidence/01.03-20261017-183105/11-ha-cleanup.txt)也已清理。备份 run 为 `20261018T001028Z-0266aefd`，.16 restic 快照 `d32beb9a9e69a889e4301c07dffce0006e9f749083c8b08ef2d92fada341eea5`；snapshot revision 115931，12MiB，离线展开及整包逐文件取回验证通过。三节点私有材料与真实 snapshot 均不入 Git。UTC 时间跨至 10 月 18 日，对应管理 Mac 的 10 月 17 日晚间。

## 4. 未完成项与结论

备份/取回、离线快照展开、CoreDNS 分散及单 VM HA 已通过；01.03.01 短名补测失败已修正，待真实重跑。可准备 01.04，执行其新实验前先补测 DNS。规划 .15 管理机分发/登录仍待交付。Phase 01 **未完整完成**；实际物理故障域、启动新 etcd 的在线隔离服务恢复、整集群灾难重建及恢复后 Secret/审计行为不属于本次通过范围。
