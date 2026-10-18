# 01.10 执行前核验与有限真实链路

09 已完成验收、清理与反例补证，归档提交为 `a79ea70`，见[09 验收归档](../core-07-10/runs/09-20261018T113437Z/README.md)。本次检查 10 的执行路径，在唯一临时空间运行有限客户端与镜像拉取 Job；没有启动正式 `lab-p10`，没有发布 10 的正式 passed.json/handoff.json。

## 修正 Harbor 项目机器人清理

Harbor v2.15.0 的 `/robots` 默认返回 system 级账号；按显示项目名前缀过滤不能证明项目机器人不存在。[实际接口实现](https://github.com/goharbor/harbor/blob/v2.15.0/src/server/v2.0/handler/robot.go)要求同时指定 `Level=project,ProjectID=<ID>`，过滤键大小写须准确。

清理器现在先核对原项目 ID、名称与私有属性，再查询这个项目的完整机器人元数据。每个返回账号还须核对实际项目权限；只有本 run 描述、创建意图和项目 scope 都匹配的账号才可撤销。发现额外账号时先保留项目。没有改动系统机器人或其他项目，也未增加新依赖。

原生模板测试同时验证完整过滤参数，以及“名称含本项目前缀、但实际属于另一个项目”等拒绝场景。最终实际 Registry 验证明确撤销第二代账号，未把项目级查询遗漏或项目删除级联当作显式账号清理。

## 最终实际核验

| 检查 | 已完成结果与证据 |
| --- | --- |
| Shell / Ansible 入口 | [主入口语法检查](syntax-10.txt)通过；stage-10.sh、core-stage.sh 的 bash 语法通过。所有 core 测试 YAML 先做解析检查。 |
| 有限检查与证书材料 | [16 项最终测试](core-tests.txt)通过，含原生 Ansible/OpenSSL 的链、DNS SAN、用途、密钥匹配与私有权限，以及 Harbor 查询和归属拒绝场景。 |
| 正式入口 validate | [完整日志](validate-10.txt)包含 `01.10 SOURCE VALIDATION PASS`；14 个公开变体实际渲染并严格校验，应用有限 Go 测试、静态构建及 OCI 打包通过；全部主机 failed=0/unreachable=0。264 个源码/版本锁摘要与[最终上下文](validation-context.json)一致。 |
| 真实 Registry 正反认证 | [原生 Registry 有限夹具](../../tests/core-registry-smoke.yml)使用唯一私有项目与原始三个拉取 Job。错误凭据必须得到真实 unauthorized/401/denied；第一代凭据拉取成功；撤销第一代后，第二代用新 repository scope 真实成功。见[最终完整日志](registry-smoke.txt)。 |
| 项目、账号、缓存清理 | [精确清理结果](registry-evidence/attempt-registry/observations/harbor-cleaned.json)明确记录撤销第二代 ID=7，并确认项目消失。复核 API 返回项目/该账号 404。两个 worker 的私有别名均为 0，bootstrap busybox 仍在；原 system 机器人 id=1 保留。 |
| 实际 SA / RBAC 请求 | [有限客户端夹具](../../tests/core-access-smoke.yml)复用原 SA/Role/Binding 与投射卷，容器仅执行一次原 API 客户端后退出。9 条请求得到预期状态：读取本空间 Pod、全局 Node、指定配置为 200；读取 Secret、越权删除、跨空间读取为 403；允许删除为 200；无 Token 为 403；错误 audience 为 401。见[完整日志](access-smoke.txt)及 `access-evidence/attempt-access/observations/rbac-*.json`。 |
| audience 与寿命 | 实际投射 Token 的 audience 匹配，公开 expires_at 与 Pod 创建时刻相差不超过 610 秒；无 Token 客户端 token_mounted=false。公开证据没有 JWT。 |
| Bound Token | 直接调用原生 10 Token 生命周期步骤；同一个 Pod UID 绑定 Token 在删除前认证成功，删除后同一 Token 认证失败。见[公开生命周期结果](access-evidence/attempt-access/observations/bound-token-lifecycle.json)。 |
| 只读交接 | 原生交接步骤取得三 API 的 ok、三个 etcd health=true，验证同集群的 07/08/09 回执及安全指标 API；引用已有 HA 验收，不执行新的关机。见[交接前检查](access-evidence/attempt-access/observations/handoff-before-cleanup.json)。 |

两个最终有限夹具结束后，临时 Namespace、精确 UID 的临时 ClusterRole/Binding、项目机器人、两个测试仓库、项目和私有镜像别名全部回收。TokenReview 与 Registry 私密输入只在临时私有目录，未复制到公开记录。十节点仍 Ready，Metrics Server 保留十节点新鲜指标；详见[最终复核](verification.json)和[实际来源摘要](source-hashes.json)。

初轮 Registry 试验暴露默认 system 列表遗漏项目账号的问题；初轮访问夹具发生动态 include 的 YAML 解析错误，已按原 Namespace/授权 UID 明确恢复清理，再修正夹具并重新实测。初轮原件保留在 `*-initial`、`*-second`，成功结论只引用上表最终日志。

## 正式执行边界

原[配置、Secret 与身份手册](../../core-resources/config/README.md)给出完整四条命令。正式 run 使用新的 10-... 目录，核对 09 回执后完成 ConfigMap env/普通卷/subPath 对照、应用 Secret 认证及传播、TLS Secret 使用、Registry 轮换、SA/RBAC、Bound Token 和最终清理交接。

配置传播与完整阶段验收尚待用户正式 run；上述有限验证没有启动长期 HTTP 服务，也没有提前生成 passed.json/handoff.json。成功后指标基础组件和原管理身份保留，测试空间、凭据、私有项目与缓存别名精确回收。
