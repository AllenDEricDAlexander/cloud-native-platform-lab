# 02.08 执行前核验

正式资源实验未执行。全部模板预览、4项请求核算/节点字段边界回归、Go race/vet、真实 Ansible 正常/故意失败/恢复离线编排已通过，见 delivery-review.json。

PriorityClass 本身服务端预览通过；因预览不落地，引用它的两个 Pod 在结构预览时暂移除该引用，原引用检查为已声明的两个负优先级。正式 all 先创建本批 PriorityClass，再对原 Pod 在真实 Namespace 严格预览后应用。

已构建并核验两个架构的固定上限 Go 诊断镜像；实际 CPU/OOM/卷驱逐/抢占/PDB 结果仍由操作者 all 运行采集。整 VM 压力排序保持 BLOCKED。
