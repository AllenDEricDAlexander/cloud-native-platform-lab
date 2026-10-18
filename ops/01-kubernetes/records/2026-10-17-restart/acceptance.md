# Phase 01 验收记录（进行中）

## 1. 范围与输入

执行日期：2026-10-17（管理 Mac）；执行批次 2026-10-17-restart。输入为 [版本锁](../../../versions.lock.yaml)、[引导配置](../../bootstrap/README.md)及用户实际入群输出。01.01–01.04 的配置、测试和脱敏证据随检查点归档；执行时使用对应工作区版本，不能用更早的 Git HEAD 代替执行输入。物理宿主机目前只登记 planned-hypervisor，实际故障域尚未独立核实。

本批已验收十节点基础健康、kubelet/安全基线、普通网络/Service/DNS 原矩阵、Mac 受限身份、完整备份/取回及单 VM HA。短名 DNS 已在 01.04 开头补测通过；01.04.01–05 已完成真实验收和清理，其余要求以表中实际状态为准。

## 2. 交付与用例

| 要求 / 步骤号 | 配置或脚本路径 | 测试入口与参数 | 预期结果 | 实际结果与证据 | 状态 |
| --- | --- | --- | --- | --- | --- |
| 01.02.06–07 十节点入群 | [Join 入口](../../ansible/playbooks/join-control-plane.yml) | 用户运行两个 join playbook | 全部 Ready、入群无失败 | [控制平面](evidence/01.02-join-control-plane-retry-20261017-123053.txt)、[七节点](evidence/01.02-join-workers-20261017-123816.txt)、[只读现场](evidence/01.02-cluster-baseline-readonly.txt) | 通过 |
| 01.02.01 实际角色预算、DNS/cgroup/PID | [verify-hosts.yml](../../ansible/playbooks/verify-hosts.yml) | 只读检查实际 kubelet 配置 | 与台账一致 | [十节点实际配置](evidence/01.02-ten-node-effective-config.txt) 全部 changed=0/failed=0/unreachable=0 | 通过 |
| 安全基线与 CRI 网络状态 | 同上 | Enforcing、服务 active、CRI 两 Ready=true | 十节点全部满足 | 同上 | 通过 |
| Cilium/CoreDNS/系统组件 | [Cilium 配置](../../bootstrap/cilium/cilium-values.yaml) | status、workload/Pod 状态 | DS 各 10/10，operator/DNS 各 2/2 | [只读现场](evidence/01.02-cluster-baseline-readonly.txt) | 通过 |
| 正常态三 API/VIP 与 etcd | [基础验收手册](../../bootstrap/acceptance/README.md) | 各端点 readyz、etcd health/status | 四 API 可用，三 etcd healthy，单 leader/无 learner | [只读现场](evidence/01.02-cluster-baseline-readonly.txt) | 通过 |
| 普通 Pod 十节点双向 HTTP | [临时清单](../../bootstrap/acceptance/network-smoke.yaml)、[检查入口](../../bootstrap/acceptance/check-network.py) | 用户部署后执行 | 100 条路径成功，其中 90 跨节点 | [真实网络矩阵](evidence/01.02-acceptance-20261017-125334/14-network-matrix.txt) NETWORK ACCEPTANCE PASS | 通过 |
| 01.03.01 Service 与内外 DNS | 同上 | 十节点 DNS、Service HTTP 及短名补测 | 地址正确且 HTTP 后端身份正确 | 原始失败保留；[修正后的真实矩阵](evidence/01.04-20261017-204751/03-dns-recheck.txt)：100 Pod HTTP、50 DNS、30 Service HTTP 全通过 | 通过 |
| 临时资源清理 | 同上 | 成功后 delete、查询 Namespace | 专用 Namespace 和测试资源清理 | [删除记录](evidence/01.02-acceptance-20261017-125334/17-network-cleanup.txt)、[空查询](evidence/01.02-acceptance-20261017-125334/18-cleanup-confirm.txt) | 通过 |
| 01.02.04 加密/审计恢复材料完整性 | [配置职责](../../bootstrap/README.md) | 完整控制平面备份/取回 | 共享配置一致，恢复材料可用 | [真实凭据](evidence/01.03-20261017-183105/backup/backup-receipt.json)：三节点配置/PKI、加密密钥及审计策略归档并整包取回；离线快照展开通过。未验证在线重建后的审计/Secret 解密行为 | 恢复材料通过；在线恢复待后续 |
| 01.02.08 受限身份与恢复管理员 | [身份配置手册](../../bootstrap/access/README.md) | configure-access / verify-access / backup-access | 身份、默认 Context、恢复与备份可用 | [真实权限](evidence/01.02-access-20261017-131508/02-access-verification.txt)、[恢复入口](evidence/01.02-access-20261017-131508/04-recovery-direct-api.txt)、[.16 取回](evidence/01.02-access-20261017-131508/05-access-backup-restore.txt)均 PASS；Mac 默认只读 | Mac/证书包通过；.15 分发待交付 |
| 01.03.02–03 HA 与完整备份/隔离恢复 | [操作脚本](../../operations/README.md) | 完整备份/离线展开/取回后，观测单 VM 停机 | 故障期间 API/调度可用并恢复 | [备份凭据](evidence/01.03-20261017-183105/backup/backup-receipt.json)、[HA 输出](evidence/01.03-20261017-183105/09-ha-watch.txt)、[观测状态](evidence/01.03-20261017-183105/ha/state.json)：cp01 停机、cp03 接管、新 Pod 调度通过；应用失败 0，API 失败采样 1/97；恢复/清理 PASS | 通过（单 VM/离线展开范围） |
| 01.04.01 实验空间与基准 | [Pod 实验入口](../../core-resources/pods/README.md) | prepare：独立 Namespace、统一标签、预算/网络策略、可控 HTTP | 可控健康与延迟，资源/身份受限 | [真实 prepare](evidence/01.04-20261017-204751/08-prepare.txt)、[健康 503](evidence/01.04-20261017-204751/baseline-ready-false.txt)，基准响应恢复 | 通过 |
| 01.04.02 状态、错误与恢复 | [lab.py](../../core-resources/pods/lab.py) | success/failed/crash/bad-image/pending | 区分 phase/state/reason，并验证修复 | [真实状态实验](evidence/01.04-20261017-204751/resume-20261017-210836-k0KHwt/09-states.txt)：退出 0/7、CrashLoopBackOff、ErrImageNeverPull、8 核请求无法调度及修复均通过 | 通过 |
| 01.04.03 Init 与 Sidecar | 同上 | 失败 Init、普通多容器、原生 Sidecar | 主容器受 Init 约束，启动/退出顺序明确 | [Sidecar 验收](evidence/01.04-20261017-204751/resume-20261017-210836-k0KHwt/10-sidecars.txt)、[原生启停轨迹](evidence/01.04-20261017-204751/native-completed-side.txt)有 init→side→main→main 停→side 停顺序 | 通过 |
| 01.04.04 临时容器诊断 | 同上 | 无 Shell 应用、受限 target 调试、DNS/连接/慢请求 | 可定位故障，应用 SA 不获调试授权 | [真实诊断日志](evidence/01.04-20261017-204751/shellless-debugged-diag.txt)看到目标进程、正常 DNS/NXDOMAIN、拒绝连接、1 秒超时/5 秒成功；[应用 SA 权限](evidence/01.04-20261017-204751/application-sa-debug-permission.txt)为 no | 通过 |
| 01.04.05 OOM、驱逐与正常终止 | [压力入口](../../core-resources/pods/pressure.py)、[可控应用](../../core-resources/pods/app.sh) | 32Mi 上限 OOM；worker02 soft 阈值驱逐；TERM | 三种结束原因可区分，节点恢复 | [OOMKilled/137](evidence/01.04-20261017-204751/resume-20261017-210836-k0KHwt/12-memory.txt)、[真实驱逐/恢复](evidence/01.04-20261017-204751/pressure.json)、[TERM 回执](evidence/01.04-20261017-204751/termination-receipt-e4eeb469-94c5-4e1d-b6c2-aa44857d1663.json) Completed/0 且 UID 一致 | 通过 |
| 01.04 总体验收与清理 | [批次脚本](../../core-resources/pods/run.sh) | verify / cleanup | 完整证据、基准/十节点恢复、本批零残留 | [最终验收](evidence/01.04-20261017-204751/resume-20261017-215220-kXZU2U/15-verify.txt)、[清理 PASS](evidence/01.04-20261017-204751/resume-20261017-215220-kXZU2U/16-cleanup.txt)、[空列表](evidence/01.04-20261017-204751/cleanup-confirm.json)通过 | 通过 |
| 01.05–01.10 其余核心资源实验 | [阶段计划](../../../../plan/01-kubernetes.md) | 按 47 步逐项实施 | 全部要求有真实证据 | 尚未推进 | 未执行 |

## 3. 恢复与清理

用户完成普通网络与身份临时资源清理；01.03 的 [诊断资源](evidence/01.03-20261017-183105/07-dns-smoke-cleanup.txt)和 [HA 资源](evidence/01.03-20261017-183105/11-ha-cleanup.txt)也已清理。备份 run 为 `20261018T001028Z-0266aefd`，.16 restic 快照 `d32beb9a9e69a889e4301c07dffce0006e9f749083c8b08ef2d92fada341eea5`；snapshot revision 115931，12MiB，离线展开及整包逐文件取回验证通过。三节点私有材料与真实 snapshot 均不入 Git。UTC 时间跨至 10 月 18 日，对应管理 Mac 的 10 月 17 日晚间。

01.04 最终三条 PASS 对应管理 Mac 2026-10-17 晚间执行，UTC 已跨至 10 月 18 日。终止 Pod UID 为 `e4eeb469-94c5-4e1d-b6c2-aa44857d1663`，回执包含 TERM、child_reaped=true 和 exit=0；清理结果 items=[]。本批实验 Pod、Service、ConfigMap、NetworkPolicy、ResourceQuota、LimitRange 均清理；lab-core、受限身份与 RBAC 保留。worker02 原 kubelet 配置已恢复且解除 cordon；远端私有原配置副本属于恢复材料，未作为原始配置入库。

## 4. 未完成项与结论

备份/取回、离线快照展开、CoreDNS 分散及单 VM HA 已通过；01.03.01 短名补测已通过。01.04.01–05 的真实实验、总验收及清理全部通过，可进入 01.05；本次未开始 01.05。规划 .15 管理机分发/登录仍待交付。Phase 01 **未完整完成**；实际物理故障域、启动新 etcd 的在线隔离服务恢复、整集群灾难重建及恢复后 Secret/审计行为不属于本次通过范围。

## 5. 01.04 实验小结

本节建立了一个能调节启动延迟、健康状态、请求延迟并处理 TERM 的轻量应用。用普通 Pod、Init/Sidecar 和临时容器，在受限身份与明确预算下反复制造故障、保存状态/事件/日志、验证修复，最后清理同批资源；应用源码与批次入口保留供后续复现。

关键结论：

- Pod phase、容器 state 和 reason 描述不同层次；CrashLoopBackOff 是等待原因。镜像错误与调度资源不足都可能表现为 Pending，需要结合事件定位。
- Init 成功是主容器启动条件；普通 Sidecar 需要协作结束，原生 Sidecar 能按生命周期顺序随主容器收尾。共享 emptyDir 随 Pod UID 生存，重建 Pod 会重建该卷。
- 无 Shell 镜像可以通过授权的非 root 临时容器诊断；正常 DNS、NXDOMAIN、连接拒绝和请求超时具有不同证据。业务默认 ServiceAccount 不具备调试权限。
- 容器 OOM 和节点驱逐都可能出现退出码 137：前者看容器 OOMKilled，后者看 Pod Evicted、memory message 与节点压力；正常终止看 Completed/0 及 TERM 回执。
- 本次节点压力通过临时提高 worker02 软阈值触发真实 kubelet 驱逐，使用约 96Mi 受限负载；不属于耗尽整机内存或宿主机 OOM 验收。完成后原配置 SHA、节点健康和可调度状态均恢复。

本节三次脚本问题与修正一并保留：Crash/Init 的两秒 exec 竞态改为取证后重建；readiness 全扫描改为写入完成标记；删除后 CRI 日志依赖改为绑定 Pod UID 的终止消息。继续执行使用检查点、归属检查和独立证据目录，保留原失败记录，不依赖放宽验收条件。
