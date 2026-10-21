# 02.10 第一次修复运行：身份拒绝判定失败，恢复通过

19 个前序结果通过，包括真实 Sidecar/Ambient/waypoint 和两个 SPIRE agent。spire-workloads 的授权 mTLS 实际成功；负向 Workload API 被持续监听重试，最终呈现超时，未满足明确身份拒绝断言，因此 all 失败。没有将超时放宽成拒绝。

Ansible：ok=1193 changed=367 unreachable=0 failed=1 skipped=6 rescued=0 ignored=0。自动恢复与清理通过，见 state/closed.json 和 postcheck.json。原始日志保留。

修复为单次 FetchX509SVID 并重建身份镜像后，全新 [R2](../02.10-20261021T154100Z-agent-r2/README.md)24 项与恢复全部通过。
