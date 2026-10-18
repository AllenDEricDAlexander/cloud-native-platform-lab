# 02.02.01 前置与完整源码准入校验

2026-10-18，02.01 已提交为 `f7b0811`。下一步限定为 02.02.01：ClusterIP 与 EndpointSlice；正式实验未启动。

[最终 Ansible 日志](ansible-validate-20261018T145134Z-RQu9YR)包含 `02.02.01 SOURCE VALIDATION PASS`；Mac 与两台 worker 全部 failed/unreachable/rescued/ignored=0，两台 worker changed=0。

## 已完成的验证

- 02.01 原始实验/清理回执的真假值、摘要、run/集群 UID 与完成指针一致；归档前 138 个原件仍保持原字节。
- 继承的十节点、API、Cilium/Envoy/kube-proxy、CoreDNS/operator/Hubble 健康检查通过。两个 worker 的 Enforcing、firewalld/containerd/kubelet 与各自两个完整 Digest 镜像缓存检查通过；没有联网拉取。
- [完整生成 YAML](attempts/20261018T145135Z-ecffdafe-validate/clusterip.yaml)包含五个完整对象，严格服务端 dry-run 通过。业务对象在既有 lab-core restricted 空间做同规格准入，正式 run 会在真实目标空间再校验。
- [源码及输入 SHA-256](attempts/20261018T145135Z-ecffdafe-validate/source.json)与当前交付逐文件匹配。
- Python unittest 八项通过：包括端点 UID、未就绪摘除、重复 Slice 去重、Service owner、错误端口、无身份 HTTP 200，以及完成指针不能掩盖原始清理失败。
- Bash/Ansible 语法与 YAML 重复键检查通过；[机器可读结果](verification.json)保存验证范围。

## 尚未执行

当前 `lab-service-clusterip` 不存在，没有创建 Pod、切换 Readiness 或执行扩缩容；没有实验/清理通过回执。源码与准入验证不能代替真实 150 次请求及五阶段运行。

完整 Ansible、YAML、每条命令的作用和预期见 [02.02.01 手册](../../examples/service-clusterip/README.md)。
