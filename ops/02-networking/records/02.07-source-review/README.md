# 02.07 执行前核验

完整 VM 调度专题已实现，实际集群实验未执行。validate 已在原十 VM 集群完成全部清单 strict server dry-run，未创建实验空间、Pod 或节点标签/污点。

核验包含：四项调度边界回归、两项共享批次/原 UID 回归；真实 Ansible 的正常、故意观察失败、显式恢复三条离线分支；模型额外校验预期命令 rc=1 不被错误当作执行失败。结果见 runtime-tests-final.txt、scheduling-tests.txt、offline-results.json 及各次原始 Ansible 日志。

节点 NoExecute 前检确认 storage03 当前所有非实验 Pod 都无限容忍测试污点。正式执行会再次检查；节点原 UID/标签/污点写入 context，JSONPatch 受原字段保护，失败走 always 恢复。不会使用物理宿主机标签。

正式使用 [完整指南](../../examples/scheduling/README.md) 的一个 all 命令；先实际完成 02.06 与清理，回执由脚本自动查找，无须再手动归档才进入下一步。
