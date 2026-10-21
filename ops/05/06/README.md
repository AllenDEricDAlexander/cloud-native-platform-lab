# 05.06 Loki、Tempo、Pyroscope

覆盖 05.06.01–05。单副本原生 ConfigMap/Deployment/PVC，按需启用，不强制与 ELK 长期全量双写。每个后端 2Gi WAL PVC、有限内存，RGW 分别独立 bucket 与受限凭据；Loki 标签仅 service/environment/version 等稳定维度，trace_id 留内容/结构化元数据。

```bash
bash ops/05/06/run.sh validate
# 后续内网：原生配置校验后再部署
bash ops/05/06/run.sh render loki
bash ops/05/06/run.sh render tempo
bash ops/05/06/run.sh render pyroscope
bash ops/05/06/run.sh install
bash ops/05/06/run.sh check
bash ops/05/06/run.sh profile-check
bash ops/05/06/run.sh compare
```

backends 输入：HTTPS rgw_endpoint、region、三个不同 bucket、三个不同 `loki_s3_secret/tempo_s3_secret/pyroscope_s3_secret`（access_key/secret_key）、storage_class、tls_secret（服务 SAN/客户端 CA）、ca_secret（RGW CA）、gateway_namespace、三个受控 API URL/curl_config。镜像键 loki/tempo/pyroscope，各自 compatibility_file 必须核对所选精确版配置/CLI 参数；不要将本轮 YAML 构造视为原生解析通过。

Loki/Tempo/Pyroscope 开启租户区分，入口由既有受控 TLS 身份代理把身份映射到 X-Scope-OrgID；不得把用户可任填 header 当权限边界。Collector/Grafana 必须挂载 CA/客户端证书与受控 tenant header，03/04 的出口对应此处服务。Grafana 数据源 ConfigMap 提供 Loki→Trace、Trace→Logs/Metrics 关系，敏感认证经现有 Secret provisioning 覆盖，不能使用 skipVerify。Tempo 拓扑指标需核对真实 servicegraph/metrics-generator 来源，启用 nodeGraph 选项不算已经产生服务图。

`profiling.json` 提供 Java Agent 叠加配置，不覆盖已有 OTel JAVA_TOOL_OPTIONS；Agent Jar 固定物料，挂载后使用与所选版本兼容的 mTLS/认证出口。实际同负载分别不开/开启 Agent，查询真实 CPU/分配热点并与 JFR 采样比对。profile-check 需 `profile_type_id/profile_selector`，返回实际 series；不能只看 Agent 在线就说已定位热点。其他六语言先确认支持与符号，不宣称接入方式相同。

ELK/Loki comparison_file/sha256 包含 elk/loki 两条实测记录：dataset_sha256、duration_seconds、requests_per_second、retention_days、resource_budget、query_cases 必须相同；提供 measured=true、records>0、ingestion_bytes/query_p95_ms/cpu_seconds/memory_peak_bytes/storage_bytes、原始证据路径/SHA。比较只做已测数据的计算，不自己生成性能结果。

`fault` 仅暂停本批后端 Deployment，单次一个，保存队列/丢弃/内存/恢复缺口。RGW 凭据失效使用独立测试 bucket/凭据，由原 RGW 管理入口禁用后及时恢复；网络延迟仅在隔离代理端设置，禁止改全局 qdisc 或停 Ceph。任何故障均保留最低外部 Zabbix 探测。当前未部署、未执行 native 校验/Java Profiling/同负载对比或 RGW 故障。
