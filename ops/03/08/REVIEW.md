# 03.08 离线走查（2026-10-21）

- `validate.sh`、diff 检查通过；Redis Sentinel 渲染为合法 JSON，得到数据/哨兵的五个正式对象。
- 检查 Redis/Valkey 独立、同连接 AOF 确认、Sentinel 配置保留、分片跨域副本、TLS/ACL、Kafka 完整消息集合、Rabbit 确认与 HTTP 路由区分、NATS 有界 CLI 与持久数据检查。
- 补口令严格整文件格式检查与 Secret immutable，避免把隐含密码轮换写入运行中的服务。
- 具体 CLI 选项、Chart values/API 兼容、实际镜像、AMQP confirm 统计、淘汰/多数派/消息故障均未在内网验证；每项在 materials/README 记录明确执行门槛和证据边界。
