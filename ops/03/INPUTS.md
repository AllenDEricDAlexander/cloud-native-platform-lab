# 输入契约与物料登记

仓库中的 inputs.json/devices.json/materials.json 保持未知值，不承载密码或当前未核实的信息。复制到仓库外，使用三个 CNPL03_* 文件路径变量；不要通过 source 执行 JSON/任意环境脚本。run_id 为 3–20 位小写字母、数字/横线，首位字母，同一数据集各阶段沿用一个值。动作前先查看本子阶段 README，不跨阶段并发变更同一数据集。

主集群 Kubernetes：context 为准确上下文名、cluster_uid 为 kube-system Namespace UID、kubeconfig 为仓库外 0600/0400 文件。UID/台账十节点/地址/Ready 均匹配才变更；不能从“当前 context”猜目标。SSH 使用登记 IP、known_hosts 严格验证与既有 cnpl_lab_ed25519；不同管理密钥通过 CNPL03_SSH_IDENTITY 路径指定。Ansible 沿用 00 的专用环境，CNPL03_ANSIBLE 可指向已有 ansible-playbook。

OSD：devices 列表每条含 host、stable_id（整盘 by-id）、bytes（整数）、hypervisor、datastore、backing_disk、raid、contains_data=false、approved=true、evidence_file、evidence_sha256。主 hosts.yaml 同时登记 osd_device_ids/actual_hypervisor，resources.yaml 批准初始化并核算预留。默认清单为空，绝不按 /dev/sdb 猜盘。对照列表另需 ip，必须与显式 inventory 主机集合/地址对应；对照集群输入也使用本契约，UID 与主集群不同。

独立备份：backup.independent 仅在已核实外部介质/故障域/读取条件后为 true，evidence_file/sha256 指向这项确认记录。restic repository/password_file 是 storage01 上的引用，口令文件 root 0600/0400；不把密码塞入 URL。local_restore_directory 是独立的仓库外导出目录。对象备份的 s3_endpoint/s3_destination/s3_secret/s3_ca_secret 为明确独立 HTTPS 目的地及 K8s Secret 名；不能使用本 Ceph 的 RGW，证据不能只证明域名不同。

物料 components 是按名称索引的对象。每项必有 version、compatibility_file（本地核对报告绝对路径）、compatibility_sha256。镜像项另有 image，必须是 Harbor 完整 @sha256 引用；Chart/清单项另有 file 和 sha256。它们与主版本锁该组件的 version/artifacts 对应，脚本检查 image/SHA 确实在主锁记录中。Chart 另需 values_file、values_sha256；values 中只引用预先管理的 Secret，明确所有实际镜像和启用范围。VM 使用 linux/amd64，Mac 的 arm64 工具/镜像不能冒充目标物料。

| 子阶段 | 物料 key | 类型/附加字段 |
| --- | --- | --- |
| 02–03 | ceph | 镜像；cephadm/Podman/RPM 精确包版本及私库 ID 在 ceph 输入中 |
| 04 | rook、ceph_csi、snapshot_controller、probe | rook Chart；ceph_csi 兼容记录；snapshot_controller 完整安装清单；probe 镜像（sh/sha256sum/cmp/df 等） |
| 07 | postgresql、postgresql_cnpg、cloudnativepg、barman_plugin | 普通 PostgreSQL、CNPG 专用镜像；CNPG Chart；Barman 完整安装清单 |
| 07 扩展 | postgresql_upgrade、mysql_operator、mysql、mysql_client | 升级镜像（目标 version 与 postgres.upgrade_version 相同）；MySQL Chart；MySQL 镜像加 imageRepository；客户端镜像 |
| 08 | redis、valkey、strimzi、kafka | Redis/Valkey 镜像，Strimzi Chart，Kafka/CLI 镜像 |
| 08 | rabbitmq_operator、rabbitmq、rabbitmq_perf、message_tools | Operator 安装清单、服务端镜像、perf 镜像加 command 数组（实际 Java 入口）、包含 sh/curl/jq 的受控测试工具镜像 |
| 08 | nats、nats_cli、eck、elasticsearch | NATS Chart、含 nats CLI/sh/timeout 镜像；ECK Chart、Elasticsearch 镜像 |
| 09 | demoapp_operator、demo_app | 构建后的控制器 Digest、兼容 PORT/DEMO_MESSAGE/非 root 的测试应用 Digest |

Rook 导出输入指远端官方 exporter 路径/SHA 和按版本核对的参数数组；外部连接文件为带 fsid 的 Kubernetes List，不执行其中 shell。values_file 要包含该版本正确的 driver/sidecar Digest、watch 范围和 CSI 资源限制。新安装 CRD 记录 release 与源 spec SHA；后续 spec 变化停止，CRD 升级另审，不由 Helm 静默略过。

数据库口令为仓库外单行文件，07 将一个尾换行规范化掉后存入 Secret，保持 CNPG 与 pgpass 一致。MySQL/缓存/消息的测试口令为 32–128 位十六进制，避免配置/协议转义歧义。Secret 设 immutable，不把重跑 credentials 当作密码轮换；需要轮换时按本服务明确规程更换身份。证书/凭据只保存于受控文件/Secret，不提交到 Git。

现有值为 null/pending 时可以完成源码离线走查，但不能执行部署。compatibility_file 必须是已完成的版本/API/镜像/CLI 核对记录，不能用空文件 SHA 或本轮离线报告替代。
