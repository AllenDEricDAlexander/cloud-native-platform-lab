# 03.02 cephadm 外部集群

覆盖 03.02.01–06。离线入口 `bash ops/03/02/run.sh validate`。连接内网后逐个执行同一入口的 prepare → bootstrap → hosts → osd-plan → osd-apply → baseline → mgr-failover → backup；每个动作独立退出并保存证据，先读结果再继续。

前置：01 已按选定故障域范围完成设备核对，独立备份已确认；固定 FSID 在管理端生成一次；ceph 镜像锁入主版本锁和 materials。packages 填带完整版本的 podman、cephadm、lvm2、jq、chrony，内核 RBD/Ceph 模块单独核对；管理 CLI 通过 cephadm shell 执行。private_repositories 只填写内网 repo ID；可通过仓库外 0600 的 ceph.repository_file 提供专用私库配置，通过 gpg_file/gpg_sha256 固定公钥，安装前检查身份并复制，不记录其中凭据。VM 的 Podman 与 containerd 分离。cephadm 的部署命令/版本兼容性必须记录在 compatibility_file。

prepare 保留防火墙和 SELinux；规则按十节点和既有 lab_mgmt_sources 来源增加，MON 3300/6789、OSD/MDS 6800–7568、RGW 9443，不 reload 无关策略。bootstrap 禁用未配置的 Dashboard/监控栈，避免自动开放管理端口；重试只使用原 FSID，发现其他配置停止。

若私库下载不可用，可提供 rpm_bundle/rpm_bundle_sha256 和 rpms（文件名到 SHA256 的映射）。物料包在管理端按目标 VM 的实际依赖事务准备；prepare 核对传输摘要、每个 RPM 摘要和发行签名，再用显式本地文件、关闭所有仓库和弱依赖安装。2026-10-23 的固定包保存在仓库外 cnpl-phase03，避免依赖 Rocky 代理的临时自动阻断状态。

OSD 阶段按台账逐盘执行只读检查，再将显式 paths spec 传给 cephadm。每台最多使用已批准的内存预算；失败可能已创建部分 OSD，保留 FSID/spec 和现场，重新 inspect 后逐个处置，不能重新 bootstrap、自动 zap 或重复吞盘。现有 OSD 盘有签名时会停止，不能把此错误当作允许重初始化。

baseline 默认将实际物理域映射到 CRUSH rack，创建 cnpl03-physical。显式 ceph.failure_domain=host 时使用三台 VM 的 host bucket，创建 cnpl03-host，物理冗余保持未验证。2026-10-23 用户选择 host。Ceph 纳管/放置使用台账 FQDN，保留原有 Linux/Kubernetes 名称。该动作只用于本脚本新建的外部集群。池在 03.03 创建。MGR 切换前要求健康且有 standby。

默认 backup.mode=remote，password_file 是 storage01 上 root 所有、0600/0400 的 restic 口令文件，repository 是外部加密仓库引用。选择 mac 时，repository 是当前管理 Mac 上仓库外的绝对目录，password_file 由当前用户持有且为 0600/0400，restic/restic_sha256 固定管理端二进制。storage01 的私密归档直接流入 Mac 加密仓库，stdout 不记录归档内容；完成 restic check 后读回九项管理材料并核对 FSID，只保存摘要，清除临时明文。2026-10-23 用户选择 mac。管理材料读回不代表完整集群/业务数据恢复。所有失败保留原日志，仅释放本动作临时文件。
