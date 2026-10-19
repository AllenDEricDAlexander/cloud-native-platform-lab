# 02.09 执行前核验

Docker Desktop 当前未运行；没有创建kind、启动FRR、改变主Cilium或运行数据面故障。SOURCE VALIDATION PASS 只代表本目录列出的静态/只读检查，实际21步仍由操作者 all 完成。

已校验kind0.33.0与官方工具checksum、固定Kubernetes1.36.4 arm64节点镜像；Cilium/Envoy/FRR与诊断镜像的各平台manifest/config/archive摘要；工具和离线归档都在本机seed，二进制不入Git。

五个Cilium完整profile均实际Helm渲染，检查全部容器镜像都已准备；6份内置执行对象服务端预览、5个官方Cilium CRD自身预览、9份自定义实例按锁定schema校验。实际自定义CEL/准入在kind安装CRD后、每份apply前再次执行。Envoy Gateway Chart也已实际渲染。

4项回归覆盖Loopback伪装主集群UID拒绝、非Loopback拒绝、Cilium兼容profile与外来对象删除拒绝。真实Ansible模型验证正常、观察失败、命令中途失败立即停止后续命令、显式恢复四条分支；结果见 python-tests.txt、offline-results.json 与各次日志。

临时kubeconfig仅写管理端秘密目录；Docker daemon/context、kind容器ID/标签/专属网络与API UID绑定。清理允许先前已删除的节点，按本批名称/原身份回收，不prune其他资源。

[完整指南](../../examples/dataplane/README.md)。两组集群的架构/环境不同，不作跨环境绝对性能结论。L2/BGP仅在本批Docker bridge内使用，不宣告主LAN、主VIP或默认路由。
