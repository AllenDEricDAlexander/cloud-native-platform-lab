# 02.09 整组交付复核

02.08 的17项可执行验收和清理已归档。对完整02.09重新审阅Ansible、YAML、kind/Docker边界及失败恢复，并完成修正后的全部输入核验。正式21步数据面实验由用户启动，本记录不代表实际kind/L2/BGP验收通过。

| 核验 | 实际结果 |
| --- | --- |
| 前序与主线 | 02.08原run及通过/清理摘要匹配，主集群UID和资源保护基线一致，主 .201可信TLS返回预期404 |
| 全组预检 | 最新validate为ok=5、changed=0、failed/unreachable/rescued/ignored=0，21步均未部署 |
| 配置 | 五种Cilium完整profile和Envoy Gateway Chart实际Helm渲染；容器镜像均在锁定物料中；6个内置对象严格服务端预览，5个Cilium CRD自身预览，9个自定义实例按锁定schema验证 |
| 正式准入边界 | kind安装本批CRD后，各原始对象在实际空间应用前再次严格服务端预览；当前结构校验不替代CEL/准入验收 |
| 物料 | kind工具、全部本地镜像归档、Chart和schema摘要通过；用于FRR实际HTTP探测的arm64二进制摘要匹配版本锁 |
| 回归 | 数据面7项、共享框架4项通过，Shell语法通过；覆盖主API/UID误指向、外来对象拒绝、依赖创建顺序、FRR目录权限与EndpointSlice空值 |
| 编排 | 真实Ansible正常、观察失败、单命令失败和显式recover四种离线模型通过；故障不被隐藏，失败后停止后续命令并清理 |
| Docker | 本轮保持停止，未创建kind、FRR或私有kubeconfig；正式入口先由用户启动Docker，再由all核验linux/arm64、cgroup v2和至少4CPU/6Gi资源 |

修正FRR挂载配置目录在入口umask=077下默认为0700、降权后无法遍历的问题，配置目录设0755、公开配置文件保持0644。L2故障检查兼容收敛期EndpointSlice的`endpoints: null`，保留原有节点状态、实际请求、Lease/ARP和失效端点检查。

命令说明已补全`DOCKER_CONTEXT=desktop-linux`和同步`docker desktop start && ... all`，避免遗漏启动步骤；该环境变量只限定当前终端。私有kind API仍只绑定127.0.0.1，网络仅172.30.90.0/24，BGP只允许本批Pod/VIP前缀；主十VM和CNI保持。

32份一致输入副本见`reviewed-source/`，[完整结果](delivery-review.json)、[输入摘要](source.json)和[逐项证据清单](evidence-sha256.json)已保留；`attempts/`依仓库规则只保留本地。完整Ansible/YAML、21步内容、命令及恢复见[操作指南](../../examples/dataplane/README.md)。
