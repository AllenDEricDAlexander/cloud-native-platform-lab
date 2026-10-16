# Phase 00 节点 node-readiness 矩阵

采集目录：`00.10.02-node-readiness-20261016-102410`；汇总时间：2026-10-16T10:25:13-04:00；节点数：10。
只读检查，期望值来自 hosts.yaml、resources.yaml、networks.yaml 与 versions.lock.yaml。
NetworkReady 期望为 false：00 未安装 CNI，NetworkReady=false 为阶段边界；普通 Pod 网络在 01 验收。

## 结果

| 节点 | IP | 通过 | 未通过项 |
| --- | --- | --- | --- |
| cp01 | 192.168.9.101 | 25/25 | — |
| cp02 | 192.168.9.102 | 25/25 | — |
| cp03 | 192.168.9.103 | 25/25 | — |
| infra01 | 192.168.9.104 | 25/25 | — |
| infra02 | 192.168.9.105 | 25/25 | — |
| storage01 | 192.168.9.106 | 25/25 | — |
| storage02 | 192.168.9.107 | 25/25 | — |
| storage03 | 192.168.9.108 | 25/25 | — |
| worker01 | 192.168.9.109 | 25/25 | — |
| worker02 | 192.168.9.110 | 25/25 | — |

## 唯一性

| 字段 | 结果 | 重复或空值 |
| --- | --- | --- |
| machine-id | 唯一 | — |
| BIOS UUID | 唯一 | — |
| MAC | 唯一 | — |
| SSH ED25519 | 唯一 | — |
| 主机名 | 唯一 | — |
| IPv4 | 唯一 | — |

## 明细

| 节点 | 主机名 | IPv4 | MAC | machine-id | BIOS UUID | vCPU | 内存 MiB | 磁盘 NAME:SIZE:HCTL | 运行时盘设备 | 采集时间 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cp01 | cp01.k8s.internal.egon.top | 192.168.9.101/24 | 00:50:56:99:56:c1 | f4557bab56134176bdc09f939acbbbba | 5a8c1942-3caa-085a-7cad-357f8d256c11 | 4 | 7934 | sda:100G:0:0:1:0;sdb:100G:0:0:0:0;sr0:1.9G:3:0:0:0 | /dev/sda1 | 2026-10-16T22:24:12+08:00 |
| cp02 | cp02.k8s.internal.egon.top | 192.168.9.102/24 | 00:50:56:99:41:c8 | c05c3ca6740e4a3284bf15395681ac83 | 65d71942-611e-932d-0cf0-2b1f36a8e669 | 4 | 7934 | sda:100G:0:0:1:0;sdb:100G:0:0:0:0;sr0:1.9G:3:0:0:0 | /dev/sda1 | 2026-10-16T22:24:18+08:00 |
| cp03 | cp03.k8s.internal.egon.top | 192.168.9.103/24 | 00:50:56:99:c2:84 | a00566fa418145b7b6e26273dfdda27a | bc7e1942-4bd0-87ea-c06a-296b6a10771e | 4 | 7934 | sda:100G:0:0:0:0;sdb:100G:0:0:1:0;sr0:1.9G:3:0:0:0 | /dev/sdb1 | 2026-10-16T22:24:25+08:00 |
| infra01 | infra01.k8s.internal.egon.top | 192.168.9.104/24 | 00:50:56:99:96:85 | 68ca1b074cdd4dd183b52e76e4db40c4 | 57db1942-3f63-6ff8-3411-01ea2ccd4005 | 6 | 11953 | sda:100G:0:0:0:0;sdb:100G:0:0:1:0;sr0:1.9G:3:0:0:0 | /dev/sdb1 | 2026-10-16T22:24:31+08:00 |
| infra02 | infra02.k8s.internal.egon.top | 192.168.9.105/24 | 00:50:56:99:2b:76 | b45e68483a2346f0a4d7df57b88e983b | d2531942-5b22-d994-3a69-dd58a3535d23 | 6 | 11953 | sda:100G:0:0:1:0;sdb:100G:0:0:0:0;sr0:1.9G:3:0:0:0 | /dev/sda1 | 2026-10-16T22:24:37+08:00 |
| storage01 | storage01.k8s.internal.egon.top | 192.168.9.106/24 | 00:50:56:99:39:3e | b9d5ee3c0c8544f98edf91ddd5b27156 | 79891942-7749-7b24-4e20-5c40d3b0a795 | 8 | 15985 | sda:100G:0:0:1:0;sdb:100G:0:0:0:0;sr0:1.9G:3:0:0:0 | /dev/sda1 | 2026-10-16T22:24:43+08:00 |
| storage02 | storage02.k8s.internal.egon.top | 192.168.9.107/24 | 00:50:56:99:cb:ec | dcaf1d0da8304c4799dc8f86e6c490e5 | fb871942-dd01-dba3-9a75-b212cd59f89a | 8 | 15985 | sda:100G:0:0:1:0;sdb:100G:0:0:0:0;sr0:1.9G:3:0:0:0 | /dev/sda1 | 2026-10-16T22:24:49+08:00 |
| storage03 | storage03.k8s.internal.egon.top | 192.168.9.108/24 | 00:50:56:99:a7:24 | 822b11881480442ea71fe9a5afb6e1c1 | 29161942-6cae-658d-f5bf-da58ea64b3b8 | 8 | 15985 | sda:100G:0:0:1:0;sdb:100G:0:0:0:0;sr0:1.9G:3:0:0:0 | /dev/sda1 | 2026-10-16T22:24:56+08:00 |
| worker01 | worker01.k8s.internal.egon.top | 192.168.9.109/24 | 00:50:56:99:21:68 | f9602da17401476595b2faaca9275411 | 84a91942-6f55-c5ac-5f6a-5b818f5fa497 | 8 | 15985 | sda:100G:0:0:1:0;sdb:100G:0:0:0:0;sr0:1.9G:3:0:0:0 | /dev/sda1 | 2026-10-16T22:25:02+08:00 |
| worker02 | worker02.k8s.internal.egon.top | 192.168.9.110/24 | 00:50:56:99:b9:98 | 4c6f6ccf672b45bf8d167cf42c19aaa9 | 09281942-b7af-2c4b-c7ab-bdbf98dfb549 | 8 | 15985 | sda:100G:0:0:0:0;sdb:100G:0:0:1:0;sr0:1.9G:3:0:0:0 | /dev/sdb1 | 2026-10-16T22:25:08+08:00 |

## CRI 自测明细

| 节点 | 结果 | sandbox | 网络 | pause 进程标签 | 容器状态 | 退出码 | 日志 | 近期 AVC | 清理 | 开始时间 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cp01 | PASS | SANDBOX_READY | NODE | system_u:system_r:container_t:s0:c84,c829 | CONTAINER_EXITED | 0 | phase00-cri-ok | 0 | yes | 2026-10-16T22:24:15+08:00 |
| cp02 | PASS | SANDBOX_READY | NODE | system_u:system_r:container_t:s0:c225,c654 | CONTAINER_EXITED | 0 | phase00-cri-ok | 0 | yes | 2026-10-16T22:24:21+08:00 |
| cp03 | PASS | SANDBOX_READY | NODE | system_u:system_r:container_t:s0:c638,c965 | CONTAINER_EXITED | 0 | phase00-cri-ok | 0 | yes | 2026-10-16T22:24:28+08:00 |
| infra01 | PASS | SANDBOX_READY | NODE | system_u:system_r:container_t:s0:c298,c897 | CONTAINER_EXITED | 0 | phase00-cri-ok | 0 | yes | 2026-10-16T22:24:34+08:00 |
| infra02 | PASS | SANDBOX_READY | NODE | system_u:system_r:container_t:s0:c512,c519 | CONTAINER_EXITED | 0 | phase00-cri-ok | 0 | yes | 2026-10-16T22:24:40+08:00 |
| storage01 | PASS | SANDBOX_READY | NODE | system_u:system_r:container_t:s0:c15,c31 | CONTAINER_EXITED | 0 | phase00-cri-ok | 0 | yes | 2026-10-16T22:24:46+08:00 |
| storage02 | PASS | SANDBOX_READY | NODE | system_u:system_r:container_t:s0:c740,c797 | CONTAINER_EXITED | 0 | phase00-cri-ok | 0 | yes | 2026-10-16T22:24:52+08:00 |
| storage03 | PASS | SANDBOX_READY | NODE | system_u:system_r:container_t:s0:c152,c900 | CONTAINER_EXITED | 0 | phase00-cri-ok | 0 | yes | 2026-10-16T22:24:59+08:00 |
| worker01 | PASS | SANDBOX_READY | NODE | system_u:system_r:container_t:s0:c792,c967 | CONTAINER_EXITED | 0 | phase00-cri-ok | 0 | yes | 2026-10-16T22:25:05+08:00 |
| worker02 | PASS | SANDBOX_READY | NODE | system_u:system_r:container_t:s0:c366,c849 | CONTAINER_EXITED | 0 | phase00-cri-ok | 0 | yes | 2026-10-16T22:25:11+08:00 |

总体：全部通过

