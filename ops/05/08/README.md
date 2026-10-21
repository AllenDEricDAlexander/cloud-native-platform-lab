# 05.08 压测、容量和成本

覆盖 05.08.01–06。选择 k6 主线，不要求再装 Locust。负载只在既有 build01 上由用户显式 load 启动，Mac 负责 Ansible 管理；不创建/启动本地容器或服务。固定合成 dataset/SHA、同一业务、依赖、节点资源、运行时版本、预热和缓存条件。

```bash
bash ops/05/08/run.sh validate
# 内网：先最低并发一轮，结束核对，再逐轮只改变一个因素
bash ops/05/08/run.sh load
bash ops/05/08/run.sh languages-report
bash ops/05/08/run.sh ci-report
bash ops/05/08/run.sh install-opencost
bash ops/05/08/run.sh cost-check
```

performance 输入：target_url 只允许授权内部实验服务的 HTTPS 原点；dataset_file/sha256（合成业务数据，单 `/` 相对路径 GET/POST）、ca_file/sha256、vus 1–20、duration 10–600 秒、明确 p95_ms/error_rate。需要认证时 token_file 为仓库外 0600 纯 Token，复制远端仅本轮目录，always 清理。工具键 k6_or_locust 是预先锁定的 Linux amd64 k6 文件，脚本不联网下载。k6 先 10 秒预热，再 steady，记录 P95/P99/吞吐/错误，阈值失败保留非零码与 summary。

`safety_queries` 每项 name/expr/min 或 max，至少 load_client_cpu、load_client_memory、ceph_capacity、datastore_free 四项。`safety_private_file` 是仓库外 0600 JSON（prometheus_url、ca_file、可选 bearer_token）；其中 ca_file 必须是 **build01 可读的受信任 CA 路径**。监督进程每轮取真实 Prometheus 信号，缺失/NaN/Inf/超阈值即停止仅本次 k6 进程组，有限时间后强制结束，失败不继续下一轮。查询的 URI 和阈值需现场核对，不能为了运行把水位信号置零。所有连接都有超时，不保证在网络隔离时仍能取得新水位；无数据会停止。

七语言 matrix_file/sha256 是 7 条实测记录 case=java/csharp/jsts/python/rust/c/cpp；CI 矩阵为 gitlab-cold/gitlab-warm/jenkins-cold/jenkins-warm，使用相同 source_revision/dataset_sha256/node_resources/dependency_versions/duration_seconds/load_profile/warmup_seconds。每条包含 measured=true、tool_versions、metrics、evidence_file/sha256；语言 metrics 记录启动/吞吐/P95/P99/CPU/内存/JIT/GC，CI 记录排队/拉取/依赖/编译/测试/推送和并发。冷缓存使用隔离缓存引用，禁止 prune 共享 BuildKit、Harbor、Nexus 缓存。

Ceph/应用共享瓶颈逐轮从数据库/消息/ELK/构建中只增加一项，使用相同安全监督并归档配置，达到阈值停止后续负载。RAID VMDK 功能实验不能外推独立磁盘性能；同时观测实际 Datastore，不对裸设备运行 fio。不得清理 OSD/卷来制造容量。

OpenCost 输入三个正数单价 cpu_hourly_cost/ram_gib_hourly_cost/storage_gib_hourly_cost、currency、assumptions_file/sha256，明确每小时 CPU/每 GiB RAM/每 GiB 存储与电力/折旧/共享分摊假设。Chart 键 opencost、镜像 opencost_image；复用已有 Prometheus HTTPS/认证/CA（按所选 Chart 的 Secret 引用配置）。cost-check 要求非空非零成本并记录 requests/实际用量，不以缺失解释成免费。优化只输出建议，手动调整后在同条件复测，不自动缩数据库/控制平面。

本轮未执行 k6、真实资源监督、双 CI、OpenCost 原生 Chart/API 或成本核算。脚本/矩阵校验不会生成虚构的性能报告或账单。
