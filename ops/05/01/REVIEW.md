# 05.01 离线走查

2026-10-21：`bash ops/05/validate.sh` 通过 Shell/Ruby 语法、JSON/YAML/重复键、四份 Ansible syntax-check、16 台主台账/派生 Inventory 一致性及 9 项本地正反检查。预算构造得到原始逻辑上界 14 GiB、三副本 42 GiB、含 30% 余量 61 GiB；只是最长保留期且未压缩的保守估计。

走查核对：数据库拒绝接管、schema 仅空库事务导入、秘密 stdin/no_log、逐机不同 PSK、Server loopback 与管理地址、Web 来源限制、RPM SHA/签名/NEVRA、离线 dnf 与安全基线。安装使用既有专用 Ansible，不新增依赖。

尚未运行：RPM 兼容与签名链、PostgreSQL/schema、Nginx/PHP-FPM socket 与 SELinux 策略、Zabbix 7.0 精确补丁 API/import 格式、页面、16 台数据更新、Agent 中断恢复、Ansible 幂等。部署前将上述兼容记录与物料登记主锁。API/页面检查不能代替用户后续浏览器验收，本轮未开浏览器或连接内网。
