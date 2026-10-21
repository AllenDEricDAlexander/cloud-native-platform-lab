# 输入、物料与运行边界

复制 inputs.json、materials.json 到仓库外，通过 CNPL04_INPUTS、CNPL04_MATERIALS 指向它们；不要 source 任意配置脚本。导出变量后逐阶段执行。run_id 沿用同一批次，不以换 run_id 接管旧资源。

prerequisites.file/sha256 指向已确认 00–03 主线交接的记录，当前 03 只有离线源码交付，不能作为运行前置通过证据。kubernetes 填仓库外 0600/0400 kubeconfig、准确 context 与 kube-system UID；入口核对台账的十节点 FQDN/IP/Ready。build.node 只能选择主台账 worker FQDN，不能占用控制平面或存储节点。

物料 components.<key> 每项含 version、compatibility_file、compatibility_sha256；镜像另有 image（Harbor @sha256），Chart/完整安装清单有 file、sha256。Chart 再有 values_file、values_sha256。version/image/sha256 必须与 ops/versions.lock.yaml 对应项相符。兼容报告需现场核对 CLI/CRD/Chart/API、linux/amd64、实际镜像与依赖，不得用本轮离线走查报告替代。所有物料使用已有本地文件，脚本不下载或选最新版。

Chart values 仅引用预先建立的 Secret，显式关闭动态生成密码，固定所有镜像 Digest 与依赖，设置资源/节点/安全上下文、内部 CA、TLS 入口和网络策略。后置渲染拒绝 Secret 与浮动镜像；安装前核对资源归属，CRD spec 变化停止，升级另审。Chart 参数与所选版本的兼容性留待联网后核实。

所有口令、私钥、curl config、Docker auth、kubeconfig 和 State/Plan 放仓库外受控位置。私有文件必须当前用户所有、0600/0400，不能通过目录软链落回仓库。curl config 应含 CA 与认证，不能含 insecure、verbose、trace 或输出秘密的选项。身份与签名材料按 CI 文件凭据挂载，禁止普通 MR 取得。外部认证 API 不重定向到任意主机，不在 argv 中放令牌。

resources、repos、Gateway、Ceph StorageClass、内部 Secret/ConfigMap 均使用显式输入。部署脚本只引导平台对象；业务部署由 Argo CD、平台子资源由 Crossplane/Operator 管理，比较控制器使用独立 Namespace/路径。同 ESXi 的备份 VM 不自动算独立恢复能力。
