# 01.10 最小身份矩阵

执行命令、Secret 与清理说明见 [01.10 手册](../config/README.md)。源码为 `manifests/identities.yaml.j2`、`pod.yaml.j2` 和私有 `token-review.yaml.j2`。

| 身份 | 绑定方式 | 实际允许 | 实际拒绝 |
| --- | --- | --- | --- |
| 普通应用 | 不挂 Token | 本地配置/业务处理 | 未认证的 Secret API 请求 |
| p10-reader | namespace RoleBinding + 临时只读节点 ClusterRoleBinding | 本空间 Pod 读取；全局 Node 读取 | Secret 读取、删除测试对象 |
| p10-config-reader | RoleBinding 引用 ClusterRole | 本空间指定 `p10-config` 的 GET | 相同资源名在其他空间的 GET |
| p10-operator | namespace RoleBinding | 删除一个明确的测试 ConfigMap | 无其他配置、Secret 或权限管理授权 |
| 错误 audience 变体 | 同一个 reader SA，Token audience 不匹配 API | 无普通 API 访问 | 实际 GET 必须 401，区别于已认证但权限不足的 403 |

普通 Pod 的 automountServiceAccountToken 为 false。需要访问 API 的测试身份仍关闭自动注入，但显式投射 audience 和 expirationSeconds=600 的 Token、公开 CA 和 namespace 文件。验证只保存 HTTP 状态、audience 和到期时间，不保存 JWT。

绑定 Pod UID 的 TokenRequest 另做前后 TokenReview，验证身份绑定会随原对象删除失效。TokenReview 是受保护的认证请求，不是持久化 Secret；输入文件在私有目录，结束后删除。

临时 ClusterRole/Binding 名称带本 run，精确记录 UID 后才允许清理。实验不授予 Pod cluster-admin，不改动原受限管理身份和恢复管理员。

参考：[RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)、[ServiceAccount](https://kubernetes.io/docs/concepts/security/service-accounts/)。
