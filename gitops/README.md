# GitOps 期望状态

当前为目录骨架，尚未实现或部署。按 [七阶段计划](../docs/plans/README.md) 在对应阶段补充真实文件。

| 目录 | 阶段 | 负责内容 |
| --- | --- | --- |
| `bootstrap/` | 04 | 主 Argo CD 的受控引导；引导后明确资源所有权移交 |
| `platform/` | 04 | 引用 kubernetes 与平台工程配置的 Application/ApplicationSet |
| `environments/dev/` | 04 | 开发实验的 Namespace、参数和固定制品版本 |
| `environments/staging/` | 04 | 预发布验证和晋级配置 |
| `environments/prod-like/` | 04 | 拟生产配置与受控晋级，不代表真实生产环境 |

每个实现或实验说明须包含输入、版本、操作、检查、失败恢复和清理；测试结果归根目录 `reports/`。秘密和二进制备份放受控外部位置，只保留安全引用。
