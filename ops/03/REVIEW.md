# Phase 03 离线交付走查（2026-10-21）

范围：按 plan/03-ceph-middleware.md 的 9 个子阶段、48 个计划步骤建立脚本与操作规程，目录为 01–09。coverage.json 只索引交付文件和人工门槛，不表示运行完成。本轮没有连接内网、下载物料、访问集群、启动容器/服务或正式实验。

## 已执行检查

| 检查 | 结果 | 证明边界 |
| --- | --- | --- |
| `bash ops/03/validate.sh` | 通过 | 全部 Shell 语法、JSON/YAML 解析/重复键、六份 Ansible syntax-check |
| `tests/guards.sh` | 通过 | 非法动作、未确认物料/设备、秘密权限/格式、未锁镜像、重复键、管理员连接、恢复失败/原退出码、日志归档、短暂 NotFound 的本地检查；真实外部客户端调用为零 |
| `tests/render.sh` | 通过 | 16 个生成清单的 JSON/镜像/内嵌 Shell 构造，部署函数全部替换为本地替身 |
| 48 步文件索引检查 | 通过 | ID 与计划完全对应，引用文件存在；包括明确的人工步骤 |
| DemoApp `go test -count=1 -cover ./...` | 通过，78.8% statements | 12 个顶层测试及输入子用例；内存 HTTP Transport，无监听端口/网络连接 |
| DemoApp `go vet ./...` | 通过 | 仅控制器包的静态检查 |
| Go linux/amd64、CGO=0 构建 | 通过 | 编译产物留 09/bin（Git 忽略），未启动程序、构建容器或推送镜像 |
| `git diff --check -- ops/03 ops/README.md` | 通过 | 本任务差异无空白错误；原有 02 修改未纳入 |

Ansible 对照场景只在临时离线 inventory 中执行 syntax-check，绝不将该 fixture 用于实际运行。真正的 managed inventory 需与独立设备表严格对应。Go 使用本机既有 1.27.2，GOPROXY/GOSUMDB 关闭；未新增第三方依赖。

## 走查修正

- Ceph 编排从 storage01 的管理身份发出，目标设备在对应 VM 再检查；未锁物料在 SSH 前失败。
- 显式盘/字节/签名/挂载/holder、三实际物理域和主台账预留共同约束 OSD；不调用 wipefs 清除、zap 或全局清理。
- 密钥、Secret 和未脱敏 Chart 渲染使用仓库外私有临时目录；普通证据只存脱敏版本，stdout/stderr 独立归档。日志实现兼容本机 Bash 3.2，恢复/记录不能覆盖原失败退出码。
- Chart 新 CRD 记录 release/源 spec SHA，重跑检查归属，spec 变化停在升级核对；不静默跳过兼容性问题。
- 数据库口令规范化一个尾换行，CNPG/pgpass 保持一致；恢复仅使用全新目标；故障前后均有确认写入，逐笔核对 ack 事务。
- OSD 先安排独立超时恢复，再注入单故障；watchdog 两项恢复操作均记录失败；退出失败保留恢复回执。
- PVC/Snapshot 回收同时观察 API 与后端；迁移等待正常卸载，不强行双挂。Operator 不接管其他 UID，Finalizer 确认子对象消失后才解除。

## 待连接内网后验证

所有 01–09 的 runtime_accepted 均为 false。实际 OSD/VMDK/Datastore/RAID/ESXi、可用容量、kubelet/Ceph 资源边界和真正独立备份尚需现场确认；现有同 ESXi 的 backup VM 不能满足独立灾备门槛。

Ceph/Rook/CSI/Operator/CLI/Chart/API/镜像与 RPM 的具体版本仍按主版本锁 pending 处理，不能用本报告代替 compatibility_file。必须先完成版本/API/CLI 参数和物料 SHA 核对，再做每个阶段的 inspect/plan/执行/正常与失败验证/恢复。

本轮未验证真实挂载、扩容、快照、数据/消息持久化、网络/认证/TLS、OSD/VM/CSI 故障、RTO/RPO、PITR、升级、MySQL/ECK、性能或全部清理。vSphere、真实水位/恢复限速、独立备份核实及部分版本演进保留明确人工步骤；不因具备脚本/规程就判定这些实验完成。

分步提交：01–08 各一个提交，09 的控制器、整阶段联查修正和本报告作为最后一个提交。未提交安装介质、二进制、口令、kubeconfig、原始备份或运行证据；不自动推送或启动后续实验。
