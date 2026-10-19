# 完整 02.05：内部证书自动化、轮换与公网边界

02.04 已实际验收并清理，归档提交 245fe00；[原始结果及 02.05 交接](../../records/02.04-20261019T105544Z/README.md)。本组一次完成 02.05.01、02.05.02 和清理；按操作者明确答复，02.05.03 公网发布记为 BLOCKED，不配置公网 DNS、NAT、隧道或 ACME，也不把 LAN 成功作为公网通过。

## 一次执行

在管理 Mac 的交互终端运行下面三行，不需要逐节执行：

~~~bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
export LAB_TLS_RECORDS="$PWD/ops/02-networking/records/02.05-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/certificates.sh all "$LAB_TLS_RECORDS"
~~~

| 命令 | 作用与预期结果 |
| --- | --- |
| cd | 进入仓库根目录，使用本次受检源码和相同输入。 |
| export | 为整组绑定新的 UTC 证据目录，变量只含路径。 |
| certificates.sh all | 核对原十 VM、02.04 回执、主入口 UID、全部物料、策略和模板；必要时安全输入一次根 CA 口令创建独立签发器；统一执行内部签发、定时续期、故障、权限检查和实验清理。预期 02.05 INTERNAL PASS、02.05.03 BLOCKED、02.05 CLEANUP PASS，PLAY RECAP failed/unreachable/rescued/ignored 均为 0。 |

公网不是 PASS，因此不会打印“完整 02.05 ALL PASS”。passed.json 的 internal_passed=true、phase_complete=false，步骤 01/02 为 PASS、步骤 03 为 BLOCKED；closed.json 单独证明清理完成。

首次运行会提示输入 **根 CA 口令**，不是上一组的中间 CA 口令。口令只存在入口进程内存，不回显、不写环境变量、不保存到文件。已经存在同集群、同根信任的专用签发器时复用，无需再次解密根 CA。不要把口令贴到聊天或命令参数。

预计数分钟；定时续期实验本身约等待两分钟。脚本不安装新的根信任、不改变系统时钟，根与原中间 CA 私钥始终保留在 Mac。

## 签发身份与范围

现有内部 CA 的中间层 pathLen=0，不能再签子 CA。本组在 Mac 以既有离线根签发一个独立 P-384 中间 CA：一年有效、pathLen=0、critical NameConstraints，仅允许 demo.svc.internal.egon.top 与 grpc-demo.svc.internal.egon.top 的名称树。Certificate 准入策略进一步限制为这两个准确主机名，拒绝 CA 证书、客户端认证用途及其他 SAN 类型。

专用签发器 keypair 缓存在 ~/.cnpl-secrets/certificates/lab-primary/ 下（目录 0700、私钥 0600）。只有新签发器的私钥进入 cnpl-gateway/cnpl-internal-issuer-ca；根和原中间 CA 私钥不进入 Kubernetes。该新 Secret 使用现有 Kubernetes Secret 存储机制，Base64 不代表加密；它是这两个入口名称的受限在线签发身份。CA 本身需要在一年有效期届满前单独轮换，不假定 cert-manager 自动替换 CA Secret。

使用 namespaced Issuer cnpl-gateway/cnpl-internal，不发布 ClusterIssuer。certificate-editor 只能读取、修改现有 primary-auto Certificate，不能读取 CA Secret、创建 Issuer/CertificateRequest/Pod、改 Gateway 或删除 Certificate。直接 CSR 和公网/管理域的主入口 Route 通过独立准入策略拒绝。cert-manager 默认批准权限也限定到该 Issuer 的 signerName。

这些限制同时包含 PKI、RBAC 和准入三个层面：[官方 CA Issuer 文档](https://cert-manager.io/docs/configuration/ca/)说明签发器不会在签发时替用户检查所有名称约束；本组不会只依赖 CA 扩展宣称请求已经受限。

## 全部剧本与 YAML

总入口：[certificates.sh](../../scripts/certificates.sh)、[certificates.yml](../../ansible/playbooks/certificates.yml)。沿用现有分项剧本、UID 绑定、私有 Secret 专用任务和独立 attempt 的结构；直接顺序编排即可，不增加额外模式或签发服务。

| 剧本 | 所有配置 | 作用与预期结果 |
| --- | --- | --- |
| [prepare](../../ansible/playbooks/certificates-prepare.yml) | 下列全组公开模板 | 所有输入先统一核验；CRD 与内置类型真实 server dry-run，自定义实例按锁定 CRD schema 检查，安装后再逐项执行 CEL/Webhook 严格预览。所有 VM 检查均只读。 |
| [install](../../ansible/playbooks/certificates-install.yml) | [控制器 values](../../networking/certificates/controller-values.yaml.j2)、[命名空间](../../networking/certificates/namespaces.yaml.j2)、[准入策略](../../networking/certificates/policies.yaml.j2)、[Issuer](../../networking/certificates/issuer.yaml.j2)、[最小权限](../../networking/certificates/route-editor.yaml.j2)、[私有 Secret 模板](../../networking/certificates/private-secret.yaml.j2) | 单独 SSA 安装 6 个 CRD，然后安装锁定控制器/webhook/cainjector，确认 webhook 就绪；新 CA 仅通过私有目录与 no_log 任务上传。 |
| [rotation](../../ansible/playbooks/certificates-rotation.yml) | [Certificate](../../networking/certificates/certificate.yaml.j2) | 初始 duration=1h、renewBefore=58m，不调用手动 renew、不改时钟；记录 status.renewalTime，等待定时续期后 serial/证书指纹/SPKI 更新，Secret UID 与 Certificate UID 保持，真实 .201 HTTPS 使用新证书。随后切为 7 天有效期、提前 48 小时续期，并验证稳定证书已经生效。 |
| [faults](../../ansible/playbooks/certificates-faults.yml) | [故障后端](../../networking/certificates/backend.yaml.j2)、[Service/Root/BackendTLSPolicy/Route](../../networking/certificates/routes.yaml.j2) | 按有效、错误 SAN、未知 CA、不完整链、过期五种材料依次替换单个 lab-tls 后端。Python 和独立 Go 客户端直达该 Pod，核对具体拒绝类型；实际主入口对错误后端返回 503，Envoy 上游证书验证失败计数增加。always 恢复有效材料并验证请求。 |
| [public](../../ansible/playbooks/certificates-public.yml) | [已确认的公网边界](../../networking/certificates/public-boundary.yaml) | 如实保存 BLOCKED 原因，不创建公网资源。另以 server dry-run 验证公网域和 Harbor 管理域 Route 被主入口策略拒绝，这仅证明准入边界，不算公网验收。 |
| [finish](../../ansible/playbooks/certificates-finish.yml) | 稳定版本 Certificate | 所有必需内部回执通过后写验收结果，退出短周期模式并删除 lab-tls。成功保留 cert-manager、专用 Issuer/策略、自动 Certificate 与 Secret；主入口非证书字段和原 Pod UID/spec 必须保持。 |

五种后端 Secret 在启动时一次准备；所有公开配置在部署前一次渲染。Secret YAML/JSON 只在 Mac 私有目录，权限 0600；记录仅含 UID、公开证书指纹、有效期、公开链和私有路径引用，不保存私钥或 Secret data。

固定 [版本锁](../../../versions.lock.yaml)：cert-manager 1.21.2，其[官方支持矩阵](https://cert-manager.io/docs/releases/)覆盖 Kubernetes 1.36。Chart 来自[官方 OCI](https://cert-manager.io/docs/installation/helm/)，控制器、webhook、cainjector、startupapicheck 与未使用的 acmesolver 均按 Linux amd64 摘要准备到 Harbor；运行不依赖临时公网拉取。用于第二语言验证的 [Go 客户端源码](main.go)仅用标准库，构建器仍为已有 Go 1.27.2。

## 故障与证据

错误证书仅作用于 lab-tls/fault-backend。主入口始终使用有效自动证书；网关连接上游时用独立 BackendTLSPolicy 验证根和 SNI。后端 SNI 采用受限 CA 允许的 demo.svc.internal.egon.top，连接地址仍为后端 Service/Pod，不会回到入口 VIP。

Python 与 Go 验证明确区分 hostname、unknown authority/incomplete chain、expired 和网络失败；网络超时不能算 TLS 负用例通过。诊断握手仅关闭一次验证以读取“实际收到哪张公开证书/几段链”，不发送应用请求；所有正式应用请求都验证根和名称，不使用 curl -k 或全局关闭验证。过期是专用测试叶证书的时间属性，不修改节点时钟。

内部验收包含控制器和策略就绪、首次签发、自动定时续期、稳定证书、四类故障、有效恢复、RBAC 与准入拒绝等全部必需回执；缺项或错误类型不符都失败。公开链和叶指纹用于证明实际材料，SPKI 变化证明 key rotation，不读取自动 Secret 的 tls.key 取证。

保留原始日志、每次公开清单、证书有效期/UID/指纹、续期前后状态、Python/Go 返回、Envoy 指标和保护基线。passed.json 不因公网阻塞改成完整通过。

## 结束状态与恢复

成功后 .201 的 80/443、原 Gateway/Service/Deployment/Pod UID、内部 DNS 和原手工 primary-tls 备份保持；HTTPS 已切为 primary-managed-tls。实验 Route 与空间被回收，因此 https://demo.svc.internal.egon.top/tls-probe 应返回可信自动证书及 404。控制器继续按稳定周期自动续叶证书。

入口前检或根 CA 口令错误、且没有 state/protected.json 时尚无集群变更，可以在修正原因后沿用原目录重新 all。若进入变更后失败，使用同一个目录：

~~~bash
bash ops/02-networking/scripts/certificates.sh recover "$LAB_TLS_RECORDS"
~~~

作用：按原 UID 将已有 Certificate 退出短周期，未通过内部验收时恢复切换前证书引用，核对归属后删除 lab-tls；不重新询问根 CA 口令，不补装控制器，不把恢复视作内部验收。预期 CLEANUP PASS；已有外来对象、UID 或主入口其他字段变化会停止并保留证据。

只做整组前检可运行下面一条，作用为验证全部材料和配置；它不签发 CA、上传私钥或部署资源：

~~~bash
bash ops/02-networking/scripts/certificates.sh validate "$LAB_TLS_RECORDS"
~~~
