# 06.15 相邻次版本、逐节点升级与失败恢复

覆盖 06.15.01–09。`run.sh validate|plan|inspect|drain|upgrade-node|complete-node|cleanup-plan`，没有跨节点自动循环。当前/目标必须为精确 v1.x.y 且次版本只加一；计划中的 1.36→1.37 仅候选，本轮不选择补丁、不下载 RPM、不修改版本主锁。

先完成隔离预演与兼容矩阵：etcd/containerd/Cilium/Ceph/Rook/CSI/Gateway/Operator/API 弃用逐项证据为 true，源目标版本相同，预演包含真实业务数据。plan 只离线核对矩阵、预演、冻结文件 SHA 并列顺序：cp01→cp02→cp03→普通 Worker→infra→storage。目标 RPM 另登记 `versions.lock.components.kubernetes_upgrade.version`（无 v）与三个实际 SHA，不能提前把当前运行版本改成目标。

每次只选择 upgrade.node。freeze 回执绑定该节点且 15 分钟内，确认 frozen/pdb_reviewed/independent_backup_restored、etcd_healthy_members=3、ceph_health=HEALTH_OK；必须附现场采集来源，静态 true 不能代替真实健康。对存储共置节点，还须完成 03 的 Ceph 维护、数据保护和水位检查，前一节点完全恢复后才继续。备份必须含 PKI/加密配置/etcd及独立业务数据，不能只靠 VM 快照。

drain 不使用 --force/--delete-emptydir-data，不绕过 PDB；失败留下 pending，节点仍待排查。upgrade-node 要求同一节点 UID 和已 cordon，将审核 RPM 复制到新私有节点目录、传后 SHA/签名/包名/版本复验，只用本地禁仓库 dnf 安装；缺依赖立即失败，不临时联网补包。首 CP 执行 plan/apply，其他 CP/Worker 执行 upgrade node，更新 kubelet/客户端后保持 cordon。

真实 API/etcd、DNS、跨节点/ClusterIP/VIP、网关、PVC/快照、数据库/消息、七语言/CI/GitOps、HPA、安全与观测回归另执行并保存 regression_file/SHA（node/uid/target_version/checks/ceph_health）。complete-node 只有版本、Ready 和回归材料通过才按 UID/resourceVersion 解 cordon，登记完成后才允许下一台。自动化不会自行将测试 false 改为 true。

Memory QoS/Feature Gate 在独立 Worker、可丢弃应用上逐项对比：记录目标版本、默认开关、cgroup v2 保护、回收/OOM/延迟和 VPA 行为，不能把目标版本号等同已启用。Rocky/containerd/Cilium/CSI/Ceph 升级各开窗口，按其版本支持顺序和管理权操作，禁止同日一次升级多个关键层。

失败停在当前 pending 节点，保留 RPM、kubeadm、static Pod、etcd/CSI 和业务证据；部分升级后的重跑由人工按该版本支持流程判断，本脚本不盲目继续、安装旧包或自动降级。隔离预演中的故障恢复按 17 的原状态/新集群路线，不将备份 PKI/历史钥丢弃。现场 quorum/Ceph/回归不满足时不 drain、不继续。本轮所有升级动作未执行。
