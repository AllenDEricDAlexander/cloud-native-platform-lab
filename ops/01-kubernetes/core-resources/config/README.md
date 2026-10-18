# 01.10 配置、Secret、身份与阶段交接

独立入口为 `scripts/stage-10.sh`，主步骤在 `ansible/tasks/core/stage-10*.yml`。本目录的 YAML 定义配置消费者、Secret 私有模板和镜像拉取 Job；[身份矩阵](../rbac/README.md)说明实际允许/拒绝请求。

## 完整执行命令

```bash
# 1. 固定仓库位置。
cd /Users/mario/SelfProject/cloud-native-platform-lab
# 2. 为 10 创建独立记录目录，保留其他阶段原始记录。
CNPL10="$PWD/ops/01-kubernetes/records/core-07-10/runs/10-$(date -u +%Y%m%dT%H%M%SZ)"
# 3. 运行有限检查，编译测试应用并核验公开资源清单；不创建凭据或 Harbor 项目。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-10.sh validate "$CNPL10"
# 4. 核对 09 成功回执后，只运行 10 的配置、认证、授权、清理与交接。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-10.sh run "$CNPL10"
```

第 3 条预期 `01.10 SOURCE VALIDATION PASS`。第 4 条必须有 `01.10 ACCEPTANCE PASS`、`01.10 CLEANUP PASS`；公开的 `passed.json`、`handoff.json` 只在完整检查与清理之后产生。

## 实际对照

| 组 | 作用与预期 |
| --- | --- |
| ConfigMap 三种注入 | v1 同时注入 env、普通挂载和 subPath；更新到 v2 后等待普通卷真实刷新，env/subPath 保持 v1。重建同名消费者后 UID 改变，三者均为 v2。 |
| 不可变配置 | 单独创建 immutable=true 的对象；真实 server dry-run 必须拒绝更新数据，并明确是 immutable 错误。 |
| Opaque Secret | 本批随机凭据仅在私有目录生成；实际应用认证用正确凭据返回 200、错误凭据返回 401，均不输出凭据。轮换后卷最终更新，env 保持旧值；重建后两者重新一致。 |
| TLS Secret | 实际读取证书/私钥对，验证签名链、serverAuth 和 DNS SAN；不输出私钥。 |
| Registry Secret | 创建本 attempt 专用私有 Harbor 项目，复制既有公开 busybox 的精确摘要。先验证错误凭据的真实认证拒绝，再验证受限 pull 机器人能够执行 Job。 |
| 凭据轮换 | 第二代机器人更新同一个 Secret，撤销第一代；第二次拉取使用新的 repository scope，避免旧 bearer token 缓存影响验收。 |
| SA/RBAC | 普通应用无 Token；诊断、指定配置读取和有限运维使用独立 SA。`can-i` 与 Pod 内实际请求共同核验允许/拒绝。 |
| audience/生命周期 | 显式 600 秒投射 Token；错误 audience 的实际 API 请求为 401。另发绑定真实 Pod UID 的临时 Token，Pod 删除前 TokenReview 通过，删除后相同 Token 必须失效。 |
| 阶段交接 | 检查 07–09 真实回执、当前三 API/etcd、十节点及安全指标服务；引用已完成的 03 HA 证据，不制造新的关机验收。 |

Base64 只是编码。Secret 的保护依赖已有的 etcd 加密、最小 RBAC、受控挂载和私有材料目录。公开 manifests、快照和日志不会保存 Secret 数据、JWT 或 Registry 密钥；Secret/TokenReview 的处理任务单独使用 no_log。

## 创建了什么，最后清理什么

测试空间为 `lab-p10`。Registry 测试项目以 `cnpl-p10-<run>-<attempt>` 命名，64MiB 配额；只生成两个一天有效、仅本项目 pull 权限的机器人。使用现有管理员凭据文件进行管理请求，凭据经受保护变量/标准输入传递，不改写用户原 Docker 配置。

成功后回收整个本批 Namespace、临时集群只读授权、机器人、两个测试仓库和私有项目；只按完整引用移除 worker 上的私有镜像别名，保留 bootstrap 共享镜像及内容。随机应用凭据、测试 TLS 私钥和临时认证输入在本批私有目录内清理。现有 Mac 管理身份、恢复管理员、系统 PKI、Metrics Server 不属于撤销范围。

项目/账户/镜像创建前均记录恢复意图；清理核对 run、项目 ID、精确仓库/账号范围和对象 UID。发现其他人添加的数据时保留，不把本批清理扩展成全局清理。

## 失败处理命令

```bash
# 保留旧 attempt，撤销自己的遗留 Registry 凭据后，在同源码下重做本阶段。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-10.sh resume "$CNPL10"
# 放弃本批时精确清理；其他专题及系统组件保留。
bash /Users/mario/SelfProject/cloud-native-platform-lab/ops/01-kubernetes/scripts/stage-10.sh cleanup "$CNPL10"
```

若源码已修改，先 cleanup 原目录，再建立新目录。07–09 已通过的专题不因此重跑。只有 10 的两个总 PASS 和交接文件齐全后，才进入 Phase 02。

参考：[ConfigMap](https://kubernetes.io/docs/concepts/configuration/configmap/)、[Secret](https://kubernetes.io/docs/concepts/configuration/secret/)、[Harbor 项目机器人](https://goharbor.io/docs/2.15.0/working-with-projects/project-configuration/create-robot-accounts/)。
