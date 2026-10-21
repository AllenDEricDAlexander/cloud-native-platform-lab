# 06.07 Dapr、多语言与持久 Workflow

覆盖 06.07.01–03。`run.sh validate|render|install|apply|check|invoke|cleanup-plan`，默认离线。先验证实际 Redis TLS/CA/ACL 和 Dapr 控制面 mTLS；state/pubsub 两个 Component 只对 orders-python/orders-java 可见。业务空间默认拒绝下，需补 Dapr sidecar 到 Sentry/placement/scheduler、控制器到 injector 及 Redis 精确连接，不开放全网。ServiceAccount 默认不向应用挂载 Token，Dapr sidecar 的专用投影卷、mountPath/audience 和 injector 配置必须按锁定版本确认；仅声明卷不能证明 sidecar 已取得身份。

apply 的 worker 镜像须在受控构建端准备：`serve --language python|java --backend dapr --run-id <id>`、8080 `/health`、`/dapr/subscribe`、`/events`、持久化业务 ID、有限重试和取消。此处提供 [Python](client.py) 与 [JDK](DaprClient.java) 的状态/发布客户端，使用标准库，可放入两个样例镜像验证同一 API；客户端成功仅表示状态 API/发布入口接受，不能代替服务端消费幂等或 Workflow SDK。无匹配镜像时保持阻塞，不把诊断镜像当业务 Worker。

比较原生 SDK 与 Dapr 时，复用 03 已验证 Redis/消息客户端和相同 ID/负载/事务语义：保存状态、发布、消费和 effects 回执；对同一 event ID 重放，使用 05/messages.rb 核对。Dapr Redis 组件 TLS 使用容器系统信任链，必须挂载适用 CA；API Token 若启用，客户端从受控文件读取，禁止在普通日志/命令参数输出正文。对组件名、未授权 app-id、不同 Namespace 分别验证拒绝。Dapr 不是跨数据库与消息的一致性事务保证。

[workflow.json](workflow.json) 固定可重试步骤、幂等键和补偿语义。使用锁定 Dapr Workflow SDK 在样例服务实现同一实例的启动/查询/取消接口后，按 reserve→persist→publish 启动；在中途仅重启本批一个 Worker，用同一 instance ID 查询恢复，不重新创建实例。再分别断状态/消息后端、取消、升级 SDK/工作流版本，核对有限重试、补偿和已确认副作用。源码/镜像与 SDK 组合未提供时，该分支明确待实现/待现场选择，不伪装成工作流执行通过。

将 invocation、状态、Pub/Sub 与外部任务 Trace 关联到 05。记录 sidecar 额外 CPU/内存/延迟与原生 SDK 结果，错误与重试放大另列。退出先停入口、排空消息和持久工作流，再移除 Component/样例；保留 Redis 数据和必要解密材料，共享 Dapr 不随批次卸载。本轮调用、两语言业务和 Workflow 恢复均未运行。
