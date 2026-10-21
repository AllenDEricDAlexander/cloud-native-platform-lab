# 06.01 安全边界、Keycloak 与身份

覆盖 06.01.01–04。先填写本阶段 [授权范围](scope.json)，审查允许的 Namespace、VM、窗口、负责人、停止条件和恢复入口。默认只创建本批 `cnpl06-01-<run_id>`；主机、家庭网络和外部第三方均不在样例故障范围。

```bash
bash ops/06/01/run.sh validate
CNPL06_INPUTS=/受控路径/inputs.json bash ops/06/01/run.sh render
# 连回内网、前置验收及版本锁核实后，按顺序单独执行：
CNPL06_INPUTS=/受控路径/inputs.json bash ops/06/01/run.sh install
CNPL06_INPUTS=/受控路径/inputs.json bash ops/06/01/run.sh realm
CNPL06_INPUTS=/受控路径/inputs.json bash ops/06/01/run.sh apply
CNPL06_INPUTS=/受控路径/inputs.json bash ops/06/01/run.sh check
```

Keycloak 安装清单须包含 TLS、持久数据库、受控管理员 Secret 引用、资源预算和恢复方式；禁止开发模式作为正式身份入口。realm 使用审核过的 JSON 与已认证的私有 kcadm 配置，首次创建若已存在即停止，不覆盖既有 Realm。先检查 `realm_file` 中没有客户端明文秘密。

Kubernetes API 的 issuer/audience/CA/claim/prefix 变更复用 01 的静态 Pod 配置管理：先保存三控制平面配置和独立恢复 kubeconfig，逐台修改并检查 `/readyz`，每台成功再继续。用真实 OIDC kubeconfig 执行 check，管理员 impersonation 不能代替登录验证。开发只读绑定不允许 Secret 和集群级操作；团队管理员与平台运维的绑定另经评审，禁止直接套用 cluster-admin。

GitLab、Jenkins、Argo CD、Grafana、Backstage 分别填写 [平台接入矩阵](clients.json)：确认当前版本/许可允许的协议、精确 redirect URI、受众、CA、组映射、登出和本地紧急账户。关停 IdP 的实验先确认独立恢复身份仍可认证，再观察新登录失败及恢复；现有 Token 缓存不代表新登录可用。

ServiceAccount/机器人轮换按 [凭据清单](credentials.json) 登记持有者/用途/期限/权限/恢复。样例默认关闭自动挂载；需要 API 的客户端使用投影令牌、明确 audience 和 expirationSeconds，不生成长期 Secret Token。CI、仓库和 Operator 分别替换一项身份后测新凭据允许、旧凭据过期/撤销拒绝，再回收旧值。真实 Token 和 kubeconfig 仅放仓库外 0600 文件，普通证据只记身份、权限、到期时间与退出码。

失败时先恢复 OIDC/回调配置和旧机器凭据，不扩大授权。`cleanup-plan` 只列本批归属及 UID；先解除绑定、删除样例工作负载，再审核 Realm/客户端/数据保留，不能直接卸载共享身份服务。本轮全部运行验收未执行。
