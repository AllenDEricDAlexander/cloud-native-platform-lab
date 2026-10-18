# 04 pressure 软驱逐与同目录续跑修复

本次失败属于批次 `20261018T051939Z-bca4cc12`，失败 attempt 为 `20261018T065913Z-5f203375`。成功断点保留在原目录；没有重新初始化集群或执行 HA 关机。

## 诊断依据

- 原统计中 node available 为 `15726280704` 字节，旧临时 soft 阈值为 `15743057920`，仅高 16Mi；节点内存容量为 `16761597952` 字节。
- 节点在 `2026-10-18T07:13:05Z` 报告 MemoryPressure=True，最终失败快照中的同 UID Pod 仍为 Running/Ready，未出现 memory/Evicted。[kubelet 日志](kubelet-pressure-window.txt)中没有本轮内存驱逐记录。
- 原执行没有保存阈值启用后的内存时间线，不能事后证明具体哪次内存波动重置了宽限期。可确定的脚本缺陷是：一次采样加 16Mi 无法保证持续满足 45s 的软驱逐条件；先等节点再等 Pod 的分段等待预算也可能越过 150s 独立回退窗口。
- 依据 [Kubernetes 节点压力驱逐规则](https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction/#soft-eviction-thresholds)，节点压力报告不等于已满足软驱逐宽限期。[本集群 v1.36.5 的实现](https://github.com/kubernetes/kubernetes/blob/v1.36.5/pkg/kubelet/eviction/eviction_manager.go)分别计算节点压力与宽限期，并保护系统关键 Pod。

## 修改范围

执行源码仅修改 `ansible/tasks/replay/case-04-pressure.yml` 和 `checks/lab-check.py`，继续采用源码 Kubernetes YAML + Ansible 执行 + Python 只读检查，没有新增依赖或编排层。

1. worker02 cordon 后再次检查全部活动 Pod，只允许本次受害者及 kube-system 关键 Pod，避免前检与封锁之间调度进来的其他业务受到影响。
2. 临时 soft 阈值设为节点内存容量，使用 kubelet 同一份统计中的 available + workingSet 计算。这样节点上的非零 workingSet 能稳定满足条件，不依赖 16Mi 的瞬时差值。保留 45s 宽限期、500Mi hard 基线，以及原 96Mi 内存盘/160Mi 容器限制；没有制造真实内存耗尽。
3. 105s 统一只读观测窗口检查 configz 实际加载值、Node/Pod UID、run 归属、真实可用内存至少 4GiB、统计时效、MemoryPressure、Failed/Evicted 及 memory 原因。每次 API 请求和进程超时都受剩余窗口约束，避免多段轮询叠加。
4. 观测结果持续写入新 attempt 的 `observations/04-pressure-eviction.json`。超时、API 删除、OOMKilled、正常结束、旧 UID、错误配置、其他资源驱逐均不能成为 PASS。
5. 原有 150s 独立回退先于配置替换安装；成功或失败都执行 always 恢复，并核验原 kubelet 字节 SHA、节点与系统负载健康、解除本批 cordon 后才允许写 pressure 检查点。

## 核验与原始记录

- [63 项完整回归](regression.txt)全部通过，包括真实 Ansible 模板渲染、内存跨越原 16Mi 余量、只有压力而无驱逐、错误身份/配置/原因、API 短暂不可达、请求超时预算及真实断点跳过。
- [主入口语法检查](syntax-check.txt)通过。
- [真实只读负对照](live-readonly-guard.txt)及[同一原生 Ansible 观测任务](readonly-observer-smoke.txt)确认：正常 kubelet 配置被正确拒绝，不能误报压力 PASS。smoke 日志里的一次 rescued 失败是预期负例，没有修改节点配置或 Pod。
- [完整主入口 validate](full-preflight.txt)核验 68 项源码清单及所有只读前检；不执行本次压力故障注入。
- [修复前指纹](before-repair-sha256.json)保存该目录原有 334 个文件 SHA。[核验结果](verification.json)确认除受控更新的当前 context 外，原有文件均保持原字节，8 个成功检查点保留；旧 context 原样归档。历史 1183 个原始执行文件仍由 audit 和回归核验。

[版本登记剧本](adopt-source.yml)核对固定 run/集群、成功检查点原件 SHA、十节点健康和 worker02 原配置 SHA，仅允许上述两处执行源码的准确差异。旧 context 归档至原运行目录 `origin/pressure-fix-7d4e062/context.json`；旧/新实现 SHA、沿用成功断点和 pressure 未通过状态写入相邻 source-revision.json。主入口的源码一致性门禁保持严格。

本次尚未执行修复后的真实软驱逐；它由下一次 resume 验收，不补写 pressure PASS。

## 继续执行

```bash
# 进入已修复的仓库。
cd /Users/mario/SelfProject/cloud-native-platform-lab
# 指向原记录目录，读取已有成功检查点，不新建实验批次。
CNPL_REPLAY="/Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/records/2026-10-18-ansible-replay/runs/03-06-20261018T051927Z-ha-fix-20261018T063407Z"
# 先执行必要的只读前检，跳过 03 全部和 04 前五组，从未通过的 pressure 继续。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/replay-03-06.sh resume "$CNPL_REPLAY"
```

预期看到 `03/ha 已通过，跳过`、`04/memory 已通过，跳过`，随后 `WORKER02 RESTORE PASS` 和 `04 PRESSURE PASS`。之后继续 04 termination/cleanup、05、06；最终应出现 `ANSIBLE REPLAY ACCEPTANCE PASS` 和 `ANSIBLE REPLAY CLEANUP PASS`。已完成的 HA 不再要求关机。
