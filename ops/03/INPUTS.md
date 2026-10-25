# 输入契约与物料登记

仓库中的 inputs.json/devices.json/materials.json 保持未知值，不承载密码或当前未核实的信息。复制到仓库外，使用三个 CNPL03_* 文件路径变量；不要通过 source 执行 JSON/任意环境脚本。run_id 为 3–20 位小写字母、数字/横线，首位字母，同一数据集各阶段沿用一个值。动作前先查看本子阶段 README，不跨阶段并发变更同一数据集。

主集群 Kubernetes：context 为准确上下文名、cluster_uid 为 kube-system Namespace UID、kubeconfig 为仓库外 0600/0400 文件。UID/台账十节点/地址/Ready 均匹配才变更；不能从“当前 context”猜目标。SSH 使用登记 IP、known_hosts 严格验证与既有 cnpl_lab_ed25519；不同管理密钥通过 CNPL03_SSH_IDENTITY 路径指定。Ansible 沿用 00 的专用环境，CNPL03_ANSIBLE 可指向已有 ansible-playbook。

OSD：devices 列表每条含 host、stable_id（整盘 by-id）、bytes（整数）、contains_data=false、approved=true、evidence_file、evidence_sha256。ceph.failure_domain 默认 rack，另外要求 hypervisor/datastore/backing_disk/raid 与主台账 actual_hypervisor 一致且为三物理域；显式 host 表示按三台 VM 验证，物理字段保持未知，不据此声明物理冗余。主 hosts.yaml 登记 osd_device_ids，resources.yaml 批准初始化并核算预留。默认清单为空，绝不按 /dev/sdb 猜盘。对照列表另需 ip，必须与显式 inventory 主机集合/地址对应；对照集群输入也使用本契约，UID 与主集群不同。

独立备份：backup.independent 仅在已核实外部介质/故障域/读取条件后为 true，evidence_file/sha256 指向这项确认记录。本批主备份在独立 backup VM 文件系统，管理材料和数据库对象另存 Mac 加密副本；物理离域未核验。默认 mode=remote 时 repository/password_file 是 storage01 上的引用，口令文件 root 0600/0400；mode=mac 时二者属于当前 Mac，repository 为仓库外本地绝对目录，口令文件为当前用户所有的 0600/0400 文件，restic/restic_sha256 固定二进制。Mac 备份只输出加密仓库回执及恢复材料摘要。local_restore_directory 是仓库外独立导出目录。对象备份的 s3_endpoint/s3_destination/s3_secret/s3_ca_secret 为明确 HTTPS 目的地及 K8s Secret 名，不能使用本 Ceph 的 RGW。

本批原生对象备份另需 s3_access_key_file/s3_secret_key_file/s3_config_file/s3_certificate_file/s3_key_file/s3_ca_file，均为仓库外受控文件；s3_filesystem_uuid 固定已有 `/srv/backup`，s3_binary_sha256 必须与 backup_objectstore 物料一致。prepare 仅安装缺失的锁定二进制，拒绝覆盖不同 SHA/符号链接。现有备份文件保留，不配置主数据盘静态加密；Mac restic 提供加密副本。凭据不能写入输入 JSON 明文。

物料 components 是按名称索引的对象。每项必有 version、compatibility_file（本地核对报告绝对路径）、compatibility_sha256。镜像项另有 image，必须是 Harbor 完整 @sha256 引用；Chart/清单项另有 file 和 sha256。它们与主版本锁该组件的 version/artifacts 对应，脚本检查 image/SHA 确实在主锁记录中。Chart 另需 values_file、values_sha256；values 中只引用预先管理的 Secret，明确所有实际镜像和启用范围。VM 使用 linux/amd64，Mac 的 arm64 工具/镜像不能冒充目标物料。

主机依赖可额外提供 ceph.rpm_bundle（管理端 tar 路径）、rpm_bundle_sha256、rpms（仅 RPM 文件名到 SHA256 的映射）。包内文件应与目标 VM 的精确依赖事务一致，不包含额外弱依赖；prepare 在每台 VM 再验证文件与发行签名，然后关闭所有仓库安装这些文件。repository_file 是可选的仓库外私密 repo 配置，gpg_file/gpg_sha256 指向已确认的 Ceph 公钥；这些引用不承载密码内容。

| 子阶段 | 物料 key | 类型/附加字段 |
| --- | --- | --- |
| 02–03 | ceph | 镜像；cephadm/Podman/RPM 精确包版本及私库 ID 在 ceph 输入中 |
| 04 | rook、ceph_csi、snapshot_controller、probe | Rook Chart；独立 Ceph-CSI Driver Chart/values；snapshot_controller 完整安装清单；probe 镜像 |
| 07 | postgresql、postgresql_cnpg、cloudnativepg、barman_plugin | 普通 PostgreSQL、CNPG 专用镜像；CNPG Chart；Barman 完整安装清单 |
| 07 扩展 | postgresql_upgrade、mysql_operator、mysql、mysql_client | 升级镜像（目标 version 与 postgres.upgrade_version 相同）；MySQL Chart；MySQL 镜像加 imageRepository；客户端镜像 |
| 08 | redis、valkey、strimzi、kafka | Redis/Valkey 镜像，Strimzi Chart，Kafka/CLI 镜像 |
| 08 | rabbitmq_operator、rabbitmq、rabbitmq_perf、message_tools | Operator 清单、服务端镜像、perf 镜像及实际 command；confirm 另锁 probe_class_file/probe_class_sha256/probe_source_sha256/client_jar_sha256；受控测试工具镜像 |
| 08 | nats、nats_cli、eck、elasticsearch | NATS Chart、含 nats CLI/sh/timeout 镜像；ECK Chart、Elasticsearch 镜像 |
| 09 | demoapp_operator、demo_app | 构建后的控制器 Digest、兼容 PORT/DEMO_MESSAGE/非 root 的测试应用 Digest |

Rook 导出输入指远端官方 exporter 路径/SHA 和按版本核对的参数数组；外部连接文件为带 fsid 的 Kubernetes List，不执行其中 shell。values_file 要包含该版本正确的 driver/sidecar Digest、watch 范围和 CSI 资源限制。新安装 CRD 记录 release 与源 spec SHA；后续 spec 变化停止，CRD 升级另审，不由 Helm 静默略过。

ceph.cephx_key_type 必须显式选择，本批为 aes256k；ceph.rbd_mounter=rbd-nbd、ceph.cephfs_mounter=fuse。模板保留通用内核挂载默认，不能直接套用到当前强认证集群。当前节点插件 RBD request 256Mi/limit 2Gi、CephFS 128Mi/1Gi，OnDelete；values SHA 随明确资源变更更新，不能为更新配置直接重启活动映射。

数据库口令为仓库外单行文件，07 将一个尾换行规范化掉后存入 Secret，保持 CNPG 与 pgpass 一致。MySQL/缓存/消息的测试口令为 32–128 位十六进制，避免配置/协议转义歧义。Secret 设 immutable，不把重跑 credentials 当作密码轮换；需要轮换时按本服务明确规程更换身份。证书/凭据只保存于受控文件/Secret，不提交到 Git。

middleware.nats_seed_file 是单行 NKey seed 的受控文件，生成的 Secret 包含 user.nk。operator.demo_image_tag 是 build01 上第二个 scratch 镜像的独立标签。fault.vm_host/已完成备份文件及 SHA 明确后，vm_reboot_approved 才能用于授权窗口；vm_evidence_directory 指向原始重启回执，仅供后续只读复核，不能改写原失败。交接时 fault.approved 和 vm_reboot_approved 均关闭；managed.approved=false，独立 Rook 已由用户取消。

现有值为 null/pending 时可以完成源码离线走查，但不能执行部署。compatibility_file 必须是已完成的版本/API/镜像/CLI 核对记录，不能用空文件 SHA 或本轮离线报告替代。
