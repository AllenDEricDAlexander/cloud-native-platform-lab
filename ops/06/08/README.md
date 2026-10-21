# 06.08 Argo Workflows/Events、NATS 与 Kueue

覆盖 06.08.01–04。入口 `run.sh validate|render <argo|queues>|install <argo_workflows|argo_events|kueue>|apply|queues|check|queue-check|cleanup-plan`。两条实验独立执行：Argo 属 06B；queues 属 06D 前置，可先不装 Argo。

Argo 控制器、执行器、Events 与 NATS JetStream 按实际版本锁定；JetStream 的 version 必须在 Events 控制器配置中映射到已同步 Digest 的 NATS/reloader 镜像。渲染清单不能证明控制器生成的镜像已锁定，要现场检查实际 Pod image/imageID。三副本 JetStream 需要三个真实故障域/PVC，不满足就停止持久可靠性验收。S3 endpoint 使用 TLS、精确 bucket/prefix 和只读写本批的 Secret，CA 挂载由受审控制器/执行器配置提供。

工作流是 prepare→process→archive DAG：有限并发/重试/时长，结果绑定 event ID，制品 SHA 由归档任务输出。Workflow 身份仅 create/patch workflowtaskresults；Sensor 仅在本空间创建 Workflow。使用固定 WorkflowTemplate，另配准入限制 Sensor 可创建的模板和预算，不能把创建 Workflow 权限当任意执行安全。运行日志和 S3 实际对象都要核对，不以 CR 创建成功验收。

Webhook 只放内网认证入口，authSecret 使用该版本要求的请求认证头；经精确 NetworkPolicy 允许指定网关到 12000。样例仅接受 `<run_id>-001`，生成固定 `event-<run_id>-001`，相同事件重放会遇到 AlreadyExists，避免无界创建。不同事件使用新实验批次；通用高吞吐去重需要持久事件账本，不能推广此有界样例。检查认证失败、不匹配 ID、重复事件、有限重试和 NATS 重启后的持久化。执行器取消/失败后，制品与回执保留，业务副作用按 07 的幂等/补偿契约。

Kueue 创建只选择本批 Namespace 的 ClusterQueue 和 CPU ResourceFlavor、LocalQueue；两个各请求 1 CPU 的 suspended Job 争用 1 CPU 配额。观察一个准入、另一个保持排队，完成后资源释放并准入下一任务。需要在 Kueue 管理范围中包含本批空间、Job 集成真实启用；看 Workload admission/conditions 与 Job suspend，不能仅看 Pod Pending。取消一个任务后确认配额释放，再供 13 训练使用。

同一 DAG 与 04 Tekton/GitLab/Jenkins 对照输入/制品/重试/权限/运维，不新增主 CI。退出先停 Webhook、Sensor，处理 Workflow/Job，再保护 S3/JetStream PVC；删除 LocalQueue、ClusterQueue、ResourceFlavor 前确认无活动 Workload。不删除共享控制器、队列后端或有数据 PVC。本轮执行/重放/准入未验收。
