# 04.02 构建器、代理、BuildKit 与四类缓存

覆盖 04.02.01–05。七份 Containerfile 基于已经预热工具链的 Rocky 基础镜像构建，只加入公开 CA 和无密码客户端配置，不在每次 Job 下载编译器。base_<language>、builder_<language>、runtime_<language> 的准确版本/Digest/ABI/链接与内部 CA 核对记录在物料登记。Java 主线 21，25 对比需另一个受审 Builder；C++ 主线选择 Conan，Python 选择 pip 锁文件，不要求同时配置所有替代工具。

```bash
bash ops/04/02/run.sh validate
# 连内网后：锁定 BuildKit 物料，填写 build 节点/PVC/TLS Secret
bash ops/04/02/run.sh deploy
bash ops/04/02/run.sh check
# 在可访问受控远端 BuildKit 的管理执行器内逐语言构建：
bash ops/04/02/build.sh java
```

BuildKit 为 trusted/untrusted 两套独立状态/PVC，使用 mTLS、非 root、无宿主 Socket、限定 worker，不默认加入 no-process-sandbox/privileged/Unconfined 例外。TLS 服务端证书必须覆盖两服务 DNS；客户端秘密分级管理，MR 只可取得 untrusted 身份及无写入正式仓库的权限。Rocky user namespace、seccomp/挂载、rootless snapshotter 与 StorageClass 的兼容性必须现场核对；若所选版本确实需例外，应先更新独立受限节点方案及报告，当前默认不会自动放宽 PSA。

配置沿用 00 的 Nexus 入口；maven-public 是否已建立需要现场确认，不能以同名配置证明可用。Gradle 插件仓库、Java cacerts、Node/Python CA 和带原生扩展的 OS 库要在 Builder 中核实。NuGet/Cargo/Conan 私有凭据运行时注入；仓库无上游回退配置，网络策略仅允许三台内部仓库，Nexus 的上游出口还需独立断开才能证明完整离线。

冷/暖/断外网组合使用 05 的相同固定提交和两 CI：每格单独生成缓存键（client.sh），冷缓存使用新 Job 空目录/空缓存仓库，不清理共享状态。记录构建耗时、请求流量、缓存命中、依赖缺口和 Digest；缓存热启动不等于离线冷构建。正式制品与缓存分仓库，保留策略见 cache-policy.json。失败保留构建日志，不自动 prune 节点或共享 BuildKit。
