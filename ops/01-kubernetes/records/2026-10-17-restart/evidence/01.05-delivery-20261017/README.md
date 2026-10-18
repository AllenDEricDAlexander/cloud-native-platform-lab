# 01.05 交付前核验

当前结论：完整脚本已交付，五组真实 Kubernetes 实验尚未执行。没有创建探针、队列或流量客户端 Pod。运行入口及逐命令解释见 [完整手册](../../../../core-resources/probes/README.md)。

| 已执行检查 | 结果和证据 |
| --- | --- |
| 9 项 Go 行为测试及竞态检查 | [go-race.txt](go-race.txt) 通过；包含真实 HTTP 超时、透明 TCP 转发下的既有连接、长请求排空、当前消息完成/停止领取、租约重投/去重及不足预算拒绝成功。只用 Recorder/net.Pipe，不监听端口。 |
| 10 项 Python/执行入口回归 | [python-regression.txt](python-regression.txt) 通过；包含外来对象拒绝修改、旧 Service UID 排除、资源/安全边界、partial prepare 恢复、真实 run.sh 失败及续跑跳过、原日志保留、OCI 描述符校验和终止回执拒绝路径。集群动作使用替身。 |
| 静态 linux/amd64 构建 | [build.txt](build.txt) 通过；[物料索引](artifact.json) 记录下载包、源码、二进制、OCI 归档和 manifest 摘要。Go vet 无输出成功；ELF 无 PT_INTERP，运行不依赖节点动态链接器。 |
| 重复构建 | [build-repeat.txt](build-repeat.txt)、[重复索引](artifact-repeat.json) 与首次最终构建完全一致，核对二进制及归档摘要相同，支持严格物料续跑门禁。 |
| 26 份当前清单真实准入 | [server-dry-run.txt](server-dry-run.txt) 通过，[完整清单](manifests/) 含 Pod、Service 和 NetworkPolicy；执行身份为既有受限运维身份。API dry-run 不创建对象，不证明 kubelet/CRI 行为。 |
| 两 worker 最终镜像真实准备 | [image-import-final.txt](image-import-final.txt) 均 failed=0、unreachable=0；复制后使用节点 Python 校验，containerd 导入/展开，再建立完整仓库名的 Digest 引用，CRI 可解析。没有启动容器。 |
| 两 worker 幂等性 | [image-idempotence.txt](image-idempotence.txt) 两主机 changed=0、failed=0、unreachable=0；重复执行跳过导入和建引用。 |
| 真实集群及安全基线 | [cluster-readonly.json](cluster-readonly.json)：同一集群十节点 Ready，lab-core 无 Pod；两个 worker 均 SELinux Enforcing、firewalld active，CRI 镜像源码标签/manifest 与物料一致。 |
| Python/Shell/YAML 及源文件摘要 | [static-verification.json](static-verification.json)；go.mod 无第三方模块，未启动 Docker。 |

当前应用镜像为 `cnpl.local/phase01/probe-lab@sha256:f173f2e04a71e7fbf77cafca184f2aec6f5255d01d44d97a26167bda90cdbf1b`。仅在两个 worker 本地缓存，Pod 使用 Never 拉取；公开索引和脚本可入记录，二进制/归档留在受控缓存，不入 Git。gRPC 实验复用已有 etcd Digest。

初次导入核验发现：OCI 的标签导入与 `--digests` 并不能自动提供所需的完整 `仓库名@sha256` 引用，因而后置断言正确中止。原失败输出保留于 [image-import-initial.txt](image-import-initial.txt)，对应 [当时物料](artifact-initial.json) 和初次清单/测试均带 initial 后缀。现已显式执行受控 `ctr images tag 导入标签 完整Digest引用`，再核对 manifest/CRI；最终两次 Ansible 输出证明修正和幂等结果。before-relay 文件保留后续增加 Pod 内流量客户端之前的构建输入，不作为最终交付结果。

真实实验还需用户运行 run.sh：慢启动保护/超窗重启、依赖超时与本地失活、EndpointSlice/连接、PreStop/TERM/强杀及消息补偿、四种原生探针协议，以及最后验收和清理。这些都没有提前写成 PASS。
