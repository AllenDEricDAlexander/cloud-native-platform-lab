# 交付核验：执行实现切换，真实重跑尚未开始

- [37 项回归](regression-37-pass.txt)通过；旧引导/身份/网络回归保留，新执行模型覆盖 UID、归属、TERM、备份取回逐字节比对、检查点和实际 Ansible helper 的离线执行。
- [最终 10 项专项回归](final-checks-and-helpers-pass.txt)通过，包含资源创建/apply/等待/清理、外来对象拒绝、失败现场保留且不补 PASS。
- [探针应用竞态测试](probes-go-race-pass.txt)、[控制器应用竞态测试](controllers-go-race-pass.txt)、[OCI 描述符及确定性测试](imagepack-go-pass.txt)通过；两个应用 go vet 通过。测试使用有限内存 HTTP/连接替身，没有启动监听服务。
- [最终真实 API 与只读前检](final-api-validation-pass.txt)：68 份单对象清单/变体 server dry-run、CoreDNS 源补丁 server dry-run、三对象网络 YAML 客户端检查均通过。三控制平面 etcd 工具 3.6.8、三正式成员、endpoint health、安全基线和备份路径检查通过，changed=0、failed=0、unreachable=0。未执行备份 collect、restic 远程写入、离线数据目录恢复或 VM 电源动作。
- [镜像实际导入](images-import-pass.txt)覆盖两个 worker 上的探针及 v1/v2/bad；[重复导入](images-idempotent-pass.txt)验证幂等。只导入静态 OCI 和查询 CRI，不创建容器。
- [静态核验及 SHA](static.json)确认 14 个当前 Python 文件可解析、80 个 Ansible YAML 无重复键、69 个实际渲染文件可解析、最终 context 与源码一致。Shell 语法、活动文档链接及代码 diff whitespace 检查通过；未发现公开记录中的真实私钥、客户端私钥正文或引导 Token。
- [最终只读健康](final-cluster-health.json)为原集群 UID、十节点 Ready、无压力、系统 Pod 健康；[本批空集](final-no-experiment-resources.json)确认没有部署实验资源。

旧原始记录 1183 个文件和旧源码 38 个文件逐份 SHA 验证不变；01.06 原六组、verify/cleanup 与原源码快照已核对通过。此次所有新输出与旧记录分开，新的故障运行验收由用户执行，01.07 未开始。

首次清单导出曾产生 ConfigMap 格式错误，实际 API dry-run 在创建前拒绝，见 [首次](initial-template-error-01.txt)、[第二次](initial-template-error-02.txt)；已修正源码并完成最终全清单验证。离线夹具也曾因临时路径和资源名解析失败，见 [最初回归](first-regression.txt)、[最初夹具](first-helper-fixture.txt)，最终实际 helper 执行通过。失败记录保留，不算运行成功。

交付过程的中间渲染/二进制副本留在本机并受忽略规则约束；最终 v2 的实际 YAML、context、来源 SHA 与镜像元数据入库。用户新运行的证据不受中间交付忽略项影响。
