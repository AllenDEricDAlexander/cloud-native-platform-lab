# 01.04 Pod 生命周期

原始运行已验收通过，证据保持在 `records/2026-10-17-restart/`。当前已改为源码 YAML + Ansible，新的完整命令、每条作用、预期结果与恢复方式统一见 [01.03–01.06 重跑手册](../../records/2026-10-18-ansible-replay/README.md)。

覆盖退出状态、镜像/调度失败修复、Init、普通/原生 Sidecar、受限临时调试、容器 OOM、节点软驱逐和 TERM 回执。

资源主定义位于 [manifests/](manifests/)，实际执行顺序见 [topic-04.yml](../../ansible/tasks/replay/topic-04.yml)，各组动作位于同目录的 `case-04-*.yml`。Python 只核验/观测，所有 create/apply、控制、故障与恢复动作由 Ansible 明确执行。源 `.yaml.j2` 只填运行标记、精确镜像及必要场景参数；实际渲染文件会随每次运行留存。

旧 Python 编排器及原始测试已完整保存在 [历史源码](../../records/2026-10-18-ansible-replay/legacy/sources/ops/01-kubernetes/core-resources/pods/)，不再作为执行入口。旧证据、失败过程和 PASS 不改写；新实现必须重新验收。
