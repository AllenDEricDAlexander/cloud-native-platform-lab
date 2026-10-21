# Phase 06 脚本

按 [83 步计划](../../plan/06-advanced-security-dr.md) 编写，子阶段保持原编号，分别放在 `01`–`17`。原 [专题手册](../06-advanced-security-dr/README.md) 保留背景与参考。当前仅编写及离线走查，所有安装、请求、身份/策略、故障、升级、备份和恢复验收均未执行。

| 目录 | 工作 |
| --- | --- |
| 01 | 安全范围、Keycloak、OIDC/RBAC、凭据轮换 |
| 02 | PSA/SecurityContext、Kyverno、供应链准入 |
| 03 | SOPS/age、External Secrets/Vault、加密与审计 |
| 04 | Falco/Tetragon 与调查 |
| 05 | HPA/VPA/KEDA、缩零与容量 |
| 06 | Knative Serving/Eventing |
| 07 | Dapr、多语言消息/状态和 Workflow |
| 08 | Argo Workflows/Events、NATS、Kueue |
| 09 | CAPI/CAPV 第二集群 |
| 10 | 多集群交付、Cluster Mesh/MCS 与故障切换 |
| 11 | KubeVirt/CDI 与持久化/迁移 |
| 12 | GPU、驱动与 DRA |
| 13 | KServe CPU、vLLM、Kubeflow、llm-d、成本 |
| 14 | Chaos Mesh 与单故障工程 |
| 15 | 相邻次版本升级和失败恢复 |
| 16 | 分层备份与独立数据搬运 |
| 17 | 两条重建路线、RTO/RPO、冷启动与交接 |

`bash ops/06/validate.sh` 和所有 `run.sh` 的默认动作只做离线检查。`render` 只生成清单。其他动作须显式选择，连接内网后按各目录顺序单独执行；没有跨阶段自动部署入口。06.14 仍属 06A，按专题顺序可先于 06.06；06.08.04 的 Kueue 在高级计算前独立执行。

输入和物料见 [INPUTS.md](INPUTS.md)。未知值保持 null；`ops/versions.lock.yaml` 是唯一版本主锁，不用猜测版本填平 pending。安装器只接受已审核的本地完整清单和兼容性证据，允许由锁定 Chart 在外部受控目录渲染后登记 SHA；本轮不下载、不连接集群、不启动容器/服务。

共用 Bash/Ruby 仅处理输入、物料、集群身份、作用域、批次归属和证据；各目录保留业务配置和动作。直接函数足以表达这些顺序流程，不增加框架、依赖或设计模式。禁止接管其他批次、现有 GitOps 或共享控制器；04/02 已管理的组件应复用并检查，不能通过本阶段 install 强行迁移所有权。

运行输出保存在各目录忽略的 `records/<run_id>/<动作-随机值>/`，结果记录始终包含 `runtime_accepted:false` 和 `phase_complete:false`，动作退出 0 只表示该动作成功。高风险手工步骤必须按规程另存真实证据后才能验收。不要将私钥、Token、完整 kubeconfig、未脱敏 values/日志、备份或 State 提交到 Git。
