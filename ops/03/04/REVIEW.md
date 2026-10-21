# 03.04 离线走查（2026-10-21）

- `validate.sh`：Shell、JSON/YAML、四个 Ansible Playbook 语法通过；diff 检查通过。
- 核查导出秘密只留远端、导入拒绝管理员身份、External 模式不声明 OSD、StorageClass 初始不抢默认、十节点 MON 检查与真实卷挂载区分。
- 所选 Rook/CSI 的实际 Helm values、export/import 契约、驱动 Secret/caps、CRD 与 K8s 兼容性待连接内网核实。禁止把离线通过当成该兼容性已确认。
- 未执行 helm template/install、kubectl、SSH、CSI 或挂载测试。
