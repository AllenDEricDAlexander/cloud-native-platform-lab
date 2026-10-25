# 03.08 缓存与消息

覆盖 03.08.01–07；ECK 为本轮未执行的可选扩展。离线 `bash ops/03/08/run.sh validate`。当前配置为实验室小配额实例，部署前必须计入所有副本、恢复集群及 CSI 用户态映射内存，不照搬为生产容量。

前置 05、独立备份及已明确的 VM hostname 域。credentials 从 middleware.password_file（32–128 位单行十六进制）创建缓存/测试应用身份。tls.yaml 使用本批专用 CA 签发覆盖 Service/Pod 完整 cluster.local 名的证书，私钥为 PKCS8，仅经 Secret 挂载；不扩大现有在线 CA 的签发范围。TLS 客户端认证开启。所有组件/CLI/Chart/参数先登记主锁和 materials，不自动选最新版本。

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

Rabbit HTTP 测试覆盖持久消息、重投、ACK/DLQ，不能替代 AMQP confirm。`rabbitmq-confirm` 使用已锁 perf-test 2.24.0 镜像内 SDK 5.26.0，执行 `AmqpConfirmProbe.java`：逐条核对 20 条 published/confirmed/consumed/acked、无重复和 TLS 主机名。Java 类在 Mac 使用既有 JDK 编译为 release 17，class/source/SDK SHA 锁定；不在 Mac 启动服务或容器。URI 仅在 Secret 文件，日志只记计数。此用例验证协议确认，不是吞吐压测；本批 RabbitMQ 4.4.0 三 Quorum 副本和单 Broker 故障读回已通过。

NATS 2.15.1 为三 VM JetStream 文件副本、TLS 和 NKey 认证，`nats_context_secret` 挂载 `user.nk`，不是 JWT user.creds；仅允许本批 subject/API。CLI 0.5.0 的 reply --count 在已应答后返回 1，脚本只在读到正确 pong 时接受该已核验行为。Core Pub/Sub、Request-Reply、20 条发布 ACK、消息序号、持久消费者和 leader Pod 重建已通过。`nats-check` 只读原 20 条数据和消费者状态；不重跑创建 Stream 的测试来覆盖原证据。

Redis 8.10.2、Valkey 9.1.2、Strimzi 1.3.0/Kafka 4.3.1 均已运行验证。Redis Sentinel 换主、Cluster 全部 16384 槽及单连接 WAITAOF 已验证；`redis-check` / `redis-sentinel-check` / `redis-cluster-check` / `valkey-check` 仅读回，Cluster failback 使用协调切换恢复每 VM 一个首选 master。Kafka API 为 v1，保留原 40 条消息及一个有 20 条 lag 的测试消费组。异步 Redis 复制没有零 RPO 承诺。停机前保存身份、位点/多数派和备份，没有统一 scale-to-zero 或删 namespace；实际吞吐和多重故障未测。
