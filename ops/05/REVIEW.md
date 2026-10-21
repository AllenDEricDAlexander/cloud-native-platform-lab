# Phase 05 离线交付走查（2026-10-21）

本轮按 plan/05-observability.md 的 9 个子阶段、42 个稳定步骤交付 `ops/05/01`–`09` 脚本、配置与操作规程，并逐子阶段提交。没有联网、下载物料、SSH、访问 VM/Kubernetes/CI/API、启动浏览器、本地容器/服务或正式实验。

## 已执行验证

| 检查 | 结果与证据边界 |
| --- | --- |
| `bash ops/05/validate.sh` | Shell/Ruby 语法，Python AST，k6 JavaScript 模块语法，JSON/YAML 与 YAML 重复键检查通过 |
| Ansible syntax-check | 01 的 inspect/install/configure/verify、08 的 load 共 5 份 Playbook 通过，只解析，无远端任务 |
| 本地基础检查 | 9 项，含无物料拒绝、未锁镜像/Secret 拒绝、重复键、16 台台账一致性、外部探测 TLS 与过期指标拒绝 |
| 渲染检查 | 19 组，覆盖 metrics values/资源、ServiceMonitor/ScrapeConfig、Collector、ELK 双路线/ILM/模板/查询/Kibana、三后端/数据源、SLO/AnalysisTemplate/接入片段和 OpenCost values。物料方法只在此本地 fixture 中替换，不代表真实版本锁已完成 |
| 客户端替身防护检查 | 19 项，覆盖原 UID/副本恢复、替代 UID/其他批次/GitOps 拒绝、外部客户端失败、并发缩放不覆盖、9 个非法动作在客户端调用前失败、原错误码与恢复失败并存记录、HTTP 条件调用不能绕过权限/配置/内部 URL 防护；真实 kubectl/curl/网络调用为零 |
| Context 与监督检查 | W3C 全零 ID 拒绝、同步 parent 与异步独立 trace/link；压测缺数据/NaN/Inf/越界拒绝，不启动进程或监听端口 |
| 计划索引 | 42 步 ID、子阶段目录与交付文件存在性检查通过；所有 runtime_status=not_executed |
| 文档与差异 | 68 个本地 Markdown 文件链接和任务范围 git diff --check 通过；未修改或提交既有 00–02 脏文件 |

原生 PromQL/Collector/Fluent Bit/Lua/Logstash/Loki/Tempo/Pyroscope/k6/OpenCost、Chart/CRD/API schema 不由以上构造检查代替。物料和 compatibility_file 未确认则实际部署停止。

## 整阶段联查修正

- inspect 不要求安装秘密；Zabbix 精确 7.0 LTS RPM/NEVRA/SHA/签名、Server/Agent/数据库归属和空库事务保护独立检查；API 用明确 hostid，按摘要跳过无变化的主机/探测/触发器更新，并约束 7/90 天保留。
- 私有文件只允许仓库外本人所有 0600/0400；秘密不进 argv/日志，私有 JSON 解析错误不回显正文；curl 只接受认证/CA 选项并禁止跳转/外部 API，失败不能在条件调用中绕过检查。
- CRD 同批重跑只接受相同 spec，其他批次或 GitOps 对象拒绝接管；显式 kubeconfig/context/集群 UID 与十节点基线约束实际动作。
- 故障使用 UID/resourceVersion/原副本 JSON Patch；恢复再次核对归属，拒绝替代对象/并发缩放。保留独立管理端 watchdog、EXIT/信号恢复、原失败码和恢复失败标志。管理端掉电不在该 watchdog 保证内。
- OTel 日志默认关闭；Loki 路线拒绝与 ELK namespace 重叠，不默认全量双写。三信号出口分离，mTLS、字段白名单、采样、内存/队列/重试均有边界。
- Fluent Bit 保留原 CRI 时间、offset 和有限文件缓冲，补多行/大小写敏感字段遮盖；Logstash PQ 独立 PVC，两条 ES 路线均按日索引并配置 ILM，保留脱敏失败样本。
- SLO/发布分析不把无请求、少样本、空序列、NaN/无穷值当健康；候选版本过滤与原 Rollout/GitOps 接入片段分离，独立分析成功不冒充实际回退。
- 压测只到内部实验服务，有限 VU/时长；真实安全信号缺失或超限停止本次进程组，SIGTERM 同样清理；性能/成本报告要求原始证据和相同条件，不自动调整业务资源。
- 交接只暂停有停写/刷队列/归档证据的本批闲置后端，保留主日志、最低监控、PVC/bucket 和失败记录，无全局 prune。

## 后续内网验收边界

精确版本、物料摘要和兼容记录仍按主锁 pending，不通过猜测新版本消除阻塞。build01 Zabbix 先核对实际资源、RPM/DB/PHP/Nginx/SELinux/CA、16 台数据与中断恢复、重复执行幂等。主集群需确认 Phase 03/04 前置、存储/网关和控制权交接后再逐专题运行。

七语言配置/接入契约已交付；Rust/C/C++ 的业务手动 SDK 适配、真正的 HTTP/gRPC/消息调用和 Java Profiling 属后续业务/运行集成，不能用 carrier fixture 或伪造 spans 验收。vSphere/网络设备权限、servicegraph 来源、身份到租户映射、RGW 凭据/网络故障、正式 Prometheus StatefulSet 维护与原 CI/GitOps 真实灰度均有明确人工/原拥有者边界，见 coverage.json。

未做真实部署、通知、日志轮转/生命周期、跨信号关联、过载/背压、性能/成本比较、配置/数据恢复或完整资源清理。所有 runtime_accepted/phase_complete 保持 false；第二集群观测待 06C 建成后实测。本轮不自动推送或启动后续实验，原有其他阶段脏文件保持任务外。
