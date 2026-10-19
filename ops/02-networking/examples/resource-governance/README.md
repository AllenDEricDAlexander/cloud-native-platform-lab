# 02.08 完整资源治理专题

先完成 02.07 all 与清理；然后管理 Mac 一次执行：

~~~bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
export LAB_RESOURCE_RECORDS="$PWD/ops/02-networking/records/02.08-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/resource-governance.sh all "$LAB_RESOURCE_RECORDS"
~~~

三行分别进入项目、绑定全新批次、执行全部可运行实验及自动恢复；不必逐小节发命令。

| 步骤 | 实际实验与预期 |
| --- | --- |
| 02.08.01 | 应用/构建/测试三个 Namespace 各有 ResourceQuota/LimitRange；缺失资源声明的 Pod 得到 CPU/内存/临时存储默认值；单独验证超过 Quota 和 LimitRange 的服务端拒绝，必须匹配具体拒绝原因 |
| 02.08.02 | 无 LimitRange 的独立 lab-qos 空间核对实际 Guaranteed/Burstable/BestEffort；192Mi 受控分配进入 64Mi 容器，记录 OOMKilled/137；不将 Pod OOM 当成节点内存压力或 QoS 驱逐次序证据 |
| 02.08.03 | 8 秒 CPU 忙循环受 100m 限额，要求 cgroup v2 nr_throttled/throttled_usec 实际增长；只向独立 emptyDir 写 32Mi、卷限额16Mi/Pod临时存储24Mi，等待 kubelet 报 Evicted；VM DiskPressure 保持 False |
| 02.08.04 | worker02 的真实 CPU 请求按普通容器、init、可重启 init 和 overhead 核算；低优先级预留 Pod 只保留 200m 请求余量；500m 高一级实验 Pod 触发实际抢占，记录被抢占 UID 与事件。两实验优先级均小于全部既有 Pod，拒绝可能影响既有 Pod 的配置 |
| 02.08.05 | 两 VM 各一副本；minAvailable=2 时按本批标签选择的 drain 因 PDB 失败；minAvailable=1 后允许驱逐选中 Pod，期间实际服务请求成功；精确恢复原 cordon 字段，等待双副本恢复；直接 UID 删除对照说明 PDB 不约束所有删除 |
| 恢复 | always 撤销本批维护标记/cordon，原 UID 删除五个实验 Namespace 和两个非默认 PriorityClass；校验原服务、Pod、网络配置与 .201 可信 TLS |

前检要求 worker01/02 的 MemAvailable 至少2Gi、kubelet文件系统可用空间至少10Gi。所有写盘数据在本批 emptyDir；不写真实数据盘，不关闭 SELinux/firewalld。BestEffort 样例为固定的轻量 HTTP 服务，刻意不定义 CPU/内存资源以核对 QoS；其他负载均有上限。三个工作模式在程序中另有限界：CPU≤20秒、内存≤256Mi、空卷写入≤64Mi。

**整 VM 内存压力下的 QoS 驱逐顺序保留 BLOCKED**：现有十 VM 承载主线，本入口不耗尽整 VM，不声称仅凭 QoS 可预测所有驱逐。Pod OOM、CPU 限流、空卷驱逐与 PDB/抢占都实际执行。passed.json 分开记录 available_cases_passed 与 phase_complete；blocked 项不算通过。

文件：[全套 YAML 与顺序](../../networking/resource-governance)、[Ansible 独立入口](../../ansible/playbooks/resource-governance.yml)、[验收器](../../tests/integration/resource-governance/check.py)、[有界 Go 负载](main.go)。复用已有 Ansible 编排，无额外运行服务或工具依赖。

各命令作用和预期：

- kubectl get / SSH 只读 /proc/meminfo、文件系统余量：计算请求预算、检查 VM 安全余量；不读取秘密。
- go build / crane digest：重建并核对已锁定的 amd64/arm64 诊断程序与匿名镜像摘要。
- kubectl apply --dry-run=server：所有 YAML 先校验；在实际预算空间再做两类预期拒绝。
- kubectl logs：读取本批 CPU cgroup 计数；OOM/磁盘结果用本批 Pod UID 和状态判断，不把命令错误当作压力结果。
- kubectl patch node --type=json：校验原 UID/resourceVersion，只设置本批维护标记与 cordon；恢复时要求该标记仍属于原 run。
- kubectl drain --pod-selector=本批run,app=pdb-demo：只驱逐本批 PDB Deployment 的后代，不使用 force/disable-eviction/delete-emptydir-data。预算拒绝必须匹配 PDB 原因。
- kubectl delete --raw：UID 前置条件保护本批对象；删除 controller 子 Pod 前检查 ReplicaSet→Deployment 的原 UID 链。

正常预期：所有可运行结果通过、CLEANUP PASS、failed/unreachable/rescued/ignored=0；whole_vm_pressure=BLOCKED、phase_complete=false。

失败或中断后，用原目录恢复：

~~~bash
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/02-networking/scripts/resource-governance.sh recover "$LAB_RESOURCE_RECORDS"
~~~

恢复不重跑压力。节点字段被外部维护修改时停止覆盖并保留证据；回执、每个命令、cgroup计数、驱逐/抢占事件与原资源快照都保存在批次目录。
