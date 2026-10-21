# 06.06 Knative Serving/Eventing

覆盖 06.06.01–04。`run.sh validate|render|install <knative_serving|knative_network|knative_eventing>|apply|check|traffic|request|events|cleanup-plan`。网络实现先核对已选 Envoy/Istio 适配，只安装一条兼容路径；Broker 类必须对应真实持久化实现/Channel，不能只安装核心 CRD 就宣称事件持久可靠。

先在现场锁定 Serving、网络插件、Eventing 与 Broker/Channel 的完整本地物料，依次安装并检查；若组件已由其他阶段管理则复用。apply 部署 hello、相同镜像的常驻 resident、Broker/Trigger 和 dead-letter 接收端。普通默认拒绝策略下，必须另加只允许实际网关/activator/Eventing 命名空间和端口的网络策略，按输入出口开放精确后端连接，不能依赖默认全通。

用内网 HTTPS 域、CA、认证和私有 curl 配置执行 request；保存状态/首字节/总耗时，响应正文不落普通日志。发布第二个固定 Digest 时用受控 GitOps/本批 Service 模板只变镜像，等待新 Revision Ready，再填写两个真实 Revision 执行 traffic；脚本核对同一 hello 和批次标签，按 UID/resourceVersion 条件设置 90/10，不接管别的 Service。恢复 100% stable 使用同一审核配置变更，不能删除仍有流量的 Revision。

分别测常驻高流量、间歇请求和长任务，等待实际缩零后采集第一批请求；拆分镜像拉取、启动、Readiness、activator 等待和应用耗时，记录错误率。对照 resident 时使用同样镜像、请求和资源，不能从一个请求推出成本结论。

events 重发同一 CloudEvents ID，实际接收方必须持久化业务效果并幂等；比对 05 的 ID 回执。逐项测试 filter、不匹配事件、消费者失败、有限重试、dead-letter、持久后端重启与重放，保留每条 ID 去向。HTTP 202 只代表入口接受，不证明消费/持久化完成。

清理先停止生产器、处理积压/失败目的地，再撤 Trigger/Broker/Service/路由，最后按组件归属退出控制器；共享网关和消息存储保留。当前所有请求、冷启动、灰度和事件结果未验证。
