# 02.02 Service 与 DNS 整组实际验收

批次 `02.02-20261018T225144Z`，run `20261018T225148Z-2196f879`，原集群 UID `4d3e52d7-e203-4daf-aced-9c3a666fcf5b`。全部专题与清理通过。

| 专题 | 实际证据 |
| --- | --- |
| 02.02.01 | 引用已归档 ClusterIP 的五种状态、150次HTTP请求及清理回执 |
| 02.02.02 | NodePort32474/32737；Cluster跨VM SNAT源10.244.8.40；Local保留Mac192.168.9.200；无本地端点访问超时；ClientIP十次新连接同一后端UID；临时规则恢复 |
| 02.02.03 | Mac通过.202实际HTTP成功；ARP入口worker01，MAC00:50:56:99:21:68；不同Service UID回收再分配同一VIP成功 |
| 02.02.04 | Headless返回两个真实Pod IP；手工Slice经ClusterIP到达指定Pod UID |
| 02.02.05 | CNAME、HTTP Host保留、原Harbor名称HTTPS401符合预期；别名明确因证书主机名不匹配失败 |
| 02.02.06 | UDP/TCP、搜索域、内外网DNS通过；同一CoreDNS正缓存命中增量3、负缓存增量2；Service创建后第一次轮询恢复并实际HTTP成功 |

[整组原始日志](ansible-all-20261018T225144Z-z4qVyA) recap：localhost ok270/changed65、两个worker各ok2/changed1；全部failed/unreachable/rescued/ignored为0。

[原始通过回执](passed.json)中的 `cleanup_passed:false` 是汇总时尚未执行清理的状态，保留其原始字节；[原始清理回执](state/closed.json)随后为true。[复核报告](acceptance-review.json)和[交接](handoff.json)联合验证两份原回执，下一步完整02.03。

38份执行源码/输入摘要匹配，`execution-source/`保留原始源码。116份原始文件均计算SHA256，见[evidence-sha256.json](evidence-sha256.json)，不覆盖日志或attempts。归档只读检查另外修正了已部署组件分支的Helm4兼容性：`helm list --all`已删除，改为显式状态参数；已使用真实Helm4查询核验，不改执行快照。

临时Namespace、VIP Service、地址池及宣告已回收；NodePort运行/永久规则恢复；已有控制台及关键配置UID/spec摘要不变。MetalLB0.16.1的controller1/1、两个worker speaker2/2、必要7946节点规则保留供02.03。尚未进行宣告节点故障漂移。
