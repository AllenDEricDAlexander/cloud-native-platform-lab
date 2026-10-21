# 05.03 基础设施与中间件采集

覆盖 05.03.01–05。复用 01 的 Agent 2 接入与新鲜度检查；Ceph exporter、数据库/消息 Operator、仓库与 CI 指标继续由原拥有者启用，不再安装一套数据库、ECK 或消息集群。

```bash
bash ops/05/03/run.sh validate
# 内网就绪后，先填 sources，再按顺序运行：
bash ops/05/03/run.sh render
bash ops/05/03/run.sh configure
bash ops/05/03/run.sh zabbix-verify
bash ops/05/03/run.sh check
```

`sources.example.json` 只说明字段，不能直接部署。`inputs.sources` 每项填写 id、category、kind、TLS server_name/ca_secret、可选 authorization_secret，以及按实际 exporter 版本核实的 checks PromQL。service 类型指明 namespace/service_labels/port_name，外部类型仅允许既有 192.168.9.0/24 目标及端口；使用 HTTPS（原生 HTTP exporter 前放受控 TLS 代理），CA Secret 在 metrics 命名空间。只读数据库账户由原 Operator 建立，避免收集 SQL 文本和高成本查询。

ServiceMonitor 有 sample/label/target 限制并添加 cnpl_source；外部使用匹配版本的 ScrapeConfig CRD，Prometheus 需选择同批 ScrapeConfig。完整 check 要求 Ceph、vSphere、PostgreSQL、Redis、Kafka、RabbitMQ、NATS、GitLab、Jenkins、Harbor、Nexus 共 11 类有实际数据；只接入部分源可 configure，不能判定全覆盖。无 vSphere 权限时记录 pending，Guest 文件系统不能代替 Datastore 指标。

现场对照：Ceph 同时查询 MON/OSD/PG、慢请求、恢复流量/客户端延迟与底层 Datastore；数据库核对连接/复制/事务，Redis 命中/淘汰/持久化；消息核对 ISR/Lag/队列/确认失败与已确认业务 ID。按 Phase 03 已有专用测试 topic/queue 发布 20 条，暂停**隔离测试消费者**，查询积压至少增加 20，再恢复到原副本并逐条消费核对。`fault` 仅允许本批 Phase 05 Deployment，需单独部署测试消费者；不对业务消费者或 Broker 直接缩容。NATS 有限消息确认复用 Phase 03 的测试工具和独立 Stream，禁止变更持久化业务 Stream。

CI/仓库检查应增加实际队列、Runner/Agent、失败、请求耗时、容量和缓存命中查询，把 commit/job/artifact 写入 07 时间线，区分排队、依赖下载和编译耗时。checks 中不存在或为 NaN 的信号不算成功。示例规则名以选定 exporter 为准，不能把无序列解释成“无告警”。

失败时保留 source 状态与前后数据，只回退本次采集对象；不重启或清理被观测服务。本轮未测试权限、TLS、版本/API、Ceph/Datastore 或消息/CI 实际指标。
