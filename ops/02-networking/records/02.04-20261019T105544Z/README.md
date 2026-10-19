# 完整 02.04 实际验收与 02.05 交接

批次 02.04-20261019T105544Z，run 20261019T105544Z-7a34839a。原集群 UID 4d3e52d7-e203-4daf-aced-9c3a666fcf5b。02.04.01–07 的 15 项必需结果及清理均通过。

| 项目 | 实际结果 |
| --- | --- |
| 兼容性与入口 | Gateway API 1.6.1 Standard、Envoy Gateway 1.9.2 / Envoy 1.39.1；主入口 .201，数据面两副本分布在 worker01/02；仅按 VM hostname 调度 |
| HTTP 与 TLS | 内部 DNS、前端 SAN/链、后端 TLS、Host/Path/Header、重写、重定向、超时及未知路径行为通过 |
| 授权 | RBAC 与 namespace 绑定拒绝；共享后端拒绝→授权→撤销；外空间证书拒绝→授权→实际 TLS 指纹切换→恢复原证书 |
| 协议与对照 | 真实 gRPC Health RPC、TCP/UDP nonce 与 Pod UID 匹配；临时 .203 的 Traefik Ingress 使用相同后端完成对照 |
| 权重 | 200 个独立 TLS 请求实际 v1=159、v2=41；10 个 Header 定向请求全部命中 v2 |
| 单 Pod 替换 | worker02 上原 Pod UID 12994e08-499c-4b04-a046-c7bd1071b760 被替换；129 个观测请求、0 个失败样本；替换后 16 个成功请求；新 Pod 的实际 HTTP/gRPC 及 LDS/CDS 成功/拒绝指标均通过 |
| 清理与保留 | 四个临时空间、IngressClass/.203、协议测试监听器和观测进程回收；保留 .201 的 80/443、内部 DNS、原主证书及控制器；原有工作负载 UID/spec 不变 |

129 个样本无失败是本次观察结果，不构成零丢包或生产 SLA 承诺。清理后 HTTPS /v1 返回可信主证书和 404，符合空主入口预期。

[原始完整日志](ansible-all-20261019T111315Z-PkiQaR)：localhost ok627/changed199，dns ok9/changed3，四台 VM 各 ok2/changed1；failed/unreachable/rescued/ignored 均为 0。[通过回执](passed.json)保留清理前原值，[清理回执](state/closed.json)确认主入口 ready、formal_acceptance_passed=true。

63 份执行源码与输入摘要全部匹配，快照位于 execution-source/；385 份原始文件逐项计算 SHA256，见 [摘要清单](evidence-sha256.json)。二进制和 attempts 按既有 Git 规则留在本地证据目录，原始文件不删除；Git 保存主要回执、日志、输入快照与摘要。

[复核](acceptance-review.json)、[交接](handoff.json)。归档时额外只读确认了主入口 Gateway/Service/Deployment 原 UID、跨两个 VM 的双副本、可信 TLS 指纹、内部 DNS、实验清理和既有工作负载保护基线。

首次 JSONPath 前检失败日志与 repairs/ 保留。修复当时基础 context 的摘要属于当时状态；随后正式 all 按设计扩充 context，原失败日志没有改写。后续 02.05 使用本批完整 passed/closed 和持久入口交接。
