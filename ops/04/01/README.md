# 04.01 仓库、环境与交付契约

覆盖 04.01.01–04。contracts.json 固定七语言、双 CI、linux/amd64、健康接口和制品身份。应用源码、受审 CI 模板、IaC、GitOps 分仓库管理；普通 MR 无发布/签名/IaC 凭据，GitOps 机器人提交不得触发应用构建。GitLab 的受保护分支/标签、审批与机器人权限需在现场项目设置中核对并保存证据，脚本不盲目覆盖现有项目设置。

```bash
bash ops/04/01/run.sh validate
# 仓库外配置填写 run_id 后可离线预览，不调用 kubectl：
CNPL04_INPUTS=/受控路径/inputs.json bash ops/04/01/run.sh render
# 连回内网、前置 00–03 验收和集群身份均核实后：
CNPL04_INPUTS=/受控路径/inputs.json bash ops/04/01/run.sh apply
bash ops/04/01/run.sh check
```

apply 创建三个 apps 环境及三个 CI 空间的限额、默认拒绝、DNS/内网仓库出口和无自动挂载 Token 的应用身份。已存在且不属于本 run_id 的资源会停止，不接管旧 Namespace。预算是本批次起点，不代表全部组件可以同时按上限运行。网关入口、Metrics、BuildKit、数据服务和 API 例外由后续明确策略添加，不能临时开放全网。

检查保存配额/身份/策略对象；后续还需真实跨环境密钥拒绝、网络允许/拒绝及超额调度实验。优雅退出/日志/Metrics/Trace 在 05 样例与 08 真实发布验收。清理必须先退出 GitOps 管理并预览批次对象，不能直接删除有持久数据的 Namespace。
