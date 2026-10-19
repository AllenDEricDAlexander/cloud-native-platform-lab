# 完整 02.04 执行前核验

02.03 已按原始执行回执归档并提交 dce5146；[96 份原始文件摘要复核](preceding-evidence-review.json)全部一致。保留前序证据与执行时源码快照，不用 02.04 的版本锁覆盖旧快照。

本记录是源码核验与隔离编排演练，正式 02.04 集群部署、实际 VIP 流量及 Pod 故障实验尚未执行。完整操作见 [一次执行全部七节](../../examples/gateway/README.md)。

## 已完成

- [Ansible 语法检查](ansible-syntax.log)、Bash 语法、Python 编译检查通过。
- 实际 Ansible [渲染日志](render.log)和 [全部公开渲染结果](rendered/)：19 份自定义资源通过锁定 Gateway API 1.6.1 / EnvoyProxy CRD 的 OpenAPI 结构及未知字段检查；两个锁定 Chart 正常渲染，实际工作负载镜像均为 Harbor 完整摘要。
- [39 份内置资源](builtin-schema-review.json)通过 Kubernetes v1.36.5 官方 OpenAPI schema 离线校验（省略可选 null，处理 int-or-string）；不能代替服务端 CEL/Webhook/PSA 准入。
- [27 项本组 Python 测试](unit-gateway.log)通过，覆盖 UID 防接管、原代条件、证书引用精确恢复、Secret 数据禁止取证、错误叶私钥拒绝上传、受限测试 CA 签发/复用、空 ports、DNS 原记录/serial、未完整验收与中断观测等。前序 [MetalLB 22 项](unit-metallb.log)、[Service 19 项](unit-services.log)、[ClusterIP 15 项](unit-service-clusterip.log)、[网络基线 7 项](unit-network-baseline.log)均通过，共 90 项。
- [Go 四项真实协议单元测试及 race/vet](go-validation.json)通过；[确定性构建](image-build.json)与版本锁镜像和客户端摘要一致。[镜像物料](images.json)及 [诊断镜像发布回执](fixture-published.json)保留了本次已完成的 Harbor 准备证据。
- [DNS 原角色渲染](dns-render.log)产生与增量逻辑一致的两个短名称 A 记录，不重复已有记录或 PTR；正式应用从 slurp 获取原区域精确字节，应用前再核对 SHA256。

## 隔离完整编排与失败恢复

Kubernetes API、DNS 和 VIP 流量均为替身。实际 Ansible 分项剧本、模板、锁定 CRD 结构校验、Chart、隔离 CA 叶证书签发、UID 计划、证书引用补丁、验收缺项检查、有界异步观测和恢复函数参与执行。测试 CA、叶私钥、模拟 Secret 及模拟 passed/closed 仅在临时目录；不归档为真实集群验收。

| 场景 | 证据与结果 |
| --- | --- |
| 完整正常路径 | [原始日志](offline/success-ansible.txt)、[结果](offline/success-report.json)：626 个 Ansible 任务，failed/unreachable/rescued/ignored 为 0；七节完整编排及清理通过，主入口收敛 80/443。 |
| 外空间证书实验中主动注入失败 | [原始日志](offline/failure-ansible.txt)：预期失败退出 2；43 项任务，always 仍按 UID 恢复原证书引用并撤销临时授权。 |
| 中断后 recover | [原始日志](offline/recover-ansible.txt)、[结果](offline/failure-recover-report.json)：模拟已切到外空间证书并遗留观测进程的现场；56 项任务通过，恢复证书/停止观测/清理四空间，明确 formal_acceptance_passed=false。 |

两台 worker 的硬反亲和搭配 maxSurge=0/maxUnavailable=1，避免默认滚动更新等待第三个调度位置。排空 10 秒、最短排空 2 秒，Pod 终止宽限 45 秒；最终主入口检查同时核对实际滚动策略和 Pod 终止宽限。修正后已重跑完整 626 项编排。追加的 [34 项公开/私有任务回归](offline/final-private-public-tasks.log)验证 Secret 专用路径、叶私钥匹配和 JSON 0600；首次正常演练日志保留于 offline/success-before-rollout-fix-ansible.txt。

最初隔离驱动搬到临时目录后，模板相对路径解析失败；[初始日志](offline/harness-path-error-before-fix.txt)保留，已修正驱动路径后完成整组演练。演练过程中完善了替身 Deployment status 模拟；这两项属于测试驱动问题，未执行真实集群变更。

## 当前远程核验限制

[只读网络诊断](network-diagnostics.json)显示：当前 API 请求超时，SSH 到 .101 超时（此前也出现 No route to host），Mac 内部 API 名称暂不能解析。统一 validate 在创建上下文及任何集群变更前退出；[原始输出](ansible-validate-20261019T014021Z-7rOzti)保留。本次不能声称十 VM 当前在线、远程安全状态、实际服务端准入、ARP/DNS 候选已再次实测通过。

恢复 Mac 到实验网的连通后，直接执行完整 all；它会先重做全部前置核验，自定义对象在 CRD 安装后再逐项严格服务端 dry-run。无需分小节执行。启动时只安全输入一次现有中间 CA 口令；validate/recover 不询问口令。

[最终源码摘要](source.json)及 reviewed-source/ 保存受检输入；[汇总](review.json)明确区分离线通过与未完成的远程前检。没有部署 Envoy Gateway、Traefik、实验后端，没有修改实际 DNS 或主池。
