# 02.09 跨 VM BGP 回程问题：真实报文诊断

用户明确授权 Agent 在现有 .101–.110 VM 主集群执行02.09、采集现场、修复到可运行用例通过并自动回退。Mac仅作管理端，未运行Docker/kind；未修改VM的rp_filter或关闭SELinux/firewalld。

## 证据与根因

原基线模式下，同一现有CoreDNS Pod允许worker02分别用管理IP和Cilium内部IP连接。切到授权实验的eBPF模式后，相同Pod UID和地址：

- 使用192.168.9.110：TCP超时，IPReversePathFilter计数从898增至902。
- 使用10.244.9.1：HTTP返回200，计数保持902。

详见 [tcp-source-probes.json](tcp-source-probes.json) 和 [ebpf-tcp-source-probes.json](ebpf-tcp-source-probes.json)。

随后在真实FRR的179端口同时抓取FRR Pod网络空间和worker02的报文头：管理IP发出的SYN从cilium_vxlan离开，FRR的SYN-ACK却从worker02 ens33返回，重传后仍无ACK；对应探测窗口RPF计数增加。内部IP发出的SYN和返回SYN-ACK都经过隧道，完成三次握手，RPF计数不增加。[bgp-live-transport.json](bgp-live-transport.json) 保留完整报文头及源端口对应关系。

这是当前BPF路径、Pod内软件邻居与ens33严格反向路径检查组合下的回程不对称；不能仅靠把BGP源地址固定成管理IP解决。[Linux内核rp_filter说明](https://docs.kernel.org/networking/ip-sysctl.html)解释了严格模式按返回路径校验源地址的语义。

## 受控诊断试验

在本批拥有的FRR和两份NodeConfigOverride内，通过Ansible及UID/spec/run测试，临时添加并使用两个真实CiliumInternalIP。两个邻居均Established，RIB恰好包含两个Worker PodCIDR及本批VIP /32，路径有效；见 [internal-address-trial.json](internal-address-trial.json)。

这只是诊断试验。原整组断言仍要求管理IP，所以该诊断批次预期未通过；没有把试验结果当作正式验收。该批次已完成原状态恢复与清理，见 [diagnostic-closed.json](diagnostic-closed.json)。临时执行清单和原始输出仍保留在诊断批次的本地attempt内。

## 正式修复与后续验收

正式模板与验收器统一从CiliumNode读取Worker的CiliumInternalIP，校验地址唯一且属于各自PodCIDR，模式切换时再次核验没有漂移。FRR和实际生成NodeConfig均使用同一映射，使软件邻居的双向传输保持在隧道内。原管理地址、严格RPF、防火墙规则与SELinux配置保持。

全新正式批次为 `../02.09-20261021T122923Z-agent-final/`，其passed.json与state/closed.json才是整组验收和清理结论。没有在该正式批次运行临时配置试验或更改源码。外部真实上游BGP转发仍单列BLOCKED。
