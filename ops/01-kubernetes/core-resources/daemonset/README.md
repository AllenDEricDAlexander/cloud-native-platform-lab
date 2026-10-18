# DaemonSet 源码

本目录属于 01.07，执行入口、完整命令和恢复说明见 [01.07 手册](../statefulset/README.md)。

`manifests/daemon.yaml.j2` 显式定义节点标签、精确容忍、RollingUpdate/OnDelete、资源上限和安全上下文。实验不使用 hostNetwork、hostPath 或特权权限。
