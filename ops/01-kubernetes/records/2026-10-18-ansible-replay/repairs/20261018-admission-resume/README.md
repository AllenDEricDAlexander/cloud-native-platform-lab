# 保留现场时的准入前检修复

用户在修复版目录 `03-06-20261018T051927Z-ha-fix-20261018T063407Z` 继续执行，前检因 `create --dry-run=server` 遇到既有 `p03-ha` 返回 AlreadyExists。保留失败现场是预期行为；把“创建”语义用于整套目录的续跑前检是脚本缺陷。此前离线 API 替身错误地忽略了 dry-run create 的同名冲突，也缺少已有对象场景的真实前检验证。

## 最小职责调整

只有两个执行源码文件变化：`resource.yml` 和 `replay-preflight.yml`。

- 目录预检：逐份渲染并执行 `create --dry-run=client --validate=strict`，同时读取同名对象并校验 run 归属。可检查同名 Pod 的不同变体，不更新现场，也不会把后续阶段的清单拿到当前阶段的 quota/limitrange 下假定执行。
- 实际创建：确认对象不存在后，先 `create --dry-run=server`，成功才实际 create。
- 实际更新：先 `apply --dry-run=server`，成功才实际 apply。Pod 的不可变 command 等变更仍被拒绝，修复 Pod 继续按原流程删除重建。
- 外来或无标签的同名对象在归属断言处停止；删除、覆盖现场或忽略真正准入错误都不是本次修复方式。

前检结果现在明确为 `REPLAY SOURCE SCHEMA PASS`；服务端准入由每次实际 create/apply 前的 helper 分别执行，不再把目录结构检查称为整套服务端准入。

## 核验

[55 项完整回归](regression-55-pass.txt)通过。离线 API 替身已补上 AlreadyExists、Pod 不可变字段和 dry-run 不持久化语义，真实 Ansible helper 覆盖已有 Pod 的原始/修复清单、拒绝更新、外来无标签对象以及调用顺序。

[真实 API 正负对照](live-controls-pass.txt)在保留 `p03-ha`、`p03-client` 的情况下验证：

1. 原 server create dry-run 确实 AlreadyExists，新的 client 结构校验通过。
2. 合法 Deployment 更新的 server apply dry-run 通过。
3. `replicas=-1` 的 server create dry-run 被拒绝。
4. 同名 Pod command 变体结构检查通过，但 server apply dry-run 仍以不可变字段拒绝。

全部写请求都带 dry-run；未创建运行对象、未重启或删除已有对象。[前后快照](cluster-before.json)与 [之后快照](cluster-after-controls.json)中的 7 个对象 UID、resourceVersion、spec 全部一致，见 [verification.json](verification.json)。反例文件仅为本地测试输入，不是部署入口。

更重要的是，已直接在该运行目录、现场仍存在的情况下执行[完整主入口 validate](full-preflight-pass.txt)：68 项源码目录检查、CoreDNS 补丁 dry-run、网络 YAML 结构检查及三控制平面只读检查全部完成，所有主机 failed=0、unreachable=0；三个节点 changed=0。管理端 changed 仅为新本地证据和编译物料。

## 当前目录和原始记录

[更新剧本](adopt-source.yml)先核对原 run/集群、DNS/备份 PASS、HA 未通过、十节点健康及备份时效，再仅允许上述两个执行源码的准确差异。旧 context 原样归档至当前目录 `origin/admission-fix-a191669/context.json`，旧/新实现 SHA 及沿用范围写入相邻 `source-revision.json`；当前 context 才切换到新 SHA。主入口严格源码一致性检查未放宽。

原失败日志、回执和通过检查点不变，旧 context 的归档 SHA 与[修复前清单](before-repair-sha256.json)相符。没有重新做 DNS/备份，没有启动 HA 或 01.07。

继续使用同一目录：

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
CNPL_REPLAY="$PWD/ops/01-kubernetes/records/2026-10-18-ansible-replay/runs/03-06-20261018T051927Z-ha-fix-20261018T063407Z"
bash ops/01-kubernetes/scripts/replay-03-06.sh resume "$CNPL_REPLAY"
```

先在准备提示按一次回车；等正式 Power Off 指令后关闭实际打印的目标，等 `FAULT CHECKS PASS` 再开启同一台。关机/开机后均自动检测，无需回车。真实 HA 仍需本次重跑验证。
