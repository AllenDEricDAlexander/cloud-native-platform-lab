# 03.07 关系型数据库

覆盖 03.07.01–05。离线 `bash ops/03/07/run.sh validate`。现场 credentials → baseline → baseline-test → baseline-restart → operator → ha → ha-test → archiving → backup → pitr-before → pitr-after → pitr → failover → dump → restore-dump → check；升级和 MySQL 对照单独按需运行。

postgresql 镜像供普通 PostgreSQL，postgresql_cnpg 镜像专供 CNPG，cloudnativepg 为 Operator Chart；不能假定普通 postgres 镜像能直接运行 CNPG instance manager。两种服务端和客户端 major/协议组合须在物料兼容记录核定。Chart 的 values_file/values_sha256 放在 materials 组件内，限定只监视本 namespace、固定所有内网镜像。

credentials 从仓库外文件制作超级用户、app 和 pgpass Secret；业务测试只使用 app。baseline 先验证 1000 条事务、哈希和重启，密码只由初始化脚本读取 Secret，不输出。HA 独立三卷、跨已核实物理域、同步至少一副本；CNPG 副本策略字段由所选版本兼容记录核对。资源量（包括 baseline、主库、PITR、新恢复集群）要分别预算，不能全开耗尽 Ceph/节点。

archiving 使用匹配的 Barman Cloud Plugin 完整离线安装清单，在该 namespace 预置 backup.s3_secret（ACCESS_KEY_ID/ACCESS_SECRET_KEY）、backup.s3_ca_secret（ca.crt）和独立 HTTPS 对象端点；按插件本版本核对 ObjectStore endpointCA 契约，不能关闭 TLS 验证。备份/WAL 都离开原 Ceph。backup 等待原生 Backup completed；PITR 必须使用新 Cluster，输入 pitr_time 选 pitr-before 写出的带时区目标时间，再 pitr-after，等待 WAL 归档后恢复。恢复核对前 1000 条哈希、目标前 1001 存在、目标后 1002 不存在；不能只看 Pod Ready。

failover 在有限连续写入期间只删除归属验证的主 Pod，记录每个已确认/失败 ID，检查新主与所有 ack 事务；总观测时间不是 RTO，实际客户端失败窗口从 writes.tsv 计算。主 Worker 故障由 06 的 vSphere 规程另做，不把主 Pod 删除当作 Worker/物理故障通过。

dump 写入明确独立的仓库外目录，restore-dump 仅导入新建空 Cluster。minor-upgrade 只允许同 major；major-migrate 使用独立新版本集群加逻辑 dump/restore，不原地换镜像。升级前检查官方支持路线、扩展/排序规则/编码和备份；源数据库及数据卷始终保留，客户端切换由用户在校验后操作。

MySQL 需 mysql_operator、mysql、mysql_client 物料和 mysql-tls/mysql-ca Secret，客户端用 VERIFY_IDENTITY。mysql 建三实例、Router 和独立 PVC；mysql-test 创建独立 app 数据库/用户并用 app 验证事务。Operator 某些版本只接受 imageRepository/version，没有 CR 级 Digest 字段，必须在内网仓库锁不可变 tag、核对部署后的 Pod imageID 与已锁 Digest；未核对时不能称完成。内网 mysql.svc.internal.egon.top 入口通过明确 VIP/证书规划另接，脚本不擅自占 VIP。

失败保留数据库和 PVC；没有清空数据目录、删集群重建、覆盖恢复或强行降 major 的快捷入口。实际数据库、备份、PITR、故障和升级均未联网验证。
