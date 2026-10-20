# 02.09 VM 版修复与交付核验

原 Mac/Docker/kind 方案不符合用户执行环境要求，已停用。用户明确选择现有 .101–.110 VM 主集群；本轮仅完成源码实现、原批清理、物料准备、VM只读前检与模型验证，未启动正式数据面切换。

| 项目 | 实际证据 |
| --- | --- |
| 原报错 | 同一份1,424,276字节EnvoyProxy CRD：client apply严格服务端预览报262144上限；server-side apply严格预览通过，主CRD UID/spec未改变，见large-crd-replay.json |
| Mac清理 | 原失败批次的三kind节点、附属资源和专属网络已删除；Docker已停止；原有停止状态sandbox容器保留，未prune镜像或无关数据 |
| 执行边界 | 根AGENTS.md禁止Mac本地容器实验；新02.09使用VM主集群；旧kind all在Mac启动任何Docker命令前拒绝，validate也不查询Docker |
| VM全组预检 | 最新Ansible validate为ok=5、changed=0、failed/unreachable/rescued/ignored=0；十VM真实IPAM/CIDR、路由、MTU、防火墙和VIP冲突前置通过 |
| 配置 | 20个内置对象严格服务端预览；25份CRD用SSA预览；8份自定义对象按锁定schema验证；4种Cilium网络profile实际Helm渲染，Secret不写公开输出 |
| 测试 | VM/历史边界回归18项、共享框架4项、Shell语法通过；真实Ansible的正常、观察失败、命令失败、显式recover和回退失败五种模型通过 |
| 原revision兼容 | 原Helm manifest中的9个控制器/ConfigMap经实际API严格dry-run后，UID和spec/data与现场完全一致；原始渲染中的零值/省略字段差异保留独立比较记录 |
| 恢复语义 | 22个正常步骤、7个恢复步骤；原Helm revision/值/manifest摘要及控制器UID/spec保护；回退失败仍撤销临时规则，且不伪造CLEANUP PASS |
| 主线复核 | 原08保护基线一致，VM Session保护逻辑真实只读执行；Cilium revision仍为4、Cilium/kube-proxy 10/10，实验空间未创建，主 .201可信TLS返回预期404 |

40份一致源码快照见 reviewed-source/，[完整报告](delivery-review.json)、[输入摘要](source.json)、[证据清单](evidence-sha256.json)已保留。此前草稿前检暴露的Helm4接口/组件层级问题保留原日志，最终输入已重新完整核验。attempts/按仓库规则保留本地，不改写历史。

新命令与全部Ansible/YAML见[VM操作指南](../../examples/dataplane/README.md)。原Mac失败目录不能续跑，VM实验必须使用新目录；正式22步仍由用户启动。原有连接可能重连，不承诺零中断；外部BGP上游转发保持BLOCKED。02.10 VM移植未交付，其旧Mac运行方案同样停用。
