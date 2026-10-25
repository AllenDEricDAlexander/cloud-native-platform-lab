# 03.01 设备与保护边界

覆盖 03.01.01–04。`validate` 完全离线。`all` 是内网整组入口：只读检查三台 storage，列出每块整盘的 by-id、HCTL 和占用，再计算已批准设备的容量。`inspect` 与 `budget` 仍可单独执行。

首次添加 OSD 盘见 [vSphere 加盘、稳定 ID 与逐台维护说明](ADD-DISKS.md)，其中附本轮现场结果和 03.02 动作顺序。

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
export CNPL03_INPUTS="$HOME/cnpl-phase03/local.json"
export CNPL03_DEVICES="$HOME/cnpl-phase03/devices.local.json"
bash ops/03/01/run.sh all
```

设备清单为空时仍完成整盘识别。`eligible_for_osd` 只表示未见文件系统、挂载、LVM 或 holder，且存在 by-id；脚本不把它写成批准。系统盘和 containerd 盘标记为占用。每条设备登记 host、stable_id、bytes、contains_data=false、approved=true、evidence_file、evidence_sha256，并与主台账 osd_device_ids 及 resources.yaml 的批准对应。rack 模式还需核对并登记 hypervisor、datastore、backing_disk、raid。证据为现场确认记录，不能用计划替代。

`CNPL03_DEVICES=/受控路径/devices.local.json bash ops/03/01/run.sh budget` 检查设备批准与容量。默认 ceph.failure_domain=rack，要求三实际物理域及完整 VMDK/Datastore/RAID 映射；显式选择 host 时，只按三台 VM 验证，不要求或声明物理放置已确认。2026-10-23 用户明确选择本轮 host 范围，三台各 1 TiB、总原始容量 3 TiB，理论三副本容量 1 TiB，65% 预算约 665.6 GiB。三副本理论上限不作承诺；失一域后两个域不能重建第三个独立副本。

主机的 systemReserved.storage=5Gi 已包含 Ceph 4Gi，不能重复计算。默认单 OSD 2Gi，仅为显式起始上限；增加 OSD/MDS/RGW 前重新核算。inspect 失败时保留证据，不执行 wipefs/zap。所有运行结果在本目录 records/<run_id>/，不入 Git。
