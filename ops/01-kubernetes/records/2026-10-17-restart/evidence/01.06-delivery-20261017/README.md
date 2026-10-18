# 01.06 交付前核验

前置提交为 `812f2c9`，其中 01.05 的实际实验、回执、源码快照及清理已验收归档。01.06 的 [完整脚本与命令解释](../../../../core-resources/controllers/README.md)已交付，真实六组实验尚未执行；没有创建本专题实验 Pod、控制器、Service 或网络策略。

| 已执行检查 | 结果与证据 |
| --- | --- |
| 7 项 Go 行为/竞态测试 | [go-race.txt](go-race.txt) 通过；覆盖版本响应、探针与业务错误区别、启动/就绪/排空、文件型临时数据、透明 TCP 转发的长请求排空、真实 Shutdown 超时及错误排空状态拒绝。仅 Recorder/net.Pipe，不监听端口。 |
| 13 项编排回归 | [python-regression.txt](python-regression.txt) 通过；覆盖 OCI 配置差异/共用二进制、33 份资源的受限边界、旧 generation/旧副本拒绝、owner UID、完整 RC/RS 接管和补副本流程、finalizer merge 及保留前台 GC 标记、先父后子清理、完整模板回滚、当前 ClusterIP 客户端、容量事件和终止回执、partial prepare/历史观察保存、真实 run.sh 失败续跑与原日志保留。外部动作使用替身。 |
| 确定性构建 | [build.txt](build.txt)、[build-repeat.txt](build-repeat.txt) 通过；[原索引](bundle.json)与[重复索引](bundle-repeat.json)一致。复用 Go 1.27.2 已核验工具链，标准库静态 linux/amd64；ELF 无解释器，Go vet 成功。 |
| 33 份真实 API 准入 | [server-dry-run.txt](server-dry-run.txt) 通过，[完整清单](manifests/)含 RC/RS、匹配/不匹配孤儿、Deployment、双策略、暂停、坏镜像/探针/业务、8 核容量和双入口。使用既有受限运维身份，不创建对象。 |
| 两 worker 三版本真实导入 | [image-import.txt](image-import.txt) 两主机 failed=0、unreachable=0；核对归档 SHA、containerd manifest、完整 Digest 引用及 CRI。未启动容器。 |
| 物料重复准备 | [image-idempotence.txt](image-idempotence.txt) 两主机 changed=0、failed=0、unreachable=0；无需再次复制/导入/建引用。 |
| 同集群前置与权限 | [preflight.txt](preflight.txt)及 preflight-*.json：十节点 Ready、无压力、worker 可调度、restricted、控制器/scale/exec 权限、同 UID 的 01.05 完整验收和清理。 |
| 镜像与安全基线只读复核 | [cluster-readonly.json](cluster-readonly.json)：本批运行对象为空，两个 worker 均 Enforcing、firewalld active；六个 CRI 查询的 APP_VERSION、源码标签及 manifest 匹配物料。 |
| 语法、链接、来源与公开材料 | [delivery-verification.json](delivery-verification.json)：Shell/Python/YAML、文档链接、源码 SHA、OCI 归档及公开材料检查。 |

三个镜像使用相同静态二进制、不同不可变 APP_VERSION 配置，因此 Digest 不同。源码、编译器和归档摘要见 bundle.json；二进制和 OCI 归档只在受控缓存，不入 Git。容量失败只修改实验 Deployment 的 Pod 请求，不更改节点可用资源、kubelet、污点或防火墙。

当前结论仅为交付前核验；实际控制器接管、调度失败、端点传播、更新流量、缩容信号和业务回滚须由用户执行后验证。真正的带权灰度也未计入此专题的通过范围。
