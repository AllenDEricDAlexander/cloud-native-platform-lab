# 02.04 JSONPath 转义修复与真实前检

用户批次：02.04-20261019T105544Z。原错误日志及 context.json 保持原字节，[修复回执](repair-review.json)与原批次 repairs/20261019-jsonpath-escaping/ 保留修复依据。

根因：检查器三处普通 Python 字符串把 JSONPath 中的 \n、\t 提前解释为控制字符，真实 kubectl 因引号内出现换行而拒绝解析。首次准备时的离线 API 替身没有执行真实 JSONPath 解析器，未覆盖此问题。

## 修复

- crd_names、secret_meta、secret_list 改为 raw string，保持 JSONPath 转义至 kubectl 解析阶段；不改变查询范围或 Secret 取证限制。
- [真实 CLI 回归](../../tests/integration/gateway/test_jsonpath.py)使用锁定 kubectl v1.36.5 和仅在测试期间运行的本机 API 夹具：复现原错误、检查 CRD 列表与缓存、Secret 元数据/空标签/不存在项、制表符分列及换行分行、公开证书 tls.crt 的点号转义。测试不连接真实集群、不输出私钥字段。
- 启动器根据首次变更前的 state/protected.json 标记判断恢复提示；只有入口前检失败时，提示原目录直接重新运行 all。

## 验证

- [32 项本组测试](unit-gateway.log)通过，其中 5 项实际调用 kubectl；[9 处生产 JSONPath 参数审计](jsonpath-audit.json)没有真实换行或制表符误入表达式。Python 编译、Bash 语法通过。
- 本目录的 ansible-validate 原始日志显示真实整组前检通过：localhost、worker01/02、infra01/02、dns 的 failed/unreachable/rescued/ignored 均为 0。20 份锁定 CRD/策略及内置对象/两套 Chart 通过真实服务端 dry-run，自定义资源按锁定 CRD 做结构检查；自定义实例的 CEL/Webhook 在正式安装 CRD 后仍会逐项严格预览。
- 十节点和 02.03 原交接一致，Harbor 四个镜像及确定性构建匹配；四台承载 VM 的安全与服务状态、.201/.203 地址冲突检查通过，DNS 候选通过 named-checkzone。只有本地取证文件发生变化。
- [保护基线](protected-after.json)与前检一致；尚未部署 Gateway/Ingress/实验命名空间，没有签发叶证书或修改实际 DNS。没有把 validate 中跳过的部署/流量/故障任务算作通过。

attempts 中保留调用时的原始源码摘要。最终 [源码摘要](source.json)与 reviewed-source/ 包含之后仅修订的错误提示及操作说明；检查器和全部受检模板与真实前检版本相同。

## 继续执行

原批次只有入口日志与基础 context，失败发生在 Ansible 启动、CA 口令输入和远端变更之前。因此无需 recover，也无需更换记录目录。在管理 Mac 直接执行：

~~~bash
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/02-networking/scripts/gateway.sh all /Users/mario/SelfProject/cloud-native-platform-lab/ops/02-networking/records/02.04-20261019T105544Z
~~~

作用：沿用原批次身份与原始日志，重新完整前检，安全输入一次 CA 口令，再运行 02.04.01–07 并清理。预期 02.04 ALL PASS 和 failed/unreachable=0。完整实际实验仍由操作者执行。
