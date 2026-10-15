# Cloud Native Platform Lab

在三台 ESXi 上建设可重复部署、可独立恢复、支持指定物料离线安装与构建的云原生实验平台。建设分为 00–06 七个阶段，06A–06E 是第 06 阶段内部专题。

## 仓库入口

| 位置 | 内容 |
| --- | --- |
| [arch/](arch/README.md) | 总体架构、拓扑、组件职责和技术约束 |
| [plan/](plan/README.md) | 七阶段任务、实施顺序、交付物和验收标准 |
| [ops/](ops/README.md) | 操作手册、台账、版本、配置、脚本和执行记录 |

按“架构 → 阶段计划 → 操作手册 → 执行记录”阅读；具体任务可查 [步骤索引](plan/step-index.md) 和 [技术覆盖索引](plan/coverage.md)。根目录只保留本入口和这三个业务目录，实际文件产生时再建子目录。

## 当前进度

截至 2026-10-14 的[执行记录](ops/00-preparation/records/2026-10-14/README.md)，Phase 00 进行中：母机已安装并运行 containerd，尚未封装为最终模板；正式十节点克隆和交付验收均为 0/10，整体阶段尚未验收。客体结果来自用户回传。

下一步：按 [Phase 00 计划](plan/00-preparation.md) 和[节点操作手册](ops/00-preparation/README.md)，继续 CRI 自测、入群工具与物料锁定、母机复验和身份封装，再克隆及验收十节点。DNS/CA、仓库、网络、离线供应和独立备份等剩余任务见阶段计划。

配置与脚本路径表示对应阶段的交付位置，未产生的文件不预建占位；[版本锁](ops/versions.lock.yaml) 和[台账](ops/inventory/README.md) 仍含待核实项，不能据此直接部署。每阶段通过验收后再交接，操作时按[模板](ops/templates/execution-record.md)留存实际证据。
