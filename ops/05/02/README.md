# 05.02 指标、面板和告警

覆盖 05.02.01–06。输入为 metrics 的存储、管理员已有 Secret、含 `alertmanager.yaml` 的 `notification_secret`、内部 HTTPS API/curl 配置、已配置 TLS 的 Gateway。版本物料分别锁定 Chart `prometheus`、镜像 `prometheus_image/prometheus_operator/prometheus_config_reloader/grafana/alertmanager/node_exporter/kube_state_metrics`；各镜像必须在 Harbor 用 Digest 固定。可选原生规则检查工具键 `prometheus_tools`。

```bash
bash ops/05/02/run.sh validate
# 以下需要内网及已补齐的 CNPL05_INPUTS/CNPL05_MATERIALS：
bash ops/05/02/run.sh render values
bash ops/05/02/run.sh check-rules
bash ops/05/02/run.sh install
bash ops/05/02/run.sh configure
bash ops/05/02/run.sh check
bash ops/05/02/run.sh alert-test
```

`install` 的 kube-prometheus-stack values 限定保留、PVC、资源与采集标签。先确认 Phase 04 最小指标平台的采集/规则控制权交接：原控制者停用旧抓取与告警，再由同一受控平台扩展；不可并行安装重复告警平台。已有非本批对象会被入口拒绝，GitOps 管理的环境应把渲染结果交原控制者。控制面/etcd 采集默认关闭，待核对其证书与端点后使用 03 的显式源接入，不开放额外监听端口。

`notification_secret` 指向事先建立的配置 Secret，02/alertmanager.yaml 为路由模板；另建 `notify` Secret 的 url，挂载至 `/etc/alertmanager/secrets/notify/url`。必须在所选 Chart 中配置 `alertmanagerSpec.secrets: [notify]` 并检查所选 Alertmanager 支持 url_file。没有现成通知渠道时先填内部测试 receiver，真实通知验收保持 pending。

`configure` 导入 4 个有实际 PromQL 的面板、Recording/Alert Rules 与 Grafana HTTPRoute。默认数据源 UID 是 `prometheus`，部署时核对实际数据源。`check` 将无数据与 up=0 都视为失败；`alert-test` 只发送 90 秒测试事件，收到 firing 和 resolved 才算通知通过。分组/抑制风暴用相同 service/environment/team 的 warning 与 critical 测试事件验证，不能只凭 API 200 判定。

`fault` 仅对输入 fault 中同一 UID、同一批次的隔离 Deployment 缩到零，5–120 秒独立 watchdog 和 EXIT 双恢复；不接管 GitOps 对象或删除 PVC。用于专用 exporter/数据源代理/Collector/测试 Alertmanager，逐项保存前后查询。Prometheus StatefulSet 重启和正式 Alertmanager 不可用实验需在现场确认其精确 UID/控制者后单独维护窗口执行，禁止通过关闭节点/API/共享存储代替。管理 Mac 关机同时丢失 watchdog 时，使用 records 中 target.json 手动恢复原副本；这不等于集群独立恢复保障。

当前只离线检查。原生 Chart/API、promtool、通知渠道、存储恢复、抓取 TLS 和故障用例均待实测。失败保留 Helm 历史、PVC 和本次证据；按 Helm 指定 revision 回退，不删命名空间或 CRD。
