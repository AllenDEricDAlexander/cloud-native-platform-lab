# 03.02 离线走查（2026-10-21）

- `bash ops/03/validate.sh`：全部现有 Shell、JSON/YAML、三个 Ansible Playbook 语法检查通过。
- `git diff --check -- ops/03`：通过。
- 无锁定物料调用 `image ceph`：按预期拒绝，未触发 SSH 或拉取。
- 核查 OSD 明确选择、三物理域、管理身份位置、失败保留 FSID、SSH 公钥限制与私密备份输出；修正编排命令统一从 storage01 发送。
- cephadm/Podman/Ceph/CRUSH 命令参数、包版本与真实 OSD 行为未在内网验证；执行前必须补齐 compatibility_file 和台账，先运行 osd-plan 检查实际选盘。
