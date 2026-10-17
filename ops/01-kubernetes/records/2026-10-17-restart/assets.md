# Phase 01 执行记录（2026-10-17 从头重做）

## 1. 2026-10-17 放弃旧批次，建立本轮记录

**用户要求**：现有 01 执行记录全部回滚放弃，从头开始执行。

**管理端已执行**：

- 将旧 `records/2026-10-17/` 与 `bootstrap/` 移出活动目录，归档至 `/Users/mario/.cnpl-archives/phase01-abandoned-20261017-101612/`。
- 共 44 个文件，逐文件比较归档前后 SHA256，一致；清单保存在归档目录的 `manifest.json`。
- 新建本轮记录，01.01 及后续步骤均待重新执行和验证。

**本轮边界**：保留 Phase 00 交付、台账、版本锁、已有镜像及管理端工具、仓库外密钥。旧引导草稿不再直接用于本轮执行。主机恢复至入群前状态后，重新复验实际版本与前置条件。

**现场状态**：尚未连接远程节点，未执行 reset、删除节点文件、修改 SELinux 标签、安装 CNI 或启动服务。不能认定节点已回滚。

**下一步**：用户登录 cp01，核对主机身份、CRI 容器和旧初始化目录的实际情况；取得输出后确定清理操作。清理结束再进入 01.01，不沿用旧批次的通过结论。

## 2. 2026-10-17 重做前的 cp01 首批现场检查

**执行方式**：用户从管理 Mac SSH 登录 `192.168.9.101`，执行三条只读命令并贴回输出；本助手没有连接远程节点。

**输出与结果**：

- `hostnamectl --static` 返回 `cp01.k8s.internal.egon.top`，目标主机身份符合本轮操作对象。
- `crictl ps -a` 只有表头，没有容器记录；尚未检查 Pod sandbox。
- `/etc/kubernetes/manifests` 与 `/var/lib/etcd` 不存在，`/etc/kubernetes` 仍存在（目录权限 `drwxr-xr-x.`，属主 `root:root`）。

证据：[用户贴回的首批现场输出](evidence/restart-cp01-initial-state.txt)。

**结论**：目前没有观察到 CRI 容器或上述两个目录。不能据此判断所有残留已清理，也不能推断已经执行过 reset；本轮没有清理命令的执行证据。

**下一步**：只读检查 `/etc/kubernetes` 的剩余目录和文件名、CRI Pod sandbox、SELinux 本地 fcontext 规则，随后按实际残留确定清理操作。01.01 仍未开始。

## 3. 2026-10-17 剩余目录检查与 Ansible 使用授权

**用户输入**：贴回 `ls -laR /etc/kubernetes` 与 `semanage fcontext -l -C` 输出，并明确可以使用 Ansible。附件按原字节归档：[目录与 SELinux 本地规则](evidence/restart-cp01-files-and-selinux.txt)。附件只含文件名、权限与标签规则，不含密钥文件内容；其中没有 `crictl pods` 的输出。

**现场观察**：`/etc/kubernetes` 仅余 `audit`、`enc`、`tmp` 三个直接子目录；其中有旧审计策略、加密配置，以及四份 kubeadm dry-run 目录。SELinux 本地 fcontext 仅列出 `/var/log/kubernetes/audit(/.*)?`。

**补充检查**：助手在 `ops/00-preparation/ansible/` 下复用现有 inventory、专用 SSH 密钥与 Ansible 环境，执行 `ansible cp01 -m ansible.builtin.command -a 'crictl pods -q'`，返回 rc=0、空输出。Ansible command 模块默认显示 CHANGED，这次操作实际只查询 sandbox 列表，没有修改节点。[查询证据](evidence/restart-cp01-sandbox-query.txt)。

## 4. 2026-10-17 Ansible 清理 cp01 旧残留

**实现**：[cleanup-cp01.yml](../../ansible/playbooks/cleanup-cp01.yml)。采用内置模块直接编排，复用 00 的连接配置，不新增角色或依赖。先核对 cp01 的地址与 FQDN、kubelet inactive、无 CRI 容器和 sandbox、无 manifests/PKI/admin kubeconfig/etcd/kubelet 配置，以及 `/etc/kubernetes` 没有未识别子项；全部满足后才清理。

**执行目录**：`ops/00-preparation/ansible/`，使用 `~/.venvs/cnpl-ansible/bin/ansible-playbook`。

**实际执行顺序**：

1. `ansible-playbook ../../01-kubernetes/ansible/playbooks/cleanup-cp01.yml --syntax-check`：通过。
2. `ansible-playbook ../../01-kubernetes/ansible/playbooks/cleanup-cp01.yml --check --diff`：前置断言通过，failed=0；仅预演，未删除文件。证据：[check](evidence/restart-cp01-cleanup-check.txt)。
3. `ansible-playbook ../../01-kubernetes/ansible/playbooks/cleanup-cp01.yml`：实际清理，failed=0、unreachable=0；清理后逐路径与本地规则断言通过。证据：[apply](evidence/restart-cp01-cleanup-apply.txt)。

**实际变更**：删除 `/etc/kubernetes/{audit,enc,tmp}`、`/var/log/kubernetes/audit`、`/root/phase01-bootstrap`；撤销旧审计目录的本地 fcontext 规则。`/root/kubeadm-init.out` 已不存在，未发生删除。删除任务关闭 diff，不读取或展示密钥内容。

**结论**：本剧本覆盖的 cp01 旧残留已清理，未执行 `kubeadm reset/init/join`、安装 CNI 或启停服务。没有修改 Phase 00 基线和仓库外管理端密钥。可以开始 01.01 的新一轮复验；01 阶段尚未通过验收。

## 5. 2026-10-17 01.01 十节点只读基线重新复验

**执行入口**：复用 `ops/00-preparation/scripts/collect-node-readiness.sh` 与其 node-readiness 采集/汇总实现，读取当前台账和版本锁，不沿用旧批次矩阵。本次未加 `--with-cri-smoke`，没有创建容器或启停服务。

**实际命令**（仓库根目录）：

```bash
bash ops/00-preparation/scripts/collect-node-readiness.sh \
  ops/01-kubernetes/records/2026-10-17-restart/evidence/01.01-node-readiness \
  2>&1 | tee ops/01-kubernetes/records/2026-10-17-restart/evidence/01.01-node-readiness.txt
```

执行时启用了 `set -euo pipefail`，采集与汇总退出码为 0。十台节点均为 26/26；machine-id、BIOS UUID、MAC、SSH ED25519 指纹、主机名与 IPv4 六项身份唯一。

- [采集汇总输出](evidence/01.01-node-readiness.txt)
- [新一轮十节点矩阵与明细](evidence/01.01-node-readiness/matrix.md)

**结论**：本轮只读检查范围内基线符合台账与版本锁，SELinux Enforcing、firewalld running、RuntimeReady=true、kubelet disabled、无 CNI 配置。尚未安装 CNI，NetworkReady=false 是当前预期，不能代表 Pod 网络通过。

**下一步**：用户在 Mac 执行同一入口的 `--with-cri-smoke` 模式，输出到新的 `evidence/01.01-cri-smoke/`；该模式从 Harbor 拉取指定镜像，临时创建 host-network sandbox 和容器，验证日志并清理，成功时每台为 27/27。此项尚未执行，01.01 的镜像可取回与通信检查也未据此认定通过。

## 6. 2026-10-17 用户执行十节点 CRI 自测，重新核验通过

**执行方式**：用户在 Mac 运行 `collect-node-readiness.sh --with-cri-smoke` 并报告全部 PASS。助手读取本轮 [汇总输出](evidence/01.01-cri-smoke.txt)、[矩阵](evidence/01.01-cri-smoke/matrix.md)与每节点采集文件，核对实际结果。

**本轮结果**：十台节点均 27/27，六项身份唯一。CRI 自测均为 PASS：经 Harbor 拉取指定镜像，sandbox 使用 NODE 网络，容器退出码 0，日志包含 `phase00-cri-ok`，自测检查的近期 AVC 为 0，清理标志均为 yes。

**边界**：这次通过的是 host-network CRI 自测；尚无 CNI，不代表普通 Pod 网络或控制平面挂载的 SELinux 访问已通过。其他引导镜像与防火墙通信仍需本轮证据。

## 7. 2026-10-17 十节点 API 域名只读查询

**助手执行**：在现有 Ansible 目录使用 `ansible k8s_nodes -m ansible.builtin.command -a 'getent ahostsv4 api.k8s.internal.egon.top'` 查询节点系统名称解析，输出保存为 [01.01-api-dns.txt](evidence/01.01-api-dns.txt)，每节点返回值保存在 `evidence/01.01-api-dns/`。

**结果**：十台 rc=0，查询地址均为 `192.168.9.100`。command 模块默认报告 CHANGED，实际只查询名称解析，没有修改节点。

**工具提示**：本次使用的 `--tree` 输出选项在当前 ansible-core 中可用，但有弃用警告，计划在 2.23 移除；警告原文留在证据中，本次查询退出码为 0。未修改依赖或关闭警告。

**下一步（待用户执行）**：复用 `playbooks/harbor-bootstrap-images.yml`，将控制平面、Cilium 与 kube-vip 镜像复制到 Harbor、校验摘要，并让十台节点预拉 kubeadm 所需的引导镜像。暂未据旧批次结果将 01.01.05 标为通过，也未执行初始化。

## 8. 2026-10-17 用户完成 01.01.05 引导镜像准备

**用户执行**：在现有 Ansible 目录运行 `playbooks/harbor-bootstrap-images.yml`，输出保存为 [01.01-bootstrap-images.txt](evidence/01.01-bootstrap-images.txt)。用户报告摘要校验通过，所有主机 failed=0、unreachable=0；助手读取本轮证据，核对报告与实际输出一致。

**结果**：

- 八个引导/自测镜像的源与 Harbor 目标摘要一致；pause 与 CRI 自测镜像的 Digest 引用与版本锁一致。
- Cilium、operator-generic、cilium-envoy、kube-vip 四个镜像已复制到 Harbor，平台清单 Digest 与版本锁一致。
- 十台节点均完成 `kubeadm config images pull` 与镜像列表查询；PLAY RECAP 的 localhost 和十台节点均 failed=0、unreachable=0。

**结论**：本轮 01.01.05 的镜像准备通过。进入 01.02.01 的配置准备；本轮防火墙通信、控制平面文件挂载的 SELinux 访问，以及实际 API/CNI 能力仍需后续分别验证。尚未执行初始化。

## 9. 2026-10-17 01.02.01 开始：配置教学与默认模板

**用户要求**：每次提供命令时解释这一步做了什么，继续逐步指导，避免只粘贴命令。

**本次教学范围**：先从 cp01 当前安装的 kubeadm 打印默认 InitConfiguration、ClusterConfiguration 与 KubeletConfiguration，理解三种对象的职责，再根据台账逐段编写本轮实际初始化配置。暂不批量生成完整部署配置，也不执行 init。

**助手已核实**：通过现有 Ansible 连接在 cp01 运行 `kubeadm config print init-defaults --help`，rc=0；支持 `--component-configs KubeletConfiguration`。帮助明确指出模板的 Bootstrap Token 是固定占位值，不会生成真实入群令牌。[帮助输出](evidence/01.02.01-init-defaults-help.txt)。同时核对 [kubeadm config 官方说明](https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-config/#kubeadm-config-print-init-defaults)与 [v1beta4 配置 API](https://kubernetes.io/docs/reference/config-api/kubeadm-config.v1beta4/)。

**下一步（待用户执行）**：从管理 Mac 经 SSH 打印默认配置，并用 tee 保存到本批次 `evidence/01.02.01-kubeadm-defaults.yaml`。这份文件是学习与字段核对的参考输出，不代表实际初始化配置已经完成或部署校验通过；此时尚未取得该模板输出。

## 10. 2026-10-17 用户生成并查看默认模板

**用户执行**：完成默认模板打印与存档，确认看到三个 kind，并要求继续解释 cp01 的 `.101` 与 VIP `.100`、逐步填写配置和说明每条命令。

**助手核验**：[本轮默认模板](evidence/01.02.01-kubeadm-defaults.yaml)含 InitConfiguration、ClusterConfiguration、KubeletConfiguration。InitConfiguration 的默认 advertiseAddress 为 `1.2.3.4`、节点名为 `node`；ClusterConfiguration 的默认版本为 `1.36.0`、仓库为 `registry.k8s.io`、Service CIDR 为 `10.96.0.0/12`。这些是模板值；本轮实际输入仍以已复验的台账与版本锁为准。

## 11. 2026-10-17 地址与身份配置草稿的教学、字段校验

**本步设计**：复用 kubeadm 原生配置对象，先写首节点身份与集群入口，不引入额外模板层或角色。保持默认模板证据不变，实际草稿由用户写入 `ops/01-kubernetes/bootstrap/kubeadm/kubeadm-init-cp01.yaml`，后续逐步补齐。

**本步参数**：

- 本机 API advertiseAddress 和 kubelet node-ip 都为 `192.168.9.101`；节点名称为已核验的 `cp01.k8s.internal.egon.top`，CRI socket 与现有配置一致。
- 全局 controlPlaneEndpoint 为 `api.k8s.internal.egon.top:6443`（DNS 指向 VIP `.100`）；API Server 证书 SAN 显式包含该域名与 VIP。
- clusterName、Kubernetes `v1.36.5` 和 Harbor 引导镜像仓库取自当前台账、版本锁与本轮镜像准备结果。

**已执行的校验**：助手通过现有 Ansible command 模块将拟用的 YAML 作为标准输入交给 cp01 的 `kubeadm config validate --config /dev/stdin`。返回 rc=0、`ok`。没有在 cp01 写入实际初始化配置，没有 init 或创建控制平面对象。

- [被校验的地址草稿快照](evidence/01.02.01-address-draft-validated.yaml)
- [kubeadm 字段校验输出](evidence/01.02.01-address-draft-validate.txt)

**边界**：本步快照仅含两种 kubeadm 对象，是未完成草稿；网络、KubeletConfiguration、资源预留、审计/加密与 SELinux 访问方案待补。字段校验通过不代表主机前置、VIP、控制平面或网络运行通过。

**下一步（待用户执行）**：在 Mac 按 [操作手册的本轮第二步](../../README.md#010201-本轮第二步首节点地址与集群入口)创建目录并写入本步草稿。确认写入后继续填写 Pod/Service 网段与 DNS，再补齐其余配置。此时尚未取得用户实际写入该文件的证据。

## 12. 2026-10-17 用户完成地址草稿写入

**用户反馈**：已完成上一轮操作，继续下一步。助手读取实际 `bootstrap/kubeadm/kubeadm-init-cp01.yaml`，解析后两个配置对象及字段值与第 11 节校验快照一致；没有网络字段或 KubeletConfiguration，符合本轮逐步填写的进度。

## 13. 2026-10-17 Pod/Service 网络与集群 DNS 草稿校验

**本步输入**：当前台账的节点网 `192.168.9.0/24`、Pod 网 `10.244.0.0/16`、Service 网 `192.168.20.0/24` 和 DNS Service IP `192.168.20.10`。通过标准库 ipaddress 检查，三类网段互不重叠，DNS 地址位于 Service 网段中；仅覆盖这些已登记范围，不代表其他外部网络已验收。

**本步设计**：向当前 ClusterConfiguration 追加 networking 与 controllerManager 配置，再追加第三段 KubeletConfiguration。复用原生字段，不引入配置生成器或新依赖。

- Pod CIDR、Service CIDR、cluster.local 与台账一致。
- 按项目的 Cilium cluster-pool 方案，关闭 kube-controller-manager 的节点 CIDR 分配；后续 Cilium values 明确使用同一 Pod 范围与每节点 /24。助手读取本地锁定的 Cilium 1.20.2 Chart，确认该版本提供 cluster-pool 模式与对应配置字段；Chart 的默认池是 `10.0.0.0/8`，不能代替本项目明确规划的范围。
- kubelet 使用 systemd cgroup，与已复验的 containerd 一致；clusterDNS 为 `.20.10`，clusterDomain 与 kubeadm networking.dnsDomain 均为 cluster.local。没有修改节点自身使用的内部 DNS `.9.11`。

**助手已执行**：在内存中合并当前地址草稿与拟追加的网络内容，用 YAML 解析核对三个 kind、字段层级、地址范围及字符串类型；通过现有 Ansible 将合并内容作为 stdin 交给 cp01 的 `kubeadm config validate --config /dev/stdin`，返回 rc=0、`ok`。实际 `bootstrap/` 草稿保持不变，待用户逐步填写。

- [拟追加后被校验的快照](evidence/01.02.01-network-draft-validated.yaml)
- [kubeadm 校验输出](evidence/01.02.01-network-draft-validate.txt)

**边界**：上述校验不代表 kubelet、Pod 网络或 CoreDNS 已运行通过；未初始化、未安装 Cilium、未修改远程节点配置。资源预留、审计/加密与 SELinux 访问方案仍待补齐。

**下一步（待用户执行）**：按 [操作手册的本轮第三步](../../README.md#010201-本轮第三步podservice-网段与集群-dns)在 Mac 追加一次网络和 kubelet DNS 配置，再经 SSH 从 stdin 校验并保存 `evidence/01.02.01-network-user-validate.txt`。取得实际写入与校验结果后进入节点资源预算教学。

## 14. 2026-10-17 用户完成网络配置，改为一次补齐全部配置

用户报告校验返回 ok，要求保留每条命令的解释，但不再逐个字段分多轮操作。助手读取实际配置与 [用户校验输出](evidence/01.02.01-network-user-validate.txt)，确认三个配置对象与本轮网络草稿一致。

本轮改为一次交付完整配置、Ansible 准备与启动入口；保留原网段、版本、安全基线、用户已填写的字段和历史证据。真实 init、Cilium 安装和 join 仍由用户显式执行，不自动启动集群。

## 15. 2026-10-17 完整引导配置与 Ansible 入口

**实现与设计**：见 [完整配置与执行顺序](../../bootstrap/README.md)。复用 kubeadm 原生配置与 kubeletconfiguration patches、原 inventory、版本锁及 00 的 container_runtime 角色；没有新增依赖、框架或生成器。

- 补齐 kubeadm 审计与 Secret 加密挂载；审计只记 Metadata，不记录请求/响应正文。
- 在 resources.yaml 明确角色预算：一般节点总预留 1 CPU/2 GiB，storage 总预留 3 CPU/6 GiB（含 Ceph 的 2 CPU/4 GiB），另有驱逐余量与 Pod PID 限制。补丁从台账渲染；这是起步预算，不是负载与容量验收。
- 控制平面由 00 角色的显式专用任务设置有限路径的持久标签，并安装 kubelet ExecStartPre restorecon；不改变该角色的常规初始化流程。控制面保持 container_t，Cilium 保留锁定 Chart 的网络组件安全设置。
- kube-vip 分引导 super-admin.conf 与稳态 admin.conf 两份清单；初始化成功后切换。Cilium 明确 cluster-pool、VXLAN、kube-proxy 共存和 Harbor 平台 Digest；单节点 operator 用 1 个，扩展后恢复 2 个。
- 五个 playbook 覆盖 prepare、首节点 dry-run/显式 init、Cilium、逐台控制平面 join 和七节点 join；join 使用短时 token，配置用后删除并撤销 token。角色补丁通过原生 patches 应用，避免在 JoinConfiguration 中混入无效的 kubelet 配置文档。
- init 原始日志重定向到节点 root 私有文件，仅输出选定的阶段行；未沿用旧批次终端直通原始输出的脚本。

**秘密**：现有 `~/.cnpl-secrets/k8s-encryption.key` 格式检查通过并复用，没有重建；三个控制平面用同一来源渲染加密配置，模式 0600、no_log、关闭 diff。秘密没有写入仓库。

## 16. 2026-10-17 完整准备、预演与检查结果

**实际执行**：

1. 五个 playbook 的 `--syntax-check` 与 init 脚本 `bash -n` 通过。
2. 锁定 Cilium 1.20.2 Chart 的 Helm lint 通过；template 渲染出的 agent、operator-generic、envoy 三个镜像均为锁定的 Harbor 平台 Digest。[渲染结果](evidence/01.02-cilium-render.yaml)。
3. `prepare.yml` 实际完成十节点配置分发、角色补丁、三个控制平面的审计/加密文件、持久标签和 CRI 预拉；localhost 与十节点均 failed=0、unreachable=0，所有 kubelet 保持 inactive。[准备输出](evidence/01.02-prepare-complete.txt)。
4. 三台控制平面用合成文件执行 container_t 读配置目录、写 etcd 目录的探针，全部通过，探针文件已清理。另在 cp01 查询 net_admin 策略允许关系：[查询记录](evidence/01.02-selinux-capability-query.txt)。这些不替代真实容器与 VIP 验收。
5. 完整 `init-cp01.yml` 默认 dry-run 实际通过，cp01 failed=0，输出明确显示角色补丁应用；未启动 kubelet或执行真实 init。[预演输出](evidence/01.02-complete-dry-run.txt)。
6. 从节点取回 dry-run 生成的 [实际 kubelet 配置](evidence/01.02-kubelet-effective-dry-run.yaml)与四类角色补丁，逐项确认 systemReserved、kubeReserved、evictionHard、podPidsLimit、clusterDNS 与台账一致。仅取回不含密钥的配置。
7. 控制平面、infra、storage、worker 四种 JoinConfiguration 用固定占位凭据在当前 kubeadm 校验，全部通过。[校验输出](evidence/01.02-join-template-validation.txt)。首次测试发现纯数字占位 certificateKey 被 YAML 当作数值，模板已加引号并重新校验通过，没有执行 join。
8. 复用既有 `verify-firewall.yml`，十节点 TCP 允许与拒绝用例通过，changed=0、failed=0，临时监听已清理。[防火墙输出](evidence/01.02-firewall-verify.txt)。该入口不验证 VXLAN UDP，数据面在 Cilium 就绪后测试。
9. 管理端密钥检查逻辑改为可读的 Python stdin 代码后，使用 `--tags controller_prepare` 实测通过，changed=0。[管理端复核](evidence/01.02-controller-prepare-check.txt)。最初用 `--limit localhost` 因隐式 localhost 不在 inventory 中被 Ansible 拒绝，改用标签入口后解决；未改变 inventory。

**当前现场**：完整输入已在节点就位，cp01 有引导 kube-vip 清单和私有 dry-run 临时文件，但 kubelet 未启动；没有可用控制平面、真实 etcd、Cilium 或入群节点。未执行 `init_apply=true`，未运行任何 join。

**下一步**：用户按完整手册从显式真实 init 开始，接着安装 Cilium、加入 cp02/cp03，再加入七个工作节点。10 Ready、实际 Allocatable、普通 Pod 网络、DNS、API 高可用和阶段其他用例仍以真实运行结果验收。

## 17. 2026-10-17 审计日志写权限补测、更正与最终准备

**发现**：在三个控制平面用 container_t 创建合成审计文件时均 Permission denied。此前的 config/etcd 探针没有覆盖审计目录；当前策略不允许该域在 container_log_t 目录创建文件。[首次失败输出](evidence/01.02-audit-label-probe.txt)。

**修正**：将 `/var/log/kubernetes/audit(/.*)?` 的持久类型改为 container_file_t；kubelet ExecStartPre 同时恢复审计目录标签。原探针扩展为 config 读取、etcd 写入、审计文件创建/写入三部分，所有合成文件结束时清理。没有改变 SELinux Enforcing 模式，也没有把控制面容器切为 spc_t。

**实际重测**：重新运行完整 prepare.yml，三台控制平面的扩展探针通过，十节点与 localhost 均 failed=0、unreachable=0；再次确认所有 kubelet inactive。[最终准备输出](evidence/01.02-prepare-final.txt)。角色补丁在本次重跑均未变化；节点已同步最新配置与脚本。

**补充核对**：

- [kubelet 状态查询](evidence/01.02-kubelet-stopped.txt)显示十台均 inactive（在最后一次准备前采集，最终 prepare 的末尾再次逐台确认）。command 默认显示 CHANGED，查询本身没有启停服务。
- kube-vip 锁定镜像的 OCI 配置读取结果为 User 未指定、Entrypoint `/kube-vip`、Cmd 未指定，与本清单的 `args: [manager]`、root 私有 kubeconfig 访问方式一致；仅查询镜像元数据，没有启动容器。
- Join 模板首次类型错误的 [失败摘要](evidence/01.02-join-template-first-failure.txt)单独保留，修正后的四角色结果仍保存在原校验成功记录。

**最终边界**：输入与节点准备完成、dry-run 通过、真实 init 未执行。完整执行手册已经说明每条命令的作用与成功条件；用户可以按顺序连续执行，某条失败时保留现场，不继续后续部署步骤。

## 18. 2026-10-17 用户真实 init 后 VIP 检查失败，原地恢复

**用户执行与失败**：用户运行 `init_apply=true`，kubeadm 已完成配置上传、节点标记、CoreDNS/kube-proxy 创建并返回成功；脚本在后置 VIP/API 检查超时。保留 [原始执行输出](evidence/01.02-init-cp01-apply.txt)与 [用户附件](evidence/01.02-cp01-init-failure-user.txt)，没有覆盖失败证据。

**现场核验**：[首轮诊断](evidence/01.02-cp01-first-failure-diagnosis.txt)显示 `.101` 本机 API 的 readyz 全部通过，etcd 正常、kubelet/containerd/firewalld active；VIP `.100` 未绑定，访问返回 no route to host。[kube-vip 日志与租约诊断](evidence/01.02-cp01-vip-logs-and-lease.txt)明确显示它请求 `https://kubernetes:6443/.../plndr-cp-lock`，却向外部 DNS `.11` 查询 kubernetes 并得到 no such host；近期未见相关 AVC。

**根因**：本轮手写的 kube-vip 清单遗漏了 [官方示例](https://kube-vip.io/docs/installation/static/#example-arp-manifest)中的 `hostAliases: kubernetes → 127.0.0.1`，控制面客户端无法通过该本机别名访问 API、完成租约选举和挂载 VIP。属于交付清单的遗漏，不是用户命令错误；此前 dry-run、合成文件探针不能覆盖这个真实运行路径。

**批量修复**：

- 两份 kube-vip 清单补齐本机别名；对照锁定 v1.2.4 源码，将无效的 vip_cidr 更正为 vip_subnet（值仍为 32），不升级镜像或依赖。
- 初始化入口增加显式 `--resume` / Ansible `init_resume=true`：先核验初始化产物与本机 API，只修复 VIP，不再次 init/reset、不重建 CA 或 etcd。
- Ansible 自动同步最新脚本与清单，已初始化节点无需重新 prepare。任务名称明确区分 dry-run、真实 init 和 VIP 恢复。
- 成功条件覆盖新 Pod 的 hostAliases、稳态凭据挂载与 Ready、VIP 地址绑定和 API 连续检查；失败显示本机 API、VIP API、地址与脱敏容器日志。

**回归**：新增离线测试，覆盖两份清单必需字段、恢复不重初始化、原 CA/数据保留、本机 API 不健康时拒绝修改、已有集群拒绝 apply、旧 Pod 不能靠暂时可访问的 VIP 误判成功，以及凭据脱敏。六项测试通过：[结果](evidence/01.02-vip-recovery-unit-tests-final.txt)。这些测试只使用临时目录与伪命令，没有连接节点或启动服务。

**实际修复**：助手执行 `init-cp01.yml -e init_resume=true`，原地更新 kube-vip 后通过，cp01 failed=0、unreachable=0，并补记计划宿主机标签。[恢复输出](evidence/01.02-cp01-vip-resume.txt)。没有执行 kubeadm init/reset，也没有启动 Cilium 或其他节点。

**修复后证明**：[修复前](evidence/01.02-cp01-before-vip-repair.txt)与 [修复后](evidence/01.02-cp01-after-vip-repair.txt)的 CA SHA256、kube-system namespace UID 一致；本机和 VIP readyz 均为 ok，ens33 上出现 `.100/32`，租约持有者为 cp01。现有集群身份被保留。

管理 Mac 另用临时保存的集群公开 CA 校验证书，经真实 API 域名访问 VIP 的 readyz 返回 HTTP 200，没有跳过 TLS 校验或改写 DNS：[管理端验证](evidence/01.02-management-vip-check.txt)。仅临时读取公开 ca.crt，没有导出私钥或启动其他组件。

**当前边界**：cp01 真实控制平面与 VIP 入口已恢复。节点 NotReady、CoreDNS Pending 是尚未安装 CNI 的当前状态；Cilium、多控制平面、其他节点及 HA 尚未执行或验收。接下来由用户继续 install-cilium.yml，不重跑首次 init。

## 19. 2026-10-17 用户安装 Cilium 后，控制平面入群在摘要任务失败

**用户执行**：[Cilium 安装输出](evidence/01.02-install-cilium.txt)显示 cp01/localhost 均 failed=0；其后 [控制平面入群失败](evidence/01.02-join-control-plane.txt)发生在 cp02 委派至 cp01 的 OpenSSL 管道，rc=127。日志显示当时尚未上传证书、渲染 JoinConfiguration 或运行 kubeadm join；always 已撤销刚创建的令牌。cp03 尚未开始。这是交付脚本的未核验依赖遗漏，不是用户命令错误。

**额外现场问题**：只读检查发现 cp01 Ready、Cilium agent/operator 正常、etcd 健康，但两个 CoreDNS 均 0/1，日志持续 `Plugins not ready: "kubernetes"`。进入一个现有 CoreDNS 容器的网络命名空间，用宿主机 Python 标准库发起 TCP 客户端连接：Service `192.168.20.1:443` 超时，`.101/.100:6443` 均 No route to host。该检查不创建 Pod 或启动后台服务。firewalld 规则仅允许节点与管理端来源，遗漏 Pod CIDR。

**原地修复**：仅增加 Pod CIDR `10.244.0.0/16` 到控制平面 `6443/tcp` 的 rich rule，cp01 上三个 TCP 路径随即全部通过，CoreDNS 两副本变为 1/1。再运行 [专用规则剧本](evidence/01.02-pod-api-firewall-fix.txt)，将相同即时/持久规则落实三个控制平面。没有 reload 防火墙，没有将整个 Pod 网段加入 trusted，没有开放其他端口或关闭 SELinux/firewalld。

## 20. 2026-10-17 入群与后续入口统一修复、验证

**代码范围与设计**：复用原 Ansible 编排和 kubeadm 原生入口，没有引入新的框架、依赖或设计模式。覆盖控制平面入群、七节点入群、后续 Cilium 扩展和相关准备配置。

- 去掉 OpenSSL/awk 管道。先 `kubeadm token generate` 得到已知随机值，再 `token create --ttl 30m --print-join-command`；严格核验原生输出的入口、令牌和 CA 公钥摘要，只使用字段渲染配置，不执行其输出字符串。输出异常也能按已知 ID 清理。
- 两个 join playbook 均先对整批目标做只读前检，全部通过才开始逐台 join：依赖、版本、主机身份、CRI、安全基线、API DNS/TCP、资源补丁、共享加密配置和节点登记匹配。控制平面额外检查文件标签、启动前 restorecon 与 Pod/API 防火墙规则。
- 不再只凭 kubelet.conf 存在跳过；发现部分产物或本机/API 记录不一致就停止并保留现场。完整已入群节点只做核验、标签及稳态 kube-vip 协调，不重新 join。
- 证书上传显式使用 cp01 的既有初始化配置；按 64 位十六进制格式提取密钥。实际 JoinConfiguration 校验放到启用 kubelet 前；成功后检查本机 API 可访问、VIP Pod 的别名/凭据与 Ready、节点 Ready 和 etcd 全成员健康。
- 每次 join 私有日志使用独立 0600 文件，失败显示阶段与路径；临时配置和令牌清理独立尝试，令牌删除支持不存在。秘密仍 no_log、配置关闭 diff；连接中断时即时清理不能保证，另有 30 分钟 TTL。
- prepare/Cilium 共用有限的 Pod/API 放行任务；Cilium 入口增加管理端客户端版本、Chart 摘要与 CoreDNS 就绪检查。安装/扩容仍由用户执行，修复过程没有重复 Helm upgrade。

**已实际完成的验证**：

1. [原生命令与四角色校验](evidence/01.02-native-join-command-validation.txt)：在 cp01 实际创建一个测试令牌，确认原生输出格式及 CA pin；control_plane/infra/storage/worker 四种模板均由现有 kubeadm 返回 ok；finally 已撤销该测试令牌。没有执行 join。占位证书分发密钥的校验仅验证字段格式，不等同于真实证书下载。
2. [控制平面入口前检](evidence/01.02-control-plane-preflight-verified.txt)与 [七节点入口前检](evidence/01.02-workers-preflight-verified.txt)：使用各自完整 playbook 的 `--tags join_preflight`，cp01 和全部九台目标均 changed=0、failed=0、unreachable=0。确认导入剧本的实际变量/路径与分组均能运行。
3. [Cilium 管理端前检](evidence/01.02-cilium-preflight-verified.txt)：客户端可执行且版本符合锁、Chart SHA256 符合锁、受控目录权限正确，changed=0、failed=0；没有执行安装段。
4. [13 项离线回归](evidence/01.02-join-regression-verified.txt)通过：包含既有六项 VIP 恢复测试及七项新增入群/状态测试，实际运行 Ansible 配合临时目录和伪 kubeadm，覆盖原生输出异常、配置错误、join 失败、秘密清理、日志权限、完整已入群重跑与部分现场拒绝。前两次测试夹具分别遗漏模拟 cp01 的 FQDN、模拟路径映射不一致，修正后通过；失败记录保留为 `01.02-join-regression-first.txt` 和 `01.02-join-regression-harness-timeout.txt`，不是节点部署输出。
5. 全部八个 Phase 01 playbook syntax-check、脚本语法与 YAML 解析检查通过，见 [静态验证](evidence/01.02-join-static-validation.txt)。

**当前现场与身份保留**：[修复后检查](evidence/01.02-after-join-script-repair.txt)显示仍只有 cp01 Ready；CoreDNS 两副本 1/1，Pod 内访问 Service/本机/VIP API TCP 全通过，SELinux Enforcing、firewalld active。CA SHA256 仍为 `e9e54d377522819602d3e1dcba9994d3337c8c336ed181984ea0956339ec80af`，kube-system UID 仍为 `4d3e52d7-e203-4daf-aced-9c3a666fcf5b`，与第 18 节修复前后一致。cp02/cp03 及七个目标仍未入群、kubelet inactive。

**边界与下一步**：没有执行真实 join、reset 或再次 init，没有启动新的节点/服务。只读前检、格式校验和离线编排回归不等于真实多节点运行验收；跨节点 VXLAN、DNS 查询、故障切换与 HA 仍待后续实际验证。用户按 [完整手册](../../bootstrap/README.md)使用带时间戳的新 retry 日志重跑控制平面入群；全部通过后再运行七节点入口。

## 21. 2026-10-17 用户完成全部入群，准备基础集群验收

**用户执行**：[cp02/cp03 入群](evidence/01.02-join-control-plane-retry-20261017-123053.txt)和 [七节点入群](evidence/01.02-join-workers-20261017-123816.txt)均 failed=0、unreachable=0；后者末尾 Cilium、CoreDNS 与节点等待也通过。助手读取日志并作独立只读复核。

**当前实测**：

- [集群只读健康记录](evidence/01.02-cluster-baseline-readonly.txt)：10 个 Ready、对应角色/污点和地址正确；cilium、envoy、kube-proxy 各 10/10，operator、CoreDNS 各 2/2，系统 Pod 就绪。统一 API 域名及 `.101/.102/.103` 的 TLS readyz 均通过。etcd 三成员健康、单 leader、无 learner、ERRORS 为空；VIP 租约持有者为 cp01。
- [十节点在用配置验收](evidence/01.02-ten-node-effective-config.txt)：新增只读 verify-hosts.yml，检查真实 `/var/lib/kubelet/config.yaml` 的角色预留、驱逐、DNS、cgroup 与 PID 配置，十台全部与台账一致；SELinux Enforcing、firewalld/containerd/kubelet active，CRI RuntimeReady 和 NetworkReady 都为 true。十台 changed=0、failed=0、unreachable=0。
- Cilium status 显示锁定 Chart 1.20.2、agent/Envoy 10/10、operator 2/2；从已有 agent 查询 cilium-health 显示 10/10 reachable。专用健康端点结果不能代替普通 Pod 的应用网络验收。
- 实际 Allocatable CPU 为 cp 3、infra 5、storage 5、worker 7 核；内存是内核 Capacity 扣除角色预留与 500Mi 驱逐余量，不能直接拿 VM 标称内存减预留作精确值。

**交付与设计**：[完整教学命令](../../bootstrap/acceptance/README.md)、[临时清单](../../bootstrap/acceptance/network-smoke.yaml)、[检查脚本](../../bootstrap/acceptance/check-network.py)。复用原生 Namespace/DaemonSet/ClusterIP Service 和现有诊断镜像，不引入新依赖或框架。仅针对固定十节点验收，直接编排比新增策略或处理器抽象更清楚。

临时 Pod 使用原锁定的 Harbor BusyBox Digest；助手检查了本地镜像层的 httpd/wget/nslookup/sh applet 路径。每节点一个非 root、只读根文件系统的普通 Pod，禁用 ServiceAccount 凭据，不使用 hostNetwork/hostPath；www 使用 emptyDir，资源限制明确，Namespace 使用 restricted Pod Security。仅诊断 Pod 容忍 cp/storage 污点，不改变节点保护。

检查脚本从十个源 Pod 各访问十个 Pod IP，核验 HTTP 返回节点身份，共 100 条路径（90 条跨节点）；各源另有四种 DNS 检查与 ClusterIP/Service 域名两次 HTTP。预期地址明确，HTTP/DNS 命令失败或结果错误均返回非零并显示失败目标，保留临时资源供诊断；完整通过后由用户单独清理。

**交付验证**：[静态验证](evidence/01.02-network-acceptance-static.txt)包含版本锁镜像比对、YAML/Python/本地链接、整清单 client dry-run，以及在已存在 default Namespace 对相同 DaemonSet/Service spec 的 server dry-run。服务器校验没有创建对象，也未创建实际验收 Namespace。verify-hosts 的 syntax-check、从根目录使用指定 ansible.cfg 的十节点 inventory 列表核对通过；只读任务已实际通过。

[五项离线回归](evidence/01.02-network-acceptance-offline-tests-final.txt)覆盖十节点/地址/Ready/普通网络检查、HTTP 后端错误、DNS 命令失败、DNS 返回错误地址和完整探测成功；仅临时文件与伪客户端，没有连接节点或启动容器。错误输出补充目标信息后重跑，五项仍通过。

**边界与下一步**：普通 Pod 验收清单尚未部署，网络矩阵、Service/DNS 真实测试和清理尚未运行；助手未自动启动测试负载或执行故障实验。用户按完整命令一次完成基础验收后反馈证据目录与最终 PASS。单控制平面停机切换在备份确认之后执行，受限身份、完整恢复材料及其余阶段用例保持未执行；[阶段验收记录](acceptance.md)不将十节点 Ready 等同于 Phase 01 完成。

## 22. 2026-10-17 用户基础验收全部通过，准备受限与恢复身份

**实际基础验收**：用户提供 `evidence/01.02-acceptance-20261017-125334/`。助手读取该目录：最终 [网络矩阵](evidence/01.02-acceptance-20261017-125334/14-network-matrix.txt)明确显示 10 个源、100 条 Pod HTTP 路径（90 跨节点）、40 DNS、20 Service HTTP 全部 PASS；[清理](evidence/01.02-acceptance-20261017-125334/17-network-cleanup.txt)已删除 Namespace/DaemonSet/Service，[Namespace 查询](evidence/01.02-acceptance-20261017-125334/18-cleanup-confirm.txt)为空。逐项更新 [acceptance.md](acceptance.md)，基础验收通过，仍不等同于完整 Phase 01 或 HA/备份恢复通过。

**身份设计与交付**：[完整命令和解释](../../bootstrap/access/README.md)、[白名单 RBAC](../../bootstrap/access/rbac.yaml)、[配置入口](../../ansible/playbooks/configure-access.yml)。复用 kubeadm、Ansible、现有 Python YAML/cryptography 50.0.2 和已锁定的 restic，不安装新依赖。使用直接编排与原生 Role/Binding，不新增策略/处理器等抽象。

- Mac 的 reader/operator 和规划中 .15 管理机的 reader/operator 各有独立 CN/密钥；普通身份 90 天，无管理员组，按具体 CN 授权，便于分别撤权。只读白名单不含 Secret/RBAC/节点 proxy；运维仅在 lab-core 获得工作负载、Service、ConfigMap 等权限。实验 Namespace 使用 restricted PSA。
- 恢复身份单独签发一年证书，唯一使用 system:masters；它绕过授权层，不混入正常 Context。单独文件提供 cp01/.101、cp02/.102、cp03/.103 与 VIP 四 Context，保持 TLS，不依赖故障集群内身份服务。没有复制 CA 私钥，保留原 admin.conf/super-admin.conf。
- 由 cp01 原生 `kubeadm kubeconfig user` 签发并通过原 SSH 取回；现有材料复用，不静默轮换。组合前核验 CA、签名、密钥匹配、CN/O、客户端用途和有效期。私有材料仅放仓库外 0700 目录、0600 文件；生成不含私钥的到期/指纹清单。正式材料尚未生成。
- 真实验收入口使用独立证书的 whoami/can-i/实际允许与 Forbidden 请求，不使用 `--as` 冒充来替代认证验收；只创建/清理临时 ConfigMap，不启动容器。修正了 kubectl 对节点等集群资源输出正常 scope Warning 的处理，认证/网络错误仍判失败。
- 终端激活脚本替换旧引导管理员 k 函数并设置当前终端 KUBECONFIG，默认只读；不覆盖原 ~/.kube/config 或 shell 启动文件。新终端需重新 source。
- 身份恢复包复用 .16 的现有加密 restic 仓库；备份入口只新增该目录快照，不 forget/prune。按本次明确快照 ID 取回 recovery.conf，逐字节比对并验证其 API 身份，随后清理临时还原目录。这不是完整 etcd/PKI/Secret 加密密钥备份，也不冒充已复制到断网介质。

**已验证**：现有 cp01 的 `kubeadm kubeconfig user --help` 支持所用参数；Mac Ansible Python 的 YAML/cryptography 能力、restic/恢复参数和本地物料路径已检查。白名单 RBAC 的 [server dry-run](evidence/01.02-access-static-validation.txt)通过（Role/RoleBinding 在已有 default Namespace 仅作同 schema 校验，没有实际授权）；Python/YAML/Bash、Ansible syntax-check 通过。

[五项离线回归](evidence/01.02-access-offline-tests-final.txt)使用独立合成 CA/证书、伪 kubectl 和真实临时本地 restic 仓库，覆盖普通证书误带管理员组、私钥不匹配、客户端/恢复 Context 分离、权限白名单、600 权限、到期清单脱敏、scope Warning/真实 Forbidden 区分，以及准确快照的加密备份/恢复路径和清理。没有连接真实 restic 仓库，也没有签发真实 CA 的新客户端证书或应用 RBAC。

**未执行边界**：正式签发、真实授权/权限验收、终端身份切换、.16 新备份/取回仍由用户按本节手册一次执行。规划的 .15 管理机不在当前已交付 inventory，独立包可生成，实际分发/登录保持待办；不把 build01 或控制平面冒充管理机。身份的证书不可单独吊销，恢复组也不能靠移除 Binding 撤权，须独立保管并显式处理到期/泄漏。完整控制平面备份和单控制平面故障实验仍未开始。

## 23. 2026-10-17 身份组合期限误判修复

**实际失败**：[用户执行输出](evidence/01.02-access-20261017-131508/01-configure-access.txt)显示 cp01 已完成五份签发并取回，随后本地 build-access.py 返回非零，被 no_log 完全隐藏。RBAC 安装尚未执行。根因属于交付脚本，不能靠重新签证或关闭安全检查解决。

**只读诊断**：助手读取现有材料，只输出公开证书元数据。五份签名/身份/私钥匹配检查均通过，旧期限逻辑均拒绝。首份普通证书 NotBefore 为 `2026-10-17T15:29:54Z`，NotAfter 为 `2027-01-15T17:15:20Z`；约 17:15 签发，但 NotBefore 沿用建集群 CA 的起点，导致 `NotAfter - NotBefore` 比 90 天多约 1 小时 45 分钟。恢复证书同理。

对照锁定 [v1.36.5 pki_helpers.go](https://github.com/kubernetes/kubernetes/blob/v1.36.5/cmd/kubeadm/app/util/pkiutil/pki_helpers.go#L565)，NewSignedCert 未单独设置起点时使用 caCert.NotBefore；[kubeconfig 实现](https://github.com/kubernetes/kubernetes/blob/v1.36.5/cmd/kubeadm/app/phases/kubeconfig/kubeconfig.go#L191)为用户配置 NotAfter 而不覆盖 NotBefore。此前合成证书测试只回溯五分钟，未覆盖这个真实行为，静态/dry-run 不会检测此语义错误。

**修正**：

- 期限上限改为 NotAfter 相对当前时间的剩余期限，不再减 CA 起点；原 90 天/一年策略及十分钟容差保留。签名、私钥匹配、CN/O、客户端用途、当前有效和至少七天余量仍严格检查。
- 增加 --check-only，只读核验全部已有输入，不创建文件或修改权限。
- 增加只承载安全说明的校验异常；格式/解析/签名等底层异常只输出固定原因和异常类型，不输出原始配置内容。Ansible 保持私有命令 no_log，但单独的 assert 会显示安全 JSON 原因，不再只显示 censored。
- 增加 access_assemble 标签，只运行本机组合、摘要检查和 RBAC 安装，不连接 cp01，不重复签发/取回。

**实际验证**：

1. 对用户现有五份证书执行 [只读检查](evidence/01.02-access-existing-materials-check.txt)，全部通过。
2. 将同五份材料放入私有临时目录，完整组合客户端配置、到期清单、恢复配置与归档，通过后删除临时目录；原输入 SHA256、权限、mtime 均未改变。[执行结果摘要](evidence/01.02-access-existing-materials-assembly.txt)。没有修改真实客户端输出目录或签发新证书，也没有应用 RBAC。
3. [八项离线回归](evidence/01.02-access-repair-offline-tests-verified.txt)全部通过：新增沿用三十天前 CA 起点的普通/恢复证书、超长剩余期限、未来/临近过期证书、check-only 不变更输入、解析异常不泄密，以及真实 localhost Ansible callback 显示安全错误的回归；原证书隔离、RBAC 白名单、真实临时本地 restic 备份/恢复仍通过。
4. configure-access.yml syntax-check 通过；--tags access_assemble 的任务列表确认前两 play 无执行任务，仅保留本机后半段。

**验证环境记录**：当前工具沙箱禁止默认 Ansible 临时目录和本地 RPC 套接字。语法检查改用临时 ANSIBLE_LOCAL_TEMP；本地 restic 测试把缓存明确放入测试临时目录。中间的环境失败保留为 `01.02-access-repair-offline-tests.txt` 和 `01.02-access-repair-offline-tests-final.txt`。随后针对八项离线回归通过自动审批运行，全部通过；未放开真实节点或集群操作，也未修改用户 Ansible 全局配置。

**下一步**：用户使用新时间戳日志和 --tags access_assemble 重跑本机后半段；成功后继续原手册的第 3 步权限验收。现有证书复用；正式权限/恢复包备份验收仍不能提前标为通过。

## 24. 2026-10-17 身份与恢复文件备份验收通过，形成阶段检查点

用户反馈六组命令全部完成。助手核对 [本地组合重跑](evidence/01.02-access-assemble-retry-20261017-132138.txt)：localhost failed=0、unreachable=0；[真实权限验收](evidence/01.02-access-20261017-131508/02-access-verification.txt)的四个独立受限身份、恢复身份和四 API Context 全部 PASS，临时 ConfigMap 清理。

[直连恢复入口](evidence/01.02-access-20261017-131508/04-recovery-direct-api.txt)返回十节点 Ready；[到期清单](evidence/01.02-access-20261017-131508/03-certificate-expiry.json)只含公开主体、组、UTC 到期时间及指纹，没有私钥。[加密备份/取回](evidence/01.02-access-20261017-131508/05-access-backup-restore.txt)确认快照 `b73df77006f44a2e2e635b9cac162431ee6cf0f865748c28dd625ed6adcc46f8` 已写入 .16，恢复文件逐字节校验与真实 API 身份验证通过。

助手另只读查询 Mac 的受限配置：当前 Context 为 lab-primary-readonly，API whoami 为 cnpl-mac-reader / system:authenticated。没有因整理文档启动工作负载或执行故障注入。

本次检查点提交范围为 01.01–01.02 的配置、Ansible、测试、脱敏证据及其必要 SELinux/资源预算支持，保留历史失败与修复；不纳入其他来源的未跟踪 fetch-k8s-clients.sh，不提交私钥、真实 kubeconfig、快照或备份归档。此前规范示例中的 token 是 kubeadm 固定占位值，测试代码中的 token 是合成夹具；未发现实际嵌入客户端私钥。

下一步允许进入 01.03，实际执行顺序为完整备份与取回验证在前、单控制平面故障实验在后。规划的 .15 管理机分发/登录、完整控制平面恢复材料、HA 与其余核心资源实验仍保留未完成，不能把身份文件恢复当作 etcd/PKI 全量恢复验收。

提交前检查：[26 项离线回归](evidence/01.02-checkpoint-regression.txt)全部通过，[十个 playbook 语法和本地链接检查](evidence/01.02-checkpoint-static.txt)通过；另检查待提交范围的私钥 PEM、长 client-key-data 与 token 候选，没有实际客户端私钥或真实 token。固定示例/合成测试 token 保留其教学意义。
