# Mac 控制台实际交付

2026-10-18 按用户最新要求选用社区 Headlamp，未部署 Kubernetes Dashboard。原集群 UID 为 `4d3e52d7-e203-4daf-aced-9c3a666fcf5b`。

| 控制台 | 实际入口 | 版本 / 状态 |
| --- | --- | --- |
| Headlamp | <https://192.168.9.110:30443> | 0.46.0，独立 Helm release revision 1，Pod 1/1 |
| Hubble UI | <http://192.168.9.109:31235> | UI 0.13.6，既有 Cilium 1.20.2 release revision 4，Pod 2/2 |

配置、登录、Token 续签、证书和回退说明见 [控制台操作说明](../../consoles/README.md)。Token 与私钥仅在 Mac 仓库外秘密目录，以下公开证据没有登录凭据。

## 验收证据

- [materials.json](materials.json)：Chart 摘要、三个上游/Harbor 镜像摘要一致；没有使用浮动镜像部署。
- [firewall-before.json](firewall-before.json)：两个工作节点新增规则前的 runtime/permanent 状态，便于按原状态撤销。
- [headlamp-checks.json](headlamp-checks.json)：Mac 页面 HTTP 200，校验证书/IP SAN；Token 经真实 Cookie 登录后读取十节点、kube-system Pod 和十节点指标。匿名读取节点为 403，无效 Token 为 401，Secret 读取为 403，创建 Deployment 的 SelfSubjectAccessReview 为 false。
- [hubble-checks.json](hubble-checks.json)：从 Mac 经 UI 同一 HTTP API 取得 control-stream 和 service-map-stream，十个 Relay 节点均 CONNECTED；本次样本为 253 条 Flow、17 个 Service 和 73 条 link。保留实际响应 protobuf 的 Base64 和摘要；测试通道均主动关闭。
- [final-validation.json](final-validation.json)：实际 release/Service/工作负载/节点健康、原工作负载 spec 未改变，以及非管理端 `.11` 对两个入口访问均被拒绝的最终复验。

Kubernetes 1.36.5 的实际功能验证已经执行，但没有打开 Mac 浏览器进行点击和截图验收。Headlamp 使用专用自签 HTTPS 证书，首次访问需要在浏览器确认；Hubble UI 为仅管理来源开放的 HTTP。未开放整个 LAN，未增加 cluster-admin 用户，未启动 Mac 长驻转发，未执行回退，未推进后续网络专题。
