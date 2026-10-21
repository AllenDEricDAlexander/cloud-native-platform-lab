# 06.09 CAPI/CAPV 第二集群

覆盖 06.09.01–05。`run.sh validate|render|plan|install <capi|capv>|apply|check|destroy|cleanup-plan`。render 只输出本批管理空间和网络计划，真正 Cluster/Provider 模板必须在 vCenter、许可证、VM 模板及 Provider/Kubernetes 版本现场锁定后生成，放仓库外 `capi.bundle_file/sha256`；不能根据主集群推断第二集群。主集群仍由 kubeadm 管理，绝不 CAPV 收编。

plan 完全离线：检查第二集群预留段、节点/VIP 唯一、Pod/Service/LAN/主集群/已登记 VPN 无重叠，并校验容量回执 SHA。回执需明确 primary_minimum_preserved、storage_recovery_headroom、dhcp_conflicts_absent、vsphere_license_verified、template_verified、vpn_routes_reviewed 为 true，且 node_ips/api_ip/vm_folder 与输入一致。DHCP、路由和实际容量仍须连接内网后复验，不能仅凭预留段保证空闲。

明确 `capi.management_target=primary|management`，按锁定本地 provider 清单依次安装 CAPI/CAPV，凭据仅有独立文件夹/资源池权限。用所选版本本地模板/clusterctl 本地仓库生成完整 Cluster、VSphereCluster、KubeadmControlPlane、MachineDeployment 和机器模板；使用已有受限身份引用，不把明文 Secret 加进包。apply 拒绝其他类型/空间、主集群名、错网络、缺少引用及文件夹不符的模板；服务端 dry-run 通过才创建。

观察 Machine→VM→bootstrap→CNI→Ready 的分层结果，保存 VM UUID/磁盘/节点/API UID 台账。CNI 使用第二集群自己的上下文/cluster ID/CIDR/预算，不能复用主集群现有部署而错指目标。check 同时核对管理面对象与真实 secondary 节点。只有 CR 而 VM 失败不算创建成功。

扩容/修复/升级先保存 MachineDeployment UID、原 replicas/version/template 引用，仅变本批目标：`kubectl -n <本批空间> scale machinedeployment/<本批名称> --current-replicas=<原值> --replicas=<0到3>`；观察实际 VM 数与 Machine 状态，再测试一个受控 Worker 故障及 MHC。替换模板/升级使用新版本不可变模板并按 CAPV 支持流程逐台，不能认为装 CAPI 就已启用节点自动扩缩。

管理状态备份须含生命周期 CR、必要 Secret/PKI 和 Provider 版本，在仓库外加密保存并验证迁移/恢复；迁移命令的暂停/源对象删除语义先按该版本帮助核对，不将管理面备份误当工作负载数据备份。destroy 还要求真正独立备份、管理状态备份 SHA，以及现场复制到输入的 approved_cluster_uid；只删除本批 Cluster UID，不删 Namespace/主集群/Ceph。等待 owner/finalizer 完成，再按 VM UUID 核查孤儿盘、VIP、DNS 和凭据，不移除未知 Finalizer。本轮 vCenter/第二集群均未访问。
