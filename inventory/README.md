# 资产与参数台账

三份 YAML 当前均为 `planned_unverified`，字段来自既有规划，未连接环境核实。`null` 表示未知，空的磁盘/路由列表不能解读为环境中确实不存在。

- `hosts.yaml`：节点身份、IP、角色、计划/实际宿主机与设备引用。
- `networks.yaml`：LAN、网关/DHCP、DNS、集群 CIDR、VIP 与对外入口。
- `resources.yaml`：角色规格、宿主机预算、数据盘/备份容量和硬件前置。

00 核实后更新状态、时间与证据；节点 Linux/CRI 完成情况逐主机记录。Ansible Inventory 和 OpenTofu 变量在对应实施目录产生，这些台账不是可直接传给 ansible-playbook 的配置。

所有 `version`、包校验、镜像 Digest 和兼容性记录归根 `versions.lock.yaml`。先填写具体字段再安装；不把 draft 状态当成已锁定版本。
