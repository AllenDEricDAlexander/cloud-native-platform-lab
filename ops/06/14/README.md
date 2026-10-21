# 06.14 Chaos Mesh 与单故障工程

覆盖 06.14.01–05，仍属 06A。`run.sh validate|render <app|fault>|install|apply|check|fault|recover|cleanup-plan`。先填写 hypotheses、00–05 前置和独立备份材料，安装包核对 containerd socket、内核、权限、节点白名单、内部 pause 镜像与仅内网控制面；不要使用广泛 all namespace 选择器。

apply 创建本批两副本 target 和一个 peer，真实 HTTP/资源/告警/队列/数据稳态先验。fault 只允许 pod/network/stress 一种、精确 Namespace+phase/stage/run/app 标签、mode=one、10–60 秒。网络只对 peer→target 加 100ms 延迟，压力仅 1 worker/25% CPU+32Mi 内存。相同空间已有任何 Chaos CR 即停止，不叠加变量。

持续时间由集群内 Chaos Mesh 控制器收敛，管理端每 2 秒采样并按 max_error_ratio 立即中止；退出/INT/TERM 会按标签和 UID 删除本批 CR、等待清理，不移除 Finalizer。Mac 失联时仍靠集群内 duration，若控制器/daemon 也异常则必须执行独立恢复规程；kill -9 不能触发 shell trap。recover 可重复执行，只处理本批故障对象。先确认控制器恢复能力和 watch 事件，再执行首个故障。

check 的健康请求不代替网络延迟、资源/HPA/重试/队列/告警的完整因果证据；网络故障还要记录 curl time_total，压力记录 metrics 与 OOM/重启，Pod 故障记录 EndpointSlice 和业务结果。故障后同时核对 Chaos CR、daemon 规则撤销、所有副本、请求与数据，再开始下一种。

高影响实验分开窗口执行，当前脚本不提供未知主机停机或全局防火墙开关：

| 故障 | 执行与恢复边界 |
| --- | --- |
| Harbor/Nexus | 只在本批测试客户端/代理隔离明确目的 IP/端口，复用 00/04 客户端入口；同时观察现有 Pod、新拉镜像 Pod 与新构建，解除本批规则后再拉制品。不能停共享仓库服务来模拟局部故障。 |
| DNS/VPN | 复用 02 已验证单项动作和定时恢复，在独立管理入口确认恢复后注入；保留带外/直连访问，不改家庭全网 DNS/路由。 |
| ESXi/存储域 | 先按 VM UUID/实际宿主/etcd 成员/Ceph OSD 副本列影响矩阵，证明多数派与可写副本、独立备份、BMC/vCenter 恢复和剩余容量，再在授权窗口只停一个域；未知实际 VM 放置就阻塞。 |

这些实验复用 00/02/03 的真实入口而非另建竞争管理层，执行前把具体命令、原状态、恢复命令和独立定时器写入本批记录。不要假定 ESXi 本地 Datastore VM 自动迁移；不对唯一数据副本实施不可恢复实验。退出保留原始失败时间线，任何残留规则/数据异常都保持未验收。本轮没有注入任何故障。
