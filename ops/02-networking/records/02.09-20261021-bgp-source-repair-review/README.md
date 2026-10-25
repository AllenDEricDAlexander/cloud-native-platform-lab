# 02.09 BGP 选源与 MetalLB 共存修复：待联网验收

本轮修复尚未提交。用户已确认暂停 VM 或切换网络，后续停止联网探测。当前只完成源码、本地回归与离线检查，没有启动正式实验，没有创建 VM/Kubernetes 资源，没有修改 VM 配置。真实 BGP 建连与服务端准入均未验收。

## 原失败证据

`02.09-20261021T002555Z` 的 Operator 更新、L2迁移和撤回通过，在 bgp 用例失败。FRR两邻居均为Active，收发消息数0、建立连接数0。该批 `state/closed.json` 回退清理PASS；本轮最初只读检查时 Cilium/kube-proxy均10/10，主入口VIP仍为.201。后续网络不可达不作为原BGP失败原因。

[failure-analysis.json](failure-analysis.json) 保存原日志摘要、原始准备阶段的路由与FRR状态。Worker到FRR Pod地址段的首选源分别为 `10.244.8.40` 和 `10.244.9.1`，FRR却只配置 `.109/.110` 邻居。原脚本未设置localAddress；[Cilium1.20.2文档](https://github.com/cilium/cilium/blob/v1.20.2/Documentation/network/bgp-control-plane/bgp-control-plane-configuration.rst#local-peering-address)说明默认源地址由路由查询决定。原失败阶段的Agent日志和报文未在回退前保存，因此不声称持有当时的抓包证据。

原Operator日志还显示Cilium LB IPAM反复移除主Service的`.201`状态，与MetalLB争写。该Service没有loadBalancerClass，原profile保留的默认LB IPAM行为会接管它。这是独立的共存缺陷。

## 修复

- 按Worker Node名创建两份CiliumBGPNodeConfigOverride，把comparison/frr的localAddress固定为`.109/.110`，并检查实际生成NodeConfig中的值。覆盖对象受原Node身份、run标签和创建UID约束，恢复时仅回收本批对象。
- 四种profile设置defaultLBServiceIPAM=none，仅分配有显式Cilium class的实验Service；持续核对原主Service UID及VIP。原Helm revision仍负责恢复，旧批次摘要保持兼容。
- FRR配置补齐vtysh.conf，FRR只被动接受Cilium连接；放行frr步骤前核对真实Router ID、ASN与两个VM邻居，避免仅凭进程Ready放行。
- 失败现场增加BGP NodeConfig/Override和两个Worker Agent日志，避免回退后丢失关键诊断。

## 已执行检查与限制

- 36项数据面/边界回归、10项公共入口回归通过；Ansible语法通过。
- 使用版本锁定CRD验证10个自定义对象结构，通过。此检查不执行服务端CEL/admission。
- 用版本锁定Chart离线渲染四个profile，均输出default-lb-service-ipam=none，且Operator checksum随模式变化。此检查使用Chart默认值合并profile，不能代替当前release值的联网预览。
- [connectivity.json](connectivity.json)记录API VIP、cp01直连API及worker01 SSH超时；随后用户确认暂停环境。未继续联网验证，未输出新的整组重跑指令。

本地检查不能证明真实TCP/BGP会话建立。环境恢复后需要重新核验基线、完成服务端预览，并在明确的执行授权范围内完成真实VM验证，再一次提交；不把本轮离线通过标成02.09验收通过。
