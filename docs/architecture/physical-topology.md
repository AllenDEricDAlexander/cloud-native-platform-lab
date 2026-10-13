# 物理拓扑与虚拟机放置

以下沿用原规划，均为待现场核实的设计值。主机身份和计划放置以 [hosts.yaml](../../inventory/hosts.yaml) 为准，规格以 [resources.yaml](../../inventory/resources.yaml) 为准。

## 1. 三台 ESXi 与十节点

| 物理宿主机 | 规划内存 | ESXi / iDRAC | Kubernetes VM | 节点内存合计 |
| --- | --- | --- | --- | --- |
| esxi01 | 128 GiB | 192.168.9.61 / .51 | cp01、storage01、infra01、worker01 | 52 GiB |
| esxi02 | 64 GiB | 192.168.9.62 / .52 | cp02、storage02、infra02 | 36 GiB |
| esxi03 | 64 GiB | 192.168.9.63 / .53 | cp03、storage03、worker02 | 40 GiB |

三个控制平面分别落在三台物理机；三个 Ceph VM 同样分散。storage 节点同时是受限 Kubernetes Worker，cephadm 守护进程仍由主机管理，资源须在 kubelet 外预留。

## 2. 集群外基础服务

OpenWrt、DNS、Harbor、GitLab、Nexus 和管理机另外建 VM 或使用已核实的独立服务位置，不占用“十个 Kubernetes 节点”的数量。起步内存预算为 2、2、8、16、8、4 GiB；放置在核算剩余容量后决定，不默认全部塞入 esxi01。

基础服务的 OS 和数据使用 ESXi 本地 Datastore；不使用待建 Ceph 保存它们的唯一启动盘、镜像和数据库。vCenter 地址与资源未知时保留为空，不能假设仅有 ESXi 登录权限就能使用 vSphere Provider 或 CAPV。

## 3. 创建与初始化顺序

1. 从现有管理终端核实 CPU/EVC、ESXi/vCenter 版本、许可证、Datastore 和 Port Group，划定禁止改动的既有 VM/磁盘。
2. 用校验过的 Rocky Linux 10 ISO 创建最小模板，配置 VMXNET3、open-vm-tools；先验证客体实际 CPU 能力与重启。
3. 为克隆准备首次启动身份生成机制，验证两个测试克隆的 MAC、UUID、machine-id、SSH host key 各不相同。
4. 准备管理执行器、DNS/CA/仓库 VM；从已验证模板创建十台节点，按角色附加系统、运行时与计划数据盘。
5. 完成 [00 节点初始化](../plans/00-preparation/node-bootstrap.md)，再交给 01 的 kubeadm。OS/CRI 不能留到入群时才首次配置。

## 4. 故障边界

节点标签 `lab.egon.top/esxi-host` 必须对应实际宿主机；迁移 VM 后同步台账和标签。单控制平面故障、单 ESXi 故障、磁盘故障分别验收，不能互相替代。

本地 Datastore 不提供自动共享磁盘。API 保持可用也不意味着故障宿主机上的全部 VM 能在别处接管。只有核对共享存储、可迁移性、许可证与剩余资源后才能安排对应恢复实验。

OSD 盘必须记录“Ceph OSD → 客体设备稳定 ID → VMDK/RDM → Datastore → 物理盘/RAID → ESXi”。未知映射时不初始化；RAID 上 VMDK 的故障实验只证明该虚拟存储路径。
