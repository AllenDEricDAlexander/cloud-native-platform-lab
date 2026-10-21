# 03.02 cephadm 外部集群

覆盖 03.02.01–06。离线入口 `bash ops/03/02/run.sh validate`。连接内网后逐个执行同一入口的 prepare → bootstrap → hosts → osd-plan → osd-apply → baseline → mgr-failover → backup；每个动作独立退出并保存证据，先读结果再继续。

前置：01 的实物映射/独立备份已确认；固定 FSID 用 uuidgen 在管理端生成一次；ceph 镜像锁入主版本锁和 materials。packages 填带完整版本的 podman、cephadm、lvm2、jq 及目标内核 Ceph 客户端包，private_repositories 只填写现有内网 repo ID，不增加公共源。VM 的 Podman 沿用受控 registry auth 与 CA，与 containerd 分离。cephadm 的部署命令/版本兼容性必须记录在 compatibility_file。

prepare 保留防火墙和 SELinux；规则按十节点和既有 lab_mgmt_sources 来源增加，MON 3300/6789、OSD/MDS 6800–7568、RGW 9443，不 reload 无关策略。bootstrap 禁用未配置的 Dashboard/监控栈，避免自动开放管理端口；重试只使用原 FSID，发现其他配置停止。

OSD 阶段按台账逐盘执行只读检查，再将显式 paths spec 传给 cephadm。每台最多使用已批准的内存预算；失败可能已创建部分 OSD，保留 FSID/spec 和现场，重新 inspect 后逐个处置，不能重新 bootstrap、自动 zap 或重复吞盘。现有 OSD 盘有签名时会停止，不能把此错误当作允许重初始化。

baseline 将 storage VM 的实际 ESXi 映射到 CRUSH rack bucket，创建跨 rack 规则；主机必须已经核实为三物理域。该动作只用于本脚本新建的外部集群，禁止借此搬迁已有业务集群。池在 03.03 创建。MGR 切换前要求健康且有 standby。

backup.password_file 是 storage01 上 root 所有、0600/0400 的 restic 口令文件；repository 是外部加密仓库引用，凭据不得嵌进 URL。FSID/认证/CRUSH/配置/服务规格暂存在 root 私有目录，加密入仓并 check 后清除临时明文。restic check 不是恢复验收；需在独立隔离位置验证取回材料。所有失败保留原日志，仅释放本动作临时文件。
