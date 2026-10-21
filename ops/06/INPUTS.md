# 输入、物料与执行边界

复制 `inputs.json` 到仓库外受控目录，设置 `CNPL06_INPUTS=/绝对路径/inputs.json`；物料表同样通过 `CNPL06_MATERIALS` 引用。不修改示例中的 null 作为现场事实。run_id 为 3–20 位小写字母/数字/横线，首位字母，每次实验固定一个新批次。

`prerequisites.file/sha256` 是现场签核的 00–05 主线、观测和恢复入口证据。`clusters` 各目标分别填写独立 kubeconfig/context/kube-system UID；primary 节点必须精确匹配主台账的十台 FQDN/IP/Ready。secondary/management/recovery 必须填写真实 nodes 数组，元素为 `{"name":"实际 FQDN","ip":"实际 IP"}`，不从主集群推断其他目标。kubeconfig、口令/令牌/客户端配置必须是仓库外当前用户所有的 0600/0400 非空文件。

安装用物料表结构如下，所有校验值必须真实计算。主锁 `components.<key>` 须登记同一 version、安装清单 SHA256 和所有实际镜像 Digest；本阶段不改主锁中尚未验证的候选版本。

```json
{
  "schema_version": 1,
  "components": {
    "keycloak": {
      "version": "现场锁定版本",
      "manifest_file": "/受控目录/keycloak-rendered.yaml",
      "manifest_sha256": "64位真实SHA256",
      "compatibility_file": "/受控目录/compatibility.json",
      "compatibility_sha256": "64位真实SHA256",
      "namespaces": ["本批控制器空间"],
      "cluster_resources": ["CustomResourceDefinition/实际CRD名"],
      "wait": [{"namespace":"本批控制器空间","resource":"deployment/实际名称","condition":"Available"}]
    }
  }
}
```

清单必须是完整对象：包含所需 Namespace、CRD、RBAC、控制器、Webhook、资源预算及指向已有 Secret 的引用。禁止内嵌 Secret/密码/私钥/Token；不包含服务端导出的 status/UID/managedFields。所有 image 均为 `harbor.k8s.internal.egon.top/...@sha256:...`，不能引用公网 tag。`namespaces` 与 `cluster_resources` 是逐对象审核范围，控制器特权、节点选择、Webhook failurePolicy/namespaceSelector、CRD 升级和镜像兼容在 compatibility_file 中逐项复核。不能把管理员导出的整集群 YAML 当作安装包。

`install` 给本批新组件打 phase/stage/run 标签；已存在且不属本批或由 GitOps 管理即拒绝，CRD spec 变化停止。安装前审核集群级权限和 CRD 影响；不要将 `kube-system` 等现有 Namespace 放入清单接管。新控制器使用单独空间，其宿主权限只限已授权实验节点。已有控制器跳过 install，按各目录的 CR/API/行为检查复用。

`images.http` 必须支持非 root、只读根文件系统、8080 `/health`、HTTP/CloudEvents 回显并记录 event ID；`images.probe` 需含 sh/curl/jq/kubectl/python3；`images.worker` 用于实际 Kafka/Rabbit/Dapr 样例，契约在相关目录说明。镜像依赖和签名先在受控构建端准备；Mac 不构建运行 Docker/Podman 集群。模型/GPU 镜像另锁。render 可用虚构 Digest 做构造检查，apply 仍核对主锁。

业务空间默认 Restricted、无 Token 自动挂载、有限额、默认拒绝网络，仅允许同空间和 kube-dns。按阶段登记 `network.egress`，例如 `{"stage":"07","cidr":"192.168.9.106/32","ports":[{"port":6379,"protocol":"TCP"}]}`。入口用 `network.ingress`，例如 `{"stage":"06","namespace":"实际网关空间","pod_labels":{"app.kubernetes.io/name":"实际网关标签"},"ports":[{"port":8080,"protocol":"TCP"}]}`；必须同时限制 Namespace、非空 PodSelector 和端口，拒绝通配。存在准入或 Sidecar 约束时先观察 Audit，再确认精确例外。11 的专用 VM 空间是单独评审的 PSA 例外。

备份门槛要求独立于主 Ceph 和三台 ESXi 故障域的真实介质及抽样恢复证据；现有同 esxi01 的 backup VM 不满足该门槛。高风险故障、密钥淘汰、控制平面变更、升级和重建必须停在材料核实处，不能通过把 independent 改为 true 代替实际验证。

`cleanup-plan` 只列本批已登记对象和 UID，保留失败证据；删除采用 UID 前置条件。Namespace、PVC/VM/DataVolume、CRD、共享控制器、备份与存储后端需要按子阶段先保护数据再回收，不提供全局 prune 或整阶段盲删。

普通 Pod/事件/恢复对象记录会删除 env、命令参数、data、注解、消息等可能携带秘密的字段，保留归属、状态、原因、镜像和投影结构；需要原始诊断输出时单独保存到仓库外私有目录并人工脱敏。密钥、快照和模型预测正文不进入普通证据。
