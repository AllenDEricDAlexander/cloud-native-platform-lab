# 完整02.03实际验收与02.04交接

批次 `02.03-20261019T000211Z`，run `20261019T000214Z-741f757b`。原集群UID `4d3e52d7-e203-4daf-aced-9c3a666fcf5b`。全部3项和清理通过。

| 项目 | 实际结果 |
| --- | --- |
| 02.03.01 | 持久主池.201–.210、autoAssign:false、两个worker/ens33；无显式申请保持未分配；Mac实际HTTP及独立VM广播ARP均通过 |
| 02.03.02 | 当前宣告worker01的speaker停止后，worker02接管；幸存speaker UID不变；首次观测到新入口成功HTTP为0.701秒；99个新连接采样无失败；原TCP连接3次继续成功后出现1次失败，随后重连，共3个epoch；恢复后两个speaker Ready且原spec完整恢复，ARP再次唯一 |
| 02.03.03 | .202从Service UID e98569c5-6e1d-49b8-8ee1-2d5f74fc8ebf撤销后，新UID 7bc2186e-07b3-426f-8160-567f65df4c93重新分配并实际可达，随后再次撤销；HTTP/ARP均不再响应，最终无活动分配 |

0.701秒是本批应用请求与ARP采样观测，不代表内核故障检测精度、包丢失率或零中断承诺。原连接发生了实际失败，不把重连当作原连接存活。

[原始日志](ansible-all-20261019T000211Z-OgshFQ)：localhost ok143/changed23，三个VM各ok2/changed1；failed/unreachable/rescued/ignored均0。[通过回执](passed.json)与[清理回执](state/closed.json)联合核对，[地址台账](vip-ledger.json)记录申请/撤销；passed内cleanup_passed:false保留为清理前原始状态，不改写。

[复核报告](acceptance-review.json)、[交接](handoff.json)。38份执行源码/输入摘要一致，原始快照保存于execution-source/；96份原始文件逐一计算SHA256，见[evidence-sha256.json](evidence-sha256.json)。

临时Namespace、VIP和观测进程已回收；原控制台、配置和speaker spec不变。MetalLB controller1/1、speaker2/2以及主池/宣告保留；.201继续预留给02.04主Gateway。
