# 06.13 CPU 模型、vLLM、训练、llm-d 与成本

覆盖 06.13.01–06。`run.sh validate|render <cpu|vllm|training>|install <kserve|kubeflow|llm_d>|apply|vllm|training|check|predict|cost <实测JSON>|cleanup-plan`。先做 CPU 分支，不因无 GPU 阻塞 CPU 模型验证；GPU/vLLM/llm-d 只有 12 真实矩阵通过后启用。

CPU 模式声明命名空间 ServingRuntime 与 InferenceService，runtime 镜像需实现所选 sklearn v1 协议/启动参数，并能以非 root 工作。根据锁定 KServe 版本选择 RawDeployment 或 Standard；此首例不自动引入 Knative。模型 URI、S3 私密 Secret/CA、存储初始化镜像、版本/hash 和网络出口必须先准备。check 等待 Ready；predict 发送受控输入并将解析后 JSON 与已知预期完整比较，只保存响应 SHA。Ready/下载成功不能代替预测正确。

vLLM 使用只读已预热模型 PVC、离线加载、显存预算不超过 0.8、长度不超过本样例 4096，禁止日志记录请求正文；GPU/模型架构/精度和显存实际验证后才能增大。记录同模型/版本/硬件下并发、首 token、吞吐、峰值显存、OOM/错误率，不能仅按参数量推断容量。GPU 1 卡样例不等于分布式能力。

training 提供可重复的 CPU 线性拟合 Job，输出权重/偏置到独立 PVC，经 Kueue 受限 LocalQueue 准入；08 ClusterQueue 必须允许本阶段的明确 Namespace 标签。先排队/准入/完成读取模型 JSON 与 SHA，再测试取消/失败/释放。Kubeflow 只安装受控选择的 Pipeline/训练模块，另用该版本官方兼容的任务入口编排同一输入→训练→归档任务，保留 Pipeline/训练任务与制品运行 ID；普通 Job 不冒充已验收 Kubeflow。

llm_d 安装要求 GPU 矩阵和 distributed_evidence_file/SHA，后者核对 vLLM 单节点成功、模型/网关、GPU 数/高速网络、内存/缓存、调度和恢复。完整受审本地配方记录在物料包中，不用空 CRD 声称部署。用同一请求集比较单实例与分离/分布式推理，测故障与恢复；硬件不足就保留明确阻塞。

cost.rb 使用实测 gpu_hours/idle_gpu_hours/power_kwh/successful_requests/output_tokens 和显式 gpu_hour_rate/electricity_rate/currency/assumptions 计算估算。GPU 费率是否含电力在 assumptions 中说明，避免双计；OpenCost 自定义设备成本与 DCGM 请求/Token 指标分开登记。没有数据不输出精确账单，零请求/Token 的单位成本返回 null。

退出先停入口和训练，保存模型/制品/回执，确认队列和 GPU 释放，再撤本批服务/Claim/任务；模型 PVC、训练产物和共享控制器另审保留。当前 CPU/GPU/训练/成本数据均未运行验证。
