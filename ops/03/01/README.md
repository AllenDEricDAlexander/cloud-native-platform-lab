# 03.01 设备与保护边界

覆盖 03.01.01–04。`validate` 完全离线；`inspect` 连接三台已登记 storage VM，只读检查；`budget` 根据已批准的设备与主台账计算容量，不连接主机。

```bash
bash ops/03/01/run.sh validate
# 连接内网后，先准备仓库外 local.json 的 run_id，再运行：
CNPL03_INPUTS=/受控路径/local.json bash ops/03/01/run.sh inspect
```

首次 inspect 允许设备清单为空，用 lsblk/HCTL/serial 获取候选线索；这不代表任何盘已批准。vSphere 控制台逐项核对 VMDK、Datastore、RAID、ESXi，更新主台账的 actual_hypervisor、osd_device_ids 和 resources.yaml 的初始化批准，再填写 devices.local.json。每条设备需 host、stable_id、bytes、hypervisor、datastore、backing_disk、raid、contains_data=false、approved=true、evidence_file、evidence_sha256。证据为现场确认记录，不能用计划替代。

`CNPL03_DEVICES=/受控路径/devices.local.json bash ops/03/01/run.sh budget` 检查三独立域和完整映射。三副本理论上限不作承诺；失一域后两个域不能重建第三个独立副本。额外核对快照、日志、Datastore 实际余量，pool_quota_bytes 必须低于预算。

主机的 systemReserved.storage=5Gi 已包含 Ceph 4Gi，不能重复计算。默认单 OSD 2Gi，仅为显式起始上限；增加 OSD/MDS/RGW 前重新核算。inspect 失败时保留证据，不执行 wipefs/zap。所有运行结果在本目录 records/<run_id>/，不入 Git。
