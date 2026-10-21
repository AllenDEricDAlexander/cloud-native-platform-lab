# 02.09：现有十 VM 主集群的数据面对照

执行目标已由用户明确为 .101–.110 的现有主集群。Mac 只运行管理命令、Ansible、Helm、kubectl 和只读探测；不启动 Docker Desktop，不创建本地 kind。项目根目录 AGENTS.md 固定了这一约束。

BGP 软件邻居位于 Pod 网络内，使用每个 Worker 在 CiliumNode 中登记的真实 CiliumInternalIP 作为传输对等地址，使请求与回包都走隧道。管理端仍通过 .109/.110 操作 VM。这样保留原 ens33 的严格 rp_filter 设置，避免使用 VM 管理地址时隧道请求、ens33 回包形成的不对称路径。

本组会临时切换主集群 Cilium/kube-proxy 与路由，既有连接可能中断并重连。停止其他集群网络维护后，一次执行：

~~~bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
export LAB_DATAPLANE_RECORDS="$PWD/ops/02-networking/records/02.09-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/dataplane.sh all "$LAB_DATAPLANE_RECORDS"
~~~

三行依次进入仓库、绑定全新证据批次、完成本专题全部前检、22步实验和自动回退清理。无需 Docker 命令或新增 VM；原 Mac/kind 失败批次不能续跑，必须使用新目录。

20261020T230854Z 的 VM 批次在 L2 地址分配处失败，已自动恢复；重跑同样使用上述全新目录。入口末尾现在固定显示首个失败步骤、原错误、日志行号、本次回退清理结果和完整日志路径；`summary-all-*.json` 保留相同汇总。回退成功不会把实验失败改成通过，入口保留 Ansible 原退出码。

## 前置与恢复基线

- 同集群 02.08 的可运行验收与清理回执匹配；十 VM Ready、无压力；原 Cilium 1.20.2、cluster-pool IPAM、kube-proxy/VXLAN 基线保持。真实地址块来自 CiliumNode，不切换 IPAM。
- 保存原 Cilium Helm revision、值和 manifest 的摘要、控制器 UID/spec、Cilium ConfigMap 摘要、Node UID、路由和 firewalld 规则。Helm TLS 内容只在进程内计算摘要，不输出、不存入公开记录。
- 恢复使用原 Helm revision 的既有 manifest（含原 TLS/RBAC），不重新渲染近似配置。kube-proxy 通过 NodeSelector 暂停并恢复，DaemonSet 原 UID 保持。
- 测试 VIP .211–.214 必须与 MetalLB 地址池和现有 Service 不相交；NodePort 31080/31090 必须未占用。
- 复用既有 Envoy Gateway controller/GatewayClass；在实验空间创建独立 HTTP 网关，不重装主 .201 网关。

## 一次完成的内容

| 范围 | 操作与预期 |
| --- | --- |
| 工作负载与基准 | 两 Worker 各一个 API 副本、client 与持久 TCP 观测；同一 Pod IP、DNS、ClusterIP、NodePort、HTTP Gateway、API Service 可信 TLS 矩阵；响应检查 nonce/原后端 UID |
| CRD | 预览与实际应用均使用 server-side apply，避免 last-applied 注解的256KiB限制；只补齐缺失的版本锁定 Cilium CRD |
| eBPF | 保留原 Cilium/IPAM，启用 kube-proxy replacement；暂停原 kube-proxy DS并等待Pod消失；十个一次性 VM Pod 用原 kube-proxy 镜像执行 --cleanup；重复矩阵 |
| Native Routing | 同一 VM 集群切换 Native/autoDirectNodeRoutes；读取每 VM 到其余 CiliumNode PodCIDR 的内核直连路由，重复矩阵 |
| L2 | 专属 .211–.214 地址池；核对池无冲突、VIP/Lease、cp01 发起的新鲜 ARP 与 Worker MAC、Mac 实际 HTTP；用本批标签让原宣告者退出选择范围，验证迁移后恢复。撤回策略后，独立 VM 连续三次 ARP 无响应才通过；此为选择器撤出，不停止 VM |
| BGP | 先回收本批 L2 Service，避免模式切换后的 VIP 重复归属。两份按 Node 名命名的 CiliumBGPNodeConfigOverride 绑定实际 CiliumInternalIP，核对地址唯一、属于各自 PodCIDR、模式切换期间不漂移，以及实际生成的 NodeConfig。FRR10.5.0 amd64 Pod 作被动邻居，ASN65009/65010；配置默认路由的下一跳解析，实际 Router ID、ASN、两个内部地址邻居配置正确才放行。RIB 必须恰好包含两 Worker PodCIDR 和本批 BGP VIP /32 且路径有效；撤回广告后两个会话仍须 Established、RIB 清空，不修改家庭上游 |
| 连接 | 保留实际成功、失败和重连日志，不承诺零中断 |
| 回退与清理 | 原 kube-proxy spec/10个Pod、原 Cilium Helm revision、原 Node 路由/标签、原模式矩阵；撤销临时入口规则，原UID删除实验对象，主 .201可信TLS正常 |

只为 Mac .200 来源的本批 NodePort/VIP 请求，在两个 Worker 添加精确即时 rich rules，设置两小时失效保护；不改变永久规则或关闭 SELinux/firewalld，正常与失败恢复均核验原规则。

实验空间为 lab-dataplane-vm 和 lab-dataplane-vm-admin。后者容纳一次性 kube-proxy 清理 Pod（hostNetwork、原镜像、限定参数）和软件 FRR；FRR不使用hostNetwork或主机挂载，其路由表只属于自己的Pod网络空间。

新增 Cilium BGP CRD 作为组件 schema 保留；本批 Pool、宣告策略、BGP配置/广告、两份 NodeConfigOverride、Service和测试空间按原UID回收。已有 CRD 不接管或覆盖其他归属实例。

**外部 BGP 转发保留 BLOCKED**：集群内 FRR证明会话、受限 RIB与撤回，不能用 Pod内Service访问替代真实上游转发。验收读取 available_cases_passed=true 与 cleanup_passed=true；phase_complete=false保留这一缺口。

## 文件与执行边界

[Ansible入口](../../ansible/playbooks/dataplane.yml)、[全部步骤/YAML](../../networking/dataplane/cases.yml)、[VM验收器](../../tests/integration/dataplane/vm.py)、[恢复编排](../../ansible/tasks/dataplane-cleanup.yml)复用既有计划→命令→取证→always框架。

- kubectl/Helm固定原VM kubeconfig和集群UID，Node/控制器UID与非本批Helm值发生漂移时拒绝覆盖。
- Helm upgrade使用固定Chart、reuse-values及限定网络配置；保留原revision供回退。
- 四种模式均设置 `operator.rollOutPods=true`，由官方 Chart 的 ConfigMap 校验和触发 Operator 更新。每次切换核对 Helm 实际 manifest、ConfigMap、Deployment 校验和、全部新 Pod UID/校验和/Ready 及 L2/BGP 开关；旧 Pod 尚存时不能通过。原 Operator 其他配置仍受漂移保护，最后随原 revision 恢复。
- 四种模式均设置 `defaultLBServiceIPAM=none`，只让 Cilium 分配显式 Cilium class 的实验 Service，避免与 MetalLB 争写原 .201 Service。模式切换及 L2/BGP 观测持续核对原主入口 UID/VIP；最后随原 Helm revision 恢复该值。
- CRD的apply/dry-run均为 --server-side --field-manager=cnpl-gateway-crds，不使用force-conflicts。
- 写操作由Ansible执行，UID与原字段测试保护并发修改。
- validate仅做VM只读前检、物料/模板/CRD严格预览和Helm渲染，不开始正式切换；all应用每份原始对象前再次严格预览。
- 等待失败时，在 always 回收之前保存 `*-diagnostics.json`，含本批 Service/Pod、Pool/宣告配置、Lease、Operator、实际 BGP NodeConfig/Override，以及两个 Worker Agent 与 FRR 的限量日志；每次 VIP 检查另存 `*-lb-last.json`。诊断读取有短超时，采集异常保留在文件中，不覆盖原错误、不阻止回退。

## 恢复

正常all自动回退。若中断或清理未完成，使用**原目录**：

~~~bash
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/02-networking/scripts/dataplane.sh recover "$LAB_DATAPLANE_RECORDS"
~~~

恢复不重跑实验；先恢复kube-proxy，再恢复原Cilium release。原状态未恢复时不宣称CLEANUP PASS；回退检查异常也撤销本批临时入口规则。原Mac/kind失败批次已清理、Docker已停止，不应再启动它续跑。

参考：[Cilium v1.20.2连接边界](https://github.com/cilium/cilium/blob/v1.20.2/Documentation/network/kubernetes/kubeproxy-free.rst)、[Operator 配置校验和](https://github.com/cilium/cilium/blob/v1.20.2/install/kubernetes/cilium/templates/cilium-operator/deployment.yaml#L44-L50)、[LB IPAM 启动时的类型选择](https://github.com/cilium/cilium/blob/v1.20.2/operator/pkg/lbipam/cell.go#L55-L80)、[FRR 多跳邻居的默认路由解析](https://docs.frrouting.org/en/stable-10.5/bgp.html#clicmd-neighbor-PEER-ebgp-multihop)、[Cilium v1.20.2 BGP](https://github.com/cilium/cilium/blob/v1.20.2/Documentation/network/bgp-control-plane/bgp-control-plane-configuration.rst)。
