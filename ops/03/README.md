# Phase 03 脚本

按 [48 个计划步骤](../../plan/03-ceph-middleware.md) 编写。新执行目录固定为 `ops/03/01`–`09`；旧的 [专题说明](../03-ceph-middleware/README.md) 保留为背景。当前交付只完成源码走查与离线检查，**所有 VM、Ceph、Kubernetes、数据库、消息及故障恢复验收均未执行**。

| 目录 | 内容 | 依赖 |
| --- | --- | --- |
| [01](01/README.md) | 设备、物理域、资源与独立备份 | 00 的台账与 01–02 主线 |
| 02 | cephadm、显式 OSD、CRUSH、管理备份 | 01 |
| 03 | RBD、CephFS、RGW 与受限客户端 | 02 |
| 04 | Rook External、CSI、StorageClass、快照控制链 | 03 |
| 05 | 卷生命周期与校验 | 04 |
| 06 | 故障、安全维护、独立 Rook 对照 | 05、独立备份 |
| 07 | PostgreSQL/CNPG、WAL/PITR、MySQL | 05、独立备份 |
| 08 | Redis/Valkey、Kafka、RabbitMQ、NATS、ECK | 05 |
| 09 | DemoApp Operator、启停与交接 | 01–08 |

## 输入与执行方式

Mac 只作管理端。所有入口默认 `validate`，只解析本地源码；不安装软件、不拉取物料、不启动容器或服务。实际动作需要明确传入动作名。逐个执行，观察证据后继续，不提供直接跨阶段启动的总开关。

复制 inputs.json、devices.json、materials.json 到仓库外的受控目录，通过 CNPL03_INPUTS、CNPL03_DEVICES、CNPL03_MATERIALS 指向它们。三份环境变量只保存文件路径；秘密不放 argv、Git 或日志。凭据文件必须为当前用户所有、权限 0600/0400，且位于仓库外。远端秘密路径表示已通过受控渠道放到 storage01 的文件，脚本不把内容取回日志。

主机、IP、物理放置的唯一来源仍为 ops/inventory/hosts.yaml；实际放置未知就停止。版本锁仍为 ops/versions.lock.yaml；本轮不联网选版本、不把 pending 提升为已验证。连接内网后，把确认的组件同步登记版本锁，并在 materials.local.json.components 中填写对应 version、image（内网 sha256 Digest）、compatibility_file、compatibility_sha256。Chart/清单另填 file、sha256。compatibility_file 记录 Ceph/Rook/CSI/K8s/API/Chart 与镜像组合的核对结果。未锁定时执行入口失败关闭。

Kubernetes 入口需绝对 kubeconfig 路径、context 和 kube-system UID，并核验十节点身份/地址/Ready。namespace 与对象按 run_id 核对归属，拒绝接管其他批次。同一数据集重试沿用原 run_id，不通过改身份掩盖失败。每次动作独立保存 context/result 与检查输出；result 的 exit=0 只表示本动作成功，不等于阶段验收。

共享函数只处理输入、目标身份、物料和归属检查。部署流程保留在各子目录；简单顺序任务不引入额外设计模式或框架。保留 SELinux Enforcing/firewalld；不覆盖无关配置，不清理全局资源，不自动重新 bootstrap，不运行磁盘擦除。

## 本地检查

```bash
bash ops/03/validate.sh
```

执行 Bash 语法、JSON/YAML 解析/重复键与 Ansible syntax-check。该结果不证明工具选项、CRD/Chart 兼容、现场身份、设备、权限、网络、挂载、恢复或实际性能。后续联网测试由用户逐阶段执行。
