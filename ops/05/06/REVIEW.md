# 05.06 离线走查

2026-10-21：三后端资源/配置、数据源关联在本地构造通过；检查三个不同 bucket/凭据、HTTPS/CA、租户边界说明、保留/WAL/资源上限、无 trace_id 标签、实测对比条件一致性。

原生 Loki/Tempo/Pyroscope 配置 API、CLI 参数、RGW path-style/CA/权限、身份到租户映射、Grafana CA/证书 provisioning、实际 Trace/日志/Profile 热点与 Agent 开销、RGW 凭据/网络/后端恢复均待内网。单副本只是受控实验预算，不承诺后端高可用或零丢失。
