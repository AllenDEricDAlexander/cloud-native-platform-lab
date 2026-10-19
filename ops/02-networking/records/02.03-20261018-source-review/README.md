# 完整 02.03 执行前核验

正式故障与业务验收尚未执行。本记录只证明源码、配置准入及隔离替身编排已核验；主池和实验负载未部署，真实 speaker 没有被停止。前序完整02.02已由 `e572f31` 归档提交。

## 已完成的核验

- [结果](review.json)：63项Python测试通过（本批22、Service19、ClusterIP15、网络基准7）。本批覆盖双方向维护补丁/精确恢复、Pod/Service UID、空端点、重复ARP、网络失败分类、原有TCP连接与重连、部分主池回滚、进程身份与符号链接等。
- [最终真实只读日志](ansible-validate-20261018T235419Z-kPgXgE)：Mac、worker01、worker02、infra01的failed/unreachable均为0。原十VM、02.02原始回执、组件UID、内部镜像摘要、确定性构建、全部YAML严格服务端dry-run、CRD/Webhook、两个维护补丁严格dry-run、三个VM安全状态、十个VIP地址ARP冲突检查均通过。
- [源码摘要](source.json)与 `reviewed-source/` 完整保存最终受检输入；最终source与实际文件逐一相同。
- [保护基线](protected-after.json)与所有validate前快照一致，含MetalLB speaker/controller及Headlamp/Hubble UI；没有改变现有工作负载spec或关键配置。02.02的116份原始证据仍逐一符合归档SHA256。

## 离线编排与失败路径

网络和Kubernetes均为隔离替身，真实检查器的UID保护、端点检查、补丁计划、异步观测循环及恢复逻辑参与执行；不将模拟HTTP/ARP结果作为正式业务证据。

| 场景 | 结果 |
| --- | --- |
| [整批正常](offline/success-ansible.txt) | 122个Ansible任务通过；speaker完整恢复、观测退出、实验清理、完整主池保留 |
| [故障后主动注入失败](offline/failure-ansible.txt) | 预期Ansible失败退出2；always仍恢复原spec/两个speaker并停止观测 |
| [中断后recover](offline/recover-ansible.txt) | 17个任务通过；还原模拟维护状态，识别并停止遗留观测进程，保留完整主池 |
| [首次主池只创建一半](offline/partial-ansible.txt) | 15个任务通过；仅按原UID撤回本批不完整对象，正常关闭恢复批次 |

初次中断恢复替身演练发现 `/var` 与 `/private/var` 符号链接造成进程身份字符串比较不一致，旧日志 `offline/recover-path-bug-before-fix.txt` 保留；已改为解析实际argv并比较解析后的真实路径，补充针对性回归，并用真实本机替身进程重验恢复与退出。该问题未发生在用户集群运行中。

包装入口使用Python标准库fcntl独占锁；已核验真实validate期间不能再次取得锁，命令结束后内核自动释放，不遗留阻塞recover的目录锁。

下一步按[完整03个步骤、Ansible、YAML和命令](../../examples/metallb/README.md)，由用户一次运行all，正式结果将生成在新记录目录。
