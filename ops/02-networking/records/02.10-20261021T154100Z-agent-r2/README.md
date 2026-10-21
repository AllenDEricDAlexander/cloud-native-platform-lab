# 02.10 真实 VM 整组验收与恢复归档

用户授权直接在现有 .101–.110 VM 主集群修复并运行到可用范围通过。Mac 只作管理端。本批为修复后的全新正式 all，执行期间没有修改源码或临时修补实验资源。

**24 个可运行用例全部通过，自动恢复、清理和追加复核通过。**

~~~text
localhost : ok=1228 changed=375 unreachable=0 failed=0 skipped=9 rescued=0 ignored=0
~~~

## 真实结果

| 范围 | 验收证据 |
| --- | --- |
| 启动前置 | 两 Worker 原生 iptables nft 后端；八个 amd64 镜像摘要；两个真实 Pod 的启动、UID 与 nonce |
| Sidecar | 实际注入、探针就绪、跨 VM 请求、STRICT mTLS、身份 403/RBAC、拒绝裸明文；公开证书元数据与 mutual_tls 指标 |
| 流量与生命周期 | 503 实际后端次数为 3，超时有界 504；旧客户端退出、新 UID 与重新注入后通信；裸请求控制持续成功 |
| Ambient/waypoint | 无 Sidecar 的 L4 身份允许/拒绝与 mTLS 指标；waypoint 本代 Programmed、目标 Worker 就绪；路径/方法 L7 拒绝 |
| SPIRE | 两 Worker PSAT Node UID、六条注册、真实 Workload API/mTLS；未注册工作负载明确 PermissionDenied |
| SVID 生命周期 | 真实 serial 变化；注册撤销后单次签发返回 PermissionDenied；53 份持有旧 SVID 的记录证明到期后失败，verifier 仍成功 |
| 自动恢复 | 六个实验 Namespace、本批 CRD/RBAC/Webhook/GatewayClass 回收；原 Cilium values/manifest/ConfigMap、控制器 UID/spec、路由及即时/永久防火墙恢复 |
| 恢复后复核 | 十节点 Ready；Cilium、Cilium Envoy、kube-proxy 均 10/10；主 .201 原 Service UID 与可信 TLS 保持；SELinux Enforcing/firewalld active |

[passed.json](passed.json)含全部 24 项实际结果，[state/closed.json](state/closed.json)是清理回执，[postcheck.json](postcheck.json)与[independent-postcheck.json](independent-postcheck.json)是恢复复核，[handoff.json](handoff.json)是阶段交接。原始日志为本目录 ansible-all-*，机器汇总见 [acceptance-review.json](acceptance-review.json)。

Worker 保留新增的原生 iptables-nft/iptables-libs 1.8.11-16 前置工具和公开内容寻址镜像缓存；没有安装容器引擎。原有网络配置和业务恢复，包前置的保留与网络回退分别记录。

## 失败与修复

原用户批次 `02.10-20261021T144447Z` 保留原始失败与后续恢复日志；第一次修复运行 `02.10-20261021T152200Z-agent-r1` 暴露 SDK 监听重试导致的身份拒绝误判，记录同样保留并已自动恢复。本批使用单次 FetchX509SVID RPC，超时/不可达不会算作权限拒绝。详见[根因与回归归档](../02.10-20261021-vm-repair-review/README.md)。

执行输入的 SHA256 与最终源码一致，详细 attempt 按仓库规则保留本地，摘要归档。没有忽略实际失败或降低断言。

## 验收边界

`available_cases_passed=true`、`cleanup_passed=true`。Trace/SLO、发布联动和身份联合/网格集成保持 BLOCKED；Istio 与独立 SPIRE 没有联合根信任。`phase02_complete=false`，不把本批基础验收外推为所有 Phase02 进阶范围已完成。
