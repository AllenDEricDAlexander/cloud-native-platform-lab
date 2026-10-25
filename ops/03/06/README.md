# 03.06 单故障与恢复

覆盖 03.06.01–06。离线 `bash ops/03/06/run.sh validate`。先完成 05 的已知数据集/哈希和独立备份，再以明确 fault.osd_id/approved 运行 osd-stop；恢复健康后才运行 osd-out。单次最多 60 秒，watchdog 最多 180 秒。

先验证 ok-to-stop、业务 I/O、原 OSD up/in，保存 run/FSID/集群 UID/OSD ID 的 recovery.json，再在 storage01 安排独立 systemd timer，最后注入故障。正常、命令失败和退出均恢复该 OSD/start/in 并等待健康；管理端掉线时 timer 恢复。SIGKILL 无法执行本地 trap，重连后运行 recover；timer 本身不保证 storage01 整机断电后的恢复，所以 VM 故障不复用此注入动作。失败的 recovery.json 保留；恢复未完成不得继续。

csi 先检查双副本再重建一个 controller Pod。csi-node 仅选择 cp01 无活动 PVC 的节点插件，按 Driver/DaemonSet UID 核验后重建，再重挂该节点原 smoke PVC 并读回；存在活动 PVC 就拒绝。用户态映射进程随节点插件存活，不能把该空闲节点用例说成活动映射崩溃恢复通过。两项本批均已通过，但没有证明新供应必然中断。

maintenance-plan 保存原标志与节点状态，只给出维护顺序；本批未执行正式 drain/cephadm maintenance。vm-reboot 需明确 fault.vm_host、vm_reboot_approved 和已完成数据库备份回执，只在选定客户机内执行 systemctl reboot，并安排独立 OSD 恢复 timer；不调用虚拟化接口。vm-observe 只作有界观测。维护 flag/恢复限速不能仅靠会话 trap，必须先保存原值及独立到期撤销任务；默认不设置持久 noout 或修改全局限速。

本批 storage02 客户机重启未在原定 600 秒窗口内恢复，原始失败证据 `1wxRN6` 保留。随后发现 CSI 用户态映射内存不足及一个无进程/无挂载的陈旧 NBD；提高节点插件内存后，使用 `stale-nbd.sh inspect|apply` 逐项核验所有 mount namespace、PID、holder、分区及活动映射，仅解除该陈旧设备，未删除后端镜像。Ceph 已恢复 HEALTH_OK，`reboot-check.sh verify` 读回四套 PostgreSQL、6 个确认事务和 Kafka 原始 40 条消息。原窗口仍为失败，修复后未重复重启，不宣称重启时限已通过。故障注入开关交接时关闭。

quota 在独立 16MiB 配额池最多写 24MiB，必须观察实际 quota/full 拒绝才通过，随后删除自己已写对象，池及失败证据保留。不会填满真实 OSD/Datastore 来伪造 nearfull 测试。容量水位、重建压力与限速由只读健康/ceph df 记录，真实阈值告警与吞吐需现场测量。

用户已取消 03.06.04–06 独立 Rook 自管理对照，本批 `managed.approved=false`，未创建 `cnpl03-managed`，不等待新 VM。03.04 已运行的 Rook External/Ceph-CSI 卷接入继续保留。下述 managed 模板仅留作项目参考，不在本轮执行范围。

对照动作依次为 managed-preflight → managed-deploy → managed-services → managed-check → managed-cleanup，必须有另行批准的独立配置、inventory 和空盘，不能复用当前 OSD 或推断目标。

对照 CephCluster 明确 useAllNodes/useAllDevices=false、独立 dataDirHostPath，不设默认类；创建 BlockPool/Filesystem/ObjectStore CR 观察调谐。该集合还需使用 05 的数据用例按独立 SC 再跑一轮，managed-check 的健康检查不代表数据用例通过。清理前要求 PVC 全部由数据规程释放，随后按 ObjectStore/FS/Pool → CephCluster 删除，不启用自动 wipe、不强摘 Finalizer，Operator/CRD 和磁盘残留供人工核对。资源不足时保持未执行。
