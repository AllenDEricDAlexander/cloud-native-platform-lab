# 03.09 DemoApp Operator 与交接

覆盖 03.09.01–05。`validate`/`test`/`build`/`handoff` 均为本地离线入口，不连接 Kubernetes 或启动服务。

```bash
bash ops/03/09/run.sh test
bash ops/03/09/run.sh build
```

operator/ 是无第三方依赖的 Go 教学控制器，只选 Go 一条实现路线。每五秒调谐单 namespace，Deployment 单副本/Recreate；没有生产 HA/Leader Election 承诺。接口由 CRD 的 spec/status/Conditions 定义，子对象用 owner UID 绑定。重复调谐保留 API 默认字段和 Service 地址，配置变更带哈希触发 rollout。归属冲突不接管，API 失败有可重试状态，403 表达 AccessDenied；冲突下一轮重试。Finalizer 逐个以 UID 前置条件删除自己子对象，确认消失才解除自身标志，保留其他 Finalizer。

这是直接、有限的 reconcile loop，复用 Kubernetes 的声明式调谐模型，不引入第二套框架或额外设计模式。标准库内存 Transport 测试覆盖默认字段/重复事件、非法 spec、归属、403/503、部分失败、409、配置变化、删除前置条件和分页；不创建监听端口或网络连接。Go 编译使用已有离线工具链，GOPROXY/GOSUMDB 关闭，不自动下载安装依赖。

内网连接后：build-vm → 将实际 Digest/版本登记主版本锁和 materials.demoapp_operator → deploy → exercise → delete。build-vm 只通过 Ansible 在登记 build01 上用 Podman 构建/push，Mac 不运行容器。build_authfile 指远端 0600 registry 文件，build_image_tag 必须为内网非 latest 独立标签；Containerfile 为 scratch，不拉基础镜像。demo_app 需提供监听 PORT、读取 DEMO_MESSAGE 的内网 Digest 应用镜像，支持 UID10001 和只读根文件系统。

Role 仅限 cnpl03-09 的 DemoApp、Deployment、Service、ConfigMap，不读 Secret，不改 Node。deploy 的 CRD 只能接管本批对象。exercise 实测子资源重建、配置更新和 schema 拒绝；delete 实测清理，不强摘 Finalizer。重试时若名字冲突先调查原 UID，不能改 ownerReference 绕过。

CRD 目前只有 v1alpha1 served/storage。演进时先新增可选字段/默认值并保留兼容；引入 v1beta1 必须在隔离数据上做双版本读写、转换和 storedVersions 迁移后再撤旧版本；本轮没有伪造转换 Webhook 或宣称版本迁移已验收。权限不足的负向场景先在单独 RoleBinding 中演练，不修改主业务 Role。

[启停与恢复顺序](START-STOP.md) 指导依赖顺序；handoff 输出 48 步交付索引并始终保留 runtime_accepted=false，直到逐项有真实运行验收。脚本退出成功、健康检查或本地单测都不能代替整个 Phase 03 验收。
