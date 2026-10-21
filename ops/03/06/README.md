# 03.06 单故障与独立 Rook 对照

覆盖 03.06.01–06。离线 `bash ops/03/06/run.sh validate`。先完成 05 的已知数据集/哈希和独立备份，再以明确 fault.osd_id/approved 运行 osd-stop；恢复健康后才运行 osd-out。单次最多 60 秒，watchdog 最多 180 秒。

先验证 ok-to-stop、业务 I/O、原 OSD up/in，保存 run/FSID/集群 UID/OSD ID 的 recovery.json，再在 storage01 安排独立 systemd timer，最后注入故障。正常、命令失败和退出均恢复该 OSD/start/in 并等待健康；管理端掉线时 timer 恢复。SIGKILL 无法执行本地 trap，重连后运行 recover；timer 本身不保证 storage01 整机断电后的恢复，所以 VM 故障不复用此注入动作。失败的 recovery.json 保留；恢复未完成不得继续。

csi 先检查双副本再重建一个 controller Pod；csi-node 按 DaemonSet UID 和实际写入节点唯一选择节点插件，保存原 Pod 后重建。期间比较原挂载数据，等待所属控制器自动重建。并行从另一个终端运行 04 smoke，分别记录新供应和新挂载事件。单个 Pod 快速重建可能没有捕获供应中断，应如实标明，不能据成功挂载宣称已证实中断行为。

maintenance-plan 保存原标志与节点状态，输出 drain、cephadm maintenance、vSphere 重启及反向恢复顺序；vSphere 按项目约束由用户在 Web 控制台操作。vm-observe 有界收集 I/O/健康，用户按已审核计划在另一终端操作；失败立即恢复 VM，不自动触及电源。维护 flag/恢复限速不能仅靠会话 trap，必须先保存原值及独立到期撤销任务；本脚本默认不设置持久 noout 或修改全局限速。

quota 在独立 16MiB 配额池最多写 24MiB，必须观察实际 quota/full 拒绝才通过，随后删除自己已写对象，池及失败证据保留。不会填满真实 OSD/Datastore 来伪造 nearfull 测试。容量水位、重建压力与限速由只读健康/ceph df 记录，真实阈值告警与吞吐需现场测量。

对照动作依次为 managed-preflight → managed-deploy → managed-services → managed-check → managed-cleanup。主输入 managed.approved=true、inputs_file 指向同 schema 的独立集群配置、devices_file 指向独立设备列表。独立配置还需 managed.inventory_file（显式 ceph_comparison 组）、rook.values_file（仅监视 cnpl03-managed、自有驱动前缀/锁定镜像）。每条盘含 host/bytes/stable_id/hypervisor/approved/contains_data/evidence_file/evidence_sha256。必须三物理域、三独立主机，拒绝主集群地址和主 OSD 稳定 ID。

对照 CephCluster 明确 useAllNodes/useAllDevices=false、独立 dataDirHostPath，不设默认类；创建 BlockPool/Filesystem/ObjectStore CR 观察调谐。该集合还需使用 05 的数据用例按独立 SC 再跑一轮，managed-check 的健康检查不代表数据用例通过。清理前要求 PVC 全部由数据规程释放，随后按 ObjectStore/FS/Pool → CephCluster 删除，不启用自动 wipe、不强摘 Finalizer，Operator/CRD 和磁盘残留供人工核对。资源不足时保持未执行。
