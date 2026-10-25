# 03.09 DemoApp Operator 与交接

覆盖 03.09.01–05。`validate`/`test`/`build`/`handoff` 均为本地离线入口，不连接 Kubernetes 或启动服务。

```bash
bash ops/03/09/run.sh test
bash ops/03/09/run.sh build
```

operator/ 是无第三方依赖的 Go 教学控制器，只选 Go 一条实现路线。每五秒调谐单 namespace，Deployment 单副本/Recreate；没有生产 HA/Leader Election 承诺。接口由 CRD 的 spec/status/Conditions 定义，子对象用 owner UID 绑定。重复调谐保留 API 默认字段和 Service 地址，配置变更带哈希触发 rollout。归属冲突不接管，API 失败有可重试状态，403 表达 AccessDenied；冲突下一轮重试。Finalizer 逐个以 UID 前置条件删除自己子对象，确认消失才解除自身标志，保留其他 Finalizer。

这是直接、有限的 reconcile loop，复用 Kubernetes 的声明式调谐模型，不引入第二套框架或额外设计模式。标准库内存 Transport 测试覆盖默认字段/重复事件、非法 spec、归属、403/503、部分失败、409、配置变化、删除前置条件和分页；不创建监听端口或网络连接。Go 编译使用已有离线工具链，GOPROXY/GOSUMDB 关闭，不自动下载安装依赖。

内网动作：build-vm → 将实际 Digest/版本登记主版本锁和 materials → deploy → exercise → delete。build.sh 同时构建控制器与 demo/ 的标准库 HTTP 应用；build-vm 仅在登记 build01 使用 Podman 构建/push 两个 scratch 镜像，Mac 不运行容器。build_authfile 指远端 0600 registry 文件，build_image_tag/demo_image_tag 为独立非 latest 标签；主版本锁保存实际 Digest。demo 应用监听 PORT、读取 DEMO_MESSAGE，支持 UID10001 和只读根文件系统。

Role 仅限 cnpl03-09 的 DemoApp、Deployment、Service、ConfigMap，不读 Secret，不改 Node。deploy 的 CRD 只能接管本批对象。exercise 实测子资源重建、配置更新和 schema 拒绝；delete 实测清理，不强摘 Finalizer。重试时若名字冲突先调查原 UID，不能改 ownerReference 绕过。

CRD 目前只有 v1alpha1 served/storage。演进时先新增可选字段/默认值并保留兼容；引入 v1beta1 必须在隔离数据上做双版本读写、转换和 storedVersions 迁移后再撤旧版本；本轮没有伪造转换 Webhook 或宣称版本迁移已验收。权限不足的负向场景先在单独 RoleBinding 中演练，不修改主业务 Role。

本批已实测子 Deployment 删除重建、配置变更后的 HTTP 响应、非法 spec 拒绝、无 Secret/Node 读取权限，以及删除 CR 后 Finalizer 清理全部自有子对象。控制器保留运行，测试 CR 已删除；v1beta 转换未执行。

`backup-mac.sh archive`（或 run.sh backup）将本批 Kubernetes 配置/凭据、Ceph RGW 证书、物料元数据及独立 S3 的实际 Barman 全备/WAL 对象加密存入 Mac restic。所有管理/凭据文件与一份全备包逐项 dump/比较，另对仓库执行 check --read-data；原始秘密仅在仓库外临时目录并清理。这证明备份可读，不等于完整平台/Ceph 重建演练。

[启停与恢复顺序](START-STOP.md) 指导依赖顺序；handoff 结合 coverage.json 输出 48 步及实际范围。当前完整计划 runtime_accepted=false，原因包括用户取消的独立 Rook、重启时限失败及未执行的维护/性能分支；主线配置与恢复证据见 [执行记录](../EXECUTION-ceph03a.md)。交付后不自动启动下一组实验。
