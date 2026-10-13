# 安全架构与实施时点

## 1. 主机安全从 00 完成

00 建立 SSH 密钥登录、受控 sudo、内部 CA、补丁来源、时间同步、防火墙和 SELinux 基线，配置文件纳入 Ansible。网络和 SSH 变更先验证第二条管理连接；不因排错全局关闭防火墙或长期跳过 TLS 校验。

SELinux 的实际模式、策略包、containerd 配置与 AVC 检查必须在 00 明确。kubeadm 的 RPM 安装示例包含 permissive 设置，不能据此宣称自定义 Enforcing 组合已经受支持；优先验证项目选择的 Enforcing 方案，确需例外时记录原因、范围与恢复计划。[kubeadm 安装前置](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/)

## 2. 各阶段落地内容

| 阶段 | 必须实施的最低安全能力 | 后续扩展 |
| --- | --- | --- |
| 00 | 管理账户、DNS/CA 信任、主机策略、仓库权限、离线扫描库和独立备份 | 不提前开放业务管理入口 |
| 01 | RBAC/ServiceAccount、受限 kubeconfig、Secret 保护、etcd 与加密密钥备份、审计起点 | 06A 验证统一身份和轮换 |
| 02 | TLS、默认拒绝策略、DNS/数据访问例外、服务身份实验 | 05/06 做观测和跨服务信任关联 |
| 03 | Ceph/CSI/数据库最小身份、数据备份、旧写入者隔离 | 06E 完整恢复 |
| 04 | SBOM、Trivy、Cosign、准入策略、可信发布、双 CI 权限隔离 | 06A 增加异常与应急恢复覆盖 |
| 05 | 遥测脱敏、租户/团队可见性、保留期和审计 | 故障时保留独立探测路径 |
| 06A | Keycloak、PSA、Kyverno、Falco/Tetragon、密钥轮换、混沌中止 | 不把这里当成首次实施安全 |

## 3. 信任与秘密

内部入口使用私有 CA，根私钥离线，服务私钥独立；`*.egon.top` 不覆盖多层内部域名。OS、Java、Python、Node、Rust/.NET 及 containerd 分别测试信任。恢复账户不依赖故障集群内 Keycloak 或 Secret 服务。

Git 仅保存秘密引用或按既定方案加密后的声明，不保存明文 Token、kubeconfig、VPN 私钥、密码、State 或完整备份。SOPS/age、External Secrets/Vault 在 06A 进一步比较，不作为 00 自举的前置条件。

双 CI 使用最小作用域凭据：构建推镜像、发布更新 GitOps、IaC 管目标 VM 各自隔离。不可信分支不能读取签名或 vSphere 管理凭据。认证通过后还需 RBAC/资源授权，不能用“已登录”替代权限检查。

## 4. 失败与应急行为

策略拒绝、签名材料不可用、指标缺失和证书过期都需要负向验收。准入先 Audit 再 Enforce，应急入口有明确范围、时限、撤销和审计。备份须包含恢复所需密钥的安全取得方法，但不把密钥复制进普通报告。

故障注入只针对本实验室已划定对象，先备份、设定停止条件，再验证受影响请求与数据。升级及容灾必须保留集群外执行器。
