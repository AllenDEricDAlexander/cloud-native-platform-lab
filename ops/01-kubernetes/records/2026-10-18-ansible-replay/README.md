# 01.03–01.06：源码 YAML + Ansible 执行

原 01.03–01.06 与此次源码 YAML + Ansible 重跑均已真实验收通过。新实现的本次运行验收与清理结果见[剩余实验完成记录](repairs/20261018-observer-and-completion/README.md)。

当前运行 `03-06-20261018T051927Z-ha-fix-20261018T063407Z` 的 26 个成功断点齐全，两个总 PASS 均已取得；十节点及系统负载健康，本批对象与派生 EndpointSlice 已清理。原目录作为已完成证据保留，无需重新执行其中的故障实验。

## 职责与源码

| 内容 | 位置与职责 |
| --- | --- |
| Kubernetes 资源 | `operations/manifests/` 与 `core-resources/{pods,probes,controllers}/manifests/` 的 `.yaml.j2`。字段、探针、资源请求、容器命令均可直接阅读。Jinja 只填本批标签、镜像 Digest、Service IP 和明确的场景参数。 |
| 执行与恢复 | `ansible/playbooks/replay.yml` 及 `ansible/tasks/replay/`。负责渲染、create/apply、exec 控制、scale、pause/resume/undo、备份、恢复、删除和检查点。`resource.yml` 直接把渲染后的文件传给 kubectl。 |
| 必要检查 | `checks/lab-check.py` 核对 UID、控制器收敛、终止时序、归属、清理和旧证据 SHA；`traffic.py` 只读 HTTP/流量时间线；`backup-files.py`、`backup-check.py` 核对恢复材料及取回 SHA。网络检查复用原只读验收器。 |
| 实验应用与镜像 | Go 标准库应用仍是被测试的工作负载。Ansible 使用已有锁定工具链编译，由 `tools/imagepack.go` 打包 OCI；不使用 Python 构建器，不增加集合、SDK、Docker 或构建依赖。 |
| 历史材料 | `legacy/sources/` 是旧执行源码原件；`sources-sha256.json` 与 `original-records-sha256.json` 校验来源和全部旧原始记录。旧失败记录、修复过程及源码快照保留。 |

`attempts/*/manifests/` 保存实际提交的 YAML，`snapshots/` 保存对象/事件/可读日志，`observations/` 保存请求、EndpointSlice、TERM 和恢复证据。失败不补写 PASS，续跑先保全失败现场，再重建本批未通过组。源码变更后拒绝沿用已有运行的检查点，应创建新目录。

## 一次执行完整命令

在管理 Mac 同一终端执行。先完成前检，再运行；正式运行先提示准备 ESXi 控制台，再自动检测两次手动电源操作。

```bash
# 1. 固定仓库位置，保证相对源码路径正确。
cd /Users/mario/SelfProject/cloud-native-platform-lab

# 2. 为这轮新实现生成独立记录目录，不复用 2026-10-17 的旧证据。
CNPL_REPLAY="$PWD/ops/01-kubernetes/records/2026-10-18-ansible-replay/runs/03-06-$(date -u +%Y%m%dT%H%M%SZ)"

# 3. 编译/有限测试、68 份清单及变体的严格结构检查、十节点和三 etcd 只读前检。
#    不创建实验 Pod，不快照、不修改 kubelet、不操作电源。
bash ops/01-kubernetes/scripts/replay-03-06.sh validate "$CNPL_REPLAY"

# 4. 使用同一目录开始正式运行（validate 已创建上下文，因此使用 resume）。
#    顺序：DNS → 完整备份/取回 → HA → 04 → 05 → 06 → 全部清理。
bash ops/01-kubernetes/scripts/replay-03-06.sh resume "$CNPL_REPLAY"
```

目录预检校验源码结构及同名归属；真正 create/apply 前，再分别执行相应的 server dry-run。这样续跑可以保留现场，并仍由服务端拒绝实际无效变更。

第 3 条预期有 `REPLAY SOURCE SCHEMA PASS`，且所有主机 `failed=0`、`unreachable=0`。第 4 条最终必须同时出现 `ANSIBLE REPLAY ACCEPTANCE PASS`、`ANSIBLE REPLAY CLEANUP PASS`，所有主机失败数为零。每组的 PASS 仅在断言及必要恢复完成后写入检查点。

也可直接对全新目录使用 `run`，它包含相同前检。模式含义：`validate` 只检查，`images` 仅准备两个 worker 的镜像缓存，`run` 新批执行，`resume` 相同源码/集群下续跑，`recover` 只处理已有 worker02 恢复索引并检查健康；`cleanup` 在恢复节点后取证并清理本批对象，明确结束本批，不写实验 PASS。`images` 不启动容器。

## 01.03：手动电源与备份的边界

正式执行先为 CoreDNS 补充跨节点硬反亲和并检查两个 Ready 副本，运行十节点普通 Pod 的 HTTP/DNS/Service 短名矩阵并清理。备份覆盖三节点控制平面配置/PKI、加密材料、恢复身份及一致性快照；只在隔离目录执行 etcdutl restore，不启动第二套 etcd。随后加密写入 .16，用准确 restic snapshot ID 取回并逐文件比对。

私有原件只写 `~/.cnpl-secrets/phase01-backups/` 与各节点本批私有暂存；公开记录只有回执/校验信息。每次备份重试使用独立目录。只有取回验证通过，才允许 HA。

HA 目标从当前 kube-vip 租约读取，脚本会打印实际 VM 名称和 IP：

1. 先打开 ESXi 控制台并保持三台开启，在“准备控制台”提示按回车；观测计时此时才开始。
2. 脚本重新读取 VIP 持有者、核对 UID/端口基线并确认观测在线，然后打印本次目标。看到 Power Off 指令后只关闭指定 VM，无需回车；脚本从存活节点自动检测 22/6443 均停止，再验证接管、多数派及故障中新 Pod 调度。
3. 出现 `FAULT CHECKS PASS` 后开启原目标 VM，无需回车；脚本自动等待十节点、三个 API/etcd 和应用流量恢复，再验收和清理。

HA 的观测上限为 40 分钟，关键阶段检查异步任务仍在线；其他实验保留 420 秒默认上限。若失败，先开启被关闭的 VM，确认恢复，再续跑。此次 HA 生命周期修复及原批次的修复版本续跑路径见 [修复记录](repairs/20261018-ha-observation/README.md)。

## 01.04–01.06 做什么

| 专题 / 任务文件 | 操作与通过条件 |
| --- | --- |
| 04 base / states | 创建预算、限制、隔离策略和基准应用；观察 Succeeded、退出 7、CrashLoop、缺失镜像及 8 核 Pending。修复镜像，按源码删除重建命令/请求不可变的 Pod，确认恢复。 |
| 04 sidecars / debug | 失败 Init 阻挡主容器；比较普通与原生 Sidecar 的启动/退出顺序。无 shell 应用通过受限临时容器验证进程、DNS、拒绝连接与客户端超时，默认 SA 保持无调试权限。 |
| 04 memory / pressure | 容器内存盘触发 OOMKilled/137；另在 worker02 隔离后临时把 soft 阈值设为节点内存容量，保留 45s 宽限期和 500Mi hard 基线，避免采样值加 16Mi 被内存波动抵消。105 秒统一观测实际加载配置、MemoryPressure 和同 UID 的 memory/Evicted，持续保存时间线。150 秒独立回退先于配置替换安装；必须核对原配置 SHA、节点/系统 Pod 健康后才解除本批 cordon。 |
| 04 termination | 正常删除后取得 Completed/0、匹配 UID 的 TERM 与子进程回收回执，再释放本实验 finalizer。 |
| 05 startup / liveness | 6/12/20 秒启动由真实探针历史证明保护窗口；超窗实例实际重启。依赖超时只摘除就绪，本地心跳停止触发 liveness 重启。 |
| 05 readiness / termination | 对照 EndpointSlice、新连接与原 HTTP/1.1 连接；同时测试长短请求、消息、PreStop/TERM 排空。短宽限期造成非 OOM 的 137、请求失败，再用租约重投及重复提交证明最终效果一次。 |
| 05 protocols | 同一业务错误下 HTTP/Exec 与 TCP 的差别；etcd 的原生 gRPC 空 service 与错误 service 对照。 |
| 06 replicas / history | RC/RS 接管匹配孤儿、补副本和替换 UID；模板更新产生 RS/revision，仅 scale 不产生新版本。 |
| 06 scale / strategies | 扩缩容期间长请求和 emptyDir 行为；8 核容量反例；持续流量下 RollingUpdate、Recreate 和 surge 容量阻塞，并保留真实错误率/资源时间线。 |
| 06 rollbacks / split | 暂停修改、恢复发布；错误镜像、readiness 失败、探针正常但业务 500，按实际 revision 原生回滚并比较完整模板。最后验证 stable/canary 两个独立入口，不代表加权灰度。 |

每个 topic 的 `topic-XX.yml` 是阅读顺序，`case-XX-*.yml` 是实际动作。每组先保存现场，再按本批标签和 Service UID 清理；父控制器先停止，防止 Pod 刚删又重建。Namespace、RBAC 与其他批次对象不属于清理范围。

## 失败后完整命令

```bash
# 先确认任何被关闭的控制平面 VM 已开启。
# 若曾进入 worker02 压力修改，先执行同批恢复；独立 timer 不负责自动 uncordon。
bash ops/01-kubernetes/scripts/replay-03-06.sh recover "$CNPL_REPLAY"

# 保持相同记录目录和源码，继续未通过组；原始输出不会被覆盖。
bash ops/01-kubernetes/scripts/replay-03-06.sh resume "$CNPL_REPLAY"
```

若源码已修改，`resume` 会拒绝混用版本。先对旧批执行 `recover` 恢复节点，再执行下面的显式清理，创建新批目录。不要删除旧 context、手工补 PASS 或把失败现场改名冒充成功。

```bash
# 仅在放弃本批、或源码已变更不能 resume 时使用；先恢复、取证，再清理本批资源。
bash ops/01-kubernetes/scripts/replay-03-06.sh cleanup "$CNPL_REPLAY"
```

## 交付核验与待验收范围

核验记录位于 `runs/delivery-final-validate-v2/` 及 `delivery/`。原始 01.06 六组和清理已核对通过；新实现执行了有限单测、真实 Ansible helper 离线集成、真实 API 准入及三控制平面只读检查。重跑故障实验由用户启动，此次静态/只读交付不算新实现运行验收，不开始 01.07。

委派连接已明确固定到节点 SSH 和 `/usr/bin/python3`；`/usr/bin/python3.12` 不存在的报错及当前批次备份收尾，见 [2026-10-18 修复记录](repairs/20261018-delegation/README.md)。

HA 人工等待、过期观测和自动双端口检测的修复与核验，见 [2026-10-18 HA 修复记录](repairs/20261018-ha-observation/README.md)。

已有同名对象导致 AlreadyExists 的前检修复、真实正负对照和同目录继续命令，见 [准入续跑修复记录](repairs/20261018-admission-resume/README.md)。

软驱逐阈值、105 秒统一观测窗口、63 项回归及原成功断点的保留核验，见 [pressure 续跑修复记录](repairs/20261018-pressure-resume/README.md)。
