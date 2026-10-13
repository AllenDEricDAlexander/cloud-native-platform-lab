# Kubernetes 平台配置

当前为目录骨架，尚未实现或部署。按 [七阶段计划](../docs/plans/README.md) 在对应阶段补充真实文件。

| 目录 | 阶段 | 负责内容 |
| --- | --- | --- |
| `bootstrap/` | 01 | kubeadm/kubelet、kube-vip 与 Cilium 基础配置；主机 Linux/CRI 在 infrastructure/ansible |
| `core-resources/` | 01/02/06 | 控制器、生命周期、配置、身份、调度与伸缩的可复用 YAML |
| `networking/` | 02 | Service、DNS、Cilium、MetalLB、Gateway/Ingress、TLS、策略与网格 |
| `storage/` | 03 | Rook External/CSI、StorageClass/PVC/Snapshot，不管理外部 OSD 生命周期 |
| `middleware/` | 03 | 数据库、消息 Operator 与 CR |
| `observability/` | 04/05 | 04 最小真实灰度指标源；05 完整指标/日志/追踪/剖析/成本 |
| `security/` | 01/04/06 | RBAC、PSA、准入、身份、运行时与秘密声明 |
| `operators/` | 03 | 自研 Operator 源码/CRD/RBAC/部署与 API 说明 |
| `multicluster/` | 06C | CAPI/CAPV、集群连接、Cluster Mesh 与多集群声明 |

每个实现或实验说明须包含输入、版本、操作、检查、失败恢复和清理；测试结果归根目录 `reports/`。秘密和二进制备份放受控外部位置，只保留安全引用。
