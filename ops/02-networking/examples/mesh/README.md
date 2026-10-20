# 02.10 VM 版迁移状态

项目明确禁止在 Mac 启动 Docker Desktop、kind 或其他本地容器实验。原 kind 方案停用，管理端只运行 Shell、Ansible、Helm、kubectl 与构建/测试。

当前正式 VM 入口尚未交付，状态为 BLOCKED_VM_PORT；不提供 all 命令。共享后端在任何 Docker 命令前拒绝 Mac 的 all，旧整批 all 同样提前拒绝，避免误跑。

后续必须复用现有 .101–.110 VM 集群，先核对 Sidecar/Ambient 与原 Cilium 的兼容性，限定命名空间、SA、CNI配置、SPIRE socket/PSAT权限，准备原状态回退，再交付一次完整的执行入口。历史方案和物料仅作移植参考，不是可执行交付。

02.09 改为 VM 主集群后，只有它的实际回退和清理通过，才可开始 02.10 的正式实验。
