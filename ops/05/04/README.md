# 05.04 OTel 与多语言上下文

覆盖 05.04.01–04。配置分节点 DaemonSet Agent 与单 Gateway，使用 mTLS、授权命名空间 NetworkPolicy、memory_limiter、字段白名单、敏感模式遮盖、有界 batch/queue/retry 和错误优先尾采样。gateway 单副本保证同一 Trace 的尾采样路由；扩容前需按 Trace ID 一致路由，不能直接增加副本。

```bash
bash ops/05/04/run.sh validate
# 后续内网整组入口：
bash ops/05/04/run.sh render agent-config
bash ops/05/04/run.sh render gateway-config
bash ops/05/04/run.sh check-config
bash ops/05/04/run.sh install
bash ops/05/04/run.sh scenario
bash ops/05/04/run.sh trace-check
```

输入 `otel`：tls_secret/server CA、client_secret 客户证书/CA、tempo_endpoint（host:4317）、loki_endpoint（HTTPS /otlp）、metrics_endpoint（HTTPS /api/v1/otlp）、authorized_namespaces、sample_percent。各服务端证书 SAN 与 mTLS 客户授权现场验证。Collector 镜像键 otel_collector；原生 CLI 键 otel_collector_cli。Prometheus 需显式启用 OTLP receiver 并通过 TLS 代理，metrics 与 logs 各走支持该信号的后端，不发送给 Tempo。

logs_backend 默认 disabled，避免与 ELK 重复全量写入。选择 loki 时才需要 loki_endpoint，并拒绝与 elk.selected_namespaces 重叠；短时同样本对比使用两个隔离命名空间回放相同数据集。Prometheus 与 Tempo 管道不受该日志开关影响。

`instrumentation.json` 提供七语言接入配置。Java/.NET/Node/Python 的自动插桩包单独锁版本和摘要，挂载到既有 Phase 04 样例，不改业务镜像依赖；准确启动方式按该发行版兼容说明确认。Rust/C/C++ 使用已有业务的手动 SDK/桥接适配，按 required_hooks 编译与测试，不宣称只设环境变量就自动接入。`context.py` 提供可复用 W3C carrier 与同步 parent/异步 link 的参考语义；七语言真实 SDK 编译与接入仍需其服务仓库实现/验证。

应用设置 service.name/namespace/version/instance 和 deployment.environment.name；禁止采集请求体、SQL 文本、Token 和动态 URL 标签。发送 `CNPL_TEST_SECRET_<随机值>` 到受控测试日志/属性，查询日志和 Trace 确认已过滤；同时验证用户 A 的查询身份不能读取团队 B（访问控制由既有网关/身份层承担）。不要把真实秘密当测试样本。

`scenario_file/sha256` 指向仓库外 JSON：`services` 恰好七项，每项 language/url/curl_config（内部授权的真实业务入口），包含至少两语言 HTTP/gRPC 与实际 Kafka/RabbitMQ 消息业务。scenario 发真实 HTTPS 请求并保留 traceparent，**不伪造七语言 spans**。业务异步 trace ID 填 `async_trace_id`，同步填 trace_id；trace-check 要求实际跨服务父子和独立 Consumer link，并拒绝测试秘密/禁止属性。七语言分别是否收到正确标识、gRPC、重试/批次/并发关联由实际后端逐项核对。

用 `fault` 暂停本批 gateway 或隔离后端代理，查询自身队列、失败/丢弃计数与恢复间隙；内存队列达到边界允许丢弃，不能承诺零丢失。尾采样只比较固定同负载，head sampling 的对照需应用采样配置单独记录。当前未做原生 Collector 校验、SDK 构建/安装、业务调用或后端关联；秘密白名单和遮盖只覆盖已定义字段，仍需实际隐私反例验收。
