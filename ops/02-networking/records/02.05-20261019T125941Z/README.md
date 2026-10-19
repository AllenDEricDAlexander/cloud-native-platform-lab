# 完整 02.05 内部验收与 02.06 交接

批次 `02.05-20261019T125941Z`，run `20261019T125941Z-26a78274`。02.05.01/02 内部验收及清理通过；操作者确认无公网能力，02.05.03 保持 **BLOCKED**，`passed=false`、`phase_complete=false`。

| 项目 | 实际结果 |
| --- | --- |
| cert-manager | 1.21.2 的 controller/webhook/cainjector 就绪，6 个 CRD、授权与签发边界检查通过 |
| 授权 | 7 项 RBAC 正反向、8 项准入拒绝通过；原根 CA 与原中间 CA 私钥留在 Mac |
| 定时续期 | 无手工 renew；revision 1→2，证书及 SPKI 均变化，Certificate/Secret UID 保持一致；网关实际证书同步更新 |
| 稳定周期 | revision 3；duration 168h / renewBefore 48h；当前叶证书截止 2026-10-26T13:04:41Z |
| TLS 故障 | 正常、错误 SAN、不可信 CA、缺少中间链、过期，以及恢复后通过；同时验证严格客户端、网关行为与校验失败计数 |
| 主入口 | .201 的 Gateway/Service/Deployment 与原两个数据面 Pod UID 保持；自动证书指纹 `a8370c4cb59f1a59f3b15222834173d80da46f760fced7a1b0a417574dc33d23` |
| 清理 | lab-tls 已删除，原有工作负载保护基线一致；保留自动签发器、授权边界与主入口稳定证书 |
| 公网 | 无公网入站/NAT/隧道，未配置公网 DNS 或 ACME；内部 TLS 不作为公网通过证据 |

[完整原始日志](ansible-all-20261019T125941Z-gtmmAR)：localhost ok422/changed126，四台 VM 各 ok2/changed1，五个主机 failed/unreachable/rescued/ignored 均为 0。

[原始内部回执](passed.json)含 13 项通过结果，[清理回执](state/closed.json)确认 `automated_ready`。额外只读复核了当前证书 revision 3、主入口身份、实验空间清理及保护基线，见 [归档复核](acceptance-review.json)。

49 份执行源码输入全部匹配，快照保存在 `execution-source/`；296 份日志、状态、attempt 与快照逐项 SHA256 见 [摘要清单](evidence-sha256.json)。原始 attempts 按仓库规则保留本地，不删除、不改写。后续状态说明不覆盖执行输入快照。

[02.06 交接](handoff.json)允许在同集群继续内部网络实验；公网 BLOCKED 仍保留。
