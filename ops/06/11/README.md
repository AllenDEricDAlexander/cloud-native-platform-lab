# 06.11 KubeVirt/CDI、持久化与迁移

覆盖 06.11.01–04。`run.sh validate|render|inspect-host|install <kubevirt|cdi>|apply|check|start|stop|restart|migrate|cleanup-plan`。inspect-host 仅对台账节点核对 FQDN/IP、SELinux、firewalld 和可读写 `/dev/kvm`，不启用嵌套虚拟化、不改 EVC、不加载模块。实际 ESXi CPU 暴露/许可证、EVC/硬件/内核兼容、预算与恢复材料另存 virtualization.evidence_file/SHA；没有 KVM 就阻塞，不静默使用模拟模式作性能验收。

锁定 KubeVirt/CDI Operator 与 CR 的本地包并按顺序安装；约束到授权 Worker，控制器特权、SCC/PSA/SELinux 兼容在包中审核。VM 专用 Namespace 明确标为 Privileged 例外，审计/告警仍为 Restricted，普通用户不能直接创建 Pod/hostPath；不能将此例外复制给普通业务空间。不要通过停用 SELinux/firewalld 解决问题。

apply 仅导入固定 Harbor Digest 的受控 containerDisk 到 1–10 GiB 的 Ceph DataVolume，带独立 registry Secret 与 CA 引用，VM 初始 Halted。CDI 导入器只允许内网仓库/目标存储的精确网络路径，禁止任意 URL/内部地址抓取。确认 DataVolume Succeeded/PVC Bound 后 start，访问控制台用显式 `virtctl ... console vm-demo` 单独交互，结束控制台再继续。

来宾中写带批次 ID 的文件和 SHA，依次 stop/start、restart 后比对；核对 VM→VMI→Pod→DataVolume/PVC→Ceph 对象及回收策略。check 只保存资源状态，不能证明来宾数据正确。热迁移先核对 CPU/EVC、目标节点网络、访问模式和 CDI/CSI 支持，填写 migration_evidence 和独立备份；脚本还检查 LiveMigratable。默认 RWO/固定单节点样例不声称可迁移，实际迁移须经审核改为受支持的共享存储/迁移路线与多目标节点约束，不能只执行 migrate 绕过限制。

退出先停来宾并保护数据，再删 VMI/VM，核对磁盘保留/回收，最后处理 DataVolume/PVC/后端；不直接删 Namespace 或 CRD。迁移失败保留源 VMI、目标事件和数据，不强制双挂 RWO 卷。本轮 VM、导入、迁移及来宾数据均未执行。
