# 05.01 遥测契约、预算和集群外探测

覆盖 05.01.01–04，并为 05.03.02 提供 16 台 Agent。`contract.json` 统一七语言服务/环境/版本、低基数指标标签、日志字段、隐私与保留预算；`budget` 输出带假设的容量上界，真实日增量和 Datastore 余量待现场测量。

```bash
bash ops/05/01/run.sh validate
bash ops/05/01/run.sh hosts
bash ops/05/01/run.sh budget
# 连接内网、完成本节输入后逐个执行：
CNPL05_INPUTS=/受控目录/inputs.json CNPL05_MATERIALS=/受控目录/materials.json bash ops/05/01/run.sh inspect
CNPL05_INPUTS=/受控目录/inputs.json CNPL05_MATERIALS=/受控目录/materials.json bash ops/05/01/run.sh install
CNPL05_INPUTS=/受控目录/inputs.json bash ops/05/01/run.sh verify
```

`install` 先 inspect，再仅在 build01 安装 RPM/systemd Server、专用 PostgreSQL、Nginx/PHP-FPM，随后 API 配置主机，最后每批两台安装主动 Agent 2。拒绝已有非本批数据库/Agent，不改变构建目录、网络、现有软件源，不重启业务服务。TLS Web 固定既有域名 8443，10051 只允许 16 台来源，10050 只监听 loopback，SELinux Enforcing/firewalld 保留。

inspect 仅需要 run_id 和本地资源门槛，不要求提前准备 PSK/证书/安装秘密。verify 只需 API 账户/CA；install/configure 才读取逐机 PSK。Server 与 Agent 安装分别有归属标记，重跑主机配置摘要未变化则跳过 host.update，服务端全局 History/Trends 限定为 7/90 天。

`zabbix.private_vars_file` 是仓库外 0600 JSON，包含 `zbx_db_password`（24–128 位安全字符）、`zbx_api_username/password`（现有可管理账户，首次初始化后需更换默认密码）、`zbx_ca_file`、`zbx_tls_cert_file/key_file`、`zbx_psks`（按 Inventory 短名映射，16 个不同的 64 位十六进制 PSK）、`zbx_web_sources`（管理来源 IPv4/CIDR）。私钥、CA 与 API 数据只从受控文件读取，探测参数由 prepare.rb 生成在私有临时目录，通过 item/trigger API 按变更接入，不需用户准备导入文件。

物料 `zabbix` 的 `file` 指向校验过的 JSON 包清单，键为 `server_packages`、`agent_packages`（每项 `file/sha256/nevra`，NEVRA 含 epoch）、`keys`（`file/sha256/fingerprint`）、`schema_file`（RPM 内 gzip schema 的绝对路径）、`schema_sha256`。服务端包需包括所选兼容版本的 Zabbix/PHP/Nginx/PostgreSQL 与依赖、SELinux policy/管理工具；Agent 包清单也须覆盖离线依赖。全部本地 RPM 签名验证，禁用网络仓库。精确版本和兼容结果写主锁后才能安装。

外部探测配置由 `probes.rb` 生成，仅作用于本批 build01：DNS、API、Harbor、管理站点和 OpenWrt 代理 TCP。所有 Web 检查校验证书；不通过停 DNS/API 或网络设备制造故障。单一专用测试目标的中断/恢复由操作者在批准窗口执行。

预期：Web/API 可用，16 台 CPU、内存、磁盘、网络在 300 秒内更新。`verify` 间隔至少 60 秒再运行，确认时间戳前进；在选定测试主机短暂停 Agent 并恢复，检查 Problem/Recovery。重跑 install 检查 Ansible changed、无数据库重建和无无故服务重启，保留首次/第二次证据。当前这些运行验收均未执行。失败后保留 records 和远端数据库，不执行卸载、清库或全局清理。
