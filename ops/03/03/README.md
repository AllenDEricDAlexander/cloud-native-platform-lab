# 03.03 块、文件与对象服务

覆盖 03.03.01–04。离线 `bash ops/03/03/run.sh validate`；现场顺序 pools → rbd-test → cephfs-test → mds-failover → rgw → s3-test → independent-copy → check。

pools 创建带 run_id 的专用 RBD、CephFS metadata/data 池，设置三副本/min_size=2、配额和输入选择的 CRUSH 规则；本批为三台 VM 的 host 域。池 ID 与批次写入 Ceph config-key，已有无归属池拒绝接管。CephFS 一个 active MDS 加 standby。三个池合计配额不能超过 01 的安全逻辑预算，RGW/快照/恢复另留空间。

rbd-test 只创建自己独占的 32MiB RBD；核对映射确实对应这张新测试卷后才 mkfs.ext4。用仅限 RBD 池的 client 身份写入、卸载重挂、比较校验和，并确认越池操作被拒绝。cephfs-test 使用独立 32MiB 子卷和限定路径身份，两个挂载点比较内容/权限。成功后释放测试资源；失败保留后端数据供调查。本批 Ceph 20.2.4 使用 AES256K，Rocky 6.12 内核客户端不支持，按用户选择使用 `rbd-nbd` / `ceph-fuse`。RBD-NBD 按实验室 Alpha 范围使用；没有开启旧 AES、关闭认证或在 Mac 映射卷。

rgw 使用 storage01 上 root 的 0600/0400 合并证书链和私钥文件，证书须覆盖 s3.svc.internal.egon.top。配置 TLS 9443，两个实例分散到 storage01/02；DNS/受控入口需在实际选择地址后配置，rgw_endpoint 必须使用规划域名。默认新池的副本和 CRUSH 规则在部署 RGW 前设置。受限 S3 用户无管理 caps，限制桶数/容量；凭据只写远端私有文件，按受控方式制作管理端 AWS profile。

s3-test 使用仓库外 0600 AWS credentials 与 CA 校验 TLS，执行 put/get/list/delete、哈希及匿名 403 拒绝。independent-copy 使用 `<rgw_profile>-independent` profile 和 backup.s3_endpoint/s3_destination，把已知数据复制到经证据确认的独立故障域并取回比较。端点字符串不同不证明物理独立，仍须 backup.evidence_file。原 RGW 绝不能作为本 Ceph 唯一灾备。

`certificate.sh` 校验用户离线中间 CA 签发的 S3 叶证书、私钥匹配与域名，再复制到本 FSID 的远端私有目录。现有在线 CA 的 demo/grpc-demo 域名约束保持不变。RGW DNS 轮询 storage01/02，没有健康负载均衡承诺。`s3-backup-mac.sh` 将已知对象加密保存至 Mac restic 仓库并读回；独立 HTTPS 数据库备份端点见 07。

清理只释放本次临时 RBD/子卷/测试对象，不删除池、文件系统、RGW 用户或唯一备份。MDS 切换失败先恢复服务、检查 PG/容量/挂载，禁止重建文件系统。本批 RBD 重挂/越池拒绝、CephFS/MDS 切换、双 RGW TLS 和 S3 读回均已通过，证据见 [执行记录](../EXECUTION-ceph03a.md)。
