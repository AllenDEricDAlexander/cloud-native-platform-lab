# Phase 00 节点 node-readiness 矩阵

采集目录：`00.10.02-node-readiness-20261016-110931`；汇总时间：2026-10-16T11:09:41-04:00；节点数：10。
只读检查，期望值来自 hosts.yaml、resources.yaml、networks.yaml 与 versions.lock.yaml。
NetworkReady 期望为 false：00 未安装 CNI，NetworkReady=false 为阶段边界；普通 Pod 网络在 01 验收。

## 结果

| 节点 | IP | 通过 | 未通过项 |
| --- | --- | --- | --- |
| cp01 | 192.168.9.101 | 25/26 | CRI 自测（result=无 network=NODE cleanup= ssh_exit=255） |
| cp02 | 192.168.9.102 | 0/26 | 采集（schema=无输出 ssh_exit=255），其余检查未执行 |
| cp03 | 192.168.9.103 | 0/26 | 采集（schema=无输出 ssh_exit=255），其余检查未执行 |
| infra01 | 192.168.9.104 | 0/26 | 采集（schema=无输出 ssh_exit=255），其余检查未执行 |
| infra02 | 192.168.9.105 | 0/26 | 采集（schema=无输出 ssh_exit=255），其余检查未执行 |
| storage01 | 192.168.9.106 | 0/26 | 采集（schema=无输出 ssh_exit=255），其余检查未执行 |
| storage02 | 192.168.9.107 | 0/26 | 采集（schema=无输出 ssh_exit=255），其余检查未执行 |
| storage03 | 192.168.9.108 | 0/26 | 采集（schema=无输出 ssh_exit=255），其余检查未执行 |
| worker01 | 192.168.9.109 | 0/26 | 采集（schema=无输出 ssh_exit=255），其余检查未执行 |
| worker02 | 192.168.9.110 | 0/26 | 采集（schema=无输出 ssh_exit=255），其余检查未执行 |

## 唯一性

未采集、未参与比对：cp02, cp03, infra01, infra02, storage01, storage02, storage03, worker01, worker02。

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
| cp01 | cp01.k8s.internal.egon.top | 192.168.9.101/24 | 00:50:56:99:56:c1 | f4557bab56134176bdc09f939acbbbba | 5a8c1942-3caa-085a-7cad-357f8d256c11 | 4 | 7934 | sda:100G:0:0:1:0;sdb:100G:0:0:0:0;sr0:1.9G:3:0:0:0 | /dev/sda1 | 2026-10-16T23:09:33+08:00 |

## CRI 自测明细

| 节点 | 结果 | sandbox | 网络 | pause 进程标签 | 容器状态 | 退出码 | 日志 | 近期 AVC | 清理 | 开始时间 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cp01 |  | SANDBOX_READY | NODE | system_u:system_r:container_t:s0:c336,c664 |  |  |  |  |  | 2026-10-16T23:09:36+08:00 |

总体：未通过

