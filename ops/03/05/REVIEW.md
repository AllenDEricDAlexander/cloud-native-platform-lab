# 03.05 离线走查（2026-10-21）

- `validate.sh`：全部现有 Shell/YAML/JSON/Ansible 语法通过；diff 检查通过。
- 修正通用清单入口对 PersistentVolume 的集群作用域识别。
- 逐项走查静态/动态供应、序号哈希、RWO/RWOP/RWX、三层扩容、快照/克隆、Snapshot/PV 回收、正常迁移及 StatefulSet 保留语义。
- 负向用例检查实际拒绝事件，回收检查包含后端；失败和正常 cleanup 都保留持久数据，不强拆失联写入者。
- 未连接 API/Ceph，未执行挂载、格式化、扩容、删除或恢复。CSI 元数据/快照实现、RWOP 支持、PV/PVC 实际行为待内网验证。
