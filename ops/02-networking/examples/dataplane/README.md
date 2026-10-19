# 02.09 独立 kind 的完整数据面对照

先完成 02.08 all 及清理。管理 Mac 的 Docker Desktop 需由操作者启动，使用本机 desktop-linux/Linux arm64、cgroup v2，至少4 CPU/6Gi内存（建议8Gi）。本入口不会启动 Docker 或改动十 VM 主集群的 Cilium、kube-proxy、路由或 VIP。

~~~bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
export LAB_DATAPLANE_RECORDS="$PWD/ops/02-networking/records/02.09-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/dataplane.sh all "$LAB_DATAPLANE_RECORDS"
~~~

三行分别进入项目、绑定全新批次、一次完成以下21个步骤和自动清理。源码与物料可在 Docker 未运行时用 validate 核验；这不代表已完成实际隔离集群验收。

| 范围 | 实际操作与预期 |
| --- | --- |
| 隔离前检 | 固定 kind0.33.0/Kubernetes1.36.4/Cilium1.20.2；kind工具官方校验和、arm64镜像平台/配置/离线归档摘要；API只绑定127.0.0.1。私有kubeconfig写入管理端秘密目录，不改默认context |
| 基准 | 新建专属 Docker bridge、一个control-plane与两个容器worker；禁用默认CNI，预加载已校验镜像，安装保留kube-proxy的VXLAN Cilium。所有kind节点必须使用private cgroup namespace |
| 真实应用与网关 | 两worker应用副本、control-plane诊断Pod、NodePort30080/30090，以及独立Envoy Gateway1.9.2/Envoy1.39.1；每组核对Pod IP、Service IP、DNS、NodePort、Gateway请求的nonce/UID及API Service可信TLS |
| 02.09.01 | 保存kube-proxy原DS；只在本批kind节点停止DS并清理其iptables链；切换eBPF替代并跑同一矩阵。持久TCP连接容器记录原连接、失败、重连，不承诺零中断 |
| 02.09.02 | 切换Native Routing、autoDirectNodeRoutes、已定义PodCIDR；同矩阵通过，并读取每节点实际PodCIDR→peerIP内核路由。与先前VXLAN在同一临时集群比较，不拿Mac与VM的绝对性能混比 |
| 02.09.03 | 启用L2、独立IPAM池172.30.90.224–230，class=io.cilium/l2-announcer；核对实际HTTP、Lease持有者与外部探针ARP MAC。暂停持有者容器，等NotReady/EndpointSlice摘除及Lease迁移后再次验证；恢复容器与流量 |
| 02.09.04 | 专属网络中的FRR10.5.0软件邻居，ASN65009/65010；只接收本批PodCIDR /24及VIP /32；独立class=io.cilium/bgp-control-plane的Service，核对Established、真实RIB和FRR路由路径HTTP。删除广告后路由撤回、该无L2路径访问失败、NodePort正向对照仍成功 |
| 回退/清理 | 重建原kube-proxy DS，恢复VXLAN/非替代模式，再跑矩阵；停止并保存持久连接观测；always恢复暂停容器、删除本批kind/附属容器/专属网络；主十VM资源与.201可信TLS不变 |

这三个kind节点是隔离实验的容器节点，不是额外VM。L2/BGP仅在专属Docker网络内传播，不接家庭路由器，不宣告192.168.9.0/24、主VIP或默认路由，不涉及物理宿主机。原主集群02.06.04的OpenWrt联动前提缺口不会因本实验而被自动视为通过。

[独立剧本](../../ansible/playbooks/dataplane.yml)、[全部模板与顺序](../../networking/dataplane)、[隔离保护/生命周期](../../tests/integration/phase02/isolated.py)、[验收器](../../tests/integration/dataplane/check.py)、[镜像归档核验](../../tests/integration/dataplane/materials.py)。

命令作用：

- docker info/inspect：只读固定daemon身份、容器ID/所属网络、镜像配置digest；拒绝host网络或不同归属。
- docker load / kind load image-archive：导入平台摘要固定的本地归档。Pod引用独有本地tag并禁止拉取，预览同时校验Chart没有额外未知镜像。
- docker network create / kind create：只创建本批独有名称和标签的网络/节点；Node镜像先按配置摘要验证，API/kubeconfig明确指定。
- helm upgrade --reset-values：只针对隔离kubeconfig切换完整Cilium值集；agent/operator按配置重启，等待收敛；不使用主集群Helm回滚充当完整回退。
- kubectl apply --dry-run=server：在实际kind中安装CRD后逐份预览；写操作由Ansible逐条执行，意外失败立即停止后续命令并保存部分结果。
- docker pause/unpause：只作用于通过kind标签、原ID、专属网络检查的节点容器；不暂停VM或其他容器。
- vtysh show bgp ... json：读取FRR实际邻居与RIB；FRR前缀表只允许本批Pod/VIP范围，没有默认路由宣告。
- kind delete cluster / docker rm/network rm：只回收本批对象；不prune其他镜像、网络、卷或容器。

正常预期：21步真实结果通过、回退矩阵通过、CLEANUP PASS、failed/unreachable/rescued/ignored=0。primary cluster_uid和临时cluster_uid分别记录，任何指向主API的临时kubeconfig会被拒绝。

失败或中断后：

~~~bash
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/02-networking/scripts/dataplane.sh recover "$LAB_DATAPLANE_RECORDS"
~~~

使用原记录和原Docker context恢复。Docker已停止时需操作者先启动它。恢复不会重跑迁移，主要恢复暂停状态并删除隔离环境；私有kubeconfig不入Git，公开回执保留UID、路由、ARP、请求和全部失败。

依据：[kind0.33.0与固定节点镜像](https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0)、[Cilium1.20.2 L2限制/class](https://github.com/cilium/cilium/blob/v1.20.2/Documentation/network/l2-announcements.rst)、[BGPv2及class](https://github.com/cilium/cilium/blob/v1.20.2/Documentation/network/bgp-control-plane/bgp-control-plane-configuration.rst)。
