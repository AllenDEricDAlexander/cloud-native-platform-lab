# 可复现实验场景

当前为目录骨架，尚未实现或部署。按 [七阶段计划](../docs/plans/README.md) 在对应阶段补充真实文件。

| 目录 | 阶段 | 负责内容 |
| --- | --- | --- |
| `kubernetes-core/` | 01 | Pod、控制器、生命周期、探针、删除传播等场景 |
| `cilium-ebpf/` | 02 | 数据面、Hubble、L2/BGP、策略与出口对照 |
| `ceph-rook/` | 03 | 外部/自管理 Ceph、卷生命周期和故障对照 |
| `devsecops/` | 04 | 七语言示例、双 CI、GitOps 与供应链实验 |
| `observability/` | 05 | 遥测关联、故障定位、性能与成本场景 |
| `serverless/` | 06B | Knative、Dapr、Argo、NATS 事件场景 |
| `multi-cluster/` | 06C | 第二集群、跨集群隔离与流量故障切换 |
| `kubevirt/` | 06D | VM/CDI、嵌套虚拟化与迁移 |
| `ai-gpu/` | 06D | Kueue、DRA、GPU、模型服务和训练 |

每个实现或实验说明须包含输入、版本、操作、检查、失败恢复和清理；测试结果归根目录 `reports/`。秘密和二进制备份放受控外部位置，只保留安全引用。
