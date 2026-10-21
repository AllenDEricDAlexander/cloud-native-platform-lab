# 05.03 离线走查

2026-10-21：全阶段离线入口及 ServiceMonitor/ScrapeConfig 两种源的本地构造通过。已核对 HTTPS/CA/认证引用、cnpl_source、基数上限、完整 11 类覆盖门槛和无数据失败；不在本阶段复制原 exporter/Operator 的部署所有权。

真实 exporter metric 名、ScrapeConfig CRD/API 及 Prometheus selector、16 台时间戳、ESXi/vCenter 许可与权限、20 条消息积压/恢复、Ceph 与 Datastore 联动、CI/仓库指标仍待内网验收。规则阈值为明确起始值，需结合真实基线调整。
