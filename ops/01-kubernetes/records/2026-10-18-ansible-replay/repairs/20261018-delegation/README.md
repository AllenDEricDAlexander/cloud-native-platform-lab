# 委派连接修复与既有备份收尾

用户运行 `runs/03-06-20261018T051927Z` 在 `backup-offcluster.yml` 的“核对远程暂存归属”失败。实际备份、etcd 隔离目录恢复、restic 加密备份及取回逐文件校验均已完成，尚未进入 HA。

## 根因与修复

[修复前复现](before-fix-reproduction.txt)确认：三个节点均有 `/usr/bin/python3.12`；控制平面 play 自动发现了该解释器，但后续 `hosts: localhost / connection: local` 的委派继承了本地连接。日志显示 `ESTABLISH LOCAL CONNECTION FOR USER: mario`，模块实际在 Mac 上执行 Linux 路径并失败。此前只读交付没有执行到这一收尾分支，离线 helper 也未覆盖混合连接，属于验证缺口。

在既有 inventory 的 `group_vars/k8s_nodes.yml` 明确 `ansible_connection: ssh`、`ansible_python_interpreter: /usr/bin/python3`。范围仅十台 Rocky 节点，未修改生成的 hosts.yml；当前 Python 入口已真实确认。该配置同时覆盖 worker02 压力注入和恢复的委派；隐式 localhost 继续使用本地连接和 Ansible venv Python。

[修复后同场景复现](after-fix-reproduction.txt)通过。[完整 38 项回归](regression-38-pass.txt)与[11 项专项回归](focused-tests-pass.txt)通过。新增连接回归通过实际 Ansible 和拒绝联网的 SSH 夹具，验证 cp01/cp02/cp03/worker02 均选择 SSH，反向委派管理端使用当前本地 Python。

## 当前批次收尾

[有限收尾 playbook](finish-backup.yml)及其[输入](inputs.json)只处理这一次失败尝试，不启动 replay 主流程：

1. 核对当前集群 UID、原 context、实验源码 SHA、备份凭据时效、原包 manifest SHA，并重新核验本地原包每个文件。原先成功的远程取回以原凭据和执行日志为证，本次没有重新执行 restic 备份/取回。
2. 实际委派到三个控制平面及 worker02 读取 hostname、执行 stat；从控制平面反向委派 Mac 执行 Python，确认两种方向。
3. 在任何删除之前，核对三个 owner.json 的原 run/节点归属。只删除已取回的本次远程暂存，保留 Mac 私有原包和 .16 加密快照。
4. 确认三个远程暂存均不存在后，调用原 checkpoint helper 写 `03-backup.json`，取得 `03 BACKUP PASS`。

[实际输出](backup-finish-pass.txt)为 failed=0、unreachable=0；[完成结果](completion.json)及[核验摘要](verification.json)已保存。修复前 154 个现有运行文件逐一按[原 SHA 清单](original-run-files-sha256.json)验证未变；仅新增真实完成后的备份检查点。没有修改 context、原回执、原通过标记或实验源码，也没有放宽 resume 的源码一致性门禁。

继续使用同一记录目录：

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
CNPL_REPLAY="$PWD/ops/01-kubernetes/records/2026-10-18-ansible-replay/runs/03-06-20261018T051927Z"
bash ops/01-kubernetes/scripts/replay-03-06.sh resume "$CNPL_REPLAY"
```

这会跳过已完成的 DNS 和备份，进入 HA 准备及手动电源提示，再顺序执行 04–06。按终端实际打印的 VIP 持有者操作，出现 `FAULT CHECKS PASS` 后开启该 VM 并回车；本次修复没有启动故障实验或 01.07。
