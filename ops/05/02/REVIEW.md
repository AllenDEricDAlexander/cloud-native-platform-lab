# 05.02 离线走查

2026-10-21：全阶段离线入口通过；两组指标 values/resources 本地渲染通过，检查 7 天/8GB 双保留、PVC、通知 Secret 挂载与 4 个实际面板。Shell/Ruby/YAML/JSON 检查通过，未执行 Helm 或 promtool。

走查修正已有 CRD 仅允许同归属且 spec 完全一致的重跑；Secret 不进入普通 Chart 证据。curl 配置限制为认证/CA 选项，API 仅内部 HTTPS。故障目标采用 UID/resourceVersion/原副本 JSON Patch，恢复拒绝替代对象和并发外部缩放，独立 watchdog 比请求窗口多保留 35 秒以避免恢复先于注入。

仍待：所选 Chart 精确 schema 和镜像字段、PromQL 原生校验、Selector/目标覆盖、控制面 TLS、真实通知抑制/恢复、持久化恢复和自监控故障。watchdog 与主脚本同在管理端，不提供管理端掉电情况下的恢复承诺；状态与手动恢复参数保存在本次 records。
