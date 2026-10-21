# 05.09 归档、恢复、回归与按需暂停

覆盖 05.09.01–03。当前交付只是源码/离线走查，部署、故障恢复、性能和 phase acceptance 均待实测。

```bash
bash ops/05/09/run.sh validate
# 连接内网后：先归档与回归，明确空闲后再选择暂停
bash ops/05/09/run.sh archive
bash ops/05/09/run.sh restore-dashboard
bash ops/05/09/run.sh regression
bash ops/05/09/run.sh evidence-report
bash ops/05/09/run.sh pause
# 恢复时指定上次 snapshot 路径/SHA：
bash ops/05/09/run.sh resume
```

archive_directory 为仓库外不存在的新目录；只复制 Git 跟踪的公开配置、台账、主版本锁、规则、面板和源文件，保留 mode/源提交/逐文件 SHA。实际输入、认证、数据库/PV/对象数据备份另受控管理。目录归档不是数据库或观测数据恢复证明。恢复到临时环境时先重建受控 Secret/CA、核对物料和 UID/所有权，再按 01–08 对应入口安装，不能把归档直接 apply 到不同集群。

restore-dashboard 导入实际 4 面板，并检查已有 Dashboard 的批次 tag；已有配置由 sidecar/GitOps 管理时回到原控制者，同一对象只保留一个管理入口。regression 仅检查真实 Zabbix、指标、基础设施、跨语言 Trace、选定日志后端、SLO 和成本，不自动运行负载、部署或故障注入。保存新请求→日志→指标→Trace→Profile 的实际关联证据，不能仅复用旧 Trace/旧缓存截图。

evidence_directory 指向外部证据集，其 index.json.steps 必须恰好 42 个步骤（id/status/summary/runtime/evidence 数组，每个 evidence 包含 file/sha256）。passed 需 runtime=true 和实际证据，报告不自动批准 runtime_accepted/phase_complete。发布失败、节点压力、Ceph 降级、消息积压、证书故障各建案例，含时间线、实际原因可信度和恢复/数据检查；未出现的指标保持 pending。

暂停输入：selected_log_backend=elk/loki、idle_proof_file/sha256（writers_stopped/queues_flushed/configuration_archived 均 true）、pause_targets（namespace/name/uid/idle_query）。必须先停用该对照写入并刷空队列、移除不再需要的抓取/导出，idle_query 有数据且全零。只允许本批 loki/logstash/tempo/pyroscope Deployment，禁止停主日志后端，禁止停 Prometheus/Grafana/Alertmanager、Collector、Zabbix、Ceph、仓库或业务服务。源码/PVC/bucket 保留；部分失败用本次 snapshot 显式 resume，不删历史失败证据。

resume 使用 paused_snapshot_file/sha256，按原 UID 和副本恢复；对象替换、外部并发缩放或 GitOps 管理则停止交回原拥有者。暂停前后核对最低监控、集群外探测和资源回落，仍需用户现场确认报警与通知。06C 第二集群不存在时保持未实测，不以 05 的准备配置提前判定跨集群观测通过。
