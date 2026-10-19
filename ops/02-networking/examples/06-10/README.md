# 02.06–02.10：五个独立脚本，按序执行

五个专题分开提交、分开记录、分开恢复。每个all一次完成该专题全部可运行实验与自动清理，无须逐小节操作。**按顺序运行，不要五个终端并发**：节点字段和网络模式依赖前一步清理，共享批次锁会阻止冲突。

## 分步命令

先进入项目并生成本轮标识：

~~~bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
export LAB_NETWORK_BATCH="$(date -u +%Y%m%dT%H%M%SZ)"
~~~

第一行让相对路径可直接执行，第二行生成本轮UTC记录后缀。下面每条都是独立专题，可跑完一条再跑下一条，也可按顺序连续粘贴。

~~~bash
bash ops/02-networking/scripts/policies.sh all "$PWD/ops/02-networking/records/02.06-$LAB_NETWORK_BATCH"
bash ops/02-networking/scripts/scheduling.sh all "$PWD/ops/02-networking/records/02.07-$LAB_NETWORK_BATCH"
bash ops/02-networking/scripts/resource-governance.sh all "$PWD/ops/02-networking/records/02.08-$LAB_NETWORK_BATCH"
bash ops/02-networking/scripts/dataplane.sh all "$PWD/ops/02-networking/records/02.09-$LAB_NETWORK_BATCH"
bash ops/02-networking/scripts/mesh.sh all "$PWD/ops/02-networking/records/02.10-$LAB_NETWORK_BATCH"
~~~

| 命令 | 作用与预期 | 全部剧本/YAML/详细说明 |
| --- | --- | --- |
| policies.sh | 默认拒绝、标准/Cilium/FQDN/HTTP对照、内部路径/SNAT/代理；52行为用例和5组源/回程；清理；AVAILABLE CASES PASS | [02.06](../policies/README.md) |
| scheduling.sh | VM标签、Required/Preferred、三类污点、亲和/反亲和、分布；恢复原Node字段；passed与cleanup通过 | [02.07](../scheduling/README.md) |
| resource-governance.sh | 三预算/QoS、Pod OOM/CPU限流/空卷驱逐、限定抢占、PDB维护/直接删除；恢复cordon；AVAILABLE CASES PASS | [02.08](../resource-governance/README.md) |
| dataplane.sh | 专属kind中比较kube-proxy/eBPF、Overlay/Native、真实网关、L2/ARP/故障、FRR BGP/撤回，回退并删除本批环境 | [02.09](../dataplane/README.md) |
| mesh.sh | 另一专属kind中Sidecar/Ambient/waypoint、mTLS/策略/重试、SPIRE/SVID/轮换/撤销，清理后交接 | [02.10](../mesh/README.md) |

五个脚本都要求PLAY RECAP failed/unreachable/rescued/ignored=0，清理回执cleanup_passed=true。预期Pending、OOM、驱逐、配额/PDB拒绝和未授权身份由验收器判断，不能以任意命令失败代替。

BLOCKED保留：02.05公网能力、02.06 Ceph服务/主集群OpenWrt出口前提、02.08共享VM整机压力排序。02.09隔离成功不替代主集群迁移验收；phase_complete=false与通过的可运行用例分开。

## 一条命令顺序跑五个专题

若希望连续跑，先由操作者启动Docker Desktop（09/10需要，建议4CPU/8Gi，最低6Gi、linux/arm64、cgroup v2），再执行：

~~~bash
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/02-networking/scripts/run-06-10.sh all
~~~

它调用同样五个独立脚本，生成五个独立目录和整批plan/result；每一步真实可运行用例通过且清理完成后才继续。原02.05内部交接已存在，后续步骤不需额外人工归档。

整批入口的validate模式只做物料/工具/模板/版本/服务端预览及隔离结构校验，不部署实验、不自动启动Docker或应用；不替代实际all结果。

## 中断或失败

保留输出的原专题目录，执行该专题recover。例如：

~~~bash
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/02-networking/scripts/resource-governance.sh recover "/Users/mario/SelfProject/cloud-native-platform-lab/ops/02-networking/records/02.08-$LAB_NETWORK_BATCH"
~~~

此命令只恢复本批原字段/对象并清理资源，不重跑实验。成功后给失败专题换新目录all，再继续后面的独立脚本，已通过专题不必重跑。私有kubeconfig留在管理端秘密目录；公开记录保留原日志、部分成功命令、输入摘要、UID和失败原因，不含token/私钥。
