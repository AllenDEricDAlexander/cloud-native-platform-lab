# Phase 01 完整引导配置与执行顺序

本轮十节点基础集群、普通 Pod 网络、Mac 受限身份和恢复文件备份/取回均通过，准备进入 01.03 完整备份和 HA。本文件保留引导复现顺序，实际状态以 [当前执行批次](../records/2026-10-17-restart/README.md)为准。下方引导命令在管理 Mac 的 `ops/00-preparation/ansible/` 下运行，复用原 inventory、SSH 密钥、collections 与版本锁；验收/身份手册使用仓库根目录。

## 1. 配置内容与职责

| 配置 | 用途 |
| --- | --- |
| [kubeadm-init-cp01.yaml](kubeadm/kubeadm-init-cp01.yaml) | 首节点、VIP 入口、网络、审计、Secret 加密挂载与 kubelet 公共配置 |
| [资源台账](../../inventory/resources.yaml) | 各角色资源预算唯一来源；由 kubeletconfiguration 原生补丁应用到 init/join |
| [audit-policy.yaml](kubeadm/audit-policy.yaml) | Metadata 审计；不记录请求/响应正文，健康探测不写审计 |
| `kubeadm/encryption-config.yaml.j2` | 从仓库外密钥渲染 secretbox 加密配置；三个控制平面共用一份密钥 |
| `kubeadm/join-node.yaml.j2` | 短时凭据与节点参数；控制平面、infra、storage、worker 共用一个明确的原生模板 |
| [kube-vip 引导清单](kube-vip/kube-vip-cp01-init.yaml) / [稳态清单](kube-vip/kube-vip-control-plane.yaml) | init 引导用 super-admin.conf，成功后自动切换 admin.conf；仅管理 API VIP |
| [Cilium values](cilium/cilium-values.yaml) | Overlay/VXLAN、kube-proxy 共存、cluster-pool、Harbor 平台 Digest |

复用 kubeadm 原生配置与 patches、已有 Ansible 角色，不新增框架或生成器。

kube-vip 两份清单都必须保留 `kubernetes → 127.0.0.1` 的 hostAliases；锁定版本的控制面客户端通过这个别名访问本机 API，不应查询外部 DNS。掩码使用该版本实际支持的 `vip_subnet`。这些约束已纳入离线回归测试。[官方清单](https://kube-vip.io/docs/installation/static/#example-arp-manifest)

### 资源预算

| 角色 | systemReserved | kubeReserved | 合计预留 |
| --- | --- | --- | --- |
| control_plane / infra / worker | 500m CPU / 1 GiB | 500m CPU / 1 GiB | 1 CPU / 2 GiB |
| storage | 2500m CPU / 5 GiB | 500m CPU / 1 GiB | 3 CPU / 6 GiB，其中 Ceph 份额为 2 CPU / 4 GiB |

另设置 memory.available 500Mi、nodefs.available 10%、imagefs.available 15%、inode 与 PID 阈值，单 Pod PID 上限 4096。预留会减少可分配给 Pod 的资源；硬驱逐阈值在资源紧张时触发 Pod 驱逐。这是实验室起步预算，实际 Allocatable 和 Ceph/业务负载须在启动后复核，不能视为性能或容量保证。

### SELinux 与秘密

- 控制平面保持 container_t，精确的 PKI、kubeconfig、加密/审计配置与 etcd 路径使用持久 fcontext 规则。复用 00 的 container_runtime 专用任务，常规 00 play 不受影响。
- API Server 自行创建审计文件，审计日志目录也明确使用 container_file_t；本机策略下 container_log_t 的创建权限探针失败，已更正持久规则并在三个控制平面重新验证通过。
- kubeadm 会在 kubelet 启动前创建新证书与 kubeconfig；kubelet 的 ExecStartPre 按规则 restorecon，避免新文件恢复成容器无法访问的类型。准备阶段只 daemon-reload，不启动 kubelet。
- Cilium agent/envoy 保留锁定 Chart 原有的 spc_t、能力与系统挂载要求；这不等同于普通控制平面容器的路径授权方案。
- 管理端密钥位于 `~/.cnpl-secrets/k8s-encryption.key`，已存在时只验证、不重建；真实加密配置在各控制平面的 `/etc/kubernetes/enc/encryption-config.yaml`（0600），不入 Git。
- 私有 init/join 原始日志只保存在对应节点 root 目录，终端与证据只接收受控输出。join 文件用后删除，30 分钟 token 在操作结束时撤销。
- 控制平面额外限定放行 Pod CIDR `10.244.0.0/16` 到 `6443/tcp`，让 CoreDNS 等 Pod 可以访问 API；不把 Pod 网段整体放进 trusted，也不开放其他主机端口。准备与 Cilium 入口共用该规则。
- 管理端加密密钥应与 PKI/etcd 恢复材料一起另存至受控备份；仅有 etcd 快照不足以恢复加密 Secret。

## 2. 顺序执行（每条成功后再继续）

进入 Ansible 目录，让原有配置生效；pipefail 确保 tee 不掩盖命令失败：

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab/ops/00-preparation/ansible
set -o pipefail
```

### 准备与预演：本轮已执行通过

`prepare.yml` 核对版本与台账、分发配置、应用标签、渲染角色补丁、验证合成文件访问并预拉镜像。它拒绝覆盖已经入群的节点，不启动 kubelet。下列命令只供新建、未入群节点复现；当前 cp01 已初始化，不再重跑 prepare 或首次初始化预演：

```bash
~/.venvs/cnpl-ansible/bin/ansible-playbook ../../01-kubernetes/ansible/playbooks/prepare.yml \
  2>&1 | tee ../../01-kubernetes/records/2026-10-17-restart/evidence/01.02-prepare-recheck.txt
```

默认初始化入口运行 kubeadm 的 dry-run；原始日志留在 `/root/kubeadm-init-dry-run.out`，输出过滤凭据。它不同于 Ansible `--check`，会实际执行 kubeadm 的预演和配置生成：

```bash
~/.venvs/cnpl-ansible/bin/ansible-playbook ../../01-kubernetes/ansible/playbooks/init-cp01.yml \
  2>&1 | tee ../../01-kubernetes/records/2026-10-17-restart/evidence/01.02-dry-run-recheck.txt
```

### 真实初始化 cp01（仅首次，本轮已完成）

`init_apply=true` 才启用并启动 kubelet、创建首个控制平面和本地 etcd，并在 init 成功后切换 kube-vip 凭据。当前只有 cp01，CNI 未装前节点暂时 NotReady 是预期；日志应出现 `cp01 init PASS`。

```bash
~/.venvs/cnpl-ansible/bin/ansible-playbook ../../01-kubernetes/ansible/playbooks/init-cp01.yml -e init_apply=true \
  2>&1 | tee ../../01-kubernetes/records/2026-10-17-restart/evidence/01.02-init-cp01-apply.txt
```

### 已初始化节点的 VIP 恢复

如果 kubeadm 已完成但后置 VIP 检查失败，先保留原始输出，使用恢复入口。它先从 `.101` 验证本机 API 和初始化产物，只同步并修正 kube-vip，不调用 kubeadm init/reset、不重建 CA 或 etcd。会确认新清单的镜像 Pod 已切换至正确 hostAliases/稳态凭据、VIP 已绑定，以及 API 连续通过检查；失败时显示分项诊断。

```bash
~/.venvs/cnpl-ansible/bin/ansible-playbook ../../01-kubernetes/ansible/playbooks/init-cp01.yml -e init_resume=true \
  2>&1 | tee ../../01-kubernetes/records/2026-10-17-restart/evidence/01.02-vip-resume-recheck.txt
```

当前已通过这条恢复路径；Cilium 也已安装，无需再次执行恢复或安装。

### 安装 Cilium（本轮已完成）

先检查管理端客户端版本、Chart 摘要并补齐控制平面的 Pod 到 API 规则，再取回 admin kubeconfig，以显式 kubeconfig 调用锁定的 Helm/Chart。单节点引导使用 1 个 operator，节点增多后恢复为 2。验证 agent/operator、节点 Ready 与 CoreDNS rollout；不能仅凭 Node Ready 就判定 Pod 访问 API 正常。

```bash
~/.venvs/cnpl-ansible/bin/ansible-playbook ../../01-kubernetes/ansible/playbooks/install-cilium.yml \
  2>&1 | tee ../../01-kubernetes/records/2026-10-17-restart/evidence/01.02-install-cilium.txt
```

### 加入其余控制平面

先对 cp02、cp03 整批只读前检：身份、命令和版本、CRI、VIP 解析/TCP、SELinux、firewalld、角色补丁、共享加密配置，以及本机产物与 API 节点登记是否一致。全部通过后才逐台创建 30 分钟凭据并 join；每台确认本机 API 可访问、稳态 kube-vip 配置和 Ready、节点 Ready 与 etcd 全成员健康后继续。

CA 摘要来自 `kubeadm token create --print-join-command`，不依赖节点的 OpenSSL，也不执行输出的 shell 字符串。先在本地生成随机令牌，再创建集群 Secret，即使原生输出校验失败，也能按已知 ID 撤销。控制平面证书上传显式复用 cp01 的初始化配置，密钥按格式提取；渲染后的真实 JoinConfiguration 在启用 kubelet 前校验。[kubeadm 原生命令](https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-token/)

本轮使用新的 retry 日志，保留原始失败记录：

```bash
~/.venvs/cnpl-ansible/bin/ansible-playbook ../../01-kubernetes/ansible/playbooks/join-control-plane.yml \
  2>&1 | tee ../../01-kubernetes/records/2026-10-17-restart/evidence/01.02-join-control-plane-retry-$(date +%Y%m%d-%H%M%S).txt
```

### 加入七个工作节点

逐台加入 infra/storage/worker，使用对应资源预算；storage 通过 NoSchedule 污点保护。标签使用实际 FQDN，宿主机信息只登记为 planned-hypervisor。最后重新应用 Cilium，恢复 2 个 operator 并等待所有节点 Ready。

这个入口同样先整批检查七台目标，全部通过才创建凭据；仅在上一条控制平面入群全部成功后执行。

```bash
~/.venvs/cnpl-ansible/bin/ansible-playbook ../../01-kubernetes/ansible/playbooks/join-workers.yml \
  2>&1 | tee ../../01-kubernetes/records/2026-10-17-restart/evidence/01.02-join-workers.txt
```

### 查看结果

下列命令只查询：第一条预期 10 个 Ready；第二条检查系统 Pod，第三条检查角色预留生效后的 Allocatable：

```bash
~/.cnpl/bin/kubectl --kubeconfig ~/.cnpl-secrets/kubeconfig-lab-primary get nodes -o wide
~/.cnpl/bin/kubectl --kubeconfig ~/.cnpl-secrets/kubeconfig-lab-primary -n kube-system get pods -o wide
~/.cnpl/bin/kubectl --kubeconfig ~/.cnpl-secrets/kubeconfig-lab-primary get nodes -o custom-columns=NAME:.metadata.name,CPU:.status.allocatable.cpu,MEMORY:.status.allocatable.memory
```

## 3. 结果边界与故障处理

当前十节点普通 Pod 双向 HTTP、Service/DNS、Mac 受限身份及恢复文件备份/取回已通过。完整控制平面备份、VIP 故障接管/HA 与阶段其他实验仍需继续；.15 管理机实际分发/登录仍待交付，不能用 Mac 上的证书包测试代替。

首次 init 入口检测到已有 CA/admin.conf、etcd member、运行对象或 kubelet 已启动时会停止并提示恢复模式。join 前检会拒绝不完整的入群现场，不能仅凭 kubelet.conf 存在跳过；完整已入群节点只核验和协调稳态 VIP，不重复 join。原始 join 日志每次独立保存为 `/root/kubeadm-join.XXXXXXXX.out`（0600），失败显示阶段与日志路径；不覆盖上一轮日志。不要原样粘贴私有日志。临时配置清理失败时仍单独尝试撤销 token；连接完全中断时无法保证即时清理，令牌另有 30 分钟到期限制。SELinux 问题先核对持久规则、ExecStartPre 与 AVC，不关闭安全控制。

只检查而不入群时，可使用 `join-preflight.yml`（默认全部九台）或任一 join 入口加 `--tags join_preflight`；管理端 Cilium 物料检查用 `install-cilium.yml --tags cilium_preflight`。不要用 `--limit` 排除 cp01，它提供集群登记与共享配置摘要；需要缩小目标时给独立前检传 `-e phase01_join_hosts=cp02`。
