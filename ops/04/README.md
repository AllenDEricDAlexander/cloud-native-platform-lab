# Phase 04 脚本

按 [55 步计划](../../plan/04-devops-platform.md) 实现，执行资产放 `ops/04/01`–`10`，原 [专题手册](../04-devops-platform/README.md) 保留为背景。本轮仅编写及离线走查；所有部署、14 组构建交付、IaC、故障恢复、灰度、准入与门户验收均未执行。

| 目录 | 工作 |
| --- | --- |
| [01](01/README.md) | 仓库、环境隔离、交付契约 |
| [02](02/README.md) | Builder、依赖代理、BuildKit、缓存 |
| [03](03/README.md) | GitLab Runner 与完整流水线 |
| [04](04/README.md) | Jenkins、JCasC、共享库与恢复 |
| [05](05/README.md) | 七语言样例与 14 组矩阵 |
| [06](06/README.md) | 双 IaC、远端 State 与集群外恢复 |
| [07](07/README.md) | Helm/Kustomize、Argo CD/ApplicationSet |
| [08](08/README.md) | Rollouts、真实指标、扫描/签名/准入 |
| [09](09/README.md) | Backstage/Crossplane 自助服务 |
| [10](10/README.md) | Tekton/Flux/Dragonfly 对照与交接 |

入口默认 validate。`bash ops/04/validate.sh` 只运行本地静态检查与不访问网络的构造检查。实际动作需显式指定，逐阶段执行并观察结果；不提供自动跨阶段部署开关。Mac 不启动 Docker/Podman/本地集群，不自动启动服务或正式实验。

离线检查使用既有Bash、Ruby、jq、kubectl的本地kustomize、Python3.11+（CNPL04_PYTHON可指定；Mac可用现有Homebrew Python）。不自动安装工具。检查内容与证明边界见[REVIEW.md](REVIEW.md)；[coverage.json](coverage.json)只索引55步文件与人工门槛，全部runtime_accepted=false。

共享 Bash/Ruby 仅处理输入、物料、目标和归属检查；部署保留在各阶段。双 CI 复用语言命令和制品契约，不增加框架或额外设计模式。未知值保持 null，版本继续以 ops/versions.lock.yaml 为唯一主锁，不通过猜测版本消除 pending。

输入见 [INPUTS.md](INPUTS.md)。运行输出进入各阶段忽略的 records/<run_id>/<动作-随机值>/，不覆盖失败证据。result.exit_code=0 仅表示当前动作成功，runtime_accepted/phase_complete 始终不自动提升。
