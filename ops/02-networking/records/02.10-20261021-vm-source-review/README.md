# 02.10 完整 VM 脚本交付核验

**源码、模板和 VM 前置核验通过；正式 Istio/SPIRE 实验待操作者运行 all。** 本目录不是运行验收，不含正式 passed.json 或清理回执。

02.09 真实 VM 整组及恢复已归档到 `02.09-20261021T122923Z-agent-final`，提交 `7b5dbf7`；本轮补齐 completed/02.09.json 与计划状态，并实现现有 VM 的完整 02.10。Mac 只作管理端。

## 已执行验证

| 项目 | 结果 |
| --- | --- |
| VM 前检与严格预览 | 最终 validate 的 changed=0/failed=0；96 个内置对象/CRD、9 个自定义结构；十 VM、主 TLS、Worker 内存/磁盘/CNI/端口及 kubelet TLS 通过 |
| Python | 23 项 mesh 边界/注入/归属/恢复测试与 10 项公共阶段回归通过 |
| Go | 身份程序 race、vet 和真实本地 TLS 正反向单元测试、HCL 语法通过；没有连接 VM Workload API |
| 物料 | 八个 amd64 归档/config/平台与工具/原 Chart 文件集合及内容摘要通过 |
| Ansible | 两个 playbook 语法、Worker inventory 恰好两台、Shell 语法通过 |
| 编排模型 | 正常、观察失败、命令失败、预览失败、原批恢复、回退失败、双重失败七种模型通过；故意失败日志的 failed 非零是预期，不是正式集群运行结果 |
| 实际工具补查 | 两 Worker 中缺失镜像的 crictl 返回 no such image；现改用实际验证过的 ctr -q 精确别名查询，首次缓存为空 rc=0；未导入镜像/启动 Pod |
| 原主线 | 02.09 恢复后的 Cilium values/manifest/ConfigMap 摘要及主 Service UID 与最终前检一致 |

机器汇总见 [result.json](result.json)，模型结果见 [offline-results.json](offline-results.json)，模型日志见 models/。早期预检记录保留本地，本目录只归档最终核验和选定证据。

## 实现与运行边界

复用公共批次编排和命令/UID 回执，VM 适配层复用已有只读观察；部署变更交给 Ansible。运行清单共 24 步，覆盖 Sidecar、Ambient/waypoint、mTLS/身份授权、超时/重试、跨 VM 与延迟/CRI 计数，及 SPIRE PSAT、签发、轮换和撤销。恢复先退应用，再撤组件/本批全局对象、还原 Cilium/主机 socket/临时规则并复核原主线。

未安装 Istio/SPIRE、未修改 Cilium、未启动正式 all；实际代理启动、xDS、mTLS、轮换、撤销和恢复验收需由正式 all 的真实回执证明。缺失的 SA/CRD/CEL 准入明确延期到依赖安装之后。Trace/SLO、发布联动和身份联合/网格集成仍保持待回访。

[全部文件、命令、逐项作用与预期](../../examples/mesh/README.md)。
