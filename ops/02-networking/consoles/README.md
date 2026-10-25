# Mac 网页控制台

2026-10-18 按用户要求部署社区控制台 **Headlamp 0.46.0**，并启用 **Hubble UI 0.13.6**。没有部署已归档的 Kubernetes Dashboard。Headlamp 是开源社区项目，目前由 Kubernetes SIG UI 维护；[项目说明](https://headlamp.dev/docs/latest/faq/)、[集群内安装](https://headlamp.dev/docs/latest/installation/in-cluster/)和 [TLS 配置](https://headlamp.dev/docs/latest/installation/in-cluster/tls/)为上游参考。实际结果见 [本轮记录](../records/2026-10-18-consoles/README.md)。

## 访问与登录

| 用途 | Mac 浏览器 URL | LAN 地址 | 登录方式 |
| --- | --- | --- | --- |
| 节点、工作负载、日志和指标 | <https://192.168.9.110:30443> | worker02 / `192.168.9.110` | Headlamp 选择 `lab-primary`，粘贴只读 Token |
| Cilium 网络流量和服务拓扑 | <http://192.168.9.109:31235> | worker01 / `192.168.9.109` | Hubble UI 没有独立账号密码；来源限定为管理 Mac |

两个入口只允许当前管理 Mac `192.168.9.200/32`。NodePort Service 使用 `externalTrafficPolicy: Local` 保留源地址，CiliumNetworkPolicy 在 Pod 入站处执行来源限制；不只依靠主机防火墙限制经过 kube-proxy 的转发流量。Pod 固定到上述工作节点，因此访问其他节点上的同一端口不是备用入口。

Headlamp 直接终止 HTTPS，使用包含 `.110` IP SAN 的专用自签证书。首次浏览器访问需要确认该证书；公开证书在 `~/.cnpl-secrets/consoles/lab-primary/headlamp-tls/tls.crt`，私钥未进入仓库。Hubble UI 使用管理 LAN 内的 HTTP。Relay 仍为 ClusterIP，UI → Relay 的 4245 查询只新增精确 Pod 标签授权，Agent ↔ Relay 的既有 mTLS 保持原配置。

在 Mac 终端复制已签发的 Token，再粘贴到 Headlamp 登录框：

```bash
pbcopy < "$HOME/.cnpl-secrets/consoles/lab-primary/headlamp-reader.token"
```

登录身份为 `system:serviceaccount:cnpl-consoles:cnpl-console-reader`，复用 Phase 01 的 `cnpl-observer` 白名单，补充 `metrics.k8s.io` 的节点和 Pod 只读权限。可以查看节点、工作负载、Service、事件、日志和指标；没有 Secret 读取、RBAC 管理或工作负载写权限。部分管理菜单显示 Forbidden 属于该权限边界。Headlamp 服务端自己的 ServiceAccount 没有 cluster-admin 绑定，也没有启用跳过用户认证的 `unsafeUseServiceAccountToken`。

Token 请求有效期 24 小时，到期后重新签发并复制：

```bash
bash ops/02-networking/consoles/refresh-token.sh
pbcopy < "$HOME/.cnpl-secrets/consoles/lab-primary/headlamp-reader.token"
```

脚本先核对集群 UID，再原子替换 0600 Token 文件，不输出凭据。再次签发不会立即吊销此前尚未过期的 Token。

## 配置与复现

| 文件 | 责任 |
| --- | --- |
| [headlamp-values.yaml](headlamp-values.yaml) | 独立 Headlamp Helm release，固定镜像摘要、HTTPS、非 root 和只读根文件系统 |
| [hubble-ui-values.yaml](hubble-ui-values.yaml) | 对现有 Cilium 1.20.2 release 的 UI 叠加配置 |
| [access.yaml](access.yaml) | Namespace、独立登录身份、只读绑定、Hubble NodePort、三个来源/Relay 策略 |
| [images.lock.yaml](images.lock.yaml) | 两个 Chart 的来源和 SHA-256、三个 Linux/amd64 镜像的来源/Harbor 目标及摘要 |
| [refresh-token.sh](refresh-token.sh) | 按需签发短期只读 Token |

采用现有 Helm release 的直接配置和独立 RBAC 绑定，不引入新的控制器、Ingress、存储或设计模式。保留 kube-proxy/VXLAN/CNI、SELinux Enforcing 和 firewalld。

安装前复验原集群 UID `4d3e52d7-e203-4daf-aced-9c3a666fcf5b`、十节点 Ready、版本与镜像摘要。三个镜像已按 [锁定清单](images.lock.yaml)复制到现有 Harbor 的公开 `bootstrap` 项目，目标摘要与上游 Linux/amd64 manifest 一致；所有新增容器均以完整摘要引用。Chart 缓存在管理 Mac 的 `~/Downloads/cloud-native-lab-seed-2026-10-14/`。

原 Cilium values、含证书的完整 manifest 和变更预览保存在仓库外 `~/.cnpl-secrets/consoles/lab-primary/`。先比较 Helm server dry-run 的原工作负载 spec，确认已有 Cilium、Envoy、operator 和 Relay 没有变化，才执行升级。本轮预览及安装后比较均通过。

复现当前工作区的配置时，先确认现有证书材料和访问对象归属，再应用资源。证书 Secret 必须从上述仓库外 TLS 文件建立，禁止把完整 Secret YAML 写入公开记录：

```bash
export KUBECONFIG="$HOME/.cnpl-secrets/kubeconfig-lab-primary"
export CNPL_SEED="$HOME/Downloads/cloud-native-lab-seed-2026-10-14"
export CNPL_TLS="$HOME/.cnpl-secrets/consoles/lab-primary/headlamp-tls"
"$HOME/.cnpl/bin/kubectl" apply -f ops/02-networking/consoles/access.yaml
"$HOME/.cnpl/bin/kubectl" -n cnpl-consoles create secret tls headlamp-tls \
  --cert="$CNPL_TLS/tls.crt" --key="$CNPL_TLS/tls.key" --dry-run=client -o yaml | \
  "$HOME/.cnpl/bin/kubectl" apply -f -
"$HOME/.cnpl/bin/helm" upgrade --install headlamp "$CNPL_SEED/consoles/headlamp-0.46.0.tgz" \
  -n cnpl-consoles -f ops/02-networking/consoles/headlamp-values.yaml \
  --rollback-on-failure --wait --timeout=5m
"$HOME/.cnpl/bin/helm" upgrade cilium "$CNPL_SEED/cilium/cilium-1.20.2.tgz" \
  -n kube-system --reuse-values -f ops/02-networking/consoles/hubble-ui-values.yaml \
  --rollback-on-failure --wait --timeout=5m
```

worker01 的 31235/tcp、worker02 的 30443/tcp 已分别增加 runtime/permanent rich rule，仅允许既有 `lab-mgmt` ipset。规则为 `rule family="ipv4" source ipset="lab-mgmt" port port="<本节点端口>" protocol="tcp" accept`，没有重载或关闭防火墙。Mac DHCP 地址变化后，需要同时复验 `lab-mgmt` ipset 和 [access.yaml](access.yaml) 的 `/32` 来源。

## 验证与回退

验收包括 Mac 直接访问两个页面、Headlamp Cookie 登录后读取十节点及指标、匿名/无效 Token/越权请求被拒绝、Hubble UI 自身的 control-stream 和 service-map-stream 返回十节点状态与真实 Flow，以及从非管理端 `.11` 访问两个 NodePort 均超时。CLI 的 Hubble 状态成功不能替代 UI 后端链路验证。本轮没有启动 Mac 长驻 port-forward，也没有打开浏览器做 GUI 验收。

本轮 Cilium 从 revision 3 升级到 4，Headlamp 为独立 release revision 1。回退前必须确认之后没有其他 Cilium 变更；本轮未实际执行回退。Headlamp 可独立卸载；关闭 Hubble UI 时对当前 release 显式叠加 `hubble.ui.enabled=false`，避免覆盖后续其他网络配置。随后仅撤销本目录拥有的 NodePort/策略/只读身份和两条原先不存在的 rich rule。删除 `cnpl-consoles` Namespace 前先确认没有其他人新增的资源，不直接清空空间。原 Cilium 与 Relay 配置、镜像缓存和其他 Namespace 均须保留。
