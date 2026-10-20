# 02.09 原 Mac/kind 失败批次：已清理、停用

批次02.09-20261020T140750Z，run20261020T140800Z-81c2e69e。gateway-install 对1.4MB EnvoyProxy CRD使用客户端apply，触发last-applied注解256KiB上限；failed=1，未通过验收。

原always清理回收了本批三个kind节点和专属Docker网络，原主集群保护基线一致；额外核对后停止Docker，原有停止状态sandbox容器和镜像数据保留。见[原日志](ansible-all-20261020T140757Z-scItTw)、[原清理回执](state/closed.json)、[Mac清理复核](mac-cleanup-review.json)、[失败复核](failure-review.json)。

32份原执行输入按SHA从原提交恢复到execution-source/；原attempts和失败日志不改写、不删除，不把清理通过当作实验通过。此目录只能归档，不能继续all。

用户已明确：Mac只做管理端，02.09改为现有.101–.110 VM主集群。新VM版及修复核验见[交付记录](../02.09-20261020T143044Z-vm-repair-review/README.md)。所有旧Docker/kind启动命令作废。
