# 开发者平台工程

当前为目录骨架，尚未实现或部署。按 [七阶段计划](../docs/plans/README.md) 在对应阶段补充真实文件。

| 目录 | 阶段 | 负责内容 |
| --- | --- | --- |
| `backstage/` | 04 | 门户配置、目录集成、Software Templates 与任务动作 |
| `crossplane/` | 04 | 平台 API、Composition、Provider 引用和资源权限 |
| `service-templates/` | 04 | 七类语言应用、CI、部署和文档的可复用模板 |

每个实现或实验说明须包含输入、版本、操作、检查、失败恢复和清理；测试结果归根目录 `reports/`。秘密和二进制备份放受控外部位置，只保留安全引用。
