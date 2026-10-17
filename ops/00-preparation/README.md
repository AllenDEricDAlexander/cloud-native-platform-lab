# Phase 00 操作流程：基础设施与服务器初始化

完成后交付：集群外基础服务（DNS、CA、OpenWrt 显式代理、Harbor、GitLab、Nexus、备份）可用；十台 Rocky Linux 10 节点完成 Linux 基线、containerd/CRI 与入群工具，能直接进入 01 的 kubeadm init/join。

本页是**可以照着执行的流程**，按依赖顺序排列，从零重建也按这个顺序。每一步写明前提、命令、预期结果、证据位置和失败时怎么办。要做什么、验收标准是什么，见 [阶段计划](../../plan/00-preparation.md)；实际执行过程与结果见 [执行记录](records/2026-10-14/README.md)（文中「第 N 节」指 [assets.md](records/2026-10-14/assets.md) 的小节）。参数来自 [台账](../inventory/README.md)，版本来自 [版本锁](../versions.lock.yaml)。

> 实际建设顺序与本页不同：先做了模板和十台节点，再补基础服务，所以执行记录中节点的部分步骤（例如先导入种子镜像，Harbor 就绪后再切换）比这里多一轮。

## 0. 开始之前

### 0.1 约定

- 所有命令在**管理 Mac** 上执行；需要登录到虚拟机控制台的步骤会单独写明。
- Ansible 命令在 `ops/00-preparation/ansible/` 下运行，使用 `~/.venvs/cnpl-ansible/bin/ansible-playbook`；`ansible.cfg` 指定了 inventory、本目录的 collections 与 SSH 设置。
- 证据：输出用 `tee` 写入 `records/<批次>/evidence/<步骤号>-<名称>.txt`。本页命令中的批次目录是 `2026-10-14`，开新批次时替换。
- 剧本都是幂等的：中途失败，修复后从头重跑即可。
- 提交前检查证据：没有 `BEGIN ... PRIVATE KEY`，不含口令、会话 cookie（如 Harbor 的 `sid=`）与订阅信息；在分支上提交后快进合并到 main。

### 0.2 安全规则（不可绕过）

- SELinux 保持 Enforcing，firewalld 保持启用，规则按来源限定（2026-10-14 用户明确要求）。遇到拒绝先取证（`ausearch -m AVC -ts recent`），按策略处理，不切换到 permissive，也不停防火墙。
- 私钥与口令只放在 Mac 的 `~/cnpl-pki`、`~/.cnpl-secrets/`；订阅地址只放在 OpenWrt。涉及私钥的任务已设 `diff: false` 或 `no_log`，运行时仍不要加 `--diff`。
- 不对「未挂载的盘」自动格式化：数据盘按台账容量唯一匹配，匹配不到就停止。storage 节点的 OSD 候选盘在 00 不分区、不格式化。
- 不使用 `curl -k`、`skip_verify` 或关闭签名校验来通过验收。

### 0.3 流程总览

| 步骤 | 内容 | 计划步骤 | 依赖 |
| --- | --- | --- | --- |
| 1 | 管理端 | 00.10.01 | — |
| 2 | 种子物料 | 00.02.03 | 1 |
| 3 | 模板 rocky10-base | 00.04.03 | 2 |
| 4 | 克隆与身份 | 00.04.04、00.04.05 | 3 |
| 5 | 内部 DNS | 00.07.01、00.07.02 | 4 |
| 6 | 内部 CA 与证书 | 00.08.01、00.08.02 | 1 |
| 7 | OpenWrt 与显式代理 | 00.05、00.06.02 | 5 |
| 8 | Harbor | 00.09.02 | 4、5、6 |
| 9 | 十台节点基线 | 00.10.02 | 5、6、8 |
| 10 | 引导镜像 | 00.09.03 | 8、9 |
| 11 | 节点检查矩阵与 CRI 自测 | 00.10.02 | 10 |
| 12 | GitLab | 00.09.01 | 5、6、7 |
| 13 | Nexus 与代理仓库 | 00.09.04 | 5、6、7 |
| 14 | 备份与恢复 | 00.10.03 | 5–13 |
| 15 | 重启复验与幂等 | 00.10.02 | 9–12 |
| 16 | 断网验收 | 00.10.04 | 全部（待编写） |
| 17 | 阶段交接 | 00.10.05 | 全部 |

## 步骤 1：管理端

**前提**：Mac 有 Homebrew Python 3.12 以上（系统自带的 3.9 不满足 ansible-core 要求）、ruby（系统自带）、crane（`brew install crane`）。

```bash
python3 -m venv ~/.venvs/cnpl-ansible
```
```bash
cd ~/SelfProject/cloud-native-platform-lab/ops/00-preparation/ansible && ~/.venvs/cnpl-ansible/bin/pip install -r requirements.txt && ~/.venvs/cnpl-ansible/bin/ansible-galaxy collection install -r requirements.yml -p collections
```
```bash
ssh-keygen -t ed25519 -f ~/.ssh/cnpl_lab_ed25519
```

**预期**：`~/.venvs/cnpl-ansible/bin/ansible --version` 显示 core 2.21.5，config file 为本目录的 ansible.cfg；`ansible-galaxy collection list -p collections` 含 ansible.posix 2.2.2。证据：`00.10.01-ansible-control-node.txt`（第 56–57 节）。

## 步骤 2：种子物料

节点在建设初期无法稳定访问外部软件源与 registry.k8s.io（第 33–34、51 节），物料先在 Mac 上下载、校验，再传到目标机。种子目录为 `~/Downloads/cloud-native-lab-seed-2026-10-14/`，每个文件的来源、SHA256 与签名指纹登记在版本锁中：

| 物料 | 用于 | 版本锁条目 |
| --- | --- | --- |
| containerd.io、cri-tools、kubeadm、kubelet、kubectl、kubernetes-cni 的 RPM 与签名公钥 | 模板 | containerd、cri_tools、kubeadm 等 |
| pause、busybox 的 linux/amd64 归档（`crane pull --platform linux/amd64`） | 模板的 CRI 自测 | pause、cri_smoke_image |
| Docker CE 与 iptables 依赖 RPM、docker.gpg | Harbor 主机 | registry_runtime |
| Harbor 离线安装包 | Harbor 主机 | harbor |
| OpenWrt 镜像、mihomo | OpenWrt | openwrt、proxy_core |

新增物料时：从官方来源下载，按官方校验文件或签名核对，把 URL、SHA256、指纹写入版本锁后再使用。Mac 为 arm64，镜像必须指定 `linux/amd64`，否则容器启动时报 `exec format error`。

## 步骤 3：模板 rocky10-base

**前提**：Rocky 10.2 ISO 已校验；esxi01 上创建 VM：2 vCPU、4 GiB、EFI、VMXNET3、系统盘 100 GiB 与第二块 100 GiB 运行时盘（精简置备）。

1. **安装与基线**（控制台）：最小安装，静态地址 .9；安装 node_base 要求的工具包（`roles/node_base/defaults/main.yml` 的 `node_base_packages`）；确认 SELinux Enforcing、firewalld 运行、cgroup v2、Swap 关闭、chrony 同步、VMware 周期时间同步关闭。Rocky 10 要求 CPU 支持 x86-64-v3，需确认客体实际可见（第 8–12 节）。
2. **运行时盘**：按 [`records/2026-10-14/commands/00.10.02-runtime-disk-configure.sh`](records/2026-10-14/commands/00.10.02-runtime-disk-configure.sh) 对**已确认为空**的第二块盘分区、建 XFS、按 UUID 挂载到 `/var/lib/containerd`（脚本先检查容量、签名与挂载状态，不符即退出）。
3. **运行时与入群工具**：把步骤 2 的 RPM 传到模板，导入签名公钥后本地安装并校验签名：
   ```
   dnf install -y --setopt=localpkg_gpgcheck=1 ./containerd.io-*.rpm ./cri-tools-*.rpm ./kubeadm-*.rpm ./kubelet-*.rpm ./kubectl-*.rpm ./kubernetes-cni-*.rpm
   ```
   containerd 配置、运行时盘依赖与 crictl 配置之后由 container_runtime 角色统一写入；kubelet 不启用（第 13–40 节）。
4. **种子镜像与 CRI 自测**：`ctr -n k8s.io images import --platform linux/amd64 <归档>` 导入 pause 与 busybox（必须是 k8s.io 命名空间，CRI 只看这里，第 34 节），再从 Mac 推送自测脚本：`ssh root@192.168.9.9 'CRI_SMOKE_CONFIRM=yes bash -s' < ops/00-preparation/tests/smoke/cri-smoke.sh`，结果应为 `smoke_result=PASS`（第 35–38 节）。
5. **封装**：先拍快照 `pre-seal-<日期>`，在模板上依次执行三组命令（第 41–42 节）。第二组改为 DHCP：
   ```
   rm -rf /root/lab-cri-smoke /var/log/phase00-cri /root/lab-artifacts /root/lab-evidence
   nmcli connection modify ens33 ipv4.method auto ipv4.addresses "" ipv4.gateway "" ipv4.dns ""
   ```
   第三组清除身份，之后不要再开新的 SSH 会话：
   ```
   truncate -s 0 /etc/machine-id
   rm -f /var/lib/systemd/random-seed /var/lib/NetworkManager/secret_key /var/lib/NetworkManager/*.lease
   journalctl --rotate && journalctl --vacuum-time=1s
   dnf clean all
   rm -f /etc/ssh/ssh_host_*
   unset HISTFILE; rm -f /root/.bash_history
   ```
   确认 machine-id 为 0 字节、主机密钥不存在后执行 `poweroff`（不是 reboot），在 vSphere 拍快照 `sealed-<日期>`。此后不再开启模板。
6. **双克隆验证**：从封装快照克隆两台临时 VM（分放两台 ESXi），比较 machine-id、`/sys/class/dmi/id/product_uuid`、MAC、SSH 主机密钥指纹与 DHCP 地址，全部不同才开始正式克隆（第 43–48 节）。

## 步骤 4：克隆与身份

1. 在 vCenter 从封装快照克隆，名称、宿主机、vCPU、内存按台账设置，不勾选「自定义操作系统」。需要数据盘的服务 VM 新增一块硬盘，容量**必须等于**台账 `data_disk_gib`；模板带来的「硬盘 2」（运行时盘）在服务 VM 上会被卸载，可删除。
2. 开机后在 vSphere「摘要」页查看 DHCP 地址，然后：
   ```bash
   cd ~/SelfProject/cloud-native-platform-lab && bash ops/00-preparation/scripts/set-vm-identity.sh <台账 id> <DHCP 地址>
   ```
   脚本从台账读取名称、地址、网关与 DNS；目标地址已被占用时停止；只需输入一次模板 root 口令（ssh-copy-id），之后都用密钥；结束时输出主机名、地址、路由、DNS 与网关连通性。
3. 把台账中该 VM 的 `vm_status` 改为 `identity_set`，然后重新生成 Inventory：
   ```bash
   ruby ops/00-preparation/scripts/generate-ansible-inventory.rb
   ```

**预期**：`ssh -i ~/.ssh/cnpl_lab_ed25519 root@<新地址> hostname` 输出台账中的 FQDN。**失败时**：报「REMOTE HOST IDENTIFICATION HAS CHANGED」是 DHCP 地址被其他克隆用过，执行 `ssh-keygen -R <地址>`（脚本已自动处理）；新地址连不上时到 vSphere 控制台检查 `nmcli connection show ens33`。

## 步骤 5：内部 DNS

**前提**：dns VM（.11）已完成步骤 4。

```bash
cd ~/SelfProject/cloud-native-platform-lab/ops/00-preparation/ansible && ~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/dns.yml | tee ../records/2026-10-14/evidence/00.07.01-dns.txt
```

剧本：service_vm（去除 Kubernetes 运行时）→ node_base → dns_server（BIND；正向、反向区域由台账生成；只对实验网开放 53；转发到 223.5.5.5、8.8.8.8，不做本地 DNSSEC 验证）→ 从 Mac 用 dig 验证。

**预期**：dns 与 localhost 都是 failed=0；六个内部名称、PTR、外部递归（rockylinux.org）与权威应答（aa 标志）全部通过。

Mac 改用内部 DNS 解析内部域名（00.07.02，只需一次）：
```bash
sudo mkdir -p /etc/resolver && echo 'nameserver 192.168.9.11' | sudo tee /etc/resolver/internal.egon.top
```

**以后改台账**：递增 `roles/dns_server/defaults/main.yml` 的 `dns_zone_serial` 后重跑本剧本。**失败时**：外部名称 SERVFAIL 而 `dig +cd` 正常，是 DNSSEC 验证被上游路径破坏（第 81 节）；本剧本已关闭本地验证。

## 步骤 6：内部 CA 与证书

```bash
cd ~/SelfProject/cloud-native-platform-lab && bash ops/00-preparation/pki/create-ca.sh
```

运行时输入根 CA 与中间 CA 的口令（由你保管）。结果：私钥（AES-256 加密）在 `~/cnpl-pki`，公开证书在 `ops/00-preparation/pki/public/`。根 CA 为 P-384、10 年；中间 CA 为 P-384、5 年，名称约束只允许 internal.egon.top 与 192.168.9.0/24。

每个 HTTPS 服务签发一张证书（输入中间 CA 口令；已存在时不覆盖）：
```bash
bash ops/00-preparation/pki/issue-cert.sh harbor.k8s.internal.egon.top 192.168.9.12
```
```bash
bash ops/00-preparation/pki/issue-cert.sh gitlab.svc.internal.egon.top 192.168.9.13
```
```bash
bash ops/00-preparation/pki/issue-cert.sh nexus.svc.internal.egon.top 192.168.9.14
```

Mac 信任根 CA（浏览器、curl 与 crane 使用）：
```bash
security add-trusted-cert -r trustRoot -k ~/Library/Keychains/login.keychain-db ops/00-preparation/pki/public/cnpl-lab-root-ca.crt
```

节点与服务 VM 的信任由 node_base 的 ca_trust 写入系统锚点，GitLab 另有 trusted-certs（角色处理）。

## 步骤 7：OpenWrt 与显式代理

**作用**：Mac 之外的主机访问外网时，只有明确配置了代理的程序经 OpenWrt；默认网关仍是 .1。

1. **VM**：按第 68–71 节把 `openwrt-25.12.5-x86-64-generic-ext4-combined.img.gz`（BIOS 版）转为 VMFS 磁盘上传；VM 设置为 Other Linux 5.x 64 位、BIOS、PVSCSI、VMXNET3、1 GiB 内存。首次开机前**断开网卡**。
2. **控制台初始配置**：关闭 LAN 的 DHCP 与 RA，设置地址后用 `passwd` 设 root 口令，再在 vSphere 连接网卡：
   ```
   uci set dhcp.lan.ignore=1; uci commit dhcp; service odhcpd stop; service odhcpd disable
   uci set network.lan.ipaddr=192.168.9.10; uci set network.lan.netmask=255.255.255.0; uci set network.lan.gateway=192.168.9.1; uci commit network; service network restart
   ```
3. **密钥与别名**（输入一次 root 口令）：
   ```bash
   ssh root@192.168.9.10 'umask 077; mkdir -p /etc/dropbear; cat >> /etc/dropbear/authorized_keys' < ~/.ssh/cnpl_lab_ed25519.pub
   ```
   ```bash
   printf '\nHost openwrt\n  HostName 192.168.9.10\n  User root\n  IdentityFile ~/.ssh/cnpl_lab_ed25519\n  IdentitiesOnly yes\n' >> ~/.ssh/config
   ```
4. **基线**（幂等；地址与掩码、DNS .11、关闭 DHCP/RA、SSH 只用密钥且只监听 LAN）：
   ```bash
   cd ~/SelfProject/cloud-native-platform-lab && ssh openwrt -o BatchMode=yes 'sh -s' < ops/00-preparation/openwrt/apply-base.sh | tee ops/00-preparation/records/2026-10-14/evidence/00.05.03-openwrt-base.txt
   ```
   预期最后有 `gateway ok`、`internet ok`，harbor 解析为 192.168.9.12。
5. **订阅地址**（只写到 OpenWrt，不经过对话与仓库；粘贴后回车，最后只显示字节数）：
   ```bash
   read -rs "SUB?粘贴订阅链接后按回车（不会显示）：" && echo && printf '%s\n' "$SUB" | ssh openwrt 'umask 077; mkdir -p /etc/mihomo; cat > /etc/mihomo/subscription-url; wc -c < /etc/mihomo/subscription-url'; unset SUB
   ```
6. **mihomo**（在 Mac 下载并按版本锁校验，可重复运行；同一版本不重复传输）：
   ```bash
   bash ops/00-preparation/openwrt/install-mihomo.sh | tee -a ops/00-preparation/records/2026-10-14/evidence/00.06.02-mihomo-install.txt
   ```
7. **验证**：
   ```bash
   curl -sS -m 20 -x http://192.168.9.10:7890 -o /dev/null -w '%{http_code} %{time_total}s\n' https://www.google.com/generate_204
   ```

**预期**：204。代理只对 192.168.9.0/24 开放；内部域名与私有地址直连，其余走订阅节点。LuCI 管理页为 http://openwrt.mgmt.internal.egon.top（root 口令）。**注意**：根分区约 100 MB、剩余约 14 MB，不要在 OpenWrt 上存放大文件。

## 步骤 8：Harbor

**前提**：harbor VM（.12，数据盘 200 GiB）完成步骤 4；已签发 Harbor 证书；种子目录有 Harbor 离线包与 Docker RPM。

```bash
cd ~/SelfProject/cloud-native-platform-lab/ops/00-preparation/ansible && ~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/harbor.yml | tee ../records/2026-10-14/evidence/00.09.02-harbor.txt
```

剧本：service_vm（保留 containerd 供 Docker 使用）→ node_base → docker_host（离线安装、验签；配置变化时在安装 Harbor **之前**重启 Docker）→ harbor（数据盘 /data、证书、harbor.yml、install.sh、`docker compose up -d`、开机单元 harbor.service、只对实验网开放 443）→ verify-harbor.yml。口令首次运行时生成在 `~/.cnpl-secrets/`。

**预期**：harbor 与 localhost 都是 failed=0；/api/v2.0/ping 为 Pong，health 为 healthy，/v2/ 未认证返回 401。浏览器访问 https://harbor.k8s.internal.egon.top，用户名 admin，`pbcopy < ~/.cnpl-secrets/harbor_admin_password` 复制口令。只验证时运行 `playbooks/verify-harbor.yml`。

**上游代理缓存与只读机器人**（00.09.03；前提：OpenWrt 代理可用，`harbor.yml` 已用当前角色运行过，其中设置了出站代理）：
```bash
~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/harbor-projects.yml | tee ../records/2026-10-14/evidence/00.09.03-harbor-projects.txt
```

剧本经 REST API 建立上游注册表与公开的代理缓存项目：dockerhub（Docker Hub）、k8s（registry.k8s.io）、quay（quay.io）、ghcr（ghcr.io），用法为 `harbor.k8s.internal.egon.top/<项目>/<上游路径>:<tag>`，例如 `dockerhub/library/busybox:1.37.0`。同时建立只读机器人 `robot$cnpl-pull`（所有项目只有 pull 权限，永不过期），密钥只在创建时返回一次，保存在 `~/.cnpl-secrets/harbor_robot_cnpl_pull`。验证：机器人能取得拉取令牌；每个代理缓存项目取得的镜像摘要与直接访问上游的结果相同。代理缓存只缓存公开的上游镜像；内部构建的镜像放在私有项目中（04 阶段）。

**失败时**：容器反复重启、日志中 `lookup redis ... no such host` 是 Docker 在 Harbor 之后重启导致（第 79 节，角色已修正，`docker compose down` 后重跑）；重启后容器 `Exited (128)` 且 Docker 日志有 `failed to initialize logging driver` 是日志容器的启动时序（第 89 节，harbor.service 负责重试）。

## 步骤 9：十台节点基线

**前提**：十台完成步骤 4；DNS、CA、Harbor 已就绪。

先对 cp01 用检查模式，再实际执行，确认后扩展到十台：
```bash
cd ~/SelfProject/cloud-native-platform-lab/ops/00-preparation/ansible && ~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/bootstrap-nodes.yml --check --limit cp01
```
```bash
~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/bootstrap-nodes.yml --limit cp01
```
```bash
~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/bootstrap-nodes.yml -e bootstrap_serial=10 | tee ../records/2026-10-14/evidence/00.10.02-bootstrap-nodes.txt
```
```bash
~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/verify-firewall.yml -e target=k8s_nodes | tee ../records/2026-10-14/evidence/00.10.02-verify-firewall.txt
```

| 角色 / 标签 | 内容 |
| --- | --- |
| node_base `system` | 工具包存在、SELinux Enforcing、基础服务、Swap 关闭、overlay、`net.ipv4.ip_forward=1`、关闭 VMware 周期时间同步 |
| node_base `firewall` | 备份原配置；ipset（k8s-nodes、k8s-control-plane、lab-mgmt）按来源放行端口（附录 A.3） |
| node_base `journald` | 持久化，上限 2G、保留 10G 空闲、30 天 |
| node_base `ca_trust` | 内部根 CA 写入系统锚点 |
| node_base `dns` | 只用内部 DNS 与搜索域；忽略路由器经 IPv6 RA 下发的 DNS，必要时自动重新激活连接 |
| container_runtime `runtime` | 版本与版本锁一致；运行时盘按 UUID 挂载且 containerd 依赖该挂载；config.toml（v3、SystemdCgroup、enable_selinux、sandbox 为 Harbor 中的 pause Digest）；Harbor 的 hosts.toml；crictl.yaml |

只改某一部分时用 `--tags`，例如 `--tags dns,ca_trust,runtime`。**预期**：failed=0；防火墙允许与拒绝用例全部符合。

## 步骤 10：引导镜像

**前提**：Mac 的 shell 代理可访问 registry.k8s.io；NO_PROXY 含内部域名（附录 B）；节点已有 hosts.toml。

```bash
~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/harbor-bootstrap-images.yml | tee ../records/2026-10-14/evidence/00.09.03-bootstrap-images.txt
```

剧本：创建公开项目 bootstrap → crane 以 `--password-stdin` 登录 → 把版本锁 `kubeadm.required_images_v1_36_5` 与 CRI 自测镜像按 `linux/amd64` 复制到 Harbor（coredns/coredns 映射为 bootstrap/coredns）→ 核对源与目标摘要、按 Digest 引用的 pause 与 busybox 与版本锁一致 → 十台执行 `kubeadm config images pull --image-repository harbor.k8s.internal.egon.top/bootstrap`。

**预期**：localhost 与十台都是 failed=0。

## 步骤 11：节点检查矩阵与 CRI 自测

```bash
cd ~/SelfProject/cloud-native-platform-lab && bash ops/00-preparation/scripts/collect-node-readiness.sh --with-cri-smoke
```

对每台推送只读的 `tests/smoke/node-readiness.sh`，再运行 `tests/smoke/cri-smoke.sh`：从 Harbor 按 Digest 拉取 busybox，创建一个 host-network sandbox 与容器，检查日志、退出码、SELinux 标签与 AVC，随后清理。期望值来自台账与版本锁。

**预期**：十台 27/27，六项身份字段唯一，CRI 自测 PASS，结果在 `records/2026-10-14/evidence/00.10.02-node-readiness-<时间>/matrix.md`。NetworkReady 为 false 是阶段边界（00 不装 CNI）。

## 步骤 12：GitLab

**前提**：gitlab VM（.13，数据盘 150 GiB）完成步骤 4；已签发 GitLab 证书；OpenWrt 代理可用。

```bash
cd ~/SelfProject/cloud-native-platform-lab/ops/00-preparation/ansible && ~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/gitlab.yml | tee ../records/2026-10-14/evidence/00.09.01-gitlab-deploy.txt
```

剧本：service_vm → node_base（dnf 经 OpenWrt 代理）→ data_disk（/var/opt/gitlab）→ gitlab（官方 el/10 仓库，软件包与元数据都验签，签名公钥按指纹导入；先写 gitlab.rb 与证书再安装，安装时软件包自动完成首次 reconfigure；随后把 root 口令设为 `~/.cnpl-secrets/gitlab_root_password` 的值并核对，删除安装时生成的随机初始口令文件；只对实验网开放 80/443）→ 从 Mac 验证登录页与 HTTP 跳转。

**预期**：首次约 15–25 分钟（下载约 1.1 GB，安装后的 reconfigure 约 10 分钟）；gitlab 与 localhost 都是 failed=0，「root 口令与管理端保存的值一致」为 ok。浏览器访问 https://gitlab.svc.internal.egon.top，用户名 root，`pbcopy < ~/.cnpl-secrets/gitlab_root_password` 复制口令。**失败时**：reconfigure 出错时到 gitlab 上执行 `gitlab-ctl reconfigure` 查看完整输出，修复后重跑剧本。

## 步骤 13：Nexus

**前提**：nexus VM（.14，数据盘 250 GiB）完成步骤 4；已签发 Nexus 证书；OpenWrt 代理可用。

```bash
cd ~/SelfProject/cloud-native-platform-lab/ops/00-preparation/ansible && ~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/nexus.yml | tee ../records/2026-10-14/evidence/00.09.04-nexus-deploy.txt
```

剧本：service_vm → node_base（dnf 经代理）→ data_disk（/opt/sonatype-work）→ nexus：经代理下载 Nexus 3.96.4-01 安装包并按版本锁 SHA256 校验，解压到 /opt/nexus-3.96.4-01（链接 /opt/nexus，自带 JDK 21）；以 nexus 账户运行的 systemd 服务，只监听 127.0.0.1:8081；用首次启动生成的初始口令把 admin 口令改为 `~/.cnpl-secrets/nexus_admin_password` 的值并核对；nginx 以内部证书提供 HTTPS（为此打开 SELinux 布尔值 httpd_can_network_connect）；只对实验网开放 80/443 → 从 Mac 验证状态接口与 HTTP 跳转。

**预期**：nexus 与 localhost 都是 failed=0。浏览器访问 https://nexus.svc.internal.egon.top，用户名 admin，`pbcopy < ~/.cnpl-secrets/nexus_admin_password` 复制口令。首次登录时网页会要求阅读并接受 Community Edition 许可协议、选择是否允许匿名访问，由你决定，剧本不代为接受。

**代理仓库与只读账户**：

1. 在 Nexus 网页设置出站代理（3.96 没有对应的 REST 接口，只能在网页上设置一次）：用 admin 登录 → 右上角齿轮 → System → HTTP；勾选 HTTP proxy，主机 `192.168.9.10`、端口 `7890`；勾选 HTTPS proxy，填同样的主机与端口；Hosts to exclude 填 `*.internal.egon.top`、`192.168.9.*`、`localhost`、`127.0.0.1`；保存。
2. 运行（从 Mac 经 REST API 配置，可重复运行）：
   ```bash
   cd ~/SelfProject/cloud-native-platform-lab/ops/00-preparation/ansible && ~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/nexus-repos.yml | tee ../records/2026-10-14/evidence/00.09.04-nexus-repos.txt
   ```

剧本先确认许可协议已被接受（未接受则停止，不代为接受），再创建或更新代理仓库：maven-central（Maven Central）、npm-proxy（npmjs）、pypi-proxy（PyPI）、nuget.org-proxy（NuGet V3）、cargo-proxy（crates.io 稀疏索引）、go-proxy（proxy.golang.org）、rocky-proxy（Rocky 官方源）；建立通用制品仓库 raw-artifacts；建立只读角色 cnpl-read 与账户 cnpl-reader（口令在 `~/.cnpl-secrets/nexus_reader_password`）。最后以 cnpl-reader 经 HTTPS 从每个代理仓库取一个固定内容，并确认未认证访问返回 401。

**预期**：localhost failed=0。某个仓库取内容失败时，先在网页 Browse 中查看该仓库的状态：显示 Remote Auto Blocked 或连接错误，通常是出站代理未设置，或上游不可达。

命名约定：`<生态>-proxy` 为上游代理，`<生态>-hosted` 为内部发布（04 阶段按需建立），`<生态>-group` 为组合入口；maven-central、nuget.org-proxy 沿用 Nexus 默认名称。匿名访问已关闭，客户端一律使用只读账户。只需要 nexus 与 backup 的系统基线和数据盘时，也可单独运行 `playbooks/service-base.yml`。

## 步骤 14：备份与恢复

**设计**：restic 加密仓库放在 backup VM（.16，/srv/backup，只提供 SFTP）；仓库口令只在管理端与各客户端，backup VM 只保存密文。dns、harbor、gitlab、nexus 每天 02:30 前后自动备份，管理 Mac 手动或按需备份只存在于 Mac 与 OpenWrt 上的内容。仓库地址使用 IP，备份不依赖内部 DNS。

| 主机 | 备份内容 | 说明 |
| --- | --- | --- |
| dns | /etc/named.conf、/etc/named.rfc1912.zones、/var/named | — |
| harbor | harbor.yml、/etc/harbor（证书）、/data（不含 database、redis）、数据库逻辑导出 | 数据库用 pg_dumpall 导出，不复制在线文件 |
| gitlab | /etc/gitlab（含 gitlab-secrets.json）、gitlab-backup 生成的备份包 | 本机只保留最近的备份包 |
| nexus | /opt/sonatype-work/nexus3（不含 log、tmp、cache） | 内置数据库需要停服务，备份期间约 1–2 分钟不可用，结束时自动重新启动 |
| 管理 Mac | ~/cnpl-pki、~/.cnpl-secrets、OpenWrt 配置包（`sysupgrade -b`） | 订阅地址不在配置包中 |

1. 在 Mac 上下载并校验 restic（验证发布者签名与 SHA256，可重复运行）：
   ```bash
   cd ~/SelfProject/cloud-native-platform-lab && bash ops/00-preparation/scripts/fetch-restic.sh
   ```
2. 部署并执行第一次备份：
   ```bash
   cd ~/SelfProject/cloud-native-platform-lab/ops/00-preparation/ansible && ~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/backup.yml | tee ../records/2026-10-14/evidence/00.10.03-backup.txt
   ```
   剧本：各客户端生成专用密钥 id_restic → backup VM 建立只能 SFTP 的 restic 账户（authorized_keys 带 restrict；sshd 的 Match 设置经 `sshd -T` 确认只作用于该账户，否则回退）→ Mac 初始化仓库（口令生成在 `~/.cnpl-secrets/restic_password`）→ 客户端逐台安装 restic（与 Mac 上校验过的文件比对 SHA256）、写入口令与连接设置（known_hosts 取自 backup VM 的主机公钥）、备份脚本与每日定时器，并立即备份一次 → Mac 备份、prune、列出快照并检查仓库。
3. 恢复演练（只恢复到临时目录，不覆盖在用文件）：
   ```bash
   ~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/restore-drill.yml | tee ../records/2026-10-14/evidence/00.10.03-restore-drill.txt
   ```
   DNS：恢复 dns 的最新快照，用 named-checkconf、named-checkzone 检查，并与在用文件逐字节比较；CA：恢复 ~/cnpl-pki，与原目录逐文件比较，根证书指纹与仓库中的公开证书一致。

**预期**：两个剧本都是 failed=0；`restic check` 显示 no errors were found。

**务必**：把 `~/.cnpl-secrets/restic_password` 另存一份到 Mac 之外（密码管理器或纸面）。Mac 损坏时，这个口令是解密全部备份的唯一途径，而它自己也只备份在这个仓库里。

偏差：backup 与被备份的服务同在 esxi01，不满足「独立备份」，验收中如实标注。

## 步骤 15：重启复验与幂等

```bash
cd ~/SelfProject/cloud-native-platform-lab/ops/00-preparation/ansible && ~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/reboot-nodes.yml | tee ../records/2026-10-14/evidence/00.11-reboot-nodes.txt
```
```bash
~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/reboot-nodes.yml -e target=dns,harbor,gitlab,nexus,backup | tee ../records/2026-10-14/evidence/00.11-reboot-services.txt && ~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/verify-services.yml | tee -a ../records/2026-10-14/evidence/00.11-reboot-services.txt
```
```bash
~/.venvs/cnpl-ansible/bin/ansible-playbook playbooks/bootstrap-nodes.yml --check -e bootstrap_serial=10 | tee ../records/2026-10-14/evidence/00.11-bootstrap-check.txt
```

reboot-nodes.yml 每次重启一台，任何一台失败即停止；重启后检查 SELinux、firewalld、DNS、失败单元，节点另查运行时盘与 containerd。之后重跑步骤 11 的矩阵。**预期**：重启全部通过；矩阵 27/27；检查模式十台 changed=0。系统级检查通过不代表服务已恢复，因此服务 VM 重启后运行 `playbooks/verify-services.yml`：内部 DNS、Harbor（API、健康、/v2/）、GitLab 登录页、Nexus 状态、备份定时器与经 SFTP 访问备份仓库，都是只读检查，可在任何变更后用来复查。

## 步骤 16：断网验收（待编写）

在一台干净的测试客户端上限制外网访问，依次验证：内部 DNS 与 TLS、Git 克隆、Harbor 镜像拉取、RPM 安装、指定语言依赖经 Nexus 获取与构建；记录任何未缓存的下载并补充物料，完成后恢复网络限制。交付 `tests/smoke/` 下的离线用例与物料缺口清单。

## 步骤 17：阶段交接

按 [阶段验收模板](../templates/phase-acceptance.md) 建立 `records/<批次>/acceptance.md`，逐项链接证据：

| 验收项 | 预期结果 | 失败后处理 |
| --- | --- | --- |
| VM、身份、放置 | 十台身份唯一，三台控制平面分散在三台 ESXi | 修正模板或放置，重新核验受影响节点 |
| 网络、DNS、时间 | 静态配置持久，只用内部 DNS，时间同步正常 | 通过控制台恢复网络，修复角色 |
| 软件源、CA、仓库 | 指定物料可经内网获取，TLS 无绕过 | 补同步缺失物料或证书链，不改用不可信来源 |
| OS、cgroup、Swap、安全 | 与预算一致，重启后仍生效 | 修复持久配置，记录明确例外 |
| CRI | containerd 自启，RuntimeReady，经 Harbor 拉取、运行、日志、清理通过 | 排查版本、socket、cgroup、证书、挂载、AVC |
| 幂等 | 第二次执行无非预期变更 | 修复剧本，不用手工结果掩盖 |
| 保护范围 | OSD 候选盘未初始化，既有 VM 与数据未受影响 | 停止后续步骤，处理偏差 |
| 离线与备份 | 干净客户端完成指定安装与构建，基础服务可从备份恢复 | 补齐物料与恢复材料后重测 |

未完成或延后的项（如 OpenTofu、vSwitch 与 VIP 二层核实、第二台 DNS、构建缓存、镜像扫描）如实标注。全部满足或明确延后后，01 才开始 kubeadm init/join；主机问题回到本阶段修复，不用 `--ignore-preflight-errors=all` 绕过。

## 附录 A：设计要点

### A.1 磁盘

- OS 盘、运行时盘与 OSD 盘分开。运行时数据在 `/var/lib/containerd`，按 UUID 挂载，containerd 依赖该挂载（盘缺失时不启动，避免写入根盘）。十台的运行时盘 UUID 相同（继承自模板，各自是独立磁盘），按 SCSI 地址核对；设备名 sda/sdb 在重启间会变化，不作为标识。
- 服务 VM 的数据盘由 data_disk / harbor 角色按「唯一容量、无分区、无文件系统」选择，XFS 带标签，挂载后恢复 SELinux 标签。

### A.2 网络与 DNS

- 每台的 FQDN、地址、连接名都来自台账；默认网关保持 .1，不指向 OpenWrt。
- 节点只用内部 DNS，不长期依赖 `/etc/hosts`。路由器会经 IPv6 RA 下发自己的 DNS，必须忽略（`ipv6.ignore-auto-dns yes`），否则内部 DNS 超时时会改问路由器，内部名称解析失败。不关闭 IPv6。

### A.3 防火墙端口（来源受限）

| 端口 | 来源 | 用途 |
| --- | --- | --- |
| 22/tcp | 现有规则（未收紧） | SSH |
| 6443/tcp | k8s-nodes、lab-mgmt → 控制平面 | kube-apiserver |
| 2379–2380/tcp | k8s-control-plane | etcd |
| 10250/tcp | k8s-nodes | kubelet |
| 8472/udp、4240/tcp | k8s-nodes | Cilium VXLAN 与健康检查 |
| 53、80/443 等 | 192.168.9.0/24 → 对应服务 VM | DNS、Harbor、GitLab |

kube-controller-manager 与 kube-scheduler 绑定在 127.0.0.1，不开放；Ceph、Hubble、NodePort、网关在 02/03 启用时再加规则。8472/udp 与 4240/tcp 在 01 数据面验证。

### A.4 containerd 与 CRI

- 配置使用 containerd 2.x 的 v3 路径（`io.containerd.cri.v1.*`），不写 1.x 的 `io.containerd.grpc.v1.cri`。
- `SystemdCgroup = true` 时，手写的 sandbox 必须给出以 `.slice` 结尾的 `cgroup_parent`（cri-smoke.sh 使用 `phase00.slice`），否则 runc 拒绝。
- sandbox 镜像固定为 Harbor 中的 Digest；Harbor 尚未就绪时不能写入，否则新 sandbox 在拉取阶段失败。
- hosts.toml 只提供端点与 CA 信任，不提供认证；bootstrap 项目为公开项目。
- CRI 自测失败先区分：镜像不在 k8s.io 命名空间、sandbox 指向不可达的仓库、Enforcing 下的真实拒绝（`ausearch -m AVC -ts recent`）；架构不符表现为 `exec format error`。

## 附录 B：管理端访问路径与常见问题

**访问路径**：Mac 用 `/etc/resolver/internal.egon.top` 把内部域名交给 .11；根 CA 在登录钥匙串；Clash Verge 的系统代理例外含 `*.internal.egon.top` 与 192.168.0.0/16；shell 的 NO_PROXY 加入内部域名：
```bash
echo 'export NO_PROXY="${NO_PROXY:+$NO_PROXY,}.internal.egon.top,192.168.9.0/24"; export no_proxy="$NO_PROXY"' >> ~/.zshrc
```
实验网经 USB 网卡 en5（.200）访问；防火墙中的 lab-mgmt 即 .200，地址变化时改 `inventories/lab/group_vars/all.yml` 的 `lab_mgmt_sources` 并重跑 node_base 的 firewall 部分。

| 现象 | 原因 | 处理 | 记录 |
| --- | --- | --- | --- |
| 节点 dnf 极慢或元数据 404 | mirrorlist 选中慢速或不同步的国内镜像 | 物料走种子；服务 VM 的剧本设置 `node_dnf_proxy` 经 OpenWrt | 第 51、74 节 |
| Mac 访问内部 HTTPS 报 SSL_ERROR_SYSCALL | 请求经 Clash 代理，代理无法解析内部域名 | NO_PROXY 与系统代理例外加入内部域名；验证命令加 `--noproxy '*'` | 第 77–78 节 |
| 内部 DNS 对外部名称 SERVFAIL | 上游路径去掉 DNSSEC 签名 | 已关闭本地验证 | 第 81 节 |
| resolv.conf 多出 fd5c:… 地址 | 路由器经 RA 下发 DNS，reapply 不清除 | node_base dns 自动重新激活连接 | 第 84、86 节 |
| Harbor 容器反复重启，`lookup redis` 失败 | Docker 在 Harbor 安装后重启（live-restore） | 已修正；`docker compose down` 后重跑 | 第 79 节 |
| Harbor 重启后 443 无监听 | syslog 日志驱动与 harbor-log 的启动时序 | harbor.service 重试 | 第 89 节 |
| OpenWrt ping 外网全丢 | 掩码误写为 225.225.225.0 | apply-base.sh 写入正确掩码 | 第 86 节 |
| OpenWrt 写文件报 No space left | 根分区约 100 MB | 不在 OpenWrt 上存放大文件 | 第 89 节 |
| Mac 脚本报 `xxx?: unbound variable` | bash 3.2 把全角标点吞进变量名 | 变量一律写成 `${var}` | 第 52、72 节 |
| `harbor.yml --limit localhost` 直接退出 | 隐式 localhost 不在 inventory 中 | 单独运行 verify-harbor.yml | 第 86 节 |

## 附录 C：自动化清单

| 类型 | 文件 | 作用 |
| --- | --- | --- |
| 剧本 | `ansible/playbooks/dns.yml` | 内部 DNS 与验证 |
| | `harbor.yml`、`verify-harbor.yml`、`harbor-projects.yml` | Harbor 部署与管理端验证；上游代理缓存与只读机器人 |
| | `bootstrap-nodes.yml`、`verify-firewall.yml` | 十台节点基线；防火墙允许与拒绝验证 |
| | `harbor-bootstrap-images.yml` | 引导镜像复制与节点预拉 |
| | `gitlab.yml` | GitLab 部署与验证 |
| | `nexus.yml`、`nexus-repos.yml` | Nexus 部署与验证；代理仓库与只读账户 |
| | `service-base.yml` | Nexus、备份的基线与数据盘 |
| | `backup.yml`、`restore-drill.yml` | 备份部署与第一次备份；恢复演练 |
| | `reboot-nodes.yml`、`verify-services.yml` | 逐台重启复验；基础服务只读验证 |
| 角色 | `ansible/roles/service_vm`、`node_base`、`container_runtime`、`data_disk`、`dns_server`、`docker_host`、`harbor`、`gitlab`、`nexus`、`nexus_repos`、`harbor_projects`、`backup_server`、`backup_client` | 见各步骤 |
| 管理端脚本 | `scripts/generate-ansible-inventory.rb` | 台账生成 Inventory |
| | `scripts/set-vm-identity.sh` | 新克隆设置名称、地址与密钥 |
| | `scripts/fetch-restic.sh`、`scripts/backup-mac.sh` | 下载并校验 restic；管理端备份与仓库检查 |
| | `scripts/collect-node-readiness.sh`、`summarize-node-readiness.py` | 节点检查矩阵 |
| 节点检查 | `tests/smoke/node-readiness.sh`、`tests/smoke/cri-smoke.sh` | 只读检查；host-network CRI 自测 |
| PKI | `pki/create-ca.sh`、`pki/issue-cert.sh` | 内部 CA 与服务证书 |
| OpenWrt | `openwrt/apply-base.sh`、`openwrt/install-mihomo.sh`、`openwrt/mihomo/` | 旁路由基线与显式代理 |

OpenTofu（`opentofu/`）尚未开始，VM 目前在 vCenter 手工克隆。
