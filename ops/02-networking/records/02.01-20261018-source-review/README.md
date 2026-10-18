# 02.01 前置复验与完整源码校验

2026-10-18 在管理 Mac 完成只读前检及源码/服务端 dry-run。范围按用户要求限定为 `.101–.110` 十台 VM，不读取或依赖物理宿主机放置。

## 交接与当前前置条件

原集群 UID 为 `4d3e52d7-e203-4daf-aced-9c3a666fcf5b`，版本 v1.36.5；已核对 01.03–01.10 的真实通过和清理回执，确认仍为原集群。十节点 Ready，无压力或封锁调度，Cilium/Envoy/kube-proxy 各 10/10、CoreDNS/operator 各 2/2，API readyz 为 ok。

十台 VM 的 Enforcing、firewalld、containerd、kubelet、chronyd、CRI RuntimeReady/NetworkReady、chrony 同步、Harbor TLS、节点到外网的显式代理请求全部通过。网络保持 VXLAN Overlay、cluster-pool IPAM 与 kube-proxy 共存。每台输出保存在最终 attempt 的 `host-*.txt`。

`.15` 管理机实际分发和持久存储仍未验收；本次使用已有管理 Mac，不依赖这两项。

## 校验与证据

- [最终完整 Ansible 日志](ansible-validate-20261018T141745Z-5J9GG7)：`02.01 SOURCE VALIDATION PASS`；十一台 Ansible 目标（Mac + 十 VM）全部 failed/unreachable/rescued/ignored=0。主机 changed=1 是将输出写到 Mac 的 delegate_to 任务，未修改 VM。
- [逐项机器可读结果](verification.json)、[原集群与网络快照](attempts/20261018T141745Z-347ecd46-validate/preflight.json)、[源码与输入 SHA-256](attempts/20261018T141745Z-347ecd46-validate/source.json)。最终源码与该摘要逐文件匹配。
- [完整生成的业务 YAML](attempts/20261018T141745Z-347ecd46-validate/fixtures.yaml)、[拒绝策略 YAML](attempts/20261018T141745Z-347ecd46-validate/deny.yaml)：共 8+1 个对象，同规格服务端严格准入通过。命名空间未创建，业务对象使用既有 lab-core restricted 空间做 dry-run；正式 run 会再在真实空间准入。
- 原 Cilium Chart SHA-256、Helm 4 服务端渲染和 Relay 入口 CiliumNetworkPolicy dry-run 通过；[渲染结果交叉核验](attempts/20261018T141745Z-347ecd46-validate/chart.json)确认网络模式、mTLS、缓冲预算、Relay VM/入口与镜像完整摘要一致。生成的 Secret 原文未输出或保存。
- [静态探测镜像信息](attempts/20261018T141745Z-347ecd46-validate/image.json)、[Relay 物料信息](attempts/20261018T141745Z-347ecd46-validate/relay.json)：Go 1.27.2 Linux/amd64 离线构建通过；两个 OCI 包的 descriptor、大小及所有 blob 摘要独立复核通过。二进制/OCI 包仅本地保留，不提交。
- `go test -race ./...` 与 `go vet ./...` 通过：覆盖回显源地址/长度/摘要、错误后端、错误 SNAT、超时、大包限制和 UDP 返回验证。
- Python unittest 七项通过：外来资源、Namespace UID 改变、既有 Hubble 保留、请求样本数量不足、Hubble 丢事件和非 POLICY_DENIED 丢弃均不会误判通过；tag@digest 与 CRI digest 引用等价，错误仓库/摘要不会放行。
- Bash/Ansible 语法、YAML 重复键检查和 `git diff --check` 通过。

所有脚本校验在用户正式运行前完成；早期源码校验记录原样保留，以最终 attempt 为当前交付依据。

## 尚未执行的部分

没有启用 Hubble、修改节点防火墙或导入节点镜像，没有创建测试 Namespace/Pod，也没有执行正式网络矩阵、故障观测、清理或 Helm 回退。只读复核确认 Hubble 仍为 false，lab-net/lab-net-peer 均不存在；本目录没有正式实验或清理通过回执。

完整文件和逐条命令说明见 [02.01 操作手册](../../examples/network-baseline/README.md)。用户执行 run、cleanup 并产生对应真实回执后，才能将 02.01 标为实际完成；不能凭本次 dry-run 提前验收。
