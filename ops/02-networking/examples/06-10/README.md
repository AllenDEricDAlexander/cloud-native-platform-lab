# Phase02 后续执行入口

Mac 只作管理端；禁止本地 Docker/kind。02.06–08 已有实际验收与清理记录；02.09 已改为用户明确选择的 .101–.110 VM 主集群方案；02.10 VM版尚未交付，不能整批 all。

| 专题 | 入口与范围 |
| --- | --- |
| 02.06 | [网络策略与出口](../policies/README.md)，保留Ceph/主Egress Gateway缺口 |
| 02.07 | [VM调度](../scheduling/README.md)，原标签/污点恢复 |
| 02.08 | [资源治理](../resource-governance/README.md)，整VM压力排序BLOCKED |
| 02.09 | [VM数据面对照](../dataplane/README.md)，完整22步与原Cilium/kube-proxy回退 |
| 02.10 | [VM移植状态](../mesh/README.md)，旧Mac/kind方案已停用 |

当前02.09在管理Mac一次执行：

~~~bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
export LAB_DATAPLANE_RECORDS="$PWD/ops/02-networking/records/02.09-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/dataplane.sh all "$LAB_DATAPLANE_RECORDS"
~~~

每一阶段使用新证据目录。失败先读原日志；正常脚本自动恢复，只有中断或未完成清理时，使用原目录 recover。原Mac/kind失败批次已经清理，不能用它继续VM实验。

旧批量入口的all在Mac提前拒绝，直到02.10完成VM移植；validate仅是源码/模板校验，不代表正式实验通过。历史kind准备记录不作为VM迁移验收。
