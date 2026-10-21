# Phase 06 离线交付走查（2026-10-21）

范围：按 17 个子阶段分别放置入口、配置/清单生成、检查与恢复规程，83 个稳定步骤全部登记 coverage.json。文件索引只证明有明确交付位置和操作边界，不代表 83 项运行测试已通过。本轮未连接内网、访问集群/vCenter、下载物料、启动容器/服务或执行正式实验。

## 已执行检查

| 检查 | 结果 | 证明边界 |
| --- | --- | --- |
| `bash ops/06/validate.sh` | 通过 | 25 份 Shell 语法、31 份 Ruby 语法、JSON/YAML 解析和重复键检查 |
| `tests/offline.rb` | 100 组通过 | 本地构造/正反输入/失败路径，真实网络、集群、SSH、安装和服务客户端调用为零 |
| 清单构造 | 通过 | 01–14、16 默认清单及 Kueue、ApplicationSet/MCS、DRA、vLLM/训练、三种故障子模式；不等于 CRD/API schema 验证 |
| 83 步文件索引 | 通过 | 与阶段计划 ID 完全相同，引用文件存在，01–17 入口和规程齐全 |
| Python 源码 | 通过 | ast.parse 静态解析，未执行 HTTP 客户端 |
| `javac -Xlint:all` | 通过 | Java 客户端使用标准 JDK 编译，产物在私有临时目录，未启动客户端 |
| 文档命令/链接 | 通过 | 9 个本地 Markdown 链接、4 个 Bash/JSON 代码块 |
| `git diff --check` | 通过 | 本任务差异无空白错误 |

管理端实际使用 Bash 3.2.57、Ruby 2.6.10、Python 3.9.6 和 javac 21.0.10。只使用现有命令和标准库，不安装新依赖。离线 fixture 的版本、Digest、容量/预演回执和公钥均为本地构造，不写回主锁，不充当环境成功记录。

## 走查修正

- 输入、JSON/YAML 重复键、私有文件路径/权限/符号链接、公钥/私钥混用在本地拒绝；加解密/快照输出只新建仓库外 0600 文件，不覆盖已有材料。
- 真实集群每次明确 kubeconfig/context/UID，primary 对照十节点 FQDN/IP/Ready；缺 context 时在 kubectl 前失败。人类身份验证核对同一 API 入口并使用真实用户身份。
- 清单先验证镜像 Digest/主锁/作用域，再用真实 API discovery 或本包 CRD 的 scope 防止伪造 metadata.namespace 绕过集群白名单。同名 Kind 按 API 组解析完整资源名，区分原生与 Knative Service；CRD/CR 同包不会提前查询尚未提供的新 API，按 Namespace→CRD Established→其他对象顺序处理。CRD 默认化后的 spec 变化要求单独核对。
- 已应用 Namespace/CRD/普通对象即时记录 UID，后续对象失败不丢失部分成功归属；其他批次、GitOps 对象拒绝接管。删除严格区分 NotFound、API 失败、归属拒绝和过期 UID，不把权限错误吞成清理成功。
- HPA/VPA/两种 KEDA 使用不同工作负载；Kafka 上限不超过实验分区。消息 ID 检查允许重复投递，但拒绝缺确认/业务效果、未知 ID 和重复业务效果。
- Dapr 实际 sidecar 的短期身份投影需检查；两语言状态回读不以非空响应代替已知值。Kueue 明确只允许同批 08/13 的空间，训练不能绕过准入。
- Chaos 一次一个变量、精确选择器、10–60 秒 duration、停止阈值和 UID 清理；原失败退出码与恢复失败分别保留。高影响故障和跨集群切换保留独立恢复门槛。
- 升级只允许相邻次版本、单节点 pending 和独立业务回归；恢复调度前重新读取 UID/resourceVersion，避免旧资源版本或节点替换。失败不会自动降级或进入下一台。
- Velero 区分快照引用和真实 DataUpload/PodVolumeBackup，恢复只读备份位置与全新隔离目标。原 etcd 路线保留对象 UID，新集群路线使用新 UID；两者都要求独立恢复 API 入口。
- etcd 恢复只写新目录，revision bump 显式计算并绑定回执，不覆盖活动目录或启动 etcd。RTO/RPO 使用真实含时区里程碑，拒绝倒置时间、缺失目标、丢失/重复业务记录。
- 普通 Pod/事件/恢复对象证据移除命令、env、data、注解、消息等潜在敏感字段；Token/私钥/完整 kubeconfig、快照与预测正文不进入普通记录。

## 待内网与现场参数就绪后验证

所有 runtime_accepted/phase_complete 保持 false。组件版本/CRD/CLI/Chart/Operator/内核/GPU/模型与签名制品仍须按主锁现场确认；本轮没有执行服务端 dry-run、控制器调谐、镜像拉取、TLS/OIDC/RBAC 行为、真实指标/消息/事件、数据持久化、挂载、故障、升级或 RTO/RPO 测量。

安装器接受受审本地完整物料包，不提供猜测版本的下载/安装。CAPI Provider 模板、Cluster Mesh/MCS 实现、GPU/DRA、迁移存储、llm-d、独立备份和恢复目标有明确现场门槛。Dapr Workflow 的具体 SDK/业务 Worker、Kubeflow 任务配方、系统/Ceph 升级及高影响故障按规程完成版本选择和实施，不把客户端/普通 Job/操作清单声称为这些模块运行成功。

没有真正独立介质、实际设备/许可、恢复入口或前序 00–05 主线证据时，相关实验保持阻塞。现有同 esxi01 的 backup VM 不满足独立灾备条件。整阶段验收、两条恢复路线、冷启动、新 VM 复制与资源清理须由用户连接内网后逐项执行并归档。

分步提交：01–16 各一个提交，17 的重建/报告脚本与全阶段联查修正作为最后一个提交。工作区分支并行切换后，后续工作在独立 worktree 的 `codex/phase06-offline-scripts` 完成；其他阶段的未提交内容未纳入。未自动推送、合并或启动后续实验。
