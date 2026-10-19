# 完整 02.06 执行前核验

02.05 内部实际验收已归档提交 d1f113d，公网 BLOCKED 保留。本目录是准备阶段证据，**没有在集群部署或执行 02.06 正式 Pod、策略、代理故障**；运行入口及全部作用/预期见 [完整指南](../../examples/policies/README.md)。

| 检查 | 最终结果与证据 |
| --- | --- |
| Ansible 语法 | 总剧本 syntax-check 通过 |
| 完整只读 validate | [最终日志](ansible-validate-20261019T134759Z-qhcNw6)：localhost ok13/changed2，failed/unreachable/rescued/ignored 均为 0；changed 是本机证据/模板目录，不是部署 |
| 执行 YAML | [35 份对象 strict server dry-run 通过](compatibility.json)：Namespace3、双向默认拒绝3、工作负载/公开根/Service12、标准策略7、Cilium8、出站1、代理故障1 |
| 出口参考 | 官方 Cilium v1.20.2 CRD SHA256 锁定并完成 CRD 自身 server dry-run；参考实例的 OpenAPI 结构通过；当前没有该 CRD，实例 CEL/准入及执行 BLOCKED，没有安装它 |
| 源码输入 | [43 份最终输入 SHA256](source.json)与最新 validate 一致，快照在 reviewed-source/；未改写既有执行记录 |
| Go 探测器 | [已执行 race 测试与 vet](go-validation.json)通过；测试真实 HTTP UID/nonce、环境代理绕行、显式代理、可信/不可信 TLS、CONNECT、超时和连接拒绝边界 |
| Python | [11 项回归通过](python-tests-final.txt)：超时/拒绝/命令失败、nonce/UID、POLICY_DENIED 与身份、双向 L7、Service DNAT 目标集合、丢失事件、外来对象、原 UID 删除、创建后崩溃恢复、BLOCKED 不冒充 PASS |
| 真实 kubectl 客户端 | 单元测试对本机有界 HTTP 替身发出真实 DELETE；验证 DeleteOptions 原 UID/body 完整，支持客户端的 chunked 请求与 timeout 查询参数；没有对真实集群 DELETE |
| 真实 Ansible 离线编排 | [模型结果](offline/results.json)：正常 ok307/failed0；故意使 Cilium 观察失败后 ok271/failed1 且 always 清理完成；显式 recover ok13/failed0。三者均检查三空间 UID 删除流程。它只证明编排，不证明数据面 |
| 现网只读前提 | 最新 attempt 的 preflight/hosts：原十 VM Ready；五台相关 VM Enforcing/public firewalld/时间同步；Cilium Client/Daemon 1.20.2；Hubble 实际 10/10；原 .201 主入口可信 TLS/404 |
| 物料 | 镜像确定性重建与 Harbor 摘要通过；[空 Docker 配置的匿名拉取摘要](anonymous-registry.json)通过；Harbor 无凭据可信 TLS 401；原显式代理外网 TLS 204 |
| 现网保护 | 结束时三实验空间仍不存在；现有网络、策略、主入口及原工作负载 UID/spec 保护基线一致 |

第一轮预览揭示了未安装的 Egress Gateway CRD，原始失败日志保留；随后改为严格区分“实际执行资源服务端准入”“未安装 CRD 的参考结构”和 BLOCKED。中间测试结果同样保留，最终以表中日志为准。

沿用既有 Ansible 编排、纯标准库 Go 诊断与独立 Python 验收器。直接扩展现有结构，不增加框架或新的业务设计模式。默认拒绝先于 Pod 创建；标准放行删除后才对比 Cilium；DNS/Service 的 Hubble 判定同时考虑 DNAT 前后 IP 和反向响应；失败不被 rescued/ignored 隐藏。

[交付复核](delivery-review.json)记录当前限制：52 个实际行为用例与 5 组源/回程证据仍待操作者一次 all 执行；Ceph 服务和 Egress Gateway/真实 VPN/出口 VM 故障继续 BLOCKED，不把模拟代理入口故障或外网 204 当成 VPN/公网源地址验收。
