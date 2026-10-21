# 观测启停与恢复次序

最低常驻：build01 Zabbix/PostgreSQL/Web/Agent 与外部 DNS/API/仓库探测；集群 Prometheus/Grafana/Alertmanager、节点/对象状态、Ceph/仓库采集、必要 Collector 和选定主日志后端。它们不能随对照实验一起清空。

首次启动：先确认 00 Linux/DNS/CA、01/02 集群/网关、03 存储/中间件和 04 样例/交付基线；01 Zabbix → 02 指标 → 03 源 → 06 后端与受控身份入口 → 04 OTel/多语言（未选日志 exporter 关闭）→ 05 ELK（若选择）→ 07 SLO → 08 有界实验。此处是依赖顺序，不是自动跨阶段执行脚本。

有状态后端恢复：先 RGW/存储和凭据 → 原 PVC/WAL → 后端 Ready → Collector/Agent 出口 → 新请求与业务 ID 核对 → 时间线/告警/队列与数据缺口。不要用新建空 bucket/PVC 冒充恢复；重型对照的停写/刷队列/归档先于 pause。原状态不可用时按已验证备份恢复到新目标，不修改旧失败数据。

故障恢复：确认只是当前批次故障，检查 records 中 target/snapshot 与恢复记录，核对 UID 后重试本批恢复。管理端故障会影响本地 watchdog，保留手动恢复入口和原副本。不得全局 prune、停 firewalld/SELinux 或清理其他阶段的资源。
