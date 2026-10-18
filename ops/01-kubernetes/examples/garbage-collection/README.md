# 01.08 删除传播、所有权与 Finalizer

独立入口为 `scripts/stage-08.sh`，Ansible 步骤位于 `ansible/tasks/core/stage-08*.yml`。本目录两个源码 YAML 定义父子控制器和外部资源模拟；只在本批 `lab-p08` 中实验。

## 完整命令及预期

```bash
# 1. 固定仓库位置。
cd /Users/mario/SelfProject/cloud-native-platform-lab
# 2. 建立 08 自己的证据目录，不复用 07 的 context。
CNPL08="$PWD/ops/01-kubernetes/records/core-07-10/runs/08-$(date -u +%Y%m%dT%H%M%SZ)"
# 3. 有限应用检查和所有删除场景的清单结构校验。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-08.sh validate "$CNPL08"
# 4. 核对 07 的同集群成功回执，然后只执行 08。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-08.sh run "$CNPL08"
```

第 3 条应有 `01.08 SOURCE VALIDATION PASS`。第 4 条应有 `01.08 ACCEPTANCE PASS`、`01.08 CLEANUP PASS`，全部主机失败数为零。

| 实验 | 如何避免偶然看不到删除窗口 |
| --- | --- |
| Foreground | 先绑定 Deployment→RS→Pod UID，在自己的一个 Pod 上加观测 finalizer。删除父对象后必须看到父对象 deletionTimestamp 和 foregroundDeletion 仍在等待；解除自己的标记后检查整条链消失。 |
| Background | 使用另一组对象，子 Pod 同样被实验标记保留；父对象必须先实际消失，子对象仍存在且进入删除。随后释放标记并确认无遗留。 |
| Orphan | 第一次只 Orphan 删除 Deployment，留下的直接子对象是 RS，Pod 仍由 RS 控制。再 Orphan 删除 RS，得到无 owner 的 Pod；新 RS 用精确 Selector 接管，要求 Pod UID 原样保留且归属变成新 RS。 |
| Finalizer | 两个 ConfigMap 模拟被保护对象和外部资源。先观察 deletionTimestamp，再删除本批模拟外部对象，确认已消失后才移除自己的 finalizer。 |

这些 finalizer 没有真实云资源或存储副作用。清理器只允许本实验标记及 Kubernetes 自己的 GC/Job 标记；外来 finalizer、其他 run 或重建后的同名 Namespace 会被拒绝。它不会批量强清未知保护标记。

## 失败后

```bash
# 相同源码下保留旧现场，新 attempt 重做尚未通过的本阶段。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-08.sh resume "$CNPL08"
# 放弃该批时，先取证，再精确回收自己的 Namespace 和实验标记。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-08.sh cleanup "$CNPL08"
```

源码改变时先清理旧目录，再创建新目录。通过后可查看 `passed.json`，以及 `attempts/*/snapshots` 中的 ownerReferences、UID、删除时间与事件，然后执行 01.09。

参考：[垃圾回收](https://kubernetes.io/docs/concepts/architecture/garbage-collection/)、[Finalizer](https://kubernetes.io/docs/concepts/overview/working-with-objects/finalizers/)。
