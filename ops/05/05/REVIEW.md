# 05.05 离线走查

2026-10-21：本地构造 logstash/direct 两条资源、ILM、索引模板、查询和 Saved Objects；JSON/YAML/重复键、Shell/Ruby 与嵌入配置检查通过。检查 ECK UID、仅选定 namespace、白名单与测试秘密遮盖、mTLS 格式对齐、独立 offset/有界缓冲/PQ、动态映射上限和已生效 ILM 查询。

未执行 Fluent Bit/Lua/Logstash 原生校验、RPM/镜像、Kibana 导入、ES 字段/生命周期、真实日志轮转/恢复、SELinux 主机访问。两条路线均按日索引，ILM 按索引创建时间删除，实际保留时长需按日边界验证。
