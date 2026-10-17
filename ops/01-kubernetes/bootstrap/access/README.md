# 01.02.08 受限管理身份与恢复入口

前置：十节点基础验收通过；本轮证据为 [20261017-125334](../../records/2026-10-17-restart/evidence/01.02-acceptance-20261017-125334/14-network-matrix.txt)。以下均在同一管理 Mac 终端执行，每步成功后继续；不启动工作负载或重启服务。

## 权限与凭据

| 身份 | Context / 范围 | 默认期限 |
| --- | --- | --- |
| Mac 日常只读 | lab-primary-readonly；节点、工作负载、Service、日志等白名单只读 | 90 天 |
| Mac 实验运维 | lab-primary-lab-ops；上述只读 + lab-core 内工作负载、Service、ConfigMap 等管理/exec | 90 天 |
| .15 管理机 | 独立 CN/密钥，分别只读与实验运维；包先保存在 Mac，未分发 | 90 天 |
| 恢复管理员 | 独立 recovery.conf；system:masters，四个 API Context | 365 天 |

普通身份均无 Secret、ServiceAccount token、RBAC 管理、节点修改/proxy 或用户冒充权限。实验运维不能改其他 Namespace，也不能修改 lab-core 的 restricted Pod Security 标签；lab-core 不放高权限 ServiceAccount。能创建工作负载的用户仍能使用该 Namespace 已有的 ServiceAccount，Namespace 级权限不是对节点放置或全部网络访问的独立隔离。

认证解决“是谁”，RBAC 决定“可以做什么”。本轮原生 `kubeadm kubeconfig user` 直接由既有 CA 签证；仅恢复身份加入 system:masters，普通身份按具体 CN 绑定白名单。这个恢复组绕过授权层，不能靠删除 RoleBinding 吊销；客户端证书无单独吊销机制。保留固定有效期、到期记录和独立保管，后续统一身份在 06A 扩展。[kubeadm 说明](https://kubernetes.io/docs/tasks/administer-cluster/kubeadm/kubeadm-certs/#generating-kubeconfig-files-for-additional-users) · [证书限制](https://kubernetes.io/docs/concepts/security/hardening-guide/authentication-mechanisms/)

## 1. 建立本轮证据目录

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
set -o pipefail
CNPL_ACCESS="$HOME/.cnpl-secrets/access/lab-primary"
CNPL_ACCESS_RECORD="$PWD/ops/01-kubernetes/records/2026-10-17-restart/evidence/01.02-access-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$CNPL_ACCESS_RECORD"
```

cd 固定仓库路径；pipefail 让 tee 不掩盖失败。ACCESS 指向仓库外秘密目录，RECORD 指向带时间戳的公开证据目录；两者不混用。mkdir 只创建证据目录。

## 2. 签发并配置身份

```bash
ANSIBLE_CONFIG="$PWD/ops/00-preparation/ansible/ansible.cfg" \
  "$HOME/.venvs/cnpl-ansible/bin/ansible-playbook" ops/01-kubernetes/ansible/playbooks/configure-access.yml \
  2>&1 | tee "$CNPL_ACCESS_RECORD/01-configure-access.txt"
```

复用既有 inventory/SSH/CA：在 cp01 签发五份不同 CN/密钥的证书，经 SSH 取回并核验签名、私钥匹配、CA、用途、主体和有效期，再组合 Mac/管理机各双 Context 与独立恢复配置。创建 lab-core（restricted）和白名单 Role/Binding；不改现有管理员、CA、节点或其他 Namespace，不自动创建实验 Pod。现有材料重跑复用，不静默覆盖或续期。秘密任务 no_log，真实文件和恢复包 0600、目录 0700。

预期 cp01/localhost failed=0、unreachable=0。如失败先保留现场，不手工打印任何完整 kubeconfig。公有定义见 [身份清单](identities.yaml)和 [RBAC](rbac.yaml)。

### 已签发材料的本地恢复

如果签发、取回已经完成，但在“校验证书归属并生成独立 kubeconfig 和恢复包”失败，修正脚本后可只运行本机后半段，复用 `issued/` 内现有证书；不重新签发或连接 cp01：

```bash
ANSIBLE_CONFIG="$PWD/ops/00-preparation/ansible/ansible.cfg" \
  "$HOME/.venvs/cnpl-ansible/bin/ansible-playbook" ops/01-kubernetes/ansible/playbooks/configure-access.yml \
  --tags access_assemble \
  2>&1 | tee "$CNPL_ACCESS_RECORD/01-configure-access-retry-$(date +%Y%m%d-%H%M%S).txt"
```

组合任务仍隐藏私有输出；由脚本输出固定结构、经过脱敏的错误原因，再由下一条 assert 显示。格式解析错误不打印输入原文。只做核验可给 build-access.py 传 `--check-only`，不会创建文件或修改权限。

kubeadm v1.36.5 的客户端证书可沿用 CA 的 NotBefore；--validity-period 决定的是签发时刻之后的到期时间。因此期限检查使用 NotAfter 相对当前时间的上限，不能把 `NotAfter - NotBefore` 当作签发期限。仍严格验证签名、CN/O、私钥匹配、用途、当前有效及至少七天余量，不放宽普通身份或恢复身份的期限策略。[锁定版本源码](https://github.com/kubernetes/kubernetes/blob/v1.36.5/cmd/kubeadm/app/util/pkiutil/pki_helpers.go#L565)

## 3. 用真实证书验收允许与拒绝

```bash
"$HOME/.venvs/cnpl-ansible/bin/python" ops/01-kubernetes/bootstrap/access/verify-access.py \
  2>&1 | tee "$CNPL_ACCESS_RECORD/02-access-verification.txt"
cat "$CNPL_ACCESS/certificates.json" | tee "$CNPL_ACCESS_RECORD/03-certificate-expiry.json"
```

第一条依次用四个独立受限身份执行 whoami、can-i 矩阵、真实读取/拒绝请求；运维身份创建、读取并删除带随机名称的临时 ConfigMap。只把真实 Forbidden 当作预期拒绝，认证/网络错误不会误判通过。恢复身份检查 CN/system:masters、读取 RBAC、四 API Context 的 TLS readyz。没有启动容器，也没有故意破坏 RBAC。

预期 `ACCESS ACCEPTANCE PASS`，测试 ConfigMap 清理。管理机身份在 Mac 上验证了证书与权限，不能替代未来 `.15` 的分发/登录验收。第二条仅保存证书主体、组、到期 UTC 和指纹清单，不含私钥；自定义证书不会自动续期，临近到期需显式轮换。

## 4. 激活默认只读并练习 Context 切换

```bash
source ops/01-kubernetes/bootstrap/access/use-access.sh
k config current-context
k auth whoami
k get nodes
```

source 将本终端 KUBECONFIG 和 k 函数切到受限 Mac 文件，替换上一轮指向引导管理员的 k；默认选 readonly。随后三条分别核对 Context、API 实际识别的 CN 和真实读取，预期 `lab-primary-readonly`、`cnpl-mac-reader`、10 个节点。没有覆盖既有 ~/.kube/config 或修改 ~/.zshrc；新终端再次 source。

```bash
k config use-context lab-primary-lab-ops
k auth whoami
k auth can-i create deployments.apps -n lab-core
k config use-context lab-primary-readonly
```

四条分别切换运维、核对 CN=cnpl-mac-operator、验证 lab-core 部署权限为 yes、切回只读。namespace 限制由 RBAC 保证，Context 的 namespace 字段只是默认值。

## 5. 验证独立恢复入口

```bash
"$HOME/.cnpl/bin/kubectl" --kubeconfig "$CNPL_ACCESS/recovery/recovery.conf" \
  --context lab-primary-recovery-cp02 --request-timeout=15s get nodes \
  2>&1 | tee "$CNPL_ACCESS_RECORD/04-recovery-direct-api.txt"
k config current-context
```

第一条仅该请求使用恢复身份并直连 `.102`，内嵌 CA 保持 TLS 校验；预期 10 个节点。第二条应仍为 readonly，证明恢复文件没有合并到日常 Context。还提供 cp01/.101、cp03/.103 和 vip 四 Context。直连避免依赖 API VIP/DNS，但不能修复网络完全中断、证书过期、API/etcd 本身不可用。

## 6. 加密备份并验证取回

```bash
bash ops/01-kubernetes/bootstrap/access/backup-access.sh \
  2>&1 | tee "$CNPL_ACCESS_RECORD/05-access-backup-restore.txt"
printf '身份配置证据：%s\n' "$CNPL_ACCESS_RECORD"
```

复用 00 已有 restic 0.19.1、SSH 和 `.16` 仓库口令，只新增本身份目录的加密快照，不 forget/prune。取得本次准确快照 ID，取回 recovery.conf 到临时私有目录，逐字节比较并用恢复出的文件直连 API；退出时清理临时目录。预期 `ACCESS BACKUP RESTORE PASS`，保留快照 ID。printf 显示证据目录。

restic 解密口令和 SSH 恢复材料仍须在 Mac 之外保管，不能只依赖被备份的 Mac。本恢复包提供 API 应急身份，不包含集群 CA 私钥、etcd Snapshot 和 Secret 加密密钥；完整控制平面备份是下一步。`.16` 是集群外备份主机，这不等于已经把文件复制到断网介质。

## 验收边界

本轮完成标准：四个独立受限身份通过允许/拒绝验收，Mac 默认只读，独立恢复配置直连成功，证书到期清单归档，恢复文件从集群外加密备份取回并可用。`.15` 管理机包已经准备，但该机器未交付，实际分发/登录保持待办；不要用 build01 或 Kubernetes 节点冒充管理机。

普通身份撤权应从 cnpl-observers 及 lab-core/cnpl-lab-operators 的 subjects 移除相应 CN；删除本地文件不等于撤销已签证书。恢复组不适用这种撤权方式，泄漏需按 CA/凭据事故处理；不在这个配置入口自动轮换 CA。
