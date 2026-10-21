# Phase 05 离线脚本

按 [42 步计划](../../plan/05-observability.md) 交付 `01`–`09`。当前仅编写、构造检查和脚本走查，所有 VM 安装、集群部署、告警、故障、性能及恢复验收均待连接内网后执行。原 [专题手册](../05-observability/README.md) 保留为设计背景。

| 目录 | 内容 |
| --- | --- |
| [01](01/README.md) | 遥测契约、预算、隐私、build01 集群外 Zabbix |
| [02](02/README.md) | Prometheus/Grafana/Alertmanager 与自监控 |
| [03](03/README.md) | Rocky、Ceph、vSphere、中间件和 CI 采集 |
| [04](04/README.md) | OTel Agent/Gateway、七语言与同步异步上下文 |
| [05](05/README.md) | ECK 复用、Fluent Bit、Logstash、ILM 与查询 |
| [06](06/README.md) | Loki/Tempo/Pyroscope 与对象存储背压 |
| [07](07/README.md) | SLI/SLO、燃尽告警、Rollouts 与时间线 |
| [08](08/README.md) | k6、七语言/双 CI 对照、容量和 OpenCost |
| [09](09/README.md) | 配置恢复、回归、故障归档和重型对照暂停 |

设计采用现有 Bash 编排、Ruby 标准库渲染、Ansible 管 VM 的结构；共用函数只处理输入、物料、集群身份、归属和证据，无需新增设计模式。各阶段显式选择动作，默认 `validate`，不自动跨阶段部署。

```bash
bash ops/05/validate.sh
bash ops/05/01/run.sh validate
```

连接内网后按 [输入说明](INPUTS.md) 准备仓库外配置，逐阶段运行 README 中的整组入口。缺失的精确版本、SHA、凭据和运行前置不会被猜测填入。主版本锁仍为 `ops/versions.lock.yaml`。

运行证据进入各目录忽略的 `records/<run_id>/<action-随机值>/`。每次保留源提交、输入摘要、UTC 时间和退出码；`runtime_accepted`、`phase_complete` 始终由实际验收判断，不随命令成功自动提升。Mac 只做管理，不运行本地容器、集群或服务。

[整阶段走查](REVIEW.md) · [42 步交付与人工边界索引](coverage.json) · [启停/恢复顺序](09/START-STOP.md)。01–09 各一次提交，09 包含整阶段联查修正。本轮不推送，不启动正式实验。
