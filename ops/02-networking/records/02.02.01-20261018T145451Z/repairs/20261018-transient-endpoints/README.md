# 02.02.01 启动过渡状态与客户端镜像策略修复

用户批次 `02.02.01-20261018T145451Z` 在 initial 等待阶段遇到 `ports=null` 遍历异常。本次只修复脚本并做只读核验；没有清理、重建 Pod、扩缩容或修改 Readiness，也没有执行全量实验。

## 根因与相关问题

1. 原检查器用 `slice.get("ports", [])` 处理缺失字段，无法处理显式 JSON null；同时 endpoints 空数组/空 Slice 和 Pod 尚未调度状态缺少启动期覆盖。现在这些状态记录为未收敛，有界等待；空占位 Slice 与其他有效 Slice 合并时仍按 UID/IP 正确聚合。
2. 原检查发生异常时，轮询快照尚未写入。现在先保存原始 API 对象，再检查并保存结果；超时包含具体 Pod 等待原因和快照路径。
3. 实际 worker01 客户端处于 ErrImageNeverPull，尽管 CRI inspecti 能查到同一摘要。其可见性原因尚未进一步归因，不能声称镜像内容本身缺失。客户端改为固定摘要 + IfNotPresent，允许 kubelet 从已验证的内网 Harbor 按需获取；后端 OCI 仍使用 Never，前检检查非空 ID 和完整 RepoDigest。
4. HTTP 200 的非对象 JSON、空身份及无效身份类型现在记为失败样本，保留原始正文，避免解析异常掩盖原始响应。

## 验证范围

- 15 项 unittest 全部通过，覆盖冷 Slice 到正常 Slice 收敛、null/空字段、未调度 Pod、空占位 Slice、超时快照、缓存元数据及响应身份等；原有 UID/owner/端口和未就绪端点断言继续有效。
- [最终 Ansible 校验日志](../../ansible-validate-20261018T151801Z-XGa1vn)包含 SOURCE VALIDATION PASS，Mac 与两台 worker 全部 failed/unreachable/rescued/ignored=0；两台 worker changed=0。五个新 YAML 严格服务端 dry-run 通过。
- [机器可读结果](verification.json)及最终 attempt 的 `source.json` 记录当前代码摘要；与工作区逐文件匹配。
- [实际 API 输入](live-inputs-after-fix.json)、[检查结果](live-state-after-fix.json)明确显示当前完整 initial 阶段仍未通过，因为 worker01 客户端未 Ready；没有伪造两台客户端已成功。
- [worker02 只读请求](live-worker02-requests.jsonl)覆盖 ClusterIP、FQDN、短名各五次，共 15 次 HTTP 200 和正确后端 UID；这不代替两客户端、五阶段共 150 次正式验收。
- [原件 SHA-256](original-evidence-sha256.json)登记的 17 个文件原字节保持不变，原 `state/source.json` 未覆盖。

## 重新执行

修复后源码指纹已变化，客户端 Pod 的 imagePullPolicy 也不可原地修改。先清理原失败批次，再新建批次执行，避免覆盖旧证据或放松源码校验。以下命令由用户在管理 Mac 执行，`&&` 保证出错即停止后续步骤：

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
bash ops/02-networking/scripts/clusterip.sh cleanup "$PWD/ops/02-networking/records/02.02.01-20261018T145451Z" &&
export LAB_SERVICE_RECORDS="$PWD/ops/02-networking/records/02.02.01-fixed-$(date -u +%Y%m%dT%H%M%SZ)" &&
bash ops/02-networking/scripts/clusterip.sh validate "$LAB_SERVICE_RECORDS" &&
bash ops/02-networking/scripts/clusterip.sh run "$LAB_SERVICE_RECORDS" &&
bash ops/02-networking/scripts/clusterip.sh cleanup "$LAB_SERVICE_RECORDS"
```

第一条 cleanup 只清理原运行拥有的隔离空间，保留日志和旧回执；validate 包含前置复验和新 YAML 准入；run 执行完整五阶段；最后 cleanup 只在验收成功后执行。完整说明见 [02.02.01 手册](../../../../examples/service-clusterip/README.md)。
