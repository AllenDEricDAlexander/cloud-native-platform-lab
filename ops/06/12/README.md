# 06.12 GPU、驱动与 DRA

覆盖 06.12.01–04。`run.sh validate|render <plugin|dra>|inspect-host|plan|install <gpu_operator|dra_driver>|apply|dra|check|cleanup-plan`。没有真实 GPU/许可/受支持软件矩阵时，plan 失败并保持阻塞。V100 SXM2 不等于可插入 R730 的 PCIe 卡，显存足够不代表当前 vLLM/驱动/CUDA 支持该算力架构。

inspect-host 只核对登记节点、PCI、内核和已有驱动，不加载/安装驱动。现场证据 JSON 必须含 node、model、vram_mib、driver_mode，以及 hardware_visible/host_compatible/license_verified/rocky_kernel_supported/cuda_arch_supported/framework_supported 为 true；附实际型号/架构/直通或 vGPU、内核、驱动、CUDA、框架版本和支持来源。只能选择 operator 或 preinstalled 一条驱动链。

安装包审核 GPU Operator 的 nodeSelector/污点容忍、驱动/Toolkit/Device Plugin/NFD/DCGM 和权限，只作用 GPU 实验节点；preinstalled 模式必须在包中关闭 Operator 驱动管理。不要在全十节点安装驱动。保留 SELinux Enforcing/firewalld，按支持矩阵解决必要设备/运行时权限。

Device Plugin 路线先确认 allocatable `nvidia.com/gpu>=1`，apply 一个有界 Job；cuda 镜像须包含匹配架构的 PyTorch，实际在 GPU 计算求和，check 要求 Job Complete 和计算标记。nvidia-smi 可见不是计算通过，也不能证明重启后正确；单独做一次授权节点重启/容器重建并复验。

DRA 另需匹配的 DeviceClass/驱动/API/Feature Gate 证据。render dra 使用独立 ResourceClaim 和请求引用，不混入 nvidia.com/gpu limit；在所选 CRD/API 中核对 exactly/claim 字段。先退出并清理上一 plugin Job，再 apply DRA Job，观察 Claim 分配、实际计算、任务取消/完成、Claim 删除后设备释放；不要让同名已完成 Job 代替第二次运行。共享、MIG、时间片与显存隔离只验证真实硬件支持的能力。

失败按 PCI→驱动→Toolkit→分配→框架计算分层定位，保留失败事件，不输出假性能。退出先停应用/Job，确认设备和 Claim 释放，再按本批安装归属退组件；驱动卸载/重启单开维护窗口，不能清理未知系统文件。本轮硬件、驱动与计算均未验收。
