# 02.09 真实 VM 整组验收与恢复归档

用户明确授权 Agent 直接在现有 .101–.110 VM 主集群执行、诊断修复并完整验证02.09，最后自动回退。本批是修复后的全新正式 all，执行期间源码未变化，也没有临时修改实验资源。

**22个可运行用例全部通过，自动恢复与清理通过。** 完整Ansible结果：

~~~text
localhost : ok=512 changed=139 unreachable=0 failed=0 skipped=9 rescued=0 ignored=0
~~~

## 实际验证

| 范围 | 证据结果 |
| --- | --- |
| 基线/eBPF | 原kube-proxy矩阵与替代后的Pod IP、DNS、ClusterIP、NodePort、Gateway及API TLS实际请求通过；十VM kube-proxy清理完成 |
| Native Routing | 十VM到其余真实CiliumNode PodCIDR的直连路由及实际请求通过 |
| L2 | VIP分配、池无冲突、Lease、独立VM新鲜ARP/MAC、Mac HTTP、持有者迁移与恢复通过；撤回后连续三次ARP无响应 |
| BGP | 两个软件邻居10.244.8.40和10.244.9.1均Established；RIB恰好包含10.244.8.0/24、10.244.9.0/24、192.168.9.211/32，路径有效 |
| BGP撤回 | 广告删除后RIB清空，两个会话保持Established |
| 连接观测 | 保留成功、失败与重连的真实日志，不声明网络切换零中断 |
| 恢复 | 原kube-proxy UID/spec、原Cilium Helm值/manifest/ConfigMap、原路由/标签/防火墙恢复；两个实验Namespace及本批全局BGP/L2对象回收 |
| 追加复核 | 十节点Ready，Cilium/kube-proxy均10/10，原主入口UID/VIP保持；十VM SELinux Enforcing、firewalld active、ens33 rp_filter与运行前一致 |

[passed.json](passed.json)记录22个用例，[state/closed.json](state/closed.json)是清理回执，[postcheck.json](postcheck.json)是恢复后追加复核，[acceptance-review.json](acceptance-review.json)汇总实际验收结果。完整输出见[原始Ansible日志](ansible-all-20261021T122949Z-fffxTl)。

本地47项回归通过，见[回归结果](../02.09-20261021-bgp-overlay-validation/result.json)。本批起始预览、运行中的逐对象严格服务端预览及四种Helm profile均通过；源码摘要与正式执行输入一致。

## 根因与修复

旧脚本将FRR Pod的软件邻居绑定到VM管理IP。BPF模式下跨VM连接出现去程VXLAN、回程ens33的不对称路径，严格反向路径检查丢弃返回SYN-ACK。真实报文、内核丢包计数和受控试验见[诊断归档](../02.09-20261021-cross-vm-bgp-review/README.md)。

正式修复动态选择Worker真实CiliumInternalIP，确保软件邻居双向都走隧道；校验地址唯一、属于各自PodCIDR、模式切换中不漂移，实际NodeConfig/FRR邻居与该映射一致。保留严格RPF及SELinux/firewalld。并落实defaultLBServiceIPAM=none隔离MetalLB，保护原.201主Service，补齐FRR配置读取及真实配置验收。

## 验收边界

`available_cases_passed=true`、`cleanup_passed=true`。外部真实上游BGP转发仍按原定义单列BLOCKED，因此`phase_complete=false`；本批证明软件邻居会话、限定RIB与撤回，不替代外部转发验收。

原失败日志与诊断试验均保留，本批没有通过忽略失败或降低断言取得成功。详细attempt按仓库规则保留本地，其摘要纳入evidence-sha256.json。
