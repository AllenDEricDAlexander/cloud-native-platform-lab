# 03.07 离线走查（2026-10-21）

- 全部 Shell/JSON/YAML/Ansible 语法与 diff 检查通过。
- 走查普通 PostgreSQL/CNPG 镜像分离、业务 app 权限、三物理域、独立 WAL/CA、PITR 双标记、新目标恢复、已确认事务不丢及 major 迁移路线。
- 修正秘密临时目录清理不能覆盖原失败退出码；dump 恢复绑定回执身份并复核 SHA；MySQL 补实际 imageID 与锁定 Digest 的现场检查。
- 没有数据库运行、PITR、故障切换、升级或 MySQL 测试证据。CNPG/Barman/MySQL CRD 字段与客户端/服务端工具组合必须在版本锁和 compatibility_file 核实。
