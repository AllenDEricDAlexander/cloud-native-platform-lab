# 01.03 DNS、高可用与完整控制平面备份

01.01–01.02 检查点为 `157e39f`，基础集群、Mac 受限身份、恢复文件备份/取回已通过；.15 管理机实际分发仍待交付。本目录已由用户完成正式备份/取回、CoreDNS 分散和单 VM HA；[真实验收](../records/2026-10-17-restart/acceptance.md)记录通过范围。短名 DNS 原命令有误，修正后待补测。

执行时这些脚本位于工作区，不属于先前的检查点提交；备份包会另外记录并保存实际实现源文件和 SHA256，避免只拿旧 Git HEAD 代替执行输入。

实际顺序是：DNS 布局/短名补测 → **01.03.03 完整备份与取回** → **01.03.02 单控制平面故障**。备份与故障步骤顺序由前置条件决定，不能只看编号先后。

## 1. 准备本轮证据目录

所有命令在同一个管理 Mac 终端执行，每组成功后再继续：

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
set -o pipefail
CNPL03="$PWD/ops/01-kubernetes/records/2026-10-17-restart/evidence/01.03-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$CNPL03"
p03() { "$HOME/.cnpl/bin/kubectl" --kubeconfig "$HOME/.cnpl-secrets/kubeconfig-lab-primary" "$@"; }
```

cd 固定路径；pipefail 保留 tee 前命令的失败状态；变量/mkdir 为本轮生成独立公开证据目录。p03 显式使用平台管理员，只用于本次集群级准备，不改变日常 KUBECONFIG/k 的只读身份。不要把任何真实 kubeconfig、快照或归档放进这个证据目录。

## 2. 分散 CoreDNS，再补 Service 短名与上游证据

现场只读检查发现两个 CoreDNS 仍同在 cp01，这是单节点引导后的布局；preferred 反亲和不会自动搬迁既有 Pod。先滚动增加按 kubernetes.io/hostname 的 required 反亲和，不更改镜像、服务或现有其他配置；遇到不同的已有硬调度规则会停下。

```bash
ANSIBLE_CONFIG="$PWD/ops/00-preparation/ansible/ansible.cfg" \
  "$HOME/.venvs/cnpl-ansible/bin/ansible-playbook" ops/01-kubernetes/ansible/playbooks/prepare-ha-dns.yml \
  2>&1 | tee "$CNPL03/01-coredns-spread.txt"
p03 -n kube-system get pods -l k8s-app=kube-dns -o wide | tee "$CNPL03/02-coredns-placement.txt"
p03 -n kube-system get configmap coredns -o yaml | tee "$CNPL03/03-coredns-corefile.yaml"
p03 -n kube-system get deployment coredns -o 'jsonpath={.spec.template.spec.dnsPolicy}{"\n"}' \
  | tee "$CNPL03/03-coredns-dns-policy.txt"
ANSIBLE_CONFIG="$PWD/ops/00-preparation/ansible/ansible.cfg" \
  "$HOME/.venvs/cnpl-ansible/bin/ansible" k8s_nodes -m ansible.builtin.command -a 'cat /etc/resolv.conf' \
  2>&1 | tee "$CNPL03/03-node-resolvers.txt"
```

五条依次执行受控滚动调整、确认两个 Ready 副本在不同节点、记录 Corefile、实际 Pod DNS 策略和十节点解析器。默认 Corefile 的 forward . /etc/resolv.conf 使用 CoreDNS Pod 的解析配置；本部署 dnsPolicy=Default，节点基础 DNS 为 .11。查询命令不会修改主机，ad-hoc command 默认显示 CHANGED 不代表配置变化；三控制平面的解析器还会归档到备份元数据。

复用已通过的诊断清单，补测短名（不是引入新的诊断镜像）：

```bash
p03 apply -f ops/01-kubernetes/bootstrap/acceptance/network-smoke.yaml \
  2>&1 | tee "$CNPL03/04-dns-smoke-apply.txt"
p03 -n cnpl-phase01-acceptance rollout status daemonset/network-smoke --timeout=5m \
  2>&1 | tee "$CNPL03/05-dns-smoke-ready.txt"
"$HOME/.venvs/cnpl-ansible/bin/python" ops/01-kubernetes/bootstrap/acceptance/check-network.py --short-name \
  2>&1 | tee "$CNPL03/06-dns-smoke.txt"
```

apply 仅创建专用诊断资源；rollout 等待十节点 Pod 就绪；--short-name 在原矩阵上增加每节点的 network-smoke 短名解析与 HTTP，验证 search suffix。预期 `100 Pod HTTP paths (90 cross-node), 50 DNS checks, 30 Service HTTP requests`，最终 NETWORK ACCEPTANCE PASS。

成功后清理，失败时保留诊断现场：

```bash
p03 delete -f ops/01-kubernetes/bootstrap/acceptance/network-smoke.yaml --ignore-not-found=true --wait=true --timeout=180s \
  2>&1 | tee "$CNPL03/07-dns-smoke-cleanup.txt"
```

## 3. 完整备份与离线恢复/取回验证

```bash
"$HOME/.venvs/cnpl-ansible/bin/python" ops/01-kubernetes/operations/backup.py check --records "$CNPL03/backup-check"
"$HOME/.venvs/cnpl-ansible/bin/python" ops/01-kubernetes/operations/backup.py run --records "$CNPL03/backup"
```

第一条只读前检：十节点 Ready、三 API、三 etcd 非 learner 成员与健康、工具版本、安全模式、必要恢复路径、至少 5GiB 空闲。默认省略 mode 时也是 check。第二条才生成备份，约定如下：

1. Ansible 在三控制平面调用 [采集入口](collect-control-plane.py)。cp01 用当前 etcd 容器的匹配 etcdctl 保存一致性 snapshot，并用 etcdutl 查看状态、在唯一 scratch 目录执行 snapshot restore；保持默认哈希验证，不使用 skip-hash-check。
2. 离线 restore 只生成新目录，不启动 etcd、不覆盖 /var/lib/etcd/member。完成后删掉该 scratch。这样验证快照可被正确解析/展开；不是启动独立 etcd 后的完整服务恢复演练。
3. 三台分别打包 /etc/kubernetes（PKI、kubeconfig、静态 Pod、Secret 加密配置和审计策略）、实际 kubelet 配置/PKI/unit drop-in、持久 SELinux fcontext。打包前后 SHA256 变化则失败，避免配置在采集中漂移。每台材料分别归档，不能把一台的证书复制冒充另外两台。
4. Mac 校验三台 CA、加密配置一致和归档完整性，补入受控加密密钥、独立访问恢复包、版本/台账和本次实现源文件；私有材料仅在 ~/.cnpl-secrets/phase01-backups/bundles/，目录 0700、文件 0600。
5. 复用 .16 的加密 restic 仓库，新增 phase01-control-plane 快照，不 forget/prune；按本次准确 ID 取回**整份备份**，逐文件比对 SHA256，再核对归档与快照记录。只有全部通过才生成 backup-receipt.json，并清理三台的本次 root 暂存。

预期 `CONTROL PLANE BACKUP RESTORE PASS`。`$CNPL03/backup/backup-receipt.json` 仅含公开验证元数据，后续 HA 会使用它；真实归档、私钥与快照不入 Git。备份凭据要求同集群且不超过 24 小时。

该脚本保留 Mac 私有材料和 .16 加密副本；它不是冷备介质交付，不验证 Mac 完全损坏后 SSH/restic 口令的另存情况，也不等于真实集群灾难重建。完整在线隔离服务恢复/灾难重建仍属后续恢复专题。[etcd 恢复说明](https://etcd.io/docs/v3.6/op-guide/recovery/)

## 4. 准备单控制平面故障实验

先确认当前 VIP 持有者，以它为本次目标；下面示例 cp01 对应 .101。如果已换成 cp02/cp03，传实际持有者：

```bash
p03 -n kube-system get lease plndr-cp-lock -o wide | tee "$CNPL03/08-vip-before.txt"
"$HOME/.venvs/cnpl-ansible/bin/python" ops/01-kubernetes/operations/ha.py prepare \
  --records "$CNPL03/ha" --receipt "$CNPL03/backup/backup-receipt.json" --target cp01
```

prepare 拒绝缺失/过期/不同集群的备份凭据，要求三 API/etcd、十节点和系统组件健康、CoreDNS 两副本分散、目标为当前 VIP 持有者；同名旧测试对象存在时拒绝覆盖。然后仅用 lab-core 运维身份创建两个小型普通 HTTP Pod 和 ClusterIP Service，以硬反亲和保证 worker01/02 各一个，不放在待关闭控制平面或 storage。

平台管理员只用于预检、读取 lease 和 etcd；实验资源由 lab-primary-lab-ops 管理，日常默认身份不变。公开 state.json 记录集群、目标、备份凭据、脚本指纹与进度，禁止并发 watch，同批清理校验资源所有权。

## 5. 启动独立观测，由用户手动关/开一台 VM

```bash
"$HOME/.venvs/cnpl-ansible/bin/python" ops/01-kubernetes/operations/ha.py watch --records "$CNPL03/ha" --seconds 600 \
  2>&1 | tee "$CNPL03/09-ha-watch.txt"
```

这条在前台保持观测。**脚本不会操作 VM 电源，也不会停止任何节点服务**：

1. 等到 `BASELINE PASS` 后，在已有 ESXi 控制台核对该 VM 的主机身份/IP，**只关闭目标控制平面**，不停止第二台；VM 显示名称以实际为准。单独停 kubelet 不能代替关机，因为其静态 Pod 可能继续运行。
2. 脚本检查目标 22/6443 双端口失联，并确认其他两控制平面仍可达；非目标也失联立即停止。通过存活 API 检查 VIP lease 已换持有者、两个存活 etcd 健康，并在故障期间经 VIP 新建/调度一个一次性 Pod 成功，验证控制器与调度器仍工作。
3. 出现 `FAULT CHECKS PASS` 后，在 ESXi **开启刚才同一台 VM**。脚本继续等到十节点 Ready、三 etcd 与系统组件健康，输出 `HA ACCEPTANCE PASS`。VIP 不要求自动回迁原节点。

应用探测通过 Mac→worker SSH→Pod/ClusterIP，使用既有 SSH 信任和临时本机回环端口，不开新的 NodePort/firewalld 端口。两条直达 Pod 和一条 ClusterIP 请求独立于 Kubernetes API；不使用依赖 API 的 kubectl port-forward。VIP API 使用只读证书保持 TLS 验证。SSH 进程和临时 TLS 文件退出时清理。

timeline.jsonl 记录每轮 UTC、API/应用结果及节点失联状态；state.json 记录首次失联、观测到的 VIP 接管、故障期间 API 恢复及最终恢复时间。采样约两秒一次，超时会影响实际间隔；这些是采样观测，不冒充精确业务 RTO。API 可出现短暂错误并如实记录，故障窗口的应用失败则不判通过；未检测到停机或新 Pod 未成功也不会误判通过。脚本不读取 vSphere 电源状态，需把实际 ESXi 关/开任务时间、目标 VM 标识另记到本轮证据中。

观察默认 600 秒，允许 120–900 秒。超时/报错时先恢复已关闭的 VM；脚本保留实验应用和记录，避免在故障未恢复时清理取证现场。若关错 VM，先恢复它，不继续关第二台。

本轮只验证单 VM 故障，不关 ESXi 主机，也不据此宣称实际物理故障域已经验收。

## 6. 恢复核验与清理

```bash
"$HOME/.venvs/cnpl-ansible/bin/python" ops/01-kubernetes/operations/ha.py verify --records "$CNPL03/ha" \
  2>&1 | tee "$CNPL03/10-ha-recovery.txt"
"$HOME/.venvs/cnpl-ansible/bin/python" ops/01-kubernetes/operations/ha.py cleanup --records "$CNPL03/ha" \
  2>&1 | tee "$CNPL03/11-ha-cleanup.txt"
printf '01.03 证据目录：%s\n' "$CNPL03"
```

verify 检查恢复健康，不能把没有通过的实验补判为 HA PASS。cleanup 先要求三控制平面、十节点、系统组件恢复，再只删除本批带所有权标识的 Deployment/Service/Pod，保留 lab-core 和其他对象。CoreDNS 分散布局是正常 HA 配置，保留它。最后归档证据路径，逐项更新阶段验收。

## 当前交付验证边界

用户已完成真实备份/取回、离线快照展开、CoreDNS 分散、cp01 停机/恢复和清理，[公开凭据与 HA 观测](../records/2026-10-17-restart/acceptance.md)已归档。短名 DNS 仍待修正后补测：BusyBox nslookup 显式指定服务器时不读取 search，现改为检查实际搜索域、查询展开后的名称，再用 wget 短名访问验证 libc 解析。原始失败日志保留。

在线隔离服务恢复、整集群灾难重建与物理故障域仍未执行；离线展开不能替代这些验收。
