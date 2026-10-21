# 03.01 离线走查（2026-10-21）

- `bash ops/03/validate.sh`：通过 Shell、JSON/YAML 重复键和 Ansible syntax-check。
- `bash ops/03/01/run.sh validate`：通过，未执行任务。
- 默认输入执行 `budget`：按预期拒绝，原因是主台账尚未批准 OSD 初始化；没有尝试连接 VM。
- `git diff --check -- ops/03`：通过。
- 已逐项检查无自动选盘、无签名清除、无分区/格式化、无服务启动。容量和三物理域依赖真实台账及映射证据，尚未验证。
