# 01.07 StatefulSet 与 DaemonSet

独立入口为 `scripts/stage-07.sh`，执行步骤在 `ansible/tasks/core/stage-07.yml` 和 `stage-07-daemon.yml`。StatefulSet 源码在本目录 `manifests/state.yaml.j2`，DaemonSet 在 `../daemonset/manifests/daemon.yaml.j2`。先完成本阶段，再执行 01.08；入口不会自动启动下一阶段。

## 一次给全的执行命令

管理 Mac 在同一终端依次执行：

```bash
# 1. 进入仓库，使用已经完成 03–06 的同一集群和管理身份。
cd /Users/mario/SelfProject/cloud-native-platform-lab
# 2. 为 07 创建独立证据目录；UTC 时间只用于目录命名。
CNPL07="$PWD/ops/01-kubernetes/records/core-07-10/runs/07-$(date -u +%Y%m%dT%H%M%SZ)"
# 3. 测试/编译小型 Go 应用，生成精确镜像，渲染全部策略变体并校验结构；不启动实验 Pod。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-07.sh validate "$CNPL07"
# 4. 使用同一目录执行 07，导入两个 worker 的镜像，并完成实验、恢复和清理。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-07.sh run "$CNPL07"
```

第 3 条预期 `01.07 SOURCE VALIDATION PASS`。第 4 条必须同时有 `01.07 ACCEPTANCE PASS`、`01.07 CLEANUP PASS`，且全部主机 `failed=0`、`unreachable=0`。

| 实验 | 实际动作与验收证据 |
| --- | --- |
| 有序稳定身份 | 两个 OrderedReady 副本；核对序号、Ready 与创建时间，实际解析 `p07-state-0.p07-state-headless.lab-p07.svc.cluster.local`。 |
| Pod 重建 | 给 emptyDir 写入原 UID 标记，删除 0 后确认名称相同、UID 不同、DNS 指向新 IP；新卷不再有旧标记。这里只证明身份稳定，不证明数据持久化。 |
| 扩缩与阻挡 | 关闭 1 的应用就绪并等 kubelet 报告 NotReady，扩到 3 后必须仍只有两个 Pod；恢复后 2 才出现。再缩到 2，验证回收最高序号，随后恢复到 3。 |
| 分区更新 | 两个不同 OCI Digest 的 v1/v2；partition=1 只更新 1、2，partition=0 更新全部。检查实际 Pod 镜像而非只看模板标签。 |
| OnDelete | 清除 RollingUpdate 字段后切换策略，先确认旧 Pod UID/镜像不变；删除 2 只更新 2，再手动更新其他序号。 |
| Parallel | 新建独立 StatefulSet，避免修改不可变 podManagementPolicy；0 不就绪时 1、2 仍创建就绪。 |
| DaemonSet 覆盖 | 对两个 worker 使用本批 `cnpl.io/core07` 标签，观察一个、零个和两个节点覆盖。 |
| 污点与容忍 | worker02 只加本次 NoSchedule，删除自己的守护 Pod 后观察不再补建；加精确容忍后恢复。完成后立即还原污点。 |
| 发布与回滚 | RollingUpdate 到 v2，故意发布不存在的本地镜像，确认 ErrImageNeverPull 后按真实 ControllerRevision 回滚；再对照 OnDelete 的实际 UID/镜像。 |

## 安全与恢复如何工作

实验空间固定为 `lab-p07`，普通应用无默认 Token、无 hostPath、无特权，只在 worker01/worker02 运行。Namespace 先绑定 UID；普通操作使用新空间内授予的受限管理身份，节点元数据由管理端管理员入口执行。

修改节点前记录 UID 和恢复意图。worker02 NoSchedule 注入前，cp01 安装 180 秒独立回退，管理 Mac 中断后也能清除本批污点。成功或失败均按 UID、标签值和污点值恢复，使用原子 JSON Patch 保留其他维护信息。

同一份源码失败后续跑：

```bash
# 原始 attempt 保留；先恢复自己的维护，再取证和重新执行未完成的 07。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-07.sh resume "$CNPL07"
# 只有决定放弃本次 07 时执行：恢复元数据、保全现场、回收本批空间和授权。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-07.sh cleanup "$CNPL07"
```

不要删除 context、改写成功断点或强制清除其他控制器 finalizer。源码变更时先用原目录 `cleanup`，再以新目录运行；清理不要求旧编译物料仍然可用。已通过的同一阶段只复核原回执并跳过；独立阶段之间不会重复执行。

证据在 `$CNPL07/attempts/*/{manifests,observations,snapshots}`。只有真实实验与清理都完成后才写 `passed.json` 和 `records/core-07-10/completed/07.json`。PVC、Ceph 和业务数据持久化留待 Phase 03。

参考：[StatefulSet](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/)、[DaemonSet](https://kubernetes.io/docs/concepts/workloads/controllers/daemonset/)。
