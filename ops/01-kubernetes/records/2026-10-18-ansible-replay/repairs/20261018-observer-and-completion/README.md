# 03–06 剩余实验完成记录

用户授权 Codex 自行修复并实际运行剩余组。原运行目录继续沿用，未执行新的 HA 关机。

## 修复

真实 Go 响应头为 `X-Connection-Id`，检查器把响应头转成普通字典后按 `X-Connection-ID` 大小写敏感查找，导致已经取得目标副本连接却未取得 connection ID。现在按 HTTP 头名不区分大小写读取，原始响应头证据保持原格式。参见 [Python HTTPResponse 文档](https://docs.python.org/3/library/http.client.html#http.client.HTTPResponse.getheader)。

观测启动失败时新增读取异步任务实际 stdout/stderr 的路径，避免只显示 ready 文件超时。执行源码只修改 `checks/traffic.py`、`ansible/tasks/replay/start-observer.yml`；[版本登记剧本](adopt-source.yml)先归档旧 context，再登记这两条准确路径，成功断点不重写。

## 实际结果

[完整执行日志](runtime-0001.txt)末尾同时出现 `ANSIBLE REPLAY ACCEPTANCE PASS`、`ANSIBLE REPLAY CLEANUP PASS`。全部主机 `failed=0`、`unreachable=0`、`rescued=0`。管理端 `ok=1887 changed=293`；控制平面和两个 worker 的本次前检/物料检查 `changed=0`。

保留并跳过 14 个原成功断点，实际完成 12 个未完成组：

| 专题 | 本次真实完成 |
| --- | --- |
| 05 | readiness：端点摘除后的新连接与原持久连接；termination：PreStop/TERM/长请求排空、短宽限期 137、消息租约重投与幂等提交；protocols：HTTP/Exec/TCP/gRPC；cleanup |
| 06 | base、RC/RS 接管与补副本、Deployment 历史、手动扩缩与临时数据、RollingUpdate/Recreate/容量阻塞、暂停/恢复及三类失败回滚、stable/canary 独立入口、cleanup |

[完成复核](completion.json)确认 26 个成功检查点齐全、十节点 Ready/无压力、系统 Pod 健康、本批资源和派生 EndpointSlice 均为 0，worker02 无待恢复状态。

旧目录修复前 602 个文件除当前 context 的受控版本登记外均保持原字节；旧 context 已原样存于原运行目录 `origin/remaining-fix-0001/context.json`。14 个原成功断点未改变。[修复前 SHA](before-sha256.json)及[本次完整原始证据索引](runtime-evidence-sha256.json)用于核对文件；所有旧失败现场和本次完整原始证据都保留在原运行目录，不因归档结果而清理。

本次实际 attempt：`attempts/20261018T075904Z-bb895794`；对应原日志 `ansible-run-20261018T075901Z-FOi1SV`。

[64 项完整回归](regression.txt)通过。本次是 03–06 实际运行验收通过；07–10 将独立交付，运行结果另行记录。
