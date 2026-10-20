# 02.06 可执行项验收与暂停记录

批次 `02.06-20261020T004459Z-agent-r4`，run `20261020T004502Z-cfaad896`。52 个行为用例均连续三次符合预期，5 组实际 SYN/socket/回程证据通过，临时资源清理通过。Ceph 服务与主集群 Egress Gateway 的既有缺口保持阻塞，`available_cases_passed=true`、`passed=false`、`phase_complete=false`。

| 项目 | 实际结果 |
| --- | --- |
| 02.06.01 | 默认拒绝与标准 NetworkPolicy 正反向行为、DNS、入口、依赖和监控验证通过 |
| 02.06.02 | 同批 Pod 上 Cilium 身份、HTTP 200/403、FQDN/DNS REFUSED 与 Hubble 关联通过 |
| 02.06.03 | Harbor 可信 TLS、三个存储 VM 的 TCP 路径、显式代理、禁止直连、代理故障与恢复通过；Ceph 服务尚未安装，PARTIAL_CEPH_BLOCKED |
| 实际源与回程 | Harbor、三个存储 VM 和代理的五组有界抓包均与实际 socket 关联 |
| 02.06.04 | 当前主集群保留 kube-proxy、未启用 Egress Gateway，BLOCKED；未切换主 CNI 或停止真实代理/VPN |
| 清理 | 三个实验 Namespace 已删除；worker01 的 26 条临时 rich rules 撤销，即时和永久规则恢复原基线；既有资源一致，主 .201 可信 TLS 返回预期 404 |

[完整原始日志](ansible-all-20261020T004459Z-oti30E)：localhost `ok=315 changed=113 unreachable=0 failed=0 skipped=1 rescued=0 ignored=0`。[行为回执](passed.json)、[清理回执](state/closed.json)与[归档复核](acceptance-review.json)的批次和集群身份一致。

本次修复 Hubble 双向过滤、firewalld 与透明代理衔接、DNS 拒绝事件及 socket 关联、代理 ACK 检查、tcpdump 就绪读取和显式 deny 原因码识别。保留原有策略检查与三次实际行为要求，临时规则在失败清理和 recover 中同样回收。此前失败或中断批次仍按时间顺序保存在本地，未提升为通过。

45 份执行输入的 SHA256 全部匹配，原样副本保存在 `execution-source/`；逐项摘要见 [证据清单](evidence-sha256.json)。`attempts/` 原始请求、Hubble 和抓包按仓库规则保留本地，不删除、不改写。

用户要求本条完整命令结束后暂停；02.07–02.10 仅完成只读前检，正式整组实验均未启动。下一步为 02.07，等待用户通知后继续。[暂停位置](../batch-02.06-10-20261019T235512Z-agent/progress.json)。
