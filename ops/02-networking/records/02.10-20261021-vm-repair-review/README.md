# 02.10 真实运行修复与验证

用户报告失败后授权 Agent 直接运行修到通过。最终批次 [02.10-20261021T154100Z-agent-r2](../02.10-20261021T154100Z-agent-r2/README.md)24 项全部通过，failed/unreachable/rescued/ignored=0，自动回退及清理通过。

## 根因与修复

1. Worker 没有 iptables-save，Istio CNI 在创建 Sidecar Pod 的网络时失败。现在 load 阶段校验本地/远端 SHA 与原 Rocky RPM 签名，禁用仓库，离线安装已锁定的两个原生 iptables RPM；原防火墙、SELinux 与路由保留。
2. 仅 crictl inspecti 校验不能证明 kubelet 能按清单引用使用镜像。通信应用恢复为已验证的 Harbor 完整 digest/IfNotPresent，并在修改 Cilium 前用两个真实 Pod 验证 UID/nonce。全部注入容器镜像都检查，显式固定 proxy_init.image，避免遗漏的 distroless 变体。
3. Istiod 自动创建的公开 CA/CRL、固定名称且无业务数据的选主 ConfigMap 被误判外来资源。现在按标签、字段形状、空间和固定锁名识别；原 Namespace/run/UID 及其他外来对象保护保留。
4. X509Source 的持续监听会重试明确的无身份拒绝，外层只得到 context deadline exceeded。负向与撤销验收改用单次 FetchX509SVID，保留真实 PermissionDenied；真实本地 Unix/gRPC 回归区分拒绝、Unavailable 与超时，未放宽错误判定。

## 已执行验证

- 原用户失败批次恢复成功；失败 all 日志保持原样。
- 26 项 mesh 与 10 项公共 Python 测试通过。
- Go race/vet 通过，含真实 Unix/gRPC 拒绝码回归、TLS 正反向和 HCL 解析。
- 八个 amd64 物料、官方安装包/工具及实际 Chart 文件内容验证通过；身份镜像按源码内容命名，保留旧物料。
- Ansible 语法通过，正式 all 中全部对象先严格服务端预览。
- 实际 VM 的 mTLS/授权/重试/超时、Ambient/waypoint、SPIRE 签发/轮换/撤销及主线恢复全部通过，见最终 passed.json 与 closed.json。

两个 Worker 保留必要的 iptables 原生工具；Mac 没有运行容器环境。本次不进入 Phase03。完整原始失败和试验记录保留；R1 的失败不能算正式通过，最终结论仅使用全新 R2。
