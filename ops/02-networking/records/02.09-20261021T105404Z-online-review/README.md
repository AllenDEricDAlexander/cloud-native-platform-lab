# 02.09 内网恢复后的运行前核验

本轮只执行 validate、只读检查与服务端 dry-run，没有执行正式 all 或切换数据面。BGP 真正的建连、路由和撤回仍由用户本轮整组运行验收；修复保留在工作区，实测通过后归档提交。

- API readyz正常，十台VM Ready；Cilium/kube-proxy均10/10，主入口VIP为192.168.9.201。
- 36项数据面及边界测试、10项公共入口测试通过，Ansible语法通过。
- 完整validate入口：ok=5、changed=0、failed=0。20个内置对象与25个CRD服务端预览通过，10个自定义对象结构校验通过。
- 另外对10个自定义对象执行实际服务端CEL/admission dry-run，包括按真实Worker Node名生成的两份NodeConfigOverride；未持久化资源。
- 四种Helm profile读取实际原release值后渲染通过，Operator配置checksum随模式变化，default-lb-service-ipam均为none。输入摘要与当前源码一致。

详见 [delivery-review.json](delivery-review.json)、[custom-server-dry-run.json](custom-server-dry-run.json) 与同目录完整validate日志。

整组运行：

~~~bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
export LAB_DATAPLANE_RECORDS="$PWD/ops/02-networking/records/02.09-$(date -u +%Y%m%dT%H%M%SZ)"
bash ops/02-networking/scripts/dataplane.sh all "$LAB_DATAPLANE_RECORDS"
~~~

三行分别进入仓库、建立新证据批次、一次完成22步及自动回退。正常预期failed=0、available_cases_passed=true、cleanup_passed=true。外部BGP转发仍为BLOCKED，phase_complete=false保留该缺口。

中断或清理未确认时只恢复原目录：

~~~bash
bash ops/02-networking/scripts/dataplane.sh recover "$LAB_DATAPLANE_RECORDS"
~~~
