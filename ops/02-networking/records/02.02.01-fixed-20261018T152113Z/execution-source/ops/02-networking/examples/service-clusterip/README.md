# 02.02.01 ClusterIP、就绪端点与实际请求

前置：[02.01 正式验收及清理已通过](../../records/02.01-20261018T142346Z/README.md)，原十台 VM 和 Hubble 保持健康。本次只实施 **02.02.01**；NodePort、LoadBalancer、Headless、ExternalName 和 DNS 缓存分别按后续小节推进，不提前部署 MetalLB。

## 要理解什么

Service 的 ClusterIP 是稳定的虚拟入口。`selector` 找到符合标签的 Pod，控制器把 Pod IP、端口和就绪状态发布到 EndpointSlice；流量转发依据可用端点变化。Readiness 为 false 时，Pod 可以仍为 Running，应用进程也可以正常运行，但 Service 不应再将新请求转给它。[Service 官方说明](https://kubernetes.io/docs/concepts/services-networking/service/) · [EndpointSlice 条件与归属](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/)。

本实验把三个地址概念放在一起验证：客户端访问 Service `:80`，EndpointSlice 中的实际目标端口是 `8080`，后端响应返回真实 Pod 名称和 UID。不能只看 ClusterIP 分配成功或 HTTP 200 就判定正确；请求必须命中当前就绪集合中的真实 UID。

## 完整文件与设计

| 文件 | 作用 |
| --- | --- |
| [service-clusterip.yml](../../ansible/playbooks/service-clusterip.yml) | 本小节完整 Ansible 入口，含前检、准入、实验与清理 |
| [clusterip.yaml.j2](../../networking/services/clusterip.yaml.j2) | 完整的 Namespace、Deployment、ClusterIP 和两个客户端 Pod，共五个对象 |
| [service-clusterip.yml 参数](../../ansible/vars/service-clusterip.yml) | 固定步骤、受控身份及两种已验镜像的完整摘要 |
| [check.py](../../tests/integration/service-clusterip/check.py) | 按 owner UID 关联 Deployment/ReplicaSet/Pod/Service/EndpointSlice，验证真实请求和清理归属 |
| [clusterip.sh](../../scripts/clusterip.sh) | 管理 Mac 的执行入口，固定 inventory、独立记录目录与完整日志 |

复用 01 阶段已验的 `/core-lab serve`、`/ready`、`ready true/false` 和 `/identity`，以及 BusyBox wget。两种镜像保持完整 Digest；后端 OCI 使用 `Never` 并严格检查两台 worker 的非空镜像 ID 和 RepoDigest。客户端使用 `IfNotPresent`，预检验证固定摘要在内网 Harbor 可读取，由 kubelet 在需要时从该内网仓库拉取，运行不重新构建镜像、不访问公网。单独 `crictl inspecti` 成功不能证明 kubelet 一定能按 `Never` 使用该引用。

采用现有 Ansible 顺序编排，变化点是副本数和一个 Pod 的 Readiness；复用既有测试应用已能表达这两个动作，不增加新接口、策略类、依赖或设计模式。

实验空间为 `lab-service-clusterip`，采用 restricted、非 root、只读根文件系统、无默认 Token。Deployment 只在 worker01/worker02 两台 VM 分布；每台各有一个客户端，最多三个后端加两个客户端。仅 `/work` 使用 8 MiB emptyDir，清理随 Pod 回收；不使用持久卷，也不更改节点污点、Cilium、CoreDNS、Hubble 或主机防火墙。

## 全部执行命令

在管理 Mac 同一个终端执行，保持 `LAB_SERVICE_RECORDS` 供本批次后续清理使用。`&&` 保证前一步通过才执行下一条，失败后保留现场和证据，不自动执行后面的 cleanup。

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
export LAB_SERVICE_RECORDS="$PWD/ops/02-networking/records/02.02.01-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/clusterip.sh preflight "$LAB_SERVICE_RECORDS" &&
bash ops/02-networking/scripts/clusterip.sh validate "$LAB_SERVICE_RECORDS" &&
bash ops/02-networking/scripts/clusterip.sh run "$LAB_SERVICE_RECORDS" &&
bash ops/02-networking/scripts/clusterip.sh cleanup "$LAB_SERVICE_RECORDS"
```

| 命令 | 作用 | 预期结果 |
| --- | --- | --- |
| `cd ...` | 固定仓库目录，使后续相对路径确定 | 当前目录为本仓库 |
| `export LAB_SERVICE_RECORDS=...` | 生成 UTC 时间命名的独立证据批次 | 只设置本终端变量，不覆盖旧实验 |
| `preflight` | 验证 02.01 原始回执摘要、同一集群、十节点与系统组件健康；只读检查两个 worker 的 Enforcing、服务、后端 OCI 缓存及客户端内网摘要 | `02.02.01 PREFLIGHT PASS`，全部 failed/unreachable=0；未创建实验负载 |
| `validate` | 重查前置、生成五个完整 YAML、在既有 restricted 空间做同规格严格服务端 dry-run | `02.02.01 SOURCE VALIDATION PASS`；生成文件位于本次 `attempts/*/clusterip.yaml`，未创建实际对象 |
| `run` | 顺序创建隔离对象，验证五个阶段和每阶段 30 次真实请求 | `02.02.01 ACCEPTANCE PASS`，生成 `passed.json`；Service UID/ClusterIP 始终相同，Readiness 目标 Pod 不被重建或重启 |
| `cleanup` | 复核 Namespace UID、运行标签与空间内没有外来对象，再删除实验空间 | `02.02.01 CLEANUP PASS`，生成 `state/closed.json`；实验空间消失，原组件与缓存保留 |

`validate` 通过不能代替正式运行；新 Namespace 尚未创建，业务对象先在既有 `lab-core` restricted 空间 dry-run。`run` 创建真实 Namespace 后，每个对象还会在实际空间再次准入。Ansible `changed` 可以只是写入 Mac 证据文件，不代表前检修改了 VM。

## 五个阶段及预期

| 阶段 | Pod / Ready 端点数 | 必须验证的现象 |
| --- | --- | --- |
| initial | 2 / 2 | 两台客户端分别通过 ClusterIP、FQDN、短名访问；响应 UID 只属于两个就绪后端 |
| expanded | 3 / 3 | 只扩容 Deployment，EndpointSlice 增加第三个端点，原 Service UID 和 ClusterIP 保持不变 |
| not-ready | 3 / 2 | 一个原 Pod 经 `ready false` 返回未就绪，仍为 Running、原 UID、无重启；EndpointSlice ready=false，新的请求不能命中它 |
| restored | 3 / 3 | 同一个原 UID 执行 `ready true`，端点恢复；服务仍可正常访问 |
| scaled-down | 2 / 2 | 缩回两副本后，旧端点退出；原 Service 继续命中当前就绪 UID |

每阶段从两台 VM 的客户端分别请求三种入口，各五次，合计 30 次；五阶段共 **150 次**。每次记录 UTC 时间、客户端、URL、真实 HTTP 响应头、后端名称/UID 与断言结果。EndpointSlice 的重复记录按 UID/IP 去重，旧 Pod UID、外来 Service owner、错误端口、未知身份即使返回 HTTP 200 也不能通过。

控制器与转发规则更新是异步的。创建过程中 EndpointSlice 的 `ports`/`endpoints` 为 null 或空列表、Pod 尚未调度或尚无状态，都记录为未收敛并继续有界等待，不抛出遍历异常，也不提前判为通过。每次轮询在检查前保存原始 API 快照，超时给出尚未 Ready 的 Pod/等待原因和快照路径。

端点收敛后，请求集合有界重试；失败样本另存独立 JSONL，不会覆盖。HTTP 200 的正文若不是 JSON 对象或没有有效 Pod 名称/UID，也只记为失败样本。仅在五阶段全部通过、Service/Deployment UID 稳定、Readiness 目标 UID 与重启计数保持一致时，才生成通过回执。

## 失败恢复与收尾

Readiness 故障由 Ansible `always` 尝试恢复；恢复前核对 Pod UID，避免操作同名替代对象。API 当时不可用时可能无法立即恢复，原证据保留；API 恢复后用同一批次 `run` 会先恢复原故障再重跑，也可直接清理隔离空间：

```bash
bash ops/02-networking/scripts/clusterip.sh cleanup "$LAB_SERVICE_RECORDS"
```

这条命令只删除本批实验空间。若检测到外来资源或 Namespace UID 改变，会停止，不能借清理删除别人的对象。仅 cleanup 成功不会产生实验通过回执。

已通过的批次不重复 run，已清理的批次不重新打开；新实验使用新目录。实验和清理均通过后，再整理交接并进入 **02.02.02：NodePort 与流量策略**。本次准备不自动启动实验。

## 修改源码后的失败批次

原批次已绑定实际执行源码。修复检查器或 YAML 后，不应覆盖 `state/source.json` 来绕过原有校验；先用原目录执行 `cleanup`，保留失败日志和快照，再建立新目录运行本页完整命令。客户端 Pod 的拉取策略属于 Pod 不可原地修改的字段，新批次也避免对旧 Pod 做非法变更。
