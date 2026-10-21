# 04.04 Jenkins 对等流水线与恢复

覆盖 04.04.01–05。validate 离线，render 输出 14 个短生命周期 Agent 的 JCasC 片段，deploy/check/trigger 需内网。jenkins-values.yaml 与 render.rb 结果合入仓库外锁定 values_file；Chart 的实际 Deployment/StatefulSet、PVC/容器名需兼容报告确认，若 Chart 名称不同同步输入与命令，不能只凭解析通过安装。

Controller 无普通执行器，插件由固定版本清单烘焙进镜像，不在启动时下载。plugins.txt 只列必需插件，不冒充版本锁；jenkins_plugins 物料报告须给出所有精确版本及依赖。Controller 保存 Ceph PVC、JCasC 与凭据加密材料；TLS 入口由 02 网关承接，现有 Secret 和内部 CA 先准备。

verify Multibranch 文件不绑定发布凭据。release 从平台仓库固定 SHA 的 Jenkinsfile 和 Shared Library 加载，源提交由发布审批者审查；发布文件夹与普通 MR 文件夹分开，凭据仅在 release 文件夹可见，不能仅靠 Jenkinsfile 的 when 条件保护。Shared Library 导出根是 library/{vars,resources}，按固定 SHA 配置，禁止任意版本覆盖。cnpl-release-approvers 需现场配置身份与权限；普通用户无插件/脚本/云模板管理权。

共享库与 GitLab 使用同一 05/build、03/shared/package、08/supply-chain、03/shared/gitops/observe，测试失败立即停止。Builder/tools/Agent 共享临时 workspace，权限为 UID/GID1000；Builder 与 tools 图片/版本、BuildKit mTLS、read-only Argo 身份、依赖代理环境变量在受信 JCasC 中设置。构建不重试外部写操作，Agent 丢失后整次重跑仍保持原 source revision，不复用另一 CI 镜像冒充构建。

backup.sh 先 quiet-down 并等待全部 busyExecutors=0，再将完整 JENKINS_HOME（含 credentials.xml、secrets/master.key 等敏感材料）流式写仓库外 0700 目录的 0600 文件，退出时恢复接单；只归档路径/SHA。该归档包含秘密，需加密和独立备份，不进入普通 CI artifacts。

恢复演练必须在全新隔离实例进行：创建新 PVC→停止该临时 Controller→校验归档 SHA/解密→以相同 Jenkins UID 解压→同版本 Controller/插件启动→核对 JCasC/凭据引用/任务/Agent→执行验证任务→记录恢复耗时和清理。不得覆盖在用 PVC，也不在本任务自动启动临时实例。现场测试 Controller 重建、Agent 丢失、Webhook/分支过滤、仓库超时/测试凭据过期和重复发布；backup 成功不等于恢复验收。
