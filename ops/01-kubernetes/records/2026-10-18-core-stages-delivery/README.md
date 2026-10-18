# 01.07–01.10 独立入口交付与核验

03–06 已在原目录完成真实重跑验收，26 个检查点和两个总 PASS 齐全，修复/实际运行记录见 [03–06 完成记录](../2026-10-18-ansible-replay/repairs/20261018-observer-and-completion/README.md)，提交 `3cb2298`。原始失败和成功证据保留。

本次交付 07、08、09、10 四个独立 Ansible 入口与 shell 薄包装，未启动这四个专题的真实实验工作负载。它们的运行结果由用户逐阶段验收。

## 独立入口

| 阶段 | Ansible 主入口 | 命令、解释、恢复与预期 |
| --- | --- | --- |
| 07 | `ansible/playbooks/stage-07.yml` | [StatefulSet/DaemonSet](../../core-resources/statefulset/README.md) |
| 08 | `ansible/playbooks/stage-08.yml` | [删除传播/所有权/Finalizer](../../examples/garbage-collection/README.md) |
| 09 | `ansible/playbooks/stage-09.yml` | [Job/CronJob/HPA](../../core-resources/jobs/README.md)、[安全指标准备](../../core-resources/autoscaling/README.md) |
| 10 | `ansible/playbooks/stage-10.yml` | [配置/Secret/交接](../../core-resources/config/README.md)、[SA/RBAC](../../core-resources/rbac/README.md) |

Kubernetes 主定义位于相应源码目录 `manifests/*.yaml.j2`。Ansible 负责渲染、操作、节点维护和清理；小型 Go 应用承载身份、幂等业务模拟、受控负载和配置消费；Python 只读取层级、证书、指标和结果，不提交 Kubernetes 变更。没有引入新集合、SDK 或依赖。

每阶段使用自己的 `lab-pXX`、run、attempt 和成功回执；普通操作授予同一受限管理用户在该空间的权限。管理员入口只用于 Namespace/RBAC/Secret/节点及指标组件等必要管理。失败不补写成功；已成功阶段验证真实断点后跳过。源码发生变化时仍能按原 UID 进行显式 cleanup。

## 已执行的交付核验

- 四个主入口 `--syntax-check`，见 `syntax-XX.txt`；最终四个真实 `validate` 入口编译测试应用、打包精确 OCI 引用、渲染并核验目录变体，见 `validate-XX-final.txt`。另对四个仅验证上下文实际执行 `cleanup`，见 `cleanup-XX-final.txt`，确认清理不依赖已编译镜像。所有主机 failed=0/unreachable=0。
- [76 项 Python 单测/有限集成](all-python-tests.txt)通过，覆盖原初始化、加入、身份、网络、HA、压力、连接观测，以及新专题的实际 owner UID/分区镜像、DaemonSet 节点集合、CronJob 真调度标记、HPA 新鲜指标、CSR 身份/SAN/签名/用途/时效、Namespace 替换和外来 Secret 拒绝。
- [Go 有限测试](go-app-tests.txt)验证：并发/冲突/重投的账本只产生一次效果；外来账本不写入；memory→hold 复用原 96Mi 缓冲，off 释放；身份接口不暴露 Secret，就绪失败不影响存活。[既有 OCI 打包工具测试](go-imagepack-tests.txt)通过。
- [真实服务端准入与清理](server-schema-03.txt)：所有公开变体 server dry-run，并将控制器 PodTemplate 在实际 ResourceQuota/LimitRange 下做 Pod server dry-run。只创建带本次标签的临时 Namespace、SA、预算及模拟 ConfigMap；没有启动工作负载。临时 finalizer 通过真实清理 helper 精确解除，空间全部回收。
- [真实 OpenSSL/Ansible 私有材料验证](tls-integration.txt)：实际生成 CA/服务证书，校验签名、SAN、EKU、密钥匹配、权限和重复执行；五类 Secret/TokenReview 模板仅在临时私有目录验证，未向集群提交真实凭据。
- [Linux 远程恢复夹具](recovery-fixture.txt)：在 worker02 的唯一 `/tmp` 目录运行实际 bash/flock 回退脚本，配置路径改为夹具、systemctl 被夹具拦截。验证正常回退、第三方修改拒绝、提交后 timer 不回退、timer 先回退后不可假提交；真实 kubelet SHA 与 PID 前后不变。
- 实际只读校验 Harbor 的机器人过滤 API 以及 Secret 的 metadata-only 归属输出格式；未创建 Registry 项目或账号。
- [Metrics Server 镜像元数据](metrics-image-metadata.json)来自官方 registry 的实际响应，验证 index/amd64/config 摘要。版本锁为 selected/runtime_pending，没有声称部署已通过。

公开输出不含私钥、JWT、Registry 密钥或 Secret 正文。完整原始 03–06 记录及 1183 个更早执行文件继续按 SHA 复核。[最终验证结果](verification.json)确认十节点健康、原批对象为 0、临时验证空间为 0，没有批准 CSR、安装指标组件、注入真实节点污点或创建 Registry 账号；07–10 没有写运行 PASS。[最终源码 SHA](source-hashes.json)与四个最终上下文完全匹配。

## 尚待用户逐阶段运行的范围

07 的真实 StatefulSet/DaemonSet 更新与节点覆盖；08 的真实控制器 GC/接管；09 的真实节点服务证书准备、Metrics Server、分钟调度与 HPA；10 的真实配置传播、Registry 凭据轮换、实际 SA 请求和 Bound Token 失效。

上述 server dry-run、夹具和单测用于发现脚本/契约问题，未被写成专题实际运行 PASS。每阶段只有自身 `run/resume` 完成断言、恢复和清理后才发布成功指针；用户可按各手册一次执行完整命令。
