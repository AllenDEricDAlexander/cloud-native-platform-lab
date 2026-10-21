# 04.10 Tekton、Flux、Dragonfly对照与交接

覆盖04.10.01–04。所有控制器和示例限定对照作用域，主Argo/CD/CI权限不复用。默认validate；render flux/tekton离线生成；deploy-*需主锁及兼容报告；bootstrap-*只安装对照顶层资源。不能与其他步骤并发修改同一对象。

Tekton主线选同一Java应用，Task按固定提交检出→Builder测试→BuildKit独立构建→扫描/签名。comparison-build-config、comparison-build-auth和文件凭据卷由受控values配置，仅能写比较Harbor仓库，不能写prod-like或IaC。首次创建PipelineRun需新workspace PVC和明确serviceAccount、Pod安全上下文、资源/worker选择；不反复复用失败workspace。构建后将回执Digest部署到独立tekton-lab验收应用，按05接口检查与清理，禁止直接改主Argo托管资源。Controller安装使用已锁完整官方清单，CRD Established后再bootstrap Task/Pipeline。

bootstrap-tekton建立Task/Pipeline与仅tekton-lab的部署Role；start-tekton需显式唯一comparison.pipeline_run，创建有5Gi临时PVC、worker选择和UID1000/fsGroup的PipelineRun。最后一步自动部署比较Deployment/Service并核对/health、/version。comparison-build-auth挂载key/cert/Docker auth到仅package步骤，密码只复制到短期0600文件并在退出时清除；Builder不挂签名卷。ConfigMap填写PIPELINE_URL、BUILDER/RUNTIME_IMAGE、限定IMAGE_REPOSITORY/REGISTRY_CACHE、BUILDKIT_ADDR、Trivy预热DB及公钥路径；不含密码。

Flux控制器启用no-cross-namespace-refs和受限默认serviceAccount，比较Kustomization明确使用flux-lab/flux-reconciler的Role，prune=false；只读源仓库Secret同Namespace。路径只能./experiments/flux/<name>、固定Git提交，目标只在flux-lab，Argo不管理该路径。验收源更新/失败/恢复和Ready、实际HTTP/Digest，不能仅看控制器Pod。

Dragonfly只在显式批准的worker节点测试，Chart使用受限节点/资源，不覆盖全体containerd。先备份并人工审查该节点containerd代理差异和自动限时回退，再按对应版本配置；不关闭SELinux/firewalld。run.sh pull direct|p2p cold|warm校验登记FQDN、实际containerd配置SHA及目标Digest，拒绝把节点已有镜像当cold，不自动rmi/prune。direct与P2P用明确批准的独立试验配置/新测试Digest，记录可比层内容、节点/Daemon缓存、耗时与带宽；p2p_hit_verified默认false，必须另有Dragonfly日志/抓包证明命中与失败回源，不以warm节点缓存冒充P2P。

结束先停PipelineRun、suspend比较Flux调谐、撤销专用机器人凭据，再cleanup.sh preview列出本run对象UID；核对后逐对象清理Task/Run/Deployment/Service/ConfigMap/RoleBinding。PVC和任何数据库/镜像制品只在备份/保留期审核后单独删除，不直接删Namespace/CRD或卸载共享Operator。Dragonfly先恢复原containerd配置并检查镜像拉取/工作负载，确认无依赖再卸载对照组件。保留失败和恢复记录。

cleanup.sh delete只允许预览中的Deployment/Service/ConfigMap/Role/RoleBinding，限定两个对照Namespace，REST DeleteOptions使用准确UID前置条件防止同名重建竞态；Task/Run、PVC与控制器卸载继续单独审查，入口不做全局prune。

handoff.rb <仓库外验收索引>验证55个步骤、passed和每份证据SHA，只生成待人工复核标记，不自动宣布阶段完成。必须核对14格、双IaC的锁/幂等/补偿/外部恢复、真实灰度与自动中止、签名/准入拒绝、自助完整链路和本对照实验，向05交接service/language/environment/revision/Digest/trace标签、指标与故障结果。当前所有运行项仍未验收。
