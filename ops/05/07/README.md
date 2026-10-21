# 05.07 SLI/SLO 与发布分析

覆盖 05.07.01–04。输入 slo.service/environment/objective/latency_seconds/min_requests 必须来自真实业务基线；不预填达标百分比。计数器契约：cnpl_http_requests_total 按 service/environment/version/outcome，outcome=success/error 是有效用户请求，excluded 需业务说明；duration histogram 使用相同有效请求、秒单位和覆盖目标的 bucket。异步消息另用业务确认/处理时限计数，不能拿 Pod Ready 或生产者发送成功代替。

```bash
bash ops/05/07/run.sh validate
# 内网后先审核分母、排除项、窗口与基线：
bash ops/05/07/run.sh render rules
bash ops/05/07/run.sh install
bash ops/05/07/run.sh check
bash ops/05/07/run.sh render rollout-patch
bash ops/05/07/run.sh analysis-run
bash ops/05/07/run.sh rollout-check
```

SLI 定义为 success/(success+error)，延迟为累计 histogram 合格请求/总有效请求；0 请求、低于 min_requests、缺失/NaN 均不生成有效 SLI。30 天错误预算为 1-objective；1h/5m=14.4、6h/30m=6 的双窗口燃尽告警区分紧急/趋势风险，短时高错误与持续低错误需真实回放验证。没有 error 序列时应由应用初始化 error=0，禁止通过 `or vector(0)` 把采集失败变成健康。

Rollouts 输入 rollout_namespace/name/uid、candidate_version、同命名空间 prometheus_secret（token）与受 CA 信任的 Prometheus URL。AnalysisTemplate 同时校验候选版本成功率和 P95，缺数据/NaN/查询错误不能晋级。`rollout-patch` 仅输出原拥有者需要合入的配置片段，不直接改 Phase 04/GitOps 的 Rollout；按原发布流程集成。analysis-run 是独立分析验证，成功不代表灰度已自动接入或回退已完成。

真实发布实验分别覆盖：好版本、故意退化版本、人工暂停/批准、自动中止和监控不可用。由 Phase 04 原 CI/GitOps 发布，先记录稳定制品与客户端基线，再变更坏版本，保留 AnalysisRun/Rollout 状态、流量权重、实际客户端请求与恢复稳定版本的结果。禁止只凭 AnalysisTemplate/AnalysisRun 存在判定阻断已通过。

timeline_event_file/sha256 指向带证据的 JSON（id/phase/observed_at/source/subject/revision/evidence_file/evidence_sha256/summary），observed_at 使用 UTC Z。`timeline-append` 加锁追加、不覆盖同 ID；部署/配置/维护/Ceph/告警均可加入 change 事件。故障报告必须有 failure_started、detected、response_started、service_restored、data_verified 五个真实时间点，输出检测/响应/服务恢复/数据验证耗时；RPO 还需已确认数据核对。

本轮未运行 promtool、Argo API、真实燃尽/退化/回退或客户端检查。失败保留事件与预算窗口，不通过清空计数器/重建监控来美化结果。
