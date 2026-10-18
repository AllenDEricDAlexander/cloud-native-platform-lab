# HA 观测生命周期、关机检测及失败收尾修复

原批次 `03-06-20261018T051927Z` 的 HA 目标为 cp03。原始输出最终为 `目标尚未同时停止 SSH/API`，本轮未通过，不补判 HA 成功。

## 实际证据与边界

[原始文件 SHA](original-run-sha256.json)固定修复前 248 个文件；[时间线摘要](failure-analysis.json)显示观测在 UTC 05:48:24 启动，05:55:24 达到原 420 秒上限自行退出，`stopped_by_ansible=false`。脚本仍停在人工关机提示，06:05:21 才结束目标端口检查。旧程序没有逐端口保留当时结果，不能仅凭通用错误确定哪个端口仍能连接。

随后只读现场确认 cp03 的 NodeLease 最后续租为 06:04:15，Ready 于 06:05:08 变 Unknown，VIP 持有者变为 cp02；06:06 后从管理 Mac 测试 cp03 的两个端口均超时。用户确认关闭的是 cp03 VM。节点状态与端口关闭不保证发生在同一时刻，本次不归咎于用户操作，也不将故障后的状态冒充当时观测。用户开启 cp03 后已恢复十节点 Ready。

## 修改与核验

- 唯一的人工准备 pause 放到观测启动之前。准备好控制台后按一次回车，再读取实际租约、复核备份时效、业务 Pod 和目标 UID。
- 从存活控制平面检查目标 SSH/API 的在线基线；观测启动后再次确认租约未换目标，然后打印明确的 Power Off 指令。关机、开机均由原生 Ansible wait_for 自动检测，无需事后回车。
- HA 观测上限为 2400 秒，异步任务上限同步增加 30 秒；其他实验仍保持原 420 秒默认值。关键阶段检查异步任务仍在运行，过期 ready 文件不能继续。
- 在故障期间创建并完成证明 Pod，前后均复核两个端口停止。最终纯文件检查关联目标 UID、接管者、两个存活 etcd、故障窗口中新 Pod 的创建时间、实际业务副本响应、恢复后原 Node UID 和三个 etcd。
- 失败时主动停止本组观测、保存部分结果和原始失败步骤，并提示先开启原目标。收尾失败不掩盖原错误，不写 PASS。
- 独立端口诊断现在同时记录 22/6443 的 TCP 状态和耗时，避免短路检查只留下笼统错误。

[54 项完整回归](regression-54-pass.txt)通过，包含实际 Ansible 异步生命周期的有限离线集成，过期观测、缺故障窗口、错误 Pod UID/创建时间、缺端口证明、错误多数派和业务失败的拒绝路径。API 及 etcd 命令参数针对三个目标逐一通过实际 Ansible 模板渲染检查。

[原生端口检查](native-port-check-pass.txt)在三个控制平面执行：彼此的 22/6443 均可达，未监听 loopback 端口可正确判定 stopped；全部 changed=0、failed=0、unreachable=0。loopback 检查只覆盖模块分支，不算新 VM 故障验收。[语法检查](syntax-pass.txt)通过。此次没有自动关开 VM、启动新的故障演练或开始 01.07。

## 不重做 DNS 和备份的显式续跑

修复修改了 HA 源码，因此原目录的严格源码门禁会拒绝直接混用版本。没有修改原 context 或放宽门禁；[准备剧本](prepare-continuation.yml)以[明确输入](inputs.json)创建了独立修复版本上下文，结果见 [实际输出](continuation-prepared.txt)。

只允许七个 HA/观测生命周期文件的准确差异，核对原 DNS/备份检查点的 run、集群 UID、通过状态、旧来源 SHA 和备份凭据时效后，原样复制两个 PASS 与回执。新 context 保留原 run/集群身份以安全接管本批失败资源，并声明新实现 SHA、原目录及原 context SHA；来源链保存在新目录 `origin/`。没有携带 HA PASS。

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
CNPL_REPLAY="$PWD/ops/01-kubernetes/records/2026-10-18-ansible-replay/runs/03-06-20261018T051927Z-ha-fix-20261018T063407Z"
bash ops/01-kubernetes/scripts/replay-03-06.sh resume "$CNPL_REPLAY"
```

本次会保存旧 HA 对象现场，再重建未通过的 HA 组；DNS 和备份不重做。先在准备提示按回车，看到实际目标的 Power Off 指令才关闭那一台；等 `FAULT CHECKS PASS` 再开启原目标，关机/开机后均不需要回车。目标从当前租约重新选择，不能固定沿用上次的 cp03。

新版本的真实 HA 仍待用户运行；原故障记录全部保持，最终核验见 [verification.json](verification.json)。

补充拒绝路径：即使自然超时后的清理阶段才出现 stop 文件，也保持 deadline 结果，不能改记为正常停止。较早的未运行续跑准备上下文归档在 initial-preparation/，输入也留作中间记录；以上命令使用最后准备的、来源 SHA 已再次核对的版本。

[实际 HA 准备步骤的只读核验](ha-preparation-readonly-pass.txt)验证当前十节点、原备份时效、两个业务 Pod UID、当前目标绑定、存活节点到目标的端口基线，以及两个/三个 etcd endpoint 的结构化健康结果，全部 changed=0、failed=0、unreachable=0。首次提取运行遗漏了管理路径和证据目录上下文，已在只读检查阶段暴露，补齐主入口原本提供的上下文后通过；不是新的故障演练。
