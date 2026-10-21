# 04.07 Helm、Kustomize、Argo CD/ApplicationSet

覆盖04.07.01–05。validate离线；render仅生成AppProject/ApplicationSet；export <仓库外新目录>生成base/<app>和environments/{dev,staging,prod-like}/<app>；deploy安装已锁Chart；bootstrap在仓库已受审提交后安装顶层声明；check读取同步/健康/HPA状态。业务对象不由CI或该引导入口直接apply。

Chart包含Values schema、Secret引用、探针、预算、HPA和可选HTTPRoute；image必须Digest。Helm只做独立比较，主GitOps使用Kustomize。同一业务对象不同时由两套工具管理。HPA启用时Deployment不写replicas；Argo忽略该字段且RespectIgnoreDifferences=true，其余漂移仍检测。现场以持续请求/压力观察HPA扩缩，确认持续同步不会重置副本。

AppProject限制准确GitOps仓库、三个Namespace、显式业务资源种类，不能创建集群级对象或Secret。ApplicationSet使用显式环境列表、create-update、preserveResourcesOnDeletion和prune=false，删除生成源先预览，不级联清空存储。顶层Namespace/CRD→控制器→等待Established/Ready→CR→应用分步引导，不用sync-wave掩盖控制器尚未Ready。

argocd.k8s.internal.egon.top的TLS/SSO、只读观察身份、仓库只读Secret、受审分支、受限Project RBAC与通知接收端需合入锁定values_file。notifications.yaml为待配置接收服务的触发模板，不能声称已发送通知；GitOps工程不启用自身应用CI回写循环。

export需要release.name/image、repositories.gitops、gitops.revision；可为各环境填写gitops.hostnames以及02的gateway_name/namespace。Gateway必须允许相应Namespace附着，TLS/路由通过条件和网络策略另核对。上线前对每个overlay执行kubectl kustomize、server dry-run/diff、Git审查；然后同步、HTTP/版本/Digest/权限负向检查。错误覆盖通过恢复已知Git版本再收敛，不手改被GitOps托管的Deployment。
