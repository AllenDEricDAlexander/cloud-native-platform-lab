# 02.10 最终 VM 前检与严格预览

本批为 validate，正式网格/身份实验未执行；没有创建工作负载或修改 VM 配置。

Ansible：`ok=5 changed=0 unreachable=0 failed=0 skipped=4 rescued=0 ignored=0`。

- 十台 VM Ready，原 kube-proxy/VXLAN 与主 .201 可信 TLS 正常；SELinux Enforcing、firewalld active。
- 两 Worker 的 kubelet TLS 验证、空闲内存、镜像缓存/解包磁盘余量、原 CNI 与 Istiod 端口检查通过。
- 96 个内置对象/CRD 预览、9 个自定义对象 OpenAPI 结构检查、实际 Istio 离线 Sidecar 注入、Cilium 兼容 profile 渲染通过。
- 正式 SA/Namespace/CRD 引用、CEL 和 Istio 准入在安装相应依赖后，每份 apply 前再次严格校验；不将预览替代正式接入与 mTLS。
- `source.json` 与最终交付源码逐项 SHA256 一致；详细 attempt 保留本地，公开渲染物摘要见 `rendered-sha256.json`。

原始日志为本目录 `ansible-validate-*`，机器结果见 [validation.json](validation.json)。源码/回归及七种编排模型见[交付核验](../02.10-20261021-vm-source-review/README.md)。
