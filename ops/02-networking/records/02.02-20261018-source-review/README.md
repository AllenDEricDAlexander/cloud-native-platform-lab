# 02.02 整组源码核验记录

这是执行前核验，正式业务验收尚未执行。02.02.01 的正式验收和清理由提交 `4bffb80` 归档；本记录仅覆盖下一批剧本准备。

- [核验结果](review.json)：41 项 Python 回归、Go race 测试及 vet、完整 Ansible 语法和执行衔接检查通过。
- [最终真实 validate 日志](ansible-validate-20261018T162255Z-MUDlUD)：Mac 与两个 worker 的 failed/unreachable 均为 0；十 VM、原集群身份、镜像完整摘要、确定性构建、全部业务 YAML 与 MetalLB Chart/CRD 的内置资源严格服务端 dry-run、VIP ARP 冲突和 VM MAC/IP 核对均通过。MetalLB CR 首次不存在，只进行了本地范围核对；真正的 CR Webhook 准入在用户执行时、匹配 CRD/控制器就绪后完成。
- [离线完整编排演练](offline/ansible-contract.txt)：255 个任务通过，所有 kubectl/helm/防火墙和网络结果均使用隔离替身。它验证模板、变量、动态端口、创建/删除 UID 回执、规则恢复和清理调用链，不证明真实网络或控制器部署通过。[复现工具](offline/harness.py)。
- [冻结源码](source.json)和 `reviewed-source/` 保存最终受检输入；[现有资源摘要](protected-after.json)与各次 validate 之前相同，含 Headlamp/Hubble UI，未改变其 spec 或关键配置。
- 02.02.01 的 64 个原始证据文件摘要复核未变。

第一轮 dry-run 发现手工 EndpointSlice 的 managed-by 标签值含斜杠，不符合 Kubernetes 标签值格式；已改为 `cnpl.io.services-suite`，原始失败日志及后续成功日志均保留。

没有运行 `all` 或 `run`、没有部署 MetalLB/测试负载、没有修改 VM 防火墙。内网镜像物料已准备。下一步由用户按[完整操作说明](../../examples/services/README.md)一次运行全部专题和清理。
