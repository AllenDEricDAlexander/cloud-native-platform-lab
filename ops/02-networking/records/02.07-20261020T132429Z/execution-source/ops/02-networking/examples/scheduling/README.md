# 02.07 完整 VM 调度实验

管理 Mac 一次执行整个专题：

~~~bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
export LAB_SCHEDULING_RECORDS="$PWD/ops/02-networking/records/02.07-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/scheduling.sh all "$LAB_SCHEDULING_RECORDS"
~~~

三行分别进入仓库、绑定全新证据批次、执行本专题全部实验与自动恢复。正式 all 要求同集群 02.06 的可运行用例及清理回执已经完成；validate 不要求你提前执行 02.06，便于预先检查全部配置。

| 范围 | 操作与预期 |
| --- | --- |
| 02.07.01 | 只使用 .101–.110 VM；worker01/02 设置本批临时 VM 标签，拓扑键使用 kubernetes.io/hostname；不查询或使用物理宿主机标签 |
| 02.07.02 | Required+nodeSelector 固定 worker01；不存在的选择器、超出单 VM allocatable 的 CPU 请求保持 Pending 并有本次 UID 对应的 FailedScheduling；不可用 Preferred 仍能调度；调度后改标签原 Pod 不驱逐，新 Pod Pending，恢复标签后新 Pod Ready |
| 02.07.03 | storage03 原有 storage:NoSchedule 保持。先检查其全部现有非实验 Pod 均无限容忍本批 NoExecute；NoSchedule 不驱逐既有 Pod、新无容忍 Pod Pending、指定容忍 Pod Ready；PreferNoSchedule 允许唯一目标 VM；NoExecute 驱逐本批无容忍与 5 秒容忍 Pod，无限容忍 Pod保留 |
| 02.07.04 | Anchor 与 Required PodAffinity 同 VM；三份硬反亲和在两个 VM 上恰有两份 Ready、一份 Pending；三份软反亲和都 Ready，记录实际分布 |
| 02.07.05 | maxSkew=1/minDomains=2 在两个 VM 分布 2:1；只有一个 eligible VM 时第二副本 Pending；ScheduleAnyway 变体在指定 VM 上都能运行 |
| 恢复 | 原 Node UID 校验，精确撤销本批标签与测试污点，保留原有污点；按 Namespace 原 UID 删除 lab-scheduling；既有 Pod、控制器、服务和网络配置保持 |

原 VM 不承受内存或磁盘压力。实验 Pod 有 CPU/内存上限、restricted 安全设置、无 token、无主机挂载，镜像复用已经核验的 policy-fixture。若目标 VM 出现不能无限容忍本批 NoExecute 的现有 Pod，前检在任何节点变更前退出；不将失败当作通过。

全部 YAML 在 [networking/scheduling](../../networking/scheduling)；顺序由 [cases.yml](../../networking/scheduling/cases.yml) 完整声明。[独立剧本](../../ansible/playbooks/scheduling.yml)复用[完整编排](../../ansible/playbooks/phase02.yml)：前检与所有 server dry-run→逐用例→接受回执→always 恢复；Node JSONPatch 在实际状态下生成，包含 UID 与原字段值测试，不覆盖别人后来写入的标签/污点。

各命令作用：

- kubectl get：读取原 Node/Pod、真实 QoS/调度状态和本次 UID 的事件；不读取私钥或 token。
- kubectl apply --dry-run=server --validate=strict：一次预览所有 YAML；此阶段不创建实验 Pod。
- kubectl apply ... -o json：由 Ansible 应用本批空间/Pod，记录真实 UID。
- kubectl patch node --type=json --patch-file：只改本批声明的标签/污点；UID 或字段发生并发变化会拒绝。
- kubectl delete --raw ... -f DeleteOptions.json：按原 UID 删除；kubectl wait --for=delete 等待彻底消失。

正常预期：专题全部用例通过，state/closed.json 的 cleanup_passed=true，PLAY RECAP failed/unreachable/rescued/ignored 均为 0。调度 Pending 和预期驱逐由验收器作为正向实验结果判断。

若中断或失败，使用原目录：

~~~bash
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/02-networking/scripts/scheduling.sh recover "$LAB_SCHEDULING_RECORDS"
~~~

此命令恢复本批 Node 字段并清理本批 Namespace，不重跑调度实验。之后换新目录 all。所有日志、命令结果、对象意图/UID、节点原字段、事件、输入摘要和清理回执留在原目录。
