# 完整 02.04：Gateway API 与传统 Ingress 对照

02.03 已正式验收并归档：[执行记录](../../records/02.03-20261019T000211Z/README.md)，提交 dce5146。本组覆盖 02.04.01–07，一次执行全部前检、部署、实验、单 Pod 替换和清理。正式集群实验由操作者启动；源码预检不代表实际流量已经验收。

## 一次执行

在管理 Mac 的交互终端完整执行下面三行，无需逐节运行：

~~~bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
export LAB_GATEWAY_RECORDS="$PWD/ops/02-networking/records/02.04-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/gateway.sh all "$LAB_GATEWAY_RECORDS"
~~~

| 命令 | 作用、影响与预期结果 |
| --- | --- |
| cd | 进入项目根目录，确保配置与来源路径一致。 |
| export | 创建带 UTC 时间的全新证据目录变量；变量只含目录，没有口令。 |
| gateway.sh all | 先核对同集群 02.03 原始交接；安全输入一次现有中间 CA 口令，签发四份 14 天叶证书；统一核验全部前置后顺序执行所有实验并清理。首次运行最后出现 02.04 ALL PASS；PLAY RECAP 的 failed/unreachable/rescued/ignored 均为 0，passed.json 与 state/closed.json 均存在且通过。 |

口令提示不回显，不进入 Ansible 变量、环境变量或文件。错误口令在集群变更前退出。中断后若同批叶证书仍有效则复用，不重新询问。只上传叶证书和叶私钥，根/中间 CA 私钥始终留在 Mac。叶私钥与渲染后的 Secret 仅存放于 ~/.cnpl-secrets/gateway/lab-primary/，目录 0700、私钥 0600；records 仅保存路径、UID、公开证书指纹和有效期。请不要把口令贴到聊天或命令参数。

统一流程预计需要数分钟，首次镜像拉取可能更久；DNS 会等待既有负缓存最多 330 秒，不修改 Mac 全局解析配置。

## 已准备的输入及自动前检

十台 VM 为 .101–.110；只按 VM 的 hostname 做反亲和，不读取或操作物理宿主机。以下检查全部由入口执行，不需要额外手工配置。

| 前置条件 | 检查方式与预期 |
| --- | --- |
| 集群与前序交接 | API api.k8s.internal.egon.top:6443、kube-system UID、02.03 passed/closed 原始摘要一致；十节点 Ready/无压力，Cilium VXLAN、kube-proxy 和系统组件健康。 |
| MetalLB | 保留 cnpl-primary 主池与两台 worker speaker 原 UID/spec，.201/.203 没有外来占用；未使用地址由 infra01 做 ARP DAD。 |
| 安全与访问 | worker01/02、infra01/02 的 Enforcing/firewalld/containerd/kubelet 保持；Harbor TLS 可信。Mac 来源保持 192.168.9.200/32，两个入口不分配 NodePort。 |
| 工具和物料 | 现有 Ansible venv、kubectl/Helm 4.3.0、crane、Go 1.27.2、锁定 Chart、JSON Schema 离线依赖、gRPC 客户端、四个 Harbor 镜像摘要匹配；Go 模块从本地缓存构建。 |
| CA | 公开根/受限中间 CA 与现有 CNPL_PKI_DIR（默认 ~/cnpl-pki）一致、链有效；只签 internal.egon.top 名称。后端 TLS SNI 为 backend.svc.internal.egon.top，不签 cluster.local。 |
| 全部配置 | 一次渲染全部公开 YAML 和两个 Chart；CRD/内置类型严格 server dry-run，自定义对象按锁定 CRD OpenAPI 检查未知字段；安装 CRD 后再逐对象执行真实 CEL/Webhook 严格 dry-run。 |
| DNS | 读取 .11 权威区域，只增加 demo.svc、grpc-demo.svc 两个 A→.201（TTL 30）并递增 serial；named-checkzone 前检，应用前复核原区域摘要。保留全部原记录及反向区域。 |
| 原系统保护 | Headlamp、Hubble、metrics、系统工作负载和关键配置建立 UID/spec 基线；结尾必须与原值一致。已有同名外来 CRD/Namespace/release/对象拒绝接管。 |

固定物料全部登记于 [版本锁](../../../versions.lock.yaml)：Gateway API 1.6.1 Standard、Envoy Gateway 1.9.2、Envoy 1.39.1、Traefik 3.7.14 / Chart 42.0.0。四个镜像已按 Linux amd64 摘要准备到现有 Harbor。Chart 与二进制位于管理端既有 gateway 种子目录，不进入 Git。

依据 [Envoy Gateway 版本矩阵](https://gateway.envoyproxy.io/news/releases/matrix/)，选定实现覆盖 Kubernetes 1.36；实际锁定 CRD 包的 HTTPRoute、GRPCRoute、TCPRoute、UDPRoute 均使用 Standard 的 v1。稳定 API 与控制器的数据面实现分别检查，协议调用任一缺项整组不能通过。

## 剧本与 YAML 全量索引

总入口：[gateway.sh](../../scripts/gateway.sh)、[gateway.yml](../../ansible/playbooks/gateway.yml)。复用本仓库现有的入口、分项剧本、UID 回执与独立证据结构；顺序编排足够，无额外设计模式。

| 剧本 | 完整清单 | 作用及预期结果 |
| --- | --- | --- |
| [prepare](../../ansible/playbooks/gateway-prepare.yml) | 下列所有清单 | 全组统一前检，SOURCE VALIDATION PASS 后才部署。validate 模式不解密 CA、不签叶证书。 |
| [install](../../ansible/playbooks/gateway-install.yml) | [命名空间](../../networking/gateway/namespaces.yaml.j2)、[控制面 values](../../networking/gateway/controller-values.yaml.j2)、[EnvoyProxy](../../networking/gateway/envoy-proxy.yaml.j2)、[Gateway](../../networking/gateway/gateway.yaml.j2)、[后端及 BackendTLSPolicy](../../networking/gateway/fixtures.yaml.j2)、[Secret 模板](../../networking/gateway/tls-secret.yaml.j2) | 02.04.01/02：18 个锁定 CRD 单独 SSA 安装，避免大 CRD 注解限制；控制面一副本在 infra01，数据面两副本分别在两台 worker；滚动策略 maxSurge=0/maxUnavailable=1，排空 10 秒、最短 2 秒，Pod 终止宽限 45 秒；.201 的四个实验端口就绪，后端六 Pod Ready。 |
| [routing](../../ansible/playbooks/gateway-routing.yml) | [路由](../../networking/gateway/routes.yaml.j2)、[后端 TLS 授权](../../networking/gateway/grant-backend-tls.yaml.j2)、[DNS 台账](../../../inventory/vips.yaml) | 02.04.03：真实 DNS、TLS 链/SAN、/v1、/v2、Header、重写、HTTP→HTTPS、504 超时、未知 Host/Path 404；/secure 响应证明后端确实使用 TLS。 |
| [authorization](../../ansible/playbooks/gateway-authorization.yml) | [RBAC](../../networking/gateway/route-editor.yaml.j2)、[后端授权](../../networking/gateway/grant-shared.yaml.j2)、[证书授权](../../networking/gateway/grant-frontend.yaml.j2) | 02.04.04：业务 SA 能创建自己的 Route，不能读别处证书或改平台 Gateway；未允许的 namespace 无法绑定；共享后端拒绝→允许→撤销；外空间证书无授权不生效、有授权实际切换指纹、最后无条件恢复原证书。 |
| [protocols](../../ansible/playbooks/gateway-protocols.yml) | routes 中的 GRPCRoute/TCPRoute/UDPRoute | 02.04.05：真实 grpc.health.v1.Health/Check 三次 SERVING；TCP/UDP 各三次 nonce 回显并匹配当前 Ready Pod UID。无需 gRPC reflection，不创建数据库或消息系统，不以端口通推断其发现语义。 |
| [ingress](../../ansible/playbooks/gateway-ingress.yml) | [Traefik values](../../networking/ingress/compare-values.yaml.j2)、[标准 Ingress](../../networking/ingress/compare.yaml.j2) | 02.04.06：临时 .203、独立非默认 cnpl-compare，只 watch 实验应用空间；同一后端 Host/Path/HTTPS/重定向对照，整组结束卸载。 |
| [weights](../../ansible/playbooks/gateway-weights.yml) | [权重与 Header 路由](../../networking/gateway/weights.yaml.j2) | 02.04.07：200 个独立 TLS 请求呈现 80/20 分布（v2 允许 20–70 个的统计区间）；十个 X-Cnpl-Canary: always 请求全部到 v2。保存逐条身份/nonce，不安装自动发布适配器。 |
| [disruption](../../ansible/playbooks/gateway-disruption.yml) | 已建立的双副本数据面 | 完成 02.04.02：观测预热后只删除一个已核对 UID 的 Envoy Pod；主 Gateway/Service/Deployment UID 不变，新 Pod 在原 VM 替换；直连新 Pod 验证 HTTP、gRPC 和 LDS/CDS 成功且拒绝计数为 0，避免只凭 Ready 判断配置完成。 |
| [finish](../../ansible/playbooks/gateway-finish.yml) | 同一 Gateway 的 80/443 收敛版本 | 汇总 15 份必需结果后写 passed.json；恢复证书、卸载 Ingress、撤销临时授权和协议监听、删除四个实验空间并写 closed.json。 |

全部模板已在仓库，all 直接渲染执行，不需要复制或补填占位 YAML。公开渲染结果在本次 attempts 目录；含私钥 Secret 的渲染结果只在私有目录。

Envoy 数据面、shutdown-manager、certgen 和控制面均指向 Harbor 锁定镜像；没有运行时公网镜像回落。[官方安装方式](https://gateway.envoyproxy.io/docs/install/install-helm/)、[EnvoyProxy 定制](https://gateway.envoyproxy.io/docs/tasks/operations/customize-envoyproxy/)、[后端 TLS](https://gateway.envoyproxy.io/docs/tasks/security/backend-tls/) 及 [Traefik Chart 42.0.0](https://github.com/traefik/traefik-helm-chart/releases/tag/v42.0.0) 是所用字段和物料来源。

## 保留状态、清理与证据

成功后保留 Envoy Gateway 控制器及 CRD、cnpl-envoy GatewayClass、cnpl-gateway/primary Gateway、EnvoyProxy、primary-tls、HTTP→HTTPS Route、两副本数据面及 .201 的 80/443、两个内部 A 记录。实验应用已清理，因此访问 https://demo.svc.internal.egon.top/v1 返回经过验证的主证书与 404；HTTP 对已登记域名重定向至 HTTPS。这是本组预期的干净主入口。14 天手工证书的自动管理属于下一步 02.05。

撤销 lab-gateway-app、lab-gateway-backends、lab-gateway-denied、ingress-compare、临时 .203、IngressClass、测试授权/路由、9000/TCP 和 9001/UDP。MetalLB 主池及 speaker、现有控制台、CNI/CoreDNS、安全状态保持。

每次 attempt 保留公开清单、准入/对象 UID、DNS 原值、证书公开指纹、逐条权重请求、故障窗口 traffic.jsonl、replacement.json、cold-proxy 指标和分项结果。故障窗口请求错误如实记录，不要求零丢包；替换后至少十个入口请求成功且新 Pod 的真实流量/xDS 通过才接受。保留原日志，不覆盖或编辑已有执行证据。

预期的拒绝（未授权引用/绑定、未知 Host/Path、超时）由检查器判定为正确行为，不应该变成 Ansible FAILED。异常不能使用 ignore_errors 或 skipped 代替 PASS。

若中断或失败，使用同一个目录执行恢复命令；它不询问 CA 口令，不补装控制器，不宣布正式验收通过：

~~~bash
bash ops/02-networking/scripts/gateway.sh recover "$LAB_GATEWAY_RECORDS"
~~~

作用：按原 UID 恢复主证书引用，停止本批观测，撤销本批临时资源并保留主入口。预期 CLEANUP PASS；若安装尚不完整，closed.json 明确记录 incomplete_retained 与原因，不能当作 02.04 通过。原资源 UID 改变或空间里出现他人的资源会停止清理并保留证据。不要把失败目录换名字继续 all；恢复后修正原因、使用新目录执行整组。

如只想重新做统一前检，使用下面一条命令；不会部署、修改 DNS 或询问 CA 口令：

~~~bash
bash ops/02-networking/scripts/gateway.sh validate "$LAB_GATEWAY_RECORDS"
~~~

作用：对全部七项配置和已准备物料做同一前检。预期 SOURCE VALIDATION PASS；自定义对象的控制器状态、CEL/Webhook 最终准入、实际流量和故障恢复仍由 all 验证。
