# 03.07 关系型数据库

覆盖 03.07.01–05。离线 `bash ops/03/07/run.sh validate`。现场 credentials → baseline → baseline-test → baseline-restart → operator → ha → ha-test → archiving → backup → pitr-before → pitr-after → pitr → failover → dump → restore-dump → check；升级和 MySQL 对照单独按需运行。

postgresql 镜像供普通 PostgreSQL，postgresql_cnpg 镜像专供 CNPG，cloudnativepg 为 Operator Chart；不能假定普通 postgres 镜像能直接运行 CNPG instance manager。两种服务端和客户端 major/协议组合须在物料兼容记录核定。Chart 的 values_file/values_sha256 放在 materials 组件内，限定只监视本 namespace、固定所有内网镜像。

credentials 从仓库外文件制作超级用户、app 和 pgpass Secret；业务测试只使用 app。baseline 验证 1000 条事务、哈希和重启，密码只由初始化脚本读取 Secret，不输出。HA 为三实例、独立 data/WAL 卷，分散到三 VM 的 hostname 域，同步至少一副本；本批 CNPG 1.30.1/Chart 0.29.1，主库从 17.10 小版本升级至 17.11，普通基准与独立大版本迁移目标为 18.6。物理故障域未验证。资源量包括全部恢复目标，另计 CSI 用户态映射内存。

archiving 使用匹配的 Barman Cloud Plugin 完整离线安装清单，在该 namespace 预置 backup.s3_secret（ACCESS_KEY_ID/ACCESS_SECRET_KEY）、backup.s3_ca_secret（ca.crt）和独立 HTTPS 对象端点；按插件本版本核对 ObjectStore endpointCA 契约，不能关闭 TLS 验证。备份/WAL 都离开原 Ceph。backup 等待原生 Backup completed；PITR 必须使用新 Cluster，输入 pitr_time 选 pitr-before 写出的带时区目标时间，再 pitr-after，等待 WAL 归档后恢复。恢复核对前 1000 条哈希、目标前 1001 存在、目标后 1002 不存在；不能只看 Pod Ready。

failover 在有限连续写入期间只删除归属验证的主 Pod，故障前至少有一次确认提交，换主后必须重新提交 10031，再检查所有 ack 事务。本批观察到主 Pod 故障后 22 秒恢复客户端提交；该时间不代表 VM 或整个数据平台恢复。客户机重启结果及失败边界见 06，不能用此 22 秒替代。

dump 写入明确独立的仓库外目录，restore-dump 仅导入新建空 Cluster。minor-upgrade 只允许同 major；major-migrate 使用独立新版本集群加逻辑 dump/restore，不原地换镜像。升级前检查官方支持路线、扩展/排序规则/编码和备份；源数据库及数据卷始终保留，客户端切换由用户在校验后操作。

MySQL Operator 2.3.1 建立 MySQL 26.10.0 三实例、两个 Router 和独立 PVC；服务端/init/sidecar 镜像锁 Digest，Operator 只接受 tag 的路径使用本批 Harbor 不可变标签并核验实际 imageID。客户端以 app 经 Router 完整 Service FQDN、VERIFY_IDENTITY 验证 1000 条事务和 SHA256；`mysql-check` 只读回原数据。`mysql-tls.yaml` 的叶证书 CN/SAN 覆盖 Service/Pod，Router 使用仅含 tls.crt/tls.key 的独立投影 Secret，以兼容该 Operator 的 CA 处理。未占用对外 MySQL VIP。

`backup-s3.sh prepare|check|restart-test` 在 backup VM 的 `/srv/backup/cnpl03-ceph03a-s3` 部署原生 SeaweedFS 4.50，使用受限身份、HTTPS 8334、持久 LevelDB2 元数据和 systemd 凭据，保留原有备份目录。主文件系统没有配置静态加密；Barman 7 天保留策略、HTTPS 和 Mac restic 加密副本分别提供保留、传输及副本保护。未验证物理离域灾备。`network-delay.sh test` 仅给独立 SQL 客户端 Pod 注入 200ms egress 延迟，已核验 20 次提交和撤销；90 秒独立 timer 已安排，本轮主动提前恢复，没有等待 timer 到期。

本批实际全备、关闭 WAL 后归档、PITR（目标前 1001 存在/后 1002 不存在）、逻辑恢复、小版本升级及独立 18.6 迁移均已通过。默认 cert-manager approver 被既有策略禁用；`lib/certificate-approval.sh` 只审核本批明确列出的 CertificateRequest 的归属、身份、Issuer 和 CSR，续签仍需该受限审批流程。失败保留数据库和 PVC，没有清空目录、覆盖恢复或强行降 major 的入口。完整证据见 [执行记录](../EXECUTION-ceph03a.md)。
