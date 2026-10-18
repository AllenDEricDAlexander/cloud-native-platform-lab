# 02.01 网络路径与诊断基准实际验收

用户已完成正式实验及清理。run 为 `20261018T142349Z-ee2fdc73`，成功 attempt 为 `20261018T142413Z-03958adb-run`，清理 attempt 为 `20261018T142902Z-14ff0342-cleanup`。原集群 UID 为 `4d3e52d7-e203-4daf-aced-9c3a666fcf5b`，十台 VM 为 `.101–.110`；不读取或依赖 ESXi 放置。

[正式运行日志](ansible-run-20261018T142412Z-fDsH8Q)包含 `02.01 ACCEPTANCE PASS`，[清理日志](ansible-cleanup-20261018T142900Z-W3kAoT)包含 `02.01 CLEANUP PASS`。Mac 与十台 VM 全部 failed/unreachable/rescued/ignored=0。[源码校验日志](ansible-validate-20261018T142357Z-lomWdH)包含 SOURCE VALIDATION PASS。

## 实际结果

| 项目 | 实际证据与结论 |
| --- | --- |
| 同 VM / 跨 VM | 100 个 Pod 有向对，HTTP/TCP 与 UDP 各 500 个样本；每对各 5 次，全部通过。 |
| Service、DNS、跨空间 | ClusterIP、Service FQDN、跨空间访问与反向请求通过；DNS/UDP 与 DNS/TCP 各 30 个查询。 |
| 大包与 MTU | UDP 1400/4096 字节共 100 个样本，HTTP 上传 128 KiB；摘要与长度校验通过。十个主空间 Pod 的 eth0 实测 MTU 均为 **1500**，不以文档预估 1450 代替实测值，也不把分片成功视为无分片 PMTU。 |
| Harbor TLS / SNAT | 50 次 TLS 请求通过；每个源 VM 的五个 SYN 地址均为该 VM 的 `.101–.110` 地址，与 Pod 内本地源地址形成实际 SNAT 对照。 |
| 样本与延迟 | 普通矩阵共 **1,365** 个请求，样本丢失为 0。Pod HTTP 平均约 7.856 ms，UDP 平均约 1.066 ms；仅代表本次样本，不作性能承诺。 |
| Mac → 业务 | API port-forward 访问返回 HTTP 200 和目标 Pod 身份；不声称已经验证尚未建立的 LAN 业务 VIP。 |
| Hubble 正常 / 超时 | 正常请求 HTTP 200；应用延迟触发约 1001.5 ms 超时。两者分别取得 10、12 条对应 FORWARDED Flow。 |
| Hubble 拒绝 / 恢复 | 策略触发约 1000.5 ms 超时并取得 2 条 POLICY_DENIED 丢弃；撤销后同一路径 HTTP 200。三个观测阶段 Relay 均连接 10/10 VM。 |

逐项复核、原始结果摘要、源地址、接口 MTU 与完整 recap 汇总在 [acceptance-review.json](acceptance-review.json)。原始 [passed.json](passed.json) 的 `cleanup_passed=false` 是实验结束时的状态，保持原字节；实际清理结果由 [state/closed.json](state/closed.json)独立确认，两个回执属于同一 run 和集群。

## 当前健康与交接

归档时再次只读确认：十节点 Ready，API readyz 为 ok；两个测试空间均不存在，Hubble Relay 1/1，连接节点 10/10。Hubble、受限查询策略、4244 来源规则与镜像缓存按设计保留，Overlay 与 kube-proxy 保持原模式。完整 Helm 回退本轮未执行。

[handoff.json](handoff.json) 与 [完成指针](../completed/02.01.json)原字节一致，后续为 **02.02.01：ClusterIP 与 EndpointSlice**。

## 原件与源码归档

[evidence-sha256.json](evidence-sha256.json)登记整理前的 138 个原件，逐文件确认原字节未变。`attempts/` 按现有 Git ignore 规则保留本地原件，OCI/二进制物料不提交；本目录入库验收摘要、日志、回执、校验索引及交接信息。

运行时的 26 个源码/输入摘要与整理前工作区逐一匹配。运行时源码尚未提交，Git 基线为 `4d99db4`；本次提交首次收录实际执行代码，不能将基线提交误记成这套源码的执行提交。将要更新的操作手册与版本锁原字节另存于 `execution-source/`，其余实际执行文件随本次提交保留，可依 passed.json 中的 SHA-256 复核。
