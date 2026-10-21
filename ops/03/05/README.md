# 03.05 卷生命周期

覆盖 03.05.01–06。离线 `bash ops/03/05/run.sh validate`；现场按 deploy → static → write → recreate → access → expand → snapshot → clone → snapshot-policy → reclaim → migrate → stateful → check 执行。先确认 04 CSI/快照控制器和 probe Digest 可用。临时卷/静态卷/恢复卷合计至少另留 12Gi 逻辑配额，Retain 后端仍占空间。

workloads.yaml 为正式清单，执行前把固定引用替换为本批 StorageClass 和锁定 probe Digest，未配置镜像不能执行。测试数据为 run_id 加 1000 个连续序号，ConfigMap 保存块/文件哈希，重建、扩容、迁移、快照和克隆都比较原哈希。CephFS 两 Pod 固定在不同 Worker；RWO 同节点可多 Pod，跨节点必须观察 Multi-Attach 拒绝；RWOP 的第二 Pod 必须因独占约束被拒绝，不能把镜像/调度错误误判为访问模式通过。

static 预建本批 RBD 镜像，PV 明确 staticVolume/imageName/Secret 和 Retain，再测试静态绑定和不匹配 PVC Pending。expand 比较 PVC/PV 2Gi 与应用实际文件系统容量；不尝试缩容。snapshot 在没有并发写入的文件用例中 sync 后恢复，不代表数据库事务一致性；类为 Retain，原快照及 backend 保留。clone 单独使用 PVC dataSource。

reclaim 只对两个专用临时卷比较 Delete/Retain；先从 CSI 写入的 PV 元数据唯一定位 RBD 镜像，不能从字符串猜 UUID。Delete 同时等待 PV 和后端消失，Retain 必须 Released 且镜像仍在。若所选 CSI 未写该元数据，则停止并按真实后端元数据补齐映射，不能把“查不到”当成“已删除”。StatefulSet 明确缩容/删除保留 PVC，重新创建后核对每个 ordinal 的数据。

migrate 只做正常停止、等待 VolumeAttachment 解除，再调度另一 Worker；节点失联时没有 fencing 证明就不做强制删除/分离。任何失败先保留 PVC/快照和事件。cleanup 只停止本批工作负载，**不会删除持久数据**。清理后端需先核对具体 PV UID、CSI handle、镜像元数据、挂载/快照和数据批准，再逐项操作；脚本不批量擦除池或摘 Finalizer。

snapshot-policy 在没有其他卷/快照操作的受控窗口比较 Delete/Retain：同时记录 SnapshotContent 和 RBD 池内镜像/快照对象集合；Delete 须回到创建前集合，Retain 须保持创建后集合。并发变化会让检查失败，停止调查，不用猜测命名规则来删除对象。Retain 快照仍在原 Ceph，不计独立备份。04 smoke PVC 的留存同样要计入台账。所有真实挂载/扩容/恢复结果仍待内网测试。
