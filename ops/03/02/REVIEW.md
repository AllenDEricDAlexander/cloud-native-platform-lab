# 03.02 离线走查（2026-10-21）

- `bash ops/03/validate.sh`：全部现有 Shell、JSON/YAML、三个 Ansible Playbook 语法检查通过。
- `git diff --check -- ops/03`：通过。
- 无锁定物料调用 `image ceph`：按预期拒绝，未触发 SSH 或拉取。
- 核查 OSD 明确选择、三物理域、管理身份位置、失败保留 FSID、SSH 公钥限制与私密备份输出；修正编排命令统一从 storage01 发送。
- cephadm/Podman/Ceph/CRUSH 命令参数、包版本与真实 OSD 行为未在内网验证；执行前必须补齐 compatibility_file 和台账，先运行 osd-plan 检查实际选盘。

## 2026-10-23 三台 VM 实际验收

Ceph/cephadm 20.2.4、Podman 5.8.2 在三台 Rocky VM 中完成部署。3 MON、2 MGR、3 OSD，HEALTH_OK，PG active+clean；host 规则、size=3/min_size=2、MGR 切换和 Mac 加密管理备份九项材料读回均通过。Kubernetes 十节点 Ready，三台 SELinux Enforcing/firewalld active。运行中修复远端 stdin、预览未就绪误判、FQDN 放置和本批 SSH 公钥来源限制；旧失败证据保留。详见 [验收报告](records/ceph03a/acceptance-20261023T074608Z-7ufobl6q/README.md)。本轮不代表完整集群恢复、业务存储或 CSI 验收。
