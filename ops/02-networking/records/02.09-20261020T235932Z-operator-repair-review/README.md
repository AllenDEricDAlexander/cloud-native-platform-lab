# 02.09 Operator 配置更新、失败汇总与后续脚本复核

本记录仅证明修复交付、模型与服务端预览通过。**没有执行正式 all，没有切换 VM 数据面，也没有取得 L2/BGP 运行时验收。** 外部 BGP 转发继续 BLOCKED。

原 VM 批次 `02.09-20261020T230854Z` 在第14步 l2 失败：完整日志第777行，`l2 未收敛：L2 VIP 不符`，后续自动回退和清理通过。原目录与原日志保持。新汇总对该日志的回放见 [previous-failure-summary.txt](previous-failure-summary.txt)。

## 修复内容

- 四个 Helm profile 均启用 `operator.rollOutPods=true`。复用官方 Chart 的 ConfigMap checksum；切换时保存旧 Operator Pod UID，随后核对本次 Helm 实际 manifest、ConfigMap、Deployment 与全部新 Pod 的 checksum/Ready/UID，不能只凭 Agent 就绪放行。
- 漂移保护只新增允许修改 `operator.rollOutPods`，其余 Operator 值仍受保护；原 revision 的恢复逻辑保持。旧批次的摘要算法兼容，并已对原失败 VM 批次执行只读 guard 验证。
- L2 保存池/Service/Lease 原始状态，核对池无冲突与 VIP；由 cp01 发起新鲜 ARP，核对宣告 Worker 的 VM MAC，避免以 Mac 的旧缓存判断迁移。迁移和恢复期间 VIP 必须保持，撤回策略后连续三次 ARP 无响应才通过。Mac 仍实际请求 HTTP。
- BGP 模式切换前按原 UID 删除本批 L2 Service，避免旧 VIP 归属混入下一阶段。FRR 补 `ip nht resolve-via-default`，使用 bgpd 查询作为 readiness；保持 zebra 与 bgpd `-n`、只读0644配置及限定前缀过滤。RIB 必须恰好包含两 Worker PodCIDR 和当前 BGP VIP /32，路径须 valid；撤回广告后两个会话仍须 Established，RIB 才能以清空判定通过。
- `Session.wait` 在 always 回收前保存限时诊断，采集异常不覆盖原失败；入口退出时将首个失败、任务来源、原错误、日志行号与本次清理结果追加到日志末尾，并另存汇总 JSON。保留原退出码；旧 closed.json、预览中的 skipping 或回退成功都不能掩盖本次失败。未进入实验的入口错误不会误导用户执行恢复。

沿用既有计划→命令→取证→always 编排与 Session 扩展点；直接补充具体检查，没有新增依赖或并行编排层。

## 验证结果

| 检查 | 结果 |
| --- | --- |
| 数据面与 Mac 禁用边界单元测试 | 31项通过 |
| 公共入口、批次与汇总单元测试 | 10项通过，含实际 Shell 退出码与日志末尾检查 |
| 真实 Ansible 模型 | 7类通过：正常、L2失败、命令失败、预检失败、显式恢复、回退失败、实验与回退同时失败；只调用临时模型命令 |
| 原失败日志回放 | 首个错误=l2，第777行；退出失败与 cleanup PASS 同时保留 |
| Shell / Ansible 语法 | 通过 |
| 最终 validate 完整入口 | `ansible-validate-20261021T001434Z-oHWMUo`：ok=5、changed=0、failed=0；末尾汇总正常 |
| 内置对象 / CRD 服务端预览 | 20 / 25项通过 |
| 自定义对象 | 8项 OpenAPI 结构通过；另在已安装 CRD 上完成8项实际 CEL/admission server dry-run，通过且未持久化 |
| Helm profile | 四种模式均有不同的 Operator 配置 checksum |
| 前后状态 | 集群UID、Helm revision 8、值/manifest、Cilium配置与101个受保护资源摘要完全一致；无实验空间 |

[delivery-review.json](delivery-review.json) 汇总最终结果，[validation.json](validation.json) 与 [custom-server-dry-run.json](custom-server-dry-run.json) 区分结构校验和实际准入预览，[source.json](source.json) 记录最终输入摘要。详细 attempt 与模型日志保留在本地，按仓库规则不强制加入 Git；[evidence-sha256.json](evidence-sha256.json) 保留文件摘要。

较早的两份 validate 日志保留为开发记录，不作为最终入口验收。其中首次校验的任务通过后，入口尚未退出时被编辑，干扰了 Shell 收尾；已固定源码重新验证。最终输入与当前源码摘要一致。

## 完整重跑

~~~bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
export LAB_DATAPLANE_RECORDS="$PWD/ops/02-networking/records/02.09-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/dataplane.sh all "$LAB_DATAPLANE_RECORDS"
~~~

三行分别进入仓库、建立全新证据批次、一次完成22步和自动回退清理。正常应为 failed=0、`available_cases_passed=true`、`cleanup_passed=true`；`phase_complete=false` 保留外部 BGP 转发缺口。不要复用原失败目录或本 validate 目录。

若中断且末尾显示清理未确认，用同一原目录恢复：

~~~bash
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/02-networking/scripts/dataplane.sh recover "$LAB_DATAPLANE_RECORDS"
~~~

脚本、YAML、全部步骤和执行边界见[完整执行说明](../../examples/dataplane/README.md)。目标始终为登记的 .101–.110 VM 主集群。
