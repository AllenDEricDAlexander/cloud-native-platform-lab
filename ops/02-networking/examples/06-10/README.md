# Phase02 后续执行入口

Mac 只作管理端；禁止本地 Docker/kind。02.06–08 已有实际验收与清理记录；02.09 的 22 项可运行用例和恢复已通过；02.10 VM 版已交付，正式验收待执行。各步骤均以登记的 VM 为目标。

| 专题 | 入口与范围 |
| --- | --- |
| 02.06 | [网络策略与出口](../policies/README.md)，保留Ceph/主Egress Gateway缺口 |
| 02.07 | [VM调度](../scheduling/README.md)，原标签/污点恢复 |
| 02.08 | [资源治理](../resource-governance/README.md)，整VM压力排序BLOCKED |
| 02.09 | [VM数据面对照](../dataplane/README.md)，完整22步与原Cilium/kube-proxy回退 |
| 02.10 | [完整 VM 网格与身份](../mesh/README.md)，24 步及原 Cilium 回退 |

当前从 02.09 归档继续 02.10，在管理 Mac 一次执行：

~~~bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
export LAB_MESH_RECORDS="$PWD/ops/02-networking/records/02.10-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/mesh.sh all "$LAB_MESH_RECORDS"
~~~

每一阶段使用新证据目录。失败先读原日志；正常脚本自动恢复，只有中断或未完成清理时，使用原目录 recover。原Mac/kind失败批次已经清理，不能用它继续VM实验。

可选 `scripts/run-06-10.sh all` 会重新顺序执行五个专题；已经完成前序实验时只运行上面的 02.10 即可。validate 仅是准备/模板校验，不代表正式实验通过。历史 kind 准备记录不作为 VM 验收。
