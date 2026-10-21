# 06.03 秘密、加密轮换、审计与工作负载信任

覆盖 06.03.01–06。`run.sh validate|render|install <external_secrets|vault>|apply|check` 与其他目录同义。ESO SecretStore 限本批空间，Vault HTTPS/CA 和角色只读 `cnpl06/<run_id>/sample`；先在 Vault 配置此策略、Kubernetes auth 和测试值，再 apply。ESO v1beta1 模板须与锁定 CRD 对照；若所选版本只提供 v1，在实际锁定时调整，服务端检查失败时不继续。

```bash
bash ops/06/03/run.sh validate
CNPL06_INPUTS=/受控路径/inputs.json bash ops/06/03/run.sh render
# 使用预先安装并锁定版本的 sops/age；以下命令由用户选择执行：
CNPL06_INPUTS=/受控路径/inputs.json bash ops/06/03/run.sh encrypt
CNPL06_INPUTS=/受控路径/inputs.json bash ops/06/03/run.sh decrypt
CNPL06_INPUTS=/受控路径/inputs.json bash ops/06/03/run.sh vault-snapshot
CNPL06_INPUTS=/受控路径/inputs.json bash ops/06/03/run.sh rotation-check
```

crypto 只在仓库外当前用户的 0700 目录创建新的 0600 文件，不覆盖已有文件；加密前明文、解密身份均检查权限，普通证据仅存输出 SHA。age 私钥用 `umask 077; age-keygen -o /受控目录/identity` 单独生成和独立备份，公钥进入 SOPS 规则；受控 GitOps 解密身份与人类恢复身份分离。离线授权/拒绝解密及密钥丢失用副本验证，避免损坏唯一身份。

Vault 仅使用隔离持久实例；init/unseal 是现场私密交互，份额分属不同持有者，不能把完整 init 响应写进 records。`vault-snapshot` 经私有 curl 配置读取 Raft 快照并写新私有文件，要求真正独立备份。重启后验证 sealed 状态、满足阈值解封、只读/拒绝路径及隔离目标恢复。自动解封依赖的外部 KMS/网络必须登记；不将未验收 Vault 替换全部基础凭据。

ESO 检查 Ready 和目标 Secret 元数据；另外逐项验证值轮换、refreshInterval、后端拒绝/不可达、旧值保留与删除语义，比较应用真实读取值的私密摘要。Ready 不能证明所有失效策略。后端测试仅隔离本空间连接，不停止共享后端。

EncryptionConfiguration 轮换由 01 的受控节点配置链执行，不向普通证据输出 key.secret。顺序：备份旧配置/PKI/etcd与历史密钥 → 三 API Server 均装新写+旧读配置 → 逐台就绪 → 验证旧 canary → 写新 canary → 仅重写实验 Secret → 所有入口读新旧数据 → 隔离备份恢复。每步完成才继续。rotation-check 只核对脱敏回执的三节点/配置 SHA/可读证据一致性，绝不自动淘汰旧密钥；生产全量重写、旧钥退役和历史备份生命周期另开窗口。

`audit-policy.yaml` 为复用 API Server 审计的完整起点：Secret/Token 仅 Metadata，统一记录主体、提交、CI 运行、IaC 变更和实验编号。按 05 流程接日志、设置保留和不可变归档，再检查一次允许/拒绝事件；不用 RequestResponse 收集 Secret 正文。SPIRE 复用 02 网格归属：精确 Namespace/SA 注册，比较 X.509 SVID 到期续期、错误信任域拒绝及撤销后失效时间；已有证书可能在 TTL 内有效，不能以删注册立即断言撤销完成。

失败先恢复上一可读配置/后端/注册，保留历史解密钥。清理先停止引用、检查秘密同步删除策略和备份，再删除本批 CR/身份；共享 Secret 后端、审计、SPIRE 不随本批卸载。本轮未执行任何秘密或控制平面变更。
