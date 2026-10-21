# 04.08 渐进发布、真实指标与签名准入

覆盖04.08.01–06。render canary/bluegreen输出独立<app>-rollout，不与07 Deployment同名争写；清单需进入受审GitOps路径，再由单独Application管理。deploy-controllers只安装锁定Rollouts/Kyverno；deploy-metrics安装本阶段最小真实采样/Prometheus，不依赖05。policy只在明确Audit/Enforce输入后安装。

Canary选择Gateway API插件，Controller镜像必须预置经SHA验证的插件与ConfigMap中的file://位置，不允许运行时从GitHub下载。兼容报告要核对Cilium/Gateway API/HTTPRoute、Rollouts/plugin版本和具体参数。插件未支持就停止，不用副本比例假装流量权重。HTTPRoute backendRefs的weight字段由Rollouts插件管理，Argo该Application必须忽略该字段并RespectIgnoreDifferences，不能持续同步抢写。

probe.py以固定间隔经真实HTTPS入口访问/compute，记录200、错误/超时、实际延迟直方图。Prometheus静态抓取采样器，两小时临时保留；无数据/零请求/NaN/查询错误都不能满足Analysis成功条件。正常版本形成1分钟基线再放10%→分析→50%暂停→批准100%；坏版本FAIL_REQUESTS=true仍有健康探针但返回500，需观察自动中止及稳定流量恢复。BlueGreen预览服务必须另配持续采样目标，不能拿仍指向旧active的健康指标批准preview；当前模板的地址须现场分别配置。

另测停止采样（无数据）、独立实验作用域屏蔽Prometheus访问（指标不可达）、路由适配失败；记录Analysis状态、真实流量、网关backend weights和回到已知Digest。abort只执行发布操作，正式回退同时恢复GitOps期望Digest。数据库结构仅允许前后兼容的新迁移，不随应用回退旧数据结构。

supply-chain.sh在可信CI内生成CycloneDX、离线Trivy结果和明确自定义buildType的来源声明，再签名镜像/来源并取回验证。Trivy DB必须是实际cache/db/metadata.json、检查UpdatedAt；HIGH/CRITICAL阻断；不声称完整SLSA等级。Cosign采用内网自管公钥模式：禁用公开tlog上传，验证仅跳过tlog要求而保留公钥/Digest签名验证；私钥和密码由0600文件挂载，密码通过stdin输入，不进argv/环境/日志。该行为以[Sigstore密码读取实现](https://github.com/sigstore/sigstore/blob/main/pkg/cryptoutils/password.go)为依据，实际锁定Cosign版本仍需现场复核。

Kyverno先Audit，再仅三个apps空间Enforce；公钥文件/SHA固定。还需仓库允许列表、Digest/资源要求和webhook故障关闭配置。admission.sh对signed/unsigned/wrong-key/registry-unavailable做server dry-run，只将明确该策略拒绝视为通过，普通连接失败不算拒绝证据。仓库失联用专用未缓存Digest和测试策略出口，不破坏共享Harbor；正式镜像缓存可能掩盖失联。可信、无签名、错误公钥、浮动标签/外部仓库和恢复身份的有限应急通道均需逐项实测。
