# 03.01 离线走查（2026-10-21）

- `bash ops/03/validate.sh`：通过 Shell、JSON/YAML 重复键和 Ansible syntax-check。
- `bash ops/03/01/run.sh validate`：通过，未执行任务。
- 默认输入执行 `budget`：按预期拒绝，原因是主台账尚未批准 OSD 初始化；没有尝试连接 VM。
- `git diff --check -- ops/03`：通过。
- 已逐项检查无自动选盘、无签名清除、无分区/格式化、无服务启动。容量和三物理域依赖真实台账及映射证据，尚未验证。
- `disk-inventory.sh --self-test` 只验证占用分类；`all` 在检查后执行预算，未批准设备时失败并保留只读证据。

## 2026-10-23 内网 VM 范围验收

用户明确选择只核对三台 VM，failure_domain=host；三台新增 1 TiB 盘的 by-id、空盘状态及容量预算整组通过，六块系统/containerd 占用盘的实际负向检查全部拒绝。现有节点安全与资源基线保留。物理故障域和底层 Datastore 余量未验收。结果与原始输出见 [03.01–02 验收](../02/records/ceph03a/acceptance-20261023T074608Z-7ufobl6q/README.md)。
