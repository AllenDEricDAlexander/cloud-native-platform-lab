# 02.10 完整 Istio 与 SPIFFE/SPIRE 专题

先完成02.09与清理，Docker Desktop保持运行（本机linux/arm64、cgroup v2、至少4CPU/6Gi，建议8Gi）。本专题创建另一套独立kind，不修改主VM的Cilium模式、CNI文件、证书或默认kubeconfig。

~~~bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
export LAB_MESH_RECORDS="$PWD/ops/02-networking/records/02.10-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/mesh.sh all "$LAB_MESH_RECORDS"
~~~

三行分别进入项目、绑定全新批次、一次执行下表全部实验与清理，不需逐节启动。

| 范围 | 操作、证据与预期 |
| --- | --- |
| 隔离/兼容性 | 复用已锁定kind/Kubernetes/Cilium；新Docker网络172.30.91.0/24、Pod10.247.0.0/16、Service10.99.0.0/16。Cilium保留kube-proxy、BPF masquerade=false、cni.exclusive=false；全部CNI变更仅在kind内 |
| 02.10.01 | Istio1.31.2 ambient profile 同时提供Sidecar注入与Ambient；Sidecar/裸应用分别在独立空间，核对注入后的真实容器及CNI模式；10个nonce/UID样本、实际CRI CPU/内存计数与明文基准比较 |
| 02.10.02 | 另一空间只标Ambient，验证无sidecar、ztunnel实际mutual_tls指标与工作负载配置；再创建revision=cnpl的waypoint并等待本代Programmed；仅相应Service接入waypoint |
| 02.10.03 | Sidecar STRICT mTLS，允许指定SA、拒绝另一个SA及裸明文；实际mutual_tls指标和公开证书元数据。故障后端503只产生原请求+2次，300ms超时产生504并恢复控制请求。Ambient先验证L4身份拒绝，再将后端限定为waypoint身份，Service的L7策略拒绝路径和方法 |
| 02.10.04 | SPIRE1.15.4在独立空间，用k8s_psat的绑定SA token证明三个节点；注册精确namespace+SA selector，未注册SA无法取得身份；使用go-spiffe2.9.0真实Workload API和双向TLS，匹配精确URI身份与响应nonce/UID |
| SVID生命周期 | 60秒SVID，watch真实观察新serial并再次mTLS。保留一份旧SVID仅在进程内存；删除allowed注册后，新签发立即受身份API拒绝，旧SVID按其NotAfter到期后连接被拒绝；另一个verifier身份持续成功作正向对照 |
| 02.10.05 | 记录公开身份、策略、请求、指标、CRI资源、轮换和失败；回收本批kind与专属网络。只有清理回执与主线保护检查通过才生成正式handoff.json，列明Phase03/04/05回访与现有BLOCKED |

Istio与独立SPIRE使用相同的标识信任域internal.egon.top，但有独立CA/bundle，**没有自动联合信任或网格接管**。SPIFFE标识不替代DNS和Kubernetes RBAC。注册撤销不是对所有已签发证书的即时全局吊销。

全部清单：[networking/mesh](../../networking/mesh)；[独立Ansible](../../ansible/playbooks/mesh.yml)；[验收器](../../tests/integration/mesh/check.py)；[真实SDK程序及TLS/HCL测试](../mesh-identity)。SPIRE server/agent HCL 是单独的可核验文件，YAML嵌入值必须逐字一致。

SPIRE agent需要hostPID/节点Workload API socket，**仅在本批隔离kind中**使用。kind kubelet服务证书为自签，WorkloadAttestor在这个隔离环境显式跳过kubelet服务证书校验，同时保留SA认证；SPIFFE工作负载的URI、证书链和mTLS验证不跳过。原根CA、原中间CA及其私钥均不上传，新的SPIRE私钥只在kind临时卷/进程内。

命令作用：

- docker/kind load：只装载离线且已验证manifest/config/archive摘要的arm64镜像；工具与Istio发布包有官方校验和。
- istioctl manifest generate：只生成公开部署清单；逐一核对所有镜像。kube-inject 用相同配置作非部署注入预演（只读原API命名空间/版本），核对代理镜像和无NET_ADMIN init。
- kubectl apply --dry-run=server：安装本批CRD后逐对象真实准入；Namespace/ServiceAccount先落地，依赖Pod随后预览再应用。预先在主API预览时只替换未创建的SA引用，原引用按本批清单核对，实际kind再次校验。
- kubectl exec /phase-lab probe：在原工作负载网络路径请求，验证HTTP、nonce、UID；403需匹配RBAC，明文/L4拒绝前后有健康对照。
- istioctl proxy-config secret 默认表格：只保留证书序号/有效期等公开元数据，不导出Secret JSON；ztunnel-config workloads验证实际工作负载映射。
- kubectl port-forward --address 127.0.0.1：有界读取本批Envoy/ztunnel指标，进程结束即关闭；只保存对应Namespace的mutual_tls行。
- docker exec kind节点 crictl stats：读取本批Pod UID的实际CRI CPU/内存计数，无需部署Metrics Server；比较仅限同一临时集群的样本。
- spire-server agent list/entry create/delete：先核对三个k8s_psat agent ID与trust domain，再精确注册/撤销本批条目；bundle show只导出公开CA证书。
- /identity-lab call/watch/hold：通过Workload API取短期身份；mTLS按URI精确授权；只输出ID、serial、有效期和结果，私钥不写公开文件或日志。
- kind delete / docker rm/network rm：只回收本批身份绑定的环境，不修改主入口或清理其他Docker资源。

正常预期：全部可运行结果与清理通过，PLAY RECAP failed/unreachable/rescued/ignored=0。主线公网、Ceph服务、OpenWrt出口迁移和共享VM整机压力等前置缺口继续进入handoff，不宣称Phase02全部完成。完整Trace/SLO、发布联动分别回访Phase04/05。

失败恢复：

~~~bash
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/02-networking/scripts/mesh.sh recover "$LAB_MESH_RECORDS"
~~~

只用原批次和原Docker context恢复；不会重跑网格安装或身份实验。原始日志、partial命令结果、错误和清理回执保留，私有kubeconfig留在管理端秘密目录。

依据：[Istio/Cilium Ambient兼容性](https://istio.io/latest/docs/ambient/install/platform-prerequisites/)、[mTLS实际验证](https://istio.io/latest/docs/ambient/usage/verify-mtls-enabled/)、[SPIRE1.15.4 PSAT](https://github.com/spiffe/spire/blob/v1.15.4/doc/plugin_server_nodeattestor_k8s_psat.md)。
