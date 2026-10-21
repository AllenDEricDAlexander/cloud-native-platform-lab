# 04.06 双 IaC、远端状态与恢复执行器

覆盖 04.06.01–07。没有现成00 OpenTofu模块，因此 module.rb 为一个全新、受保护、无业务数据的测试 VM 生成 .tf.json 模块；不改现有VM/盘。OpenTofu管虚拟硬件，00 Ansible管Linux/CRI，kubeadm/cephadm保留原入口，GitOps管集群对象。数据VM不进入本模块。

离线：validate；render-module <仓库外新目录> 仅生成配置。现场填写 iac.provider_source（完整registry/namespace/provider）、provider_version、directory、plugin_directory、backend_config、variables_file、plan_directory；两个私有目录0700，文件0600。复制经主锁验证的Provider lock到模块，不自动生成/下载锁；init使用只读锁与本地插件目录。variables_file为JSON，包含模块列出的vSphere身份/放置/模板/VM参数；vm_name只能cnpl04-<run_id>，test_ip不得占用任何登记节点/服务地址。

backend_config必须是集群外GitLab HTTP State地址，lock_address/unlock_address、POST/DELETE锁方法、CA/TLS及身份按锁定OpenTofu/GitLab版本核对。State和Plan包含秘密，仅留私有目录；CI artifacts只允许context/result/SHA引用。两CI使用同一backend地址、状态名和持久的私有Plan目录，GitLab resource_group只负责自身排队，跨CI以HTTP锁为准。不要为每个CI新建独立State管理同一VM。

```bash
bash ops/04/06/run.sh init
bash ops/04/06/run.sh plan
# 在私有目录审查保存的Plan、Provider/变量与允许地址，再填写批准SHA：
CNPL04_APPROVED_PLAN_SHA256=<保存Plan的SHA256> bash ops/04/06/run.sh apply
bash ops/04/06/run.sh ansible-check
bash ops/04/06/run.sh ansible-apply
bash ops/04/06/run.sh no-op
```

主线plan-check拒绝所有删除/替换和越界地址，apply核对同一二进制Plan与模块/变量/后端/锁指纹。保护prevent_destroy默认开启。销毁实验需另行审查将该临时测试资源保护调整、生成专用销毁Plan和明确批准；本入口拒绝普通Apply夹带销毁，不把Destroy当失败补偿。现有State迁移需先备份、核对资源映射，再在独占维护窗口人工tofu init -migrate-state；默认init不迁移。

Ansible复用00 bootstrap-nodes.yml与node_base/container_runtime，但使用仅包含新测试VM的受控inventory，--limit固定批次主机、serial=1。先核对VM UUID、唯一machine-id、SSH host key、IP、网卡、运行时独立盘UUID；按00模板补齐inventory vars/内部CA/DNS/资源预留，不能直接以十节点inventory替代。只在空新盘按既有角色初始化；不在本入口维护现有Ceph/控制平面。

故障验收依次做：两CI交替Plan/Apply/no-op；并发申请锁；初始化失败后inspect-failure；后端断连时拒绝Apply；部分创建成功时比对vCenter实际ID与State，必要Import/补偿须独立审查，保留原失败计划。禁止force-unlock、复制新State、自动destroy或覆盖正式盘。

recovery.sh在登记集群外、不依赖主Ceph的管理VM运行，仅受保护任务/人工审批；仓库、内网制品、CA、Provider镜像和State备份必须在那里可读取。实测关闭集群内Runner/Jenkins后能完成Plan与批准Apply，Jenkins故障不能阻塞人工恢复通道。vSphere许可证/API写权限、克隆/回收权限、独立备份和真实锁行为仍待现场验证。
