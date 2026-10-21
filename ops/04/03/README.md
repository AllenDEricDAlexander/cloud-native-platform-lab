# 04.03 GitLab CI 完整链路

覆盖 04.03.01–05。入口 validate、deploy、check、lint、trigger。lint 调 GitLab API，当前不执行；deploy 使用已核对 Chart 及 Secret 引用。模板串联 verify→package→security→propose→observe，后两步需实际审批/合并 GitOps MR。仅触发 pipeline、生成镜像或创建 MR 不算部署成功。

runner-values.yaml 是待按锁定 Chart 合入的安全配置；必须建立两个独立注册的 Runner/令牌/执行身份：cnpl-verify 普通 MR，cnpl-release 仅保护分支，标签、protected、run untagged、允许项目在 GitLab 服务端限制。release 的 pod_labels.trust 改为 trusted，另锁对应 values；不能靠 Job 自报标签保护凭据。发布任务不能取得管理员 kubeconfig。Manager 的 Role 仅 ci-gitlab，Job 的 application SA 无 K8s 权限。

CI 文件变量需按作用域挂载：BUILDKIT_CA/CERT/KEY、DOCKER_CONFIG、Maven/Cargo 等依赖凭据、签名密钥/口令、GIT_ASKPASS、GitLab curl config、ARGOCD_CONFIG 和健康端点 curl config；普通 MR 只允许依赖只读凭据。BUILDER_IMAGE、RUNTIME_IMAGE、RELEASE_TOOLS_IMAGE 固定 Harbor Digest。SOURCE_DIR 为 ops/04/05/examples/<language>，IMAGE_REPOSITORY 与 REGISTRY_CACHE 为独立受限仓库；GitOps 机器人只对目标仓库创建审核分支，不可合并 prod-like。

应用仓库引用平台模板应固定完整 SHA（05 的 export.sh 生成），模板升级通过 MR 回归 14 格。阻止 GitOps 仓库触发应用构建，避免回写循环。package 用不同 CI tag 和各自测试制品独立构建，同一环境晋级保留 Digest。GitOps 回写不强推、不直接 apply；审批后的观察核对部署健康和实际 source revision。

故障验收：fault.sh <Pod> 需现场记录 approved_uid 与本批次标签，测试 Job Pod 丢失、Manager 重建和重跑。仓库超时用专用测试 Job 的受限出口策略；凭据过期用单独测试机器人/文件，禁止轮换或吊销共享账号。编译/测试失败不得执行 package；已发布 SHA 重跑须由 Harbor 不可变规则拒绝覆盖或核验完全同一制品。每次故障保留 pipeline/job/Pod UID、失败点、退出码和重试后相同 source/Digest。现场还需 CI Lint、include 合并结果和 Runner/K8s API 权限实测。
