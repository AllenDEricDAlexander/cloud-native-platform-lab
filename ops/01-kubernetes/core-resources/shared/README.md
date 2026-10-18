# 07–10 共用的有限测试应用

`main.go` 只使用 Go 标准库。它是被 Kubernetes 管理的测试负载，不是集群编排器；编排、创建、修改和恢复由 Ansible 完成。

- `serve/identity/ready/local/dns`：版本、Pod 身份、普通配置读取、就绪开关、临时卷和 cluster.local DNS。
- `job`：使用最小 SA 权限向一个预建 ConfigMap 测试账本按 resourceVersion 提交业务键；首次提交后退出 7，重投看到既有键时不再产生效果。
- 受控负载：CPU 只运行一个可停止工作者；memory 分配 96Mi，hold 复用同一块内存，off 释放并主动回收。CPU/内存上限仍由 Pod 资源限制执行。
- `api`：按固定范围发出实际允许/拒绝请求，只输出状态和公开 Token 声明，不输出 API 正文或 Token。
- `secret-match/auth-check/tls-check`：仅输出布尔/通过结果，避免把 Secret 正文作为证据。

Ansible 使用已锁定的 Go 1.27.2 做有限测试和静态 linux/amd64 编译，再调用已有 `tools/imagepack.go --family core` 生成两个不可变 OCI 版本。v1/v2 的 APP_VERSION 属于镜像配置，资源清单直接引用实际 manifest Digest；不依赖公网应用镜像或新 SDK。

共用 YAML 在 `manifests/baseline.yaml.j2`：每阶段独立受限 Namespace、预算、默认限制、网络隔离以及该空间内的受限管理 Role。共用执行 helper 在 `ansible/tasks/core/`，Python `checks/core-check.py` 仅做只读状态、证书归属、层级、指标和取证检查。
