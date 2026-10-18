# Phase 01：2026-10-17 从头重做

状态：01.04.01–05 实验、总体验收与清理全部通过。[逐项验收与实验小结](acceptance.md)已更新；[最终 14–16 输出](evidence/01.04-20261017-204751/resume-20261017-215220-kXZU2U/15-verify.txt)与 [零残留记录](evidence/01.04-20261017-204751/cleanup-confirm.json)已核对。01.05 尚未开始；整个 Phase 01 仍在进行中，.15 管理机实际分发/登录仍待交付。

前置检查点：01.01–01.02 为 `157e39f`，01.03 为 `03f7094`。本次归档 01.04 完整实现、53 项回归、三次故障修正、实际执行输出和源码快照；不修改原执行状态中的旧 source_commit。执行输入由各次 script-revisions 和 SHA 明确，末次归档与当前实现一致。

01.04 批次为 `01.04-20261017-204751`，run 为 `20261018T004858Z-aa76940f`。完成标记包括 prepare、states、sidecars、debug、memory、pressure、termination、verify、cleanup。用户完成所有真实实验；助手核验回执、源码哈希和线上只读状态，未重跑故障负载。后续入口保留于 [完整手册](../../core-resources/pods/README.md)，本次不启动下一专题。

- [逐批执行记录](assets.md)：记录本轮实际命令、输出、失败、修正与结论。
- 本轮范围为 Phase 01；Phase 00 的基础设施与节点基线保留，01.01 的交接检查重新执行。
- 用户于本轮授权使用 Ansible：批量检查与已授权的旧残留清理由助手复用现有 inventory 和 SSH 配置执行，结果逐步说明并归档；不自动启动项目或长期运行进程。需要用户执行的学习操作仍每次提供 1–3 条命令。
- 用户要求命令配合解释：每一步先讲目的、执行位置、命令作用与预期结果，再根据实际输出继续；配置按职责逐段讲解。
- 用户最新要求改为一次补齐完整配置，继续解释每条命令；不再等待逐字段反馈。当前使用完整 Ansible 执行入口，早期追加命令只供回顾。
- 先确认并清理旧初始化残留，再从 01.01 开始复验，随后重新编写引导配置、初始化与加入节点。
- 原始输出取得后保存至本批次 `evidence/`；kubeconfig、Token、证书私钥和加密密钥不入记录。

旧记录与引导草稿已移至仓库外 `/Users/mario/.cnpl-archives/phase01-abandoned-20261017-101612/`，不作为本轮执行输入。归档不代表远程节点已完成回滚。

本轮已取得的证据：[清理执行](evidence/restart-cp01-cleanup-apply.txt)、[十节点只读复验矩阵](evidence/01.01-node-readiness/matrix.md)、[十节点 CRI 自测矩阵](evidence/01.01-cri-smoke/matrix.md)、[API 域名查询](evidence/01.01-api-dns.txt)。

引导镜像准备：[摘要校验与十节点预拉](evidence/01.01-bootstrap-images.txt)。

01.02 准备阶段证据：[十节点准备](evidence/01.02-prepare-complete.txt)、[完整 dry-run](evidence/01.02-complete-dry-run.txt)、[生成的 kubelet 配置](evidence/01.02-kubelet-effective-dry-run.yaml)、[Join 模板校验](evidence/01.02-join-template-validation.txt)、[TCP 防火墙验证](evidence/01.02-firewall-verify.txt)。其后 cp01 已完成真实 init；其他节点 join 尚未执行。

审计日志目录的合成创建探针发现标签权限问题，已更正为 container_file_t 并在三台控制平面复测通过；[最终 prepare 输出](evidence/01.02-prepare-final.txt)记录了该次准备结束时十节点 kubelet 均为 inactive。

后续真实 init 已由用户执行；[VIP 失败后的原地恢复](evidence/01.02-cp01-vip-resume.txt)、[修复后状态](evidence/01.02-cp01-after-vip-repair.txt)记录当时现场。CNI 后续已安装，见下方最新结果；早期 inactive/未初始化描述只代表当时检查状态。

恢复后 [管理 Mac 经 API 域名访问 VIP](evidence/01.02-management-vip-check.txt)，使用集群公开 CA 完成 TLS 校验并返回 HTTP 200。

最新结果：[用户 Cilium 安装](evidence/01.02-install-cilium.txt)、[原始入群失败](evidence/01.02-join-control-plane.txt)、[Pod 到 API 规则修正](evidence/01.02-pod-api-firewall-fix.txt)、[控制平面前检](evidence/01.02-control-plane-preflight-verified.txt)、[七节点前检](evidence/01.02-workers-preflight-verified.txt)、[原生命令与四角色校验](evidence/01.02-native-join-command-validation.txt)、[13 项离线回归](evidence/01.02-join-regression-verified.txt)、[当前集群状态](evidence/01.02-after-join-script-repair.txt)。本次未执行真实 join、reset 或重新 init。

其后用户已完成 [cp02/cp03 入群](evidence/01.02-join-control-plane-retry-20261017-123053.txt)和 [七节点入群](evidence/01.02-join-workers-20261017-123816.txt)，均 failed=0、unreachable=0。助手完成 [十节点在用配置只读验收](evidence/01.02-ten-node-effective-config.txt)与 [集群只读健康检查](evidence/01.02-cluster-baseline-readonly.txt)。[临时网络清单](../../bootstrap/acceptance/network-smoke.yaml)和 [测试脚本](../../bootstrap/acceptance/check-network.py)已准备并静态/离线验证，尚未实际部署或运行。

用户随后完成 [20261017-125334 整批基础验收](evidence/01.02-acceptance-20261017-125334/14-network-matrix.txt)，100 条 Pod HTTP 路径（90 跨节点）、40 DNS、20 Service HTTP 全通过，[临时资源已清理](evidence/01.02-acceptance-20261017-125334/17-network-cleanup.txt)。受限身份配置定义与 [离线回归](evidence/01.02-access-offline-tests-first.txt)、[静态/dry-run 检查](evidence/01.02-access-static-validation.txt)已交付，不代表真实身份和 .16 恢复文件备份已验收。
