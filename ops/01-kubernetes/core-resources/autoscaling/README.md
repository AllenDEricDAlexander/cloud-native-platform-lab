# 01.09 的安全指标入口与 HPA 源码

执行完整命令见 [01.09 手册](../jobs/README.md)。本目录包含 Metrics Server 及 CPU/内存 HPA 的资源 YAML；实际准备在 `ansible/playbooks/core-metrics.yml` 与 `ansible/tasks/core/metrics-*.yml`。

Metrics Server 固定为 v0.9.0，官方 linux/amd64 manifest 摘要为 `sha256:25d291fde59974547bac6f07fa9d6cf6f5bedd1f19d60c893311c5e741e0a42f`。版本锁已记录实际取得的 index、平台及 config 摘要；当前交付不把未执行的部署记成兼容性实测通过。

1. 已有安全、健康的指标 API 可复用；不接管外来不健康组件。
2. 缺失时先逐节点验证 kubelet 的 CA/IP SAN；需要引导时仅修改 serverTLSBootstrap，临时副本与原字节 SHA 明确绑定。300 秒独立 timer 和 commit/restore 同锁，Mac 中断也有回退。
3. 只批准原十节点身份、CN/O、DNS/IP SAN、签名、usages 和时效全部符合的精确 CSR。不会自动批准任意 Pending CSR。
4. 保持 SELinux/防火墙；只增加 Pod CIDR 到 kubelet HTTPS 的精确规则。节点 client 证书和其他 kubelet 配置保留。
5. 使用已有 crane 将固定摘要复制到 Harbor bootstrap，经 CRI 为两个 worker 预拉。管理员口令经 stdin，临时 Docker 配置只在私有目录，完成后删除。
6. Metrics Server→kubelet 使用集群 CA 校验；API 聚合→Metrics Server 使用独立服务证书及 APIService caBundle，`insecureSkipTLSVerify=false`，没有 `--kubelet-insecure-tls`。
7. 两个副本运行在 worker 上，使用显式投射 Token 与最小采集/认证委派权限。必须取得十节点的新鲜指标，才允许进入 HPA。

指标服务、其证书 Secret、最小集群授权以及已验证的 kubelet 服务证书配置是基础组件，实验 cleanup 不删除它们。测试专用 CA/私钥仅位于管理端 `~/.cnpl-secrets/core-stages/<run>/metrics-server/`；公开证据不保存私钥或 Token。

`load-config.yaml.j2` 只控制应用负载，不修改 Deployment 副本数；副本变化由 autoscaling/v2 HPA 决定。检查器同时核对选中的 CPU/内存指标、新鲜 Pod 指标、desired/ready 副本和 1–4 上限，并记录收敛过程。

来源：[Metrics Server v0.9.0](https://github.com/kubernetes-sigs/metrics-server/tree/v0.9.0)、[FAQ](https://github.com/kubernetes-sigs/metrics-server/blob/v0.9.0/FAQ.md)、[Kubernetes CSR](https://kubernetes.io/docs/reference/access-authn-authz/certificate-signing-requests/)。
