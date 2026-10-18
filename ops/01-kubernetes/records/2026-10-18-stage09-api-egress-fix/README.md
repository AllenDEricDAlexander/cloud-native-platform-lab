# 01.09 Indexed Job API 出口修复

原批次为 `09-20261018T113437Z`，run `20261018T113444Z-f130c045`，失败 attempt 为 `20261018T113624Z-9bd8aded`。失败步骤为“并行重试 Job 完成”。本次只修复当前 API 出口及相关检查，保留原失败证据，未将整个 09 标记通过。

## 根因与修复

六个 Pod 都在 GET `https://192.168.20.1:443/api/v1/namespaces/lab-p09/configmaps/p09-ledger` 时 5 秒超时、退出 1；账本为空，Job 在 180 秒后进入 DeadlineExceeded。它们没有完成预期的“先提交再退出 7”。

原 baseline 用 Kubernetes NetworkPolicy 的 ipBlock 放行控制平面节点地址，但当前 Cilium 默认 CIDR 策略不匹配集群节点身份。当前配置未启用 policy-cidr-match-mode=nodes。此前服务端准入只能证明清单可接受，未验证这个真实网络语义；这是原脚本遗漏。

修复继续使用现有 Cilium 能力：

- [公共 baseline](../../core-resources/shared/manifests/baseline.yaml.j2)使用 Namespace 内的 CiliumNetworkPolicy，按本 run 标签选择 Pod，仅放行 kube-apiserver 实体的 TCP 443/6443。普通空间隔离及 DNS 规则保留，覆盖 09 和后续 10 的 API 访问。
- 资源入口允许该类型，检查器把它纳入归属核验、快照和 Namespace 清理；未增加集群级策略或修改 Cilium 全局配置。
- Job 已进入相反终态时检查器返回独立退出码，原生 Ansible 等待器立即停止并显示真实原因。
- Indexed Job 逐序号核对预期退出 7 与重试退出 0，拒绝网络错误退出 1 冒充失败重试；账本仍必须三个键各生效一次。

依据：[Cilium 节点 CIDR 匹配与 kube-apiserver 实体说明](https://docs.cilium.io/en/stable/security/policy/layer3/#selecting-pods-or-nodes-with-cidr-ipblock)。

## 实际验证

[14 项检查与原生集成测试](core-tests.txt)通过，包括 Job 相反终态、逐序号退出码、真实 Ansible 终态仅调用一次即停止、CronJob 对照、HPA 指标和原生证书材料验证。

新增[有限真实 Job 夹具](../../tests/core-job-network-smoke.yml)，在两个唯一临时 Namespace 中分别把原 Indexed Job 固定到一个 worker，使用原镜像、原账本、原 SA/RBAC 和修复后的公共 baseline。两个 worker 均通过：

| worker | 结果 | 证据 |
| --- | --- | --- |
| worker01 | 三个序号各观察到 7 和 0，succeeded=3、failed=3，三个账本键各为 1；临时空间已回收 | [完整执行日志](worker01-job-smoke.txt)、[退出码](worker01-evidence/attempt/observations/retry-complete.json) |
| worker02 | 三个序号各观察到 7 和 0，succeeded=3、failed=3，三个账本键各为 1；临时空间已回收 | [完整执行日志](worker02-job-smoke.txt)、[退出码](worker02-evidence/attempt/observations/retry-complete.json) |

两次有限集成均为 localhost `ok=114 changed=23 failed=0 unreachable=0`，包含真实服务端准入、运行、取证和精确清理。没有删除或重建用户原 `lab-p09` 失败现场。

[原批次同目录 validate](validate-original-run.txt)已通过，包含 `01.09 SOURCE VALIDATION PASS`，全部主机 failed=0/unreachable=0。主剧本和修复来源登记剧本均通过语法检查。

## 原批次来源与继续执行

[修复前 SHA](before-sha256.json)覆盖原目录 57 个文件；旧 context 已原字节保存在原目录 `origin/api-egress-fix-0001/context.json`。只有当前 context 进行六条准确路径的来源登记，原日志、失败快照、镜像和其他原件保持原字节。

[登记剧本](adopt-source.yml)已实际执行，先核对原 run、集群、Namespace UID、未完成状态及准确差异，再归档旧 context 并切换当前来源；不改写 07/08 回执，也不补写 09 成功回执。新旧摘要和差异保存在原目录 `origin/api-egress-fix-0001/source-revision.json`。

在管理 Mac 执行：

```bash
CNPL09=/Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/records/core-07-10/runs/09-20261018T113437Z
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-09.sh resume "$CNPL09"
```

第一条定位原证据目录。第二条沿用同一 run，先取证并回收原失败空间，再执行 09 的 Job、CronJob 和 HPA；已健康的指标基础组件会复用。原日志及 attempt 保留，新执行写入新 attempt。最终仍须同时得到 `01.09 ACCEPTANCE PASS`、`01.09 CLEANUP PASS`，全部主机 failed=0/unreachable=0。

本次只完成网络故障修复及有限 Job 实证；09 其余正式实验与最终清理仍由上述 resume 完成。
