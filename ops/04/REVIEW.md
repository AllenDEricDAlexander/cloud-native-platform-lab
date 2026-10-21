# Phase 04 离线交付走查（2026-10-21）

范围：10个子阶段、55个计划步骤的脚本/配置/样例/人工操作规程。目录为01–10，默认入口validate；coverage.json仅索引交付文件和完成判定，所有runtime_accepted=false。本轮没有连接内网、触发CI、创建VM、访问集群、构建/启动容器或启动服务。为确认Cosign的stdin密码接口，只查阅了Sigstore官方源码；这不属于现场版本/运行验证。

## 已执行检查及边界

| 检查 | 结果 | 证明边界 |
| --- | --- | --- |
| bash ops/04/validate.sh | 通过 | Bash/Ruby语法，含隐藏CI文件的JSON/YAML解析/重复键，Python AST、TOML/XML解析 |
| tests/offline.sh | 通过 | 拒绝非法动作/未知物料/目标/秘密权限；失败码和恢复失败保留；缓存内容指纹；外部客户端替身调用0次 |
| tests/native.sh | 通过 | 同SHA复用、404上传并取回、同身份内容冲突拒绝、认证错误拒绝；真实Nexus调用0次 |
| 生成清单检查 | 通过 | 环境/网络/BuildKit、14个Jenkins Agent、Argo Project/ApplicationSet、Canary/BlueGreen/真实采样、准入、XRD/Composition、Flux/Tekton/Run的本地构造；不证明API schema/调谐正确 |
| 三环境kubectl kustomize | 通过 | dev/staging/prod-like渲染，Namespace、固定Digest、HPA副本字段；未运行server dry-run/diff/apply |
| 导出/Plan构造 | 通过 | 新目录源码导出、固定模板SHA、OpenTofu JSON模块、prevent_destroy/TLS和删除Plan拒绝；未运行tofu init/validate/plan/apply |
| 55步索引 | 通过 | 与计划ID完全对应，文件存在，人工完成判定保留；不等于55步实现效果已验收 |
| C/C++ clang/clang++ -fsyntax-only | 通过 | C11/C++20、Wall/Wextra/Werror的Mac宿主静态编译；不证明目标Linux ABI/链接/运行 |
| Node --check | 通过 | server.mjs/test.mjs语法；未启动HTTP服务，未运行npm依赖恢复或TS编译 |
| Rust cargo test --offline | 通过，1个测试 | 无第三方依赖，Mac宿主内存计算测试，无监听/请求；不证明Linux制品 |
| Rust Clippy/rustfmt --check | 通过 | --offline、all-targets、warnings视为错误及格式检查 |
| Python unittest | 通过，1个测试 | 标准库计算内核；另有真实采样计数/直方图内存检查，无监听/请求 |
| git diff --check | 通过 | 本任务路径无空白错误 |

已有管理端Python3.9缺少tomllib，验证入口改为优先显式CNPL04_PYTHON，必要时使用已有Homebrew Python3.14；没有安装新依赖。Python unittest按样例目录运行，避免错误的导入路径。Rust构建缓存留在独立临时目录，未入Git。未使用Docker、kind、k3d、Podman、浏览器或GUI。

## 走查修正

- 构建与发布分身份、节点与命名空间；默认拒绝网络后，仅通过显式selector开放Controller API、分级BuildKit、Gateway和Jenkins WebSocket。Job SA不能因此获得平台权限。
- 缓存键包含实际依赖文件内容和Builder Digest；镜像不包含native.tar/测试回执。两CI各自测试/构建，按语言配对比较源码SHA/Builder，不要求不同应用仓库出现同一提交。
- GitOps只提交审核分支/MR，不强推或直接写业务对象；观察同时核对Argo健康/同步、实际Digest和HTTP源码版本。Git认证使用受控askpass及Token文件，不能依赖CI秘密文件本身可执行。
- 原生包另行发布到Nexus禁止redeploy的raw hosted仓库，已有同身份包核对SHA，只有404才上传，上传后取回验证，不将CI artifacts保留期当作正式制品管理。
- Helm先建立并等待CRD，再检查CR；旧CRD spec变化停止。后置渲染给Pod模板加批次标签，Namespace复用只核验归属，不移除既有PSA标签。Secret不从普通Chart渲染创建；原始Helm诊断留仓库外0700目录。
- 私有文件/导出目录检查覆盖所有活动worktree及物理路径，不能通过原checkout或目录软链绕过。入口信号退出执行清理/恢复，恢复失败保留原失败码。
- IaC只覆盖一个新测试VM，限制登记vCenter、未占用客户端IP和硬件预算；保存Plan按SHA/输入指纹审批，拒绝所有删除/替换；首次无State需单独空状态证据。后续不自动destroy/force-unlock或另建状态。
- BlueGreen必须配置独立预览采样job；零请求/NaN/查询失败不满足放行。准入增加仓库/Digest/资源要求，避免非Harbor镜像因未匹配签名规则而绕过。
- Backstage默认仅平台组可使用受控策略；源码、GitOps MR和目录分步生成；Crossplane采用明确的2.x Namespaced API和本namespace子资源权限，数据回收不随门户自动删除。
- Tekton签名卷只挂package步骤、源码只读Token单独挂fetch；部署仅对照Namespace。Flux不管理主Argo对象；Dragonfly冷拉取拒绝已有节点缓存。清理显式对象时使用UID前置条件，PVC/CRD/数据不自动删除。

## 仍需连接内网后核对

00–03主线实际交接、现场容量/故障域、独立备份和主集群身份仍是运行前置；03源码交付不能代替Ceph/CNPG运行验收。主版本锁中04物料继续pending，未猜测并填入“已验证版本”。所有Chart/CRD/CLI选项、插件/API组合、镜像架构、Nexus依赖闭包、rootless BuildKit与Rocky安全策略需先核对。

本机没有使用可验证的Helm/OpenTofu/Groovy/.NET/TypeScript及Backstage依赖环境，因此没有声称完成Helm template/lint、tofu validate、GitLab CI Lint、JCasC加载、Jenkins/Groovy或Backstage policy类型编译、Java/.NET/TS完整构建。七语言源码有主线与明确的人工对比项（Java25/Gradle、musl、.NET自包含/Windows、扩展依赖），不能把静态源码或一种语言代表全部14格。

仍需逐格构建/制品发布/签名/MR/同步/smoke，以及冷暖/断外网、Runner/Agent/Controller故障恢复、State锁/幂等/补偿/外部恢复、真实权重/指标异常/自动中止与GitOps回退、可信/无签名/错误签名/仓库失联准入、自助数据库/目录/TechDocs及全部对照与清理证据。Trace仅定义W3C头/日志字段契约，逐语言OTel exporter/端到端传播交由05落地，未伪装已接通。

共享checkout在执行期间被另一任务切换到05分支，因此后半程隔离到附属worktree，04分支保留全部10个分步提交；没有回切/覆盖正在使用的checkout或纳入原有00–02改动。未自动推送、合并、部署或启动正式实验。
