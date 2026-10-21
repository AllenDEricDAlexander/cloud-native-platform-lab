# 03.08 缓存与消息

覆盖 03.08.01–07；ECK 为扩展对照。离线 `bash ops/03/08/run.sh validate`。按组件逐套实验、记录和停机，不能在 16Gi storage VM 上同时开启全部重型服务。

前置 05、独立备份、三物理域；credentials 从 middleware.password_file（32–128 位单行十六进制）创建缓存/测试应用身份。middleware.tls_secret 预置 ca.crt/tls.crt/tls.key，证书 SAN 覆盖相应 Service/Pod 的完整 cluster.local 名，密钥只经 Secret 挂载。tls-auth-clients 开启。所有组件及 CLI 的版本、镜像、API、Chart values、参数与证书必须先登记主版本锁和 materials；不自动下载或选择最新版本。

| 入口动作 | 目标与验证 |
| --- | --- |
| redis → redis-test → redis-restart → redis-eviction | 独立单实例、AOF/RDB、TTL、重建读回与有界淘汰 |
| redis-sentinel → redis-sentinel-failover | 三数据节点加三 Sentinel，跨域、发现新主与已写值；与分片分开 |
| redis-cluster → redis-cluster-test | 三 master、三 replica，按另一个域显式加入，检查槽、重定向与复制关系 |
| valkey → valkey-test | 独立镜像/身份空间；兼容性与许可对照，不替代 Redis |
| kafka → kafka-test → kafka-failover → kafka-lag | Strimzi/KRaft 三双角色节点、mTLS/ACL、20 个唯一 ID、acks=all/幂等生产、单 Broker、offset/lag |
| rabbitmq → rabbitmq-test → rabbitmq-confirm → rabbitmq-failover | Operator/Quorum Queue、受限 vhost/app、持久 ID、重投/死信、独立 AMQP confirm、成员失败后取回 |
| nats → nats-test → nats-failover | Core Pub/Sub/Request-Reply、JetStream 文件三副本、发布 ACK、序号、持久消费者/确认及 leader 重建 |
| eck → eck-test | 独立 ECK/Elasticsearch 三节点、受限身份、TLS 写读/匿名拒绝；独立快照恢复另测 |

缓存启动配置保存在专用 PVC，Sentinel 的重写状态不能在重启时被初始 replicaof 覆盖。Redis/Valkey CLI 需要 WAITAOF 支持，脚本不把默认异步 AOF 等同于零丢失保证；maxmemory=64mb、allkeys-lru 只为轻量缓存实验，业务关键数据不能依赖此淘汰设置。实际淘汰实验需在独立 key 空间/配额内运行并记录 INFO stats，不能用持久标记丢失冒充磁盘故障。

Kafka client 使用 Operator 生成的 PKCS12 Secret，SSL endpoint identification 开启。所选 Strimzi 需支持源清单中的 KRaft/NodePool/metadataVersion；API 版本变化时先更新对应具体清单，不启用 ZooKeeper 回退。内部监听器面向集群内客户端，外部 advertised listeners 按显式规划另配，不套单端口代理。每次功能测试新建专用 topic，消费比较完整 ID 集，积压用例有限生成 20 条，不能无限灌流量。

Rabbit HTTP 测试通过 TLS 管理 API 建立受限 app/vhost/队列，HTTP routed 只表示路由成功；AMQP publisher confirm 用锁定的 rabbitmq_perf 镜像单独测。该组件需在 materials 填实际 command 数组，并在兼容记录确认 CLI 参数、URI/RABBITMQ_PERF_TEST_URI 绑定、CA truststore、confirm/ack 统计与不输出连接口令。perf 日志可能包含 URI，不直接归档，先在受控位置脱敏。rabbitmq-confirm 的 Job 完成后仍须核对实际 20 条 confirm/ack，不单凭退出码判定可靠性。slow consumer/崩溃重投与积压在 HTTP 测试和有界 producer/consumer 参数下对照；不强缩 quorum 到零。

NATS Chart values_file 必须配置 release 的实际 Service 名为 nats、三副本、JetStream PVC/RBD、TLS/认证、跨物理域、内网 Digest；同 Chart 版本核实字段。nats_context_secret 挂载 user.creds，仅允许测试账号 subject/API。CLI 语法（reply/count、consumer next/ack）随所选版本校验，不能把 CLI 参数错误当成服务拒绝。nats-test 产生新数据，nats-failover 只核对原持久数据；重跑已有 Stream 要先核对消息和保留策略，禁止清空掩盖失败。

停机前分别保存身份、拓扑、ISR/多数派、消费位点、业务 ID 与备份。没有统一 scale-to-zero 或一键删 namespace；PVC 默认保留，清理按每套 Operator 的规则逐项释放。所有真实缓存/消息/故障与吞吐均待内网测试。
