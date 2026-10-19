# 02.10 与 02.06–10 整组交付核验

正式实验未执行，没有启动Docker/kind、安装Istio/SPIRE或对主VM制造压力。原主线保持，实际all由操作者启动。

检查包括：Istio1.31.2完整ambient安装清单生成、全部镜像引用与离线归档hash、Sidecar非部署注入预演（只读取原API的命名空间/版本信息）、无NET_ADMIN init；48份业务/身份内置对象服务端预览、15个Istio CRD自身服务端预览、8份自定义对象按锁定schema校验。未落地的SA引用在初始预览用default替代，原引用保留，实际kind内先创建Namespace/SA/CRD再逐对象严格预览与应用。

SPIRE HCL使用独立原文件，YAML嵌入逐字比对。Go单元测试使用SPIRE同族HCL解析器核对语法，并真实建立双向SPIFFE TLS，验证正确身份成功、错误客户端/服务端URI拒绝；只输出公开证书元数据。Go race/vet通过，日志见go-identity-tests.txt。

Python回归覆盖五个专题、共享批次/UID和顺序入口；实际Ansible模型覆盖正常、观察失败、命令失败停止后续命令、显式恢复四条分支。模型不证明Docker数据面。全部最终结果见delivery-review.json、各regression日志与offline-results.json。

当前Docker Desktop未运行，kind/BPF/FRR/Istio/SPIRE的真实运行和互通留给all验收，未把准备校验记成运行通过。完整Trace/SLO和发布联动回访Phase04/05；公网/Ceph/主出口/整VM压力缺口保持单列。

原始准备失败日志保留，包括镜像variant、未创建的SA引用、CRD隐式根字段及注入器读取命名空间前提的修正。最终以整组validate回执和delivery-review.json为准。

[五条独立命令和顺序入口](../../examples/06-10/README.md)、[02.10全部实现和作用](../../examples/mesh/README.md)。
