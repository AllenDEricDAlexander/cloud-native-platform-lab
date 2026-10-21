# 06.04 Falco/Tetragon 与事件调查

覆盖 06.04.01–03。入口 `run.sh validate|render|rules <falco|tetragon>|install <falco|tetragon>|apply|trigger|check|cleanup-plan`。默认只离线校验；render 不安装探针。先选登记的普通 Worker，核实 Rocky 内核、BTF/eBPF、CRI、驱动、架构、权限与资源预算，再在两个独立窗口分别安装/启用 Falco、Tetragon。

`rules falco` 输出精确匹配本批空间、只记录进程名和容器身份的规则。将它合入已审核 Falco 安装包的自定义规则挂载，复核 spawned_process/container 宏存在。`rules tetragon` 输出 Namespaced 只观测 exec 的 TracingPolicy；其 syscall 参数须按锁定内核/版本对照，只在对应 Namespace 应用，不启用 kill/override 等阻断动作。两套规则均需正反例验证，不默认作为可长期并行的组合。

连接内网后先 apply/check 样例，再保存无注入的基线，执行 trigger。样例镜像须含 sh/id/cat；授权动作只读取容器自身的 os-release，不读宿主敏感文件。按事件实际发生时间、namespace、Pod UID、节点、镜像 Digest、ServiceAccount、发布版本关联到 05 日志/Trace。不要把全部原始命令参数/环境变量作为普通证据，以免记录秘密。

比较同样动作的检测字段、漏报/误报和 CPU/内存；告警不存在即失败或前置阻塞，不能从 exec 成功推断检测成功。先人工调查，再对专用应用设计有时限的网络隔离；DNS、CSI 和系统空间不作为自动隔离目标。误报时撤销本批规则并恢复精确网络策略。

退出顺序是停止测试、撤销本批 TracingPolicy/规则、确认无阻断动作、再按组件归属退出探针；共享安全控制器不随本批卸载。内核不支持时保留明确阻塞记录。本轮探针、事件和开销均未运行验证。
