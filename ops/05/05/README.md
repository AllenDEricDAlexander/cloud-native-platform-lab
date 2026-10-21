# 05.05 ELK、解析和生命周期

覆盖 05.05.01–05。Elasticsearch/ECK 复用 Phase 03 已有实例，先用 namespace/name/UID/健康门槛核对；本目录不另建 ECK，不改原数据集群。新增小规模 Kibana，采集只允许 selected_namespaces，route 在 logstash/direct 中二选一；默认不双写全量。

```bash
bash ops/05/05/run.sh validate
# 内网与物料准备完成后：先生命周期配置，再接入写入
bash ops/05/05/run.sh configure
bash ops/05/05/run.sh install
bash ops/05/05/run.sh kibana-import
bash ops/05/05/run.sh check
```

elk 输入：既有 Elasticsearch namespace/name/uid、HTTPS API 及私有 curl 配置、selected_namespaces、route、日志 PVC storage_class、服务/客户端 tls_secret（ca.crt/tls.crt/tls.key/tls.pkcs8.key）、ES ca_secret、仅限本批索引权限的 credentials_secret（ES_USER/ES_PASSWORD）、Kibana 的 kibana_tls_secret/API。镜像键 fluent_bit/logstash/kibana；Kibana 版本需与实际 ECK/ES 匹配。PKCS8 私钥在受控目录生成并建立 Secret，不入库。

Fluent Bit tail 使用 CRI/docker 多行解析、SQLite offset、持久化 hostPath 缓冲和每输出 128M 上限，宿主机目录只挂 `/var/log` 只读与本批独立缓冲路径；仅需 pods/namespaces 只读 API 权限。SELinux 主机路径访问应按实际发行版策略授权，禁止为方便关闭 Enforcing 或默认 privileged。轮转、节点重启、Pod 删除、过长行与重试丢弃需比较发送序号/采集计数，无法只凭进程 Ready 验收。

Logstash 使用 mTLS HTTP JSON（Fluent Bit Format json 对应 JSON 数组解码），白名单/脱敏后写正常或 failed 索引；256MB 持久队列置 1Gi PVC，单副本 Recreate 避免共享队列并发。普通日志可选择 direct，先确保应用已结构化/脱敏；配置 ILM 前不能开始写。模板 dynamic=strict、单主分片/一个副本/32 字段上限，两条路线均按日创建本批索引，ILM 删除创建超过 3 天的索引，保留粒度为天。

Kibana 导入数据视图与真实错误检索，重复导入冲突时停止，不自动覆盖已有对象。用数据库失败、坏发布、权限拒绝三种受控业务事件查询 service/environment/version/trace_id/error_type，查询失败索引确认脱敏。`check` 检查 Trace 日志非空、测试秘密不存在、ILM 实际 managed 和增长统计；原生 `fluent-bit --dry-run`、`logstash --config.test_and_exit` 在锁定 Linux 物料/VM 中执行，当前 Mac 不启动容器或服务。

后端中断时使用本批隔离代理验证有界缓冲，恢复后比对唯一序号、重复/缺口；失败回退仅本次 ConfigMap/Deployment 配置，不删除索引、PVC、宿主机 offset 或原 ECK。原生插件语法、ECK/Kibana API、持久队列/轮转与生命周期时间推进均待内网实测。
