# Phase 03 脚本

按 [48 个计划步骤](../../plan/03-ceph-middleware.md) 编写，执行目录为 `ops/03/01`–`09`。2026-10-23–25 已在现有十节点 VM 主集群执行 Ceph、卷生命周期、数据库、缓存/消息和 DemoApp Operator 主线，批次为 `ceph03a`。实际配置、逐项证据和未通过项见 [本轮执行记录](EXECUTION-ceph03a.md)；[coverage.json](coverage.json) 区分通过、部分验证和用户取消。

用户已取消 **03.06.04–06 独立 Rook 自管理集群对照**，未创建对应集群或占用新盘。03.04 已有的 Rook External/Ceph-CSI 是当前卷接入链路，继续保留。整个任务只核验 VM 内部，Ceph 使用 host 故障域；物理冗余未验证。一次 storage02 客户机重启未在 600 秒窗口内恢复，后续资源修复和数据恢复已验证，不能据此宣称完整故障验收通过。

2026-10-23 [03.01–02 验收](02/records/ceph03a/acceptance-20261023T074608Z-7ufobl6q/README.md)：VM 范围通过；Ceph HEALTH_OK，3 MON/2 MGR/3 OSD，管理切换与加密备份读回通过，Kubernetes 10/10 Ready。

| 目录 | 内容 | 依赖 |
| --- | --- | --- |
| [01](01/README.md) | 设备、物理域、资源与独立备份 | 00 的台账与 01–02 主线 |
| [02](02/README.md) | cephadm、显式 OSD、CRUSH、管理备份 | 01 |
| [03](03/README.md) | RBD、CephFS、RGW 与受限客户端 | 02 |
| [04](04/README.md) | Rook External、CSI、StorageClass、快照控制链 | 03 |
| [05](05/README.md) | 卷生命周期与校验 | 04 |
| [06](06/README.md) | 单故障与恢复；独立 Rook 对照已取消 | 05、独立备份 |
| [07](07/README.md) | PostgreSQL/CNPG、WAL/PITR、MySQL | 05、独立备份 |
| [08](08/README.md) | Redis/Valkey、Kafka、RabbitMQ、NATS；ECK 为未执行扩展 | 05 |
| [09](09/README.md) | DemoApp Operator、启停与交接 | 01–08 |

## 输入与执行方式

Mac 只作管理端。所有入口默认 `validate`，只解析本地源码；不安装软件、不拉取物料、不启动容器或服务。实际动作需要明确传入动作名。逐个执行，观察证据后继续，不提供直接跨阶段启动的总开关。

复制 inputs.json、devices.json、materials.json 到仓库外的受控目录，通过 CNPL03_INPUTS、CNPL03_DEVICES、CNPL03_MATERIALS 指向它们。三份环境变量只保存文件路径；秘密不放 argv、Git 或日志。凭据文件必须为当前用户所有、权限 0600/0400，且位于仓库外。远端秘密路径表示已通过受控渠道放到 storage01 的文件，脚本不把内容取回日志。

主机/IP 来源为 ops/inventory/hosts.yaml；`ceph.failure_domain=host` 允许按已核验 VM 执行，物理字段保持未知。版本与 Digest 登记在 ops/versions.lock.yaml，物料和兼容记录位于仓库外；各组件 execution_evidence 指向实际运行证据。materials.local.json 中的 version、image、file/sha256 必须与主锁相符，Chart values 另锁 SHA。未锁定时入口失败关闭。完整字段见 [输入契约](INPUTS.md)。

Kubernetes 入口需绝对 kubeconfig 路径、context 和 kube-system UID，并核验十节点身份/地址/Ready。namespace 与对象按 run_id 核对归属，拒绝接管其他批次。同一数据集重试沿用原 run_id，不通过改身份掩盖失败。每次动作独立保存 context/result/output 与检查输出；result 的 exit=0 只表示本动作成功，不等于阶段验收。未脱敏 Secret/Chart 渲染仅在仓库外临时目录使用并清理，证据目录只保存脱敏版本。

共享函数只处理输入、目标身份、物料和归属检查。部署流程保留在各子目录；简单顺序任务不引入额外设计模式或框架。保留 SELinux Enforcing/firewalld；不覆盖无关配置，不清理全局资源，不自动重新 bootstrap，不运行磁盘擦除。

## 本地检查

```bash
bash ops/03/validate.sh
```

执行 Bash 语法、JSON/YAML 解析/重复键、Ansible syntax-check、离线防护/存储身份/20 个清单构造检查、48 步文件索引和 DemoApp 内存单测。离线结果不替代 VM 运行证据。[REVIEW.md](REVIEW.md) 保留最初离线交付的历史结论，当前状态以本轮执行记录为准。默认入口继续只校验，交付后不自动启动下一组实验。
