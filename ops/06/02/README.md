# 06.02 PSA、SecurityContext 与供应链准入

覆盖 06.02.01–04。先复用 04 的 Trivy/Cosign/Kyverno；已有控制器不执行 install。本批策略仅匹配 `cnpl06-02-<run_id>`，不更改系统空间。签名公钥按文件/SHA 引用；私钥不进入清单。

```bash
bash ops/06/02/run.sh validate
CNPL06_INPUTS=/受控路径/inputs.json bash ops/06/02/run.sh render
# 以下留到连接内网后：
CNPL06_INPUTS=/受控路径/inputs.json bash ops/06/02/run.sh apply
CNPL06_INPUTS=/受控路径/inputs.json bash ops/06/02/run.sh check
```

初始 `admission.mode=Audit`：PSA Baseline 强制、Restricted Audit/Warn，Kyverno Audit；观察合规应用实际启动、SELinux Enforcing 下 CSI/只读目录权限，再将输入改成 Enforce 重新 render/apply/check。固定 `psa_version` 到当前已验证次版本。非 root、只读根、禁提权、drop ALL、RuntimeDefault、requests/limits 是样例起点，不为兼容关闭 SELinux/firewalld。

check 先确认合法 Pod 的服务端 dry-run 成功，再确认特权样例因 PSA/Kyverno 原因被拒绝；网络/认证/CRD 错误不能算策略通过。签名验证、Harbor TLS/认证、Kyverno API 字段和供应链正反镜像须按锁定版本现场验证；检查 `PolicyReport`/准入事件，合法镜像、未签名、错误公钥、禁止仓库、缺资源分别作为一个变量测试。保留各自服务端拒绝原因，不能用同一个特权拒绝覆盖全部用例。

仓库/验证服务不可达只在样例 NetworkPolicy/代理层隔离，不停共享 Harbor；区分策略拒绝与依赖故障。Webhook Fail 策略和超时必须先核对，break-glass 仅对本策略/本空间设置限时、负责人、原配置 SHA、独立恢复身份和撤销检查，不关闭全局 Webhook。恢复后重新验证可信制品与所有拒绝用例。

清理先退出本批策略约束和工作负载，再审核 ClusterPolicy UID 删除；不卸载共享 Kyverno。未完成实际创建拒绝、签名、依赖失败及恢复前，保持未验收。
