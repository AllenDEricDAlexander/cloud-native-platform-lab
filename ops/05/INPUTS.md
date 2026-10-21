# Phase 05 输入

复制 `inputs.json`、`materials.json` 到仓库外受控目录，以 `CNPL05_INPUTS`、`CNPL05_MATERIALS` 指定绝对路径。`null` 表示尚未确认；默认验证不要求现在补齐部署值。秘密文件必须仓库外、本人所有、0600/0400，配置只记录引用。不要将 Token、PSK、口令、私钥写入终端参数或证据。

公共输入：`run_id` 为 3–20 位小写字母/数字/横线；Kubernetes 使用显式私有 kubeconfig、context、kube-system UID，且十节点 FQDN/IP/Ready 与台账一致。`prerequisites.file/sha256` 是连接内网后核对 Phase 02/03/04、存储/证书/控制权交接的现场记录。不能用本轮离线报告代替。

物料按 `components.<主锁键>` 登记 `version`、`compatibility_file/sha256`；镜像用 `image=harbor...@sha256:...`，Chart/工具用 `file/sha256`。版本及 SHA/Digest 必须已写入主锁。Chart 包在本地，禁止自动 repo update、dependency update 或联网选版本；需先把含密钥的 Chart Secret 改为 existingSecret 引用，并将部署 values 和所选 Chart 做兼容验证。首次引导可安装全新 CRD；已有 CRD 必须完成交接和兼容检查，使用禁用 CRD 创建的 Chart。

本轮不选择新版本。除主锁已有记录外，脚本新增引用的 prometheus_operator/prometheus_image/prometheus_config_reloader/node_exporter/kube_state_metrics/grafana_sidecar、otel_collector_cli/七语言插桩包、pyroscope_java_agent、opencost_image/prometheus_tools 均需后续补入主锁 components；未登记会失败。Chart 的版本与应用镜像版本分别记录，不把二者混成同一版本号。

`curl_config` 引用 curl 私有配置，可含 CA、认证头；必须使用内部 CA 验证，不能配置 insecure、重定向或额外 URL/输出选项。API 入口是无内嵌凭据的 HTTPS。原始查询结果可能含业务标签，仅留本地受控 records，提交前另行脱敏。

Zabbix 的 `private_vars_file` 为仓库外 JSON，键见 [01](01/README.md)。主机只读取 Phase 00 已生成 Inventory 的既有 16 台；不重跑初始化。不得覆盖既有 PostgreSQL 实例，首次空库初始化与后续运行通过数据库归属标记区分。

各阶段的 README 说明专属字段。资源默认隔离命名空间，写入 `cnpl.io/phase=05`、`cnpl.io/run`；存在其他批次/GitOps 资源即停止，由原控制者交接。不会为了脚本通过而删除 Phase 03 ECK 或 Phase 04 最小指标平台。
