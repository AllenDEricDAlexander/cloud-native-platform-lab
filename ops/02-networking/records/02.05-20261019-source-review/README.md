# 完整 02.05 执行前核验

02.04 已归档提交 245fe00；本次再次确认其 385 份原始文件摘要保持。完整操作见 [全部剧本、YAML、命令与预期](../../examples/certificates/README.md)。按操作者答复，公网项明确 BLOCKED。

本记录证明源码、真实只读前检和隔离编排已经核验；尚未部署 cert-manager、签发实际专用中间 CA 或改动真实主入口引用。根 CA 口令留待操作者启动 all 时安全输入。

## 核验结果

- 最终 ansible-validate 原始日志：localhost、worker01/02、infra01/02 的 failed/unreachable/rescued/ignored 全部为 0。十节点、02.04 原交接、主入口 UID、根 CA 公共身份、六个镜像、确定性 Go 客户端、所有公开清单和四台 VM 的安全状态/时间同步均通过。
- 六份 cert-manager CRD、内置资源、五类后端、策略及 Chart 完成真实服务端 dry-run；自定义实例按锁定 CRD schema 校验。Certificate/Issuer 的实际 webhook 和准入策略类型检查在安装后逐项执行，不把尚未安装的控制器当作已验收。
- [本组 10 项 Python 测试](unit-certificates.log)通过，包含真实本机 Python/Go TLS 握手：有效、错误 SAN、未知 CA、不完整链和过期；并验证受限 CA、错误根口令、UID、防私钥取证、轮换 key/UID/定时条件、公网不冒充通过及恢复引用保护。[前组 32 项](unit-gateway.log)通过，包含真实 kubectl JSONPath 解析回归。
- Go 标准库客户端的四种 TLS 场景通过 race 测试，go vet 通过；[构建摘要](client.json)匹配版本锁。[五个镜像](images.json)已经复制至 Harbor 并逐一核对 Linux amd64 完整摘要。
- [JSONPath 审计](jsonpath-audit.json)没有误解码的控制字符。[保护基线](protected-after.json)保持；真实 cert-manager/lab-tls namespace 和 cert-manager CRD 均未创建。

## 完整编排与故障恢复

| 场景 | 实际结果 |
| --- | --- |
| [正常路径](offline/success-ansible.txt) | 420 个 Ansible 任务，failed/unreachable/rescued/ignored=0；内部验收、稳定周期、自动引用与实验清理通过。 |
| [续期阶段注入失败](offline/failure-ansible.txt) | 预期退出 2；31 个任务，always 恢复原主证书引用，并把已有 Certificate 收敛回七天/提前四十八小时续期。 |
| [中断后 recover](offline/recover-ansible.txt) | 19 个任务通过；模拟中断遗留自动引用与短周期后，恢复引用、退出短周期、清理实验 namespace，internal_passed=false。 |

编排中的 Kubernetes、网关和续期时钟为隔离替身；测试 CA、Python/Go 的正反 TLS 握手和临时端口服务器使用真实密码学校验，测试结束关闭。模拟结果不作为真实 CA、真实网关故障或真实 cert-manager 定时器的运行证据。详细 [正常回执](offline/success-report.json)、[失败恢复回执](offline/failure-recover-report.json)明确注明替身范围。

初次本机 TLS 测试发现严格 X.509 校验需要完整 AKI/SKI/KeyUsage；[初始结果](unit-before-strict-x509-fix.log)保留，补齐扩展后全部通过，没有降低 Python 验证强度。测试驱动的 bool 状态和 CSR 拒绝模拟问题也保留初始日志，并修正驱动后重跑整组。

[最终来源摘要](source.json)和 reviewed-source/ 保存受检文件；[汇总](review.json)明确 actual runtime 尚未执行、公网 BLOCKED。所有原始日志保留；真实环境的部署、自动续期、故障恢复和最终内部验收由用户的一次 all 完成。
