# 06.05 HPA、VPA、KEDA 与容量

覆盖 06.05.01–06。入口 `run.sh validate|render|install <vpa|keda>|apply|check|observe|verify-messages <回执JSON>|cleanup-plan`；实际动作连接内网后分别执行。先确保 metrics-server、自定义指标 adapter、Kafka/RabbitMQ 03 数据链路真实验收；自定义指标名 `lab_http_requests_per_second` 须在 adapter 中按 Pod 提供，缺指标时记录 HPA 条件，不伪造空闲数据。

HPA 使用 CPU+真实请求率并设稳定窗口；VPA 单独指向 vpa-demo 且为 Off，仅收集建议。Kafka、Rabbit 分别指向独立 Worker，KEDA 管理自己的 HPA，不能再手工向这些 Worker 绑定同维度 HPA。Kafka 上限不超过本实验登记的 1–4 分区；RabbitMQ 凭据 Secret 的 uri 需 AMQPS/可信 CA，Kafka 明确 TLS/SCRAM，具体 scaler 字段在版本锁定时与 CRD 核对。

worker 镜像契约：`consume --backend kafka|rabbit --run-id <id>`、非 root 8080 `/health`；从受控 Secret 注入真实连接配置，业务 ID 去重后提交 effect 与 offset/ACK，Rabbit 设置有限 prefetch，关闭时先停止接新消息、完成处理再 ACK。生产器复用 03 的授权客户端，限定本批 topic/queue，发 100 条含唯一 ID 的消息；先保存发布确认清单，制造积压再开始 observe，记录处理完成和缩容。凭据/消息体不进入普通证据。

`observe` 只收集 60 秒控制器/副本时间线，不能代替吞吐与业务正确性。将真实 `published_ids`、`acknowledged_ids`、`effect_ids` 数组交给 messages.rb；允许重复投递，缺确认/业务结果、未知 ID 或重复业务效果均失败。另做消费中断、缩容中断、认证/指标源不可用实验；恢复后核对同一 ID 集合。

缩零对照分别记录：原生 HPA 的目标版本 Feature Gate 与仍在线的外部指标；KEDA scaler 谁负责 0→1；Knative activator 谁承接并缓冲冷请求。CPU 无样本不能唤醒零实例，普通 HPA 此处 min=2，不能把它当成已实现缩零。事件恢复时间需包含拉镜像、应用就绪、重平衡和积压清空。

容量实验从小负载开始，与 01 已有 PriorityClass/ResourceQuota/PDB 场景对照；高优先级只给在线样例，批任务交给 08 Kueue。观察 Pending 原因、PDB 允许驱逐数与节点余量，接近 Ceph 水位立即停止。HPA 不扩容 ESXi VM，PDB 也不能阻止 HPA 正常缩容或节点故障。

退出先停生产器、核对消费/ACK、撤 ScaledObject/HPA，再将本批 Worker 恢复约定副本；VPA 推荐报告保留。共享 KEDA/VPA 与消息系统不随本批删除。消息吞吐、缩零唤醒、压力与丢失/重复均待内网实测。
