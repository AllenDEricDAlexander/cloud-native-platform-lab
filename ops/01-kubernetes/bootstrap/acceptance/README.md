# 十节点集群基础验收

范围：01.02 入群后的健康、实际资源配置，以及 01.03.01 的普通 Pod 网络/Service/DNS。控制平面停机切换在备份验证后执行；本轮基础通过不能代替 HA、备份恢复或 Phase 01 全阶段验收。

## 1. 管理 Mac 准备

以下命令均在同一个 Mac 终端按顺序执行，每一步成功再继续。

```bash
cd /Users/mario/SelfProject/cloud-native-platform-lab
set -o pipefail
CNPL_ACCEPT_DIR="$PWD/ops/01-kubernetes/records/2026-10-17-restart/evidence/01.02-acceptance-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$CNPL_ACCEPT_DIR"
k() { "$HOME/.cnpl/bin/kubectl" --kubeconfig "$HOME/.cnpl-secrets/kubeconfig-lab-primary" "$@"; }
```

`cd` 固定仓库路径；`pipefail` 防止 tee 掩盖失败；变量和 mkdir 创建独立证据目录。`k` 是仅当前终端的函数，每次使用锁定 kubectl 和实验集群 kubeconfig，不依赖默认 Context。

## 2. 节点、角色、污点和资源

```bash
k get nodes -o wide | tee "$CNPL_ACCEPT_DIR/01-nodes.txt"
k get nodes -o 'custom-columns=NAME:.metadata.name,TAINTS:.spec.taints,CPU:.status.allocatable.cpu,MEMORY:.status.allocatable.memory' \
  | tee "$CNPL_ACCEPT_DIR/02-roles-resources.txt"
```

第一条预期恰好 10 个 Ready，地址 `.101–.110`，版本 `v1.36.5`。第二条显示调度保护和可分配资源：控制平面和 storage 各有对应 NoSchedule 污点，infra/worker 没有这两类污点；CPU 依次为 control_plane 3、infra 5、storage 5、worker 7 核。内存是内核报告 Capacity 扣除角色预留和 500Mi 驱逐余量，不能直接拿 VM 标称内存做等式。

```bash
ANSIBLE_CONFIG="$PWD/ops/00-preparation/ansible/ansible.cfg" \
  "$HOME/.venvs/cnpl-ansible/bin/ansible-playbook" ops/01-kubernetes/ansible/playbooks/verify-hosts.yml \
  2>&1 | tee "$CNPL_ACCEPT_DIR/03-effective-host-config.txt"
```

这条只读验收入口使用既有 inventory/SSH，逐台验证 SELinux Enforcing、firewalld/containerd/kubelet active，读取 `/var/lib/kubelet/config.yaml` 核对真正生效的预留、驱逐、DNS、PID、cgroup 配置，以及 CRI RuntimeReady/NetworkReady。只看到补丁文件不代表已经生效。预期十台 changed=0、failed=0、unreachable=0。

## 3. 系统组件

```bash
k -n kube-system get daemonsets,deployments -o wide | tee "$CNPL_ACCEPT_DIR/04-system-workloads.txt"
k -n kube-system get pods -o wide | tee "$CNPL_ACCEPT_DIR/05-system-pods.txt"
"$HOME/.cnpl/bin/cilium" --kubeconfig "$HOME/.cnpl-secrets/kubeconfig-lab-primary" status --wait --wait-duration 2m \
  2>&1 | tee "$CNPL_ACCEPT_DIR/06-cilium-status.txt"
```

三条分别检查控制器期望/就绪数、具体 Pod 的 Ready/状态/重启，以及 Cilium 自身健康。预期 cilium、cilium-envoy、kube-proxy 各 10/10，cilium-operator 和 CoreDNS 各 2/2，控制面系统 Pod 的 Ready 为 1/1。历史重启次数保留，持续增加才需要排查；Running 并不等于 Ready。Hubble/ClusterMesh disabled 符合当前配置。

## 4. 三 API 与 VIP

```bash
(
  set -e
  for endpoint in api.k8s.internal.egon.top 192.168.9.101 192.168.9.102 192.168.9.103; do
    printf '\n== API %s ==\n' "$endpoint"
    k --server="https://$endpoint:6443" --request-timeout=10s get --raw='/readyz?verbose'
  done
) 2>&1 | tee "$CNPL_ACCEPT_DIR/07-api-readiness.txt"
k -n kube-system get lease plndr-cp-lock -o wide | tee "$CNPL_ACCEPT_DIR/08-vip-lease.txt"
```

循环分别验证统一入口及三个独立 API，保留 TLS 校验；每项预期检查为 ok，并以 readyz check passed 结束。子 shell 的 set -e 避免前面失败却被后面的成功掩盖。lease 显示当前 VIP 选举持有者，应为三个控制平面之一；它会变化，不要求永远是 cp01。这一步只验正常状态，不证明故障时能接管。

## 5. etcd 三成员

```bash
k -n kube-system exec etcd-cp01.k8s.internal.egon.top -- \
  etcdctl --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/healthcheck-client.crt \
  --key=/etc/kubernetes/pki/etcd/healthcheck-client.key \
  endpoint health --cluster 2>&1 | tee "$CNPL_ACCEPT_DIR/09-etcd-health.txt"

k -n kube-system exec etcd-cp01.k8s.internal.egon.top -- \
  etcdctl --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/healthcheck-client.crt \
  --key=/etc/kubernetes/pki/etcd/healthcheck-client.key \
  endpoint status --cluster -w table 2>&1 | tee "$CNPL_ACCEPT_DIR/10-etcd-status.txt"
```

使用现有 etcd 容器内配套的 etcdctl 和本地证书，不要求 Mac/宿主机额外安装。127.0.0.1 是该 Pod 的本机 etcd 入口；--cluster 自动发现并检查所有成员。预期 `.101/.102/.103:2379` 三个 healthy；status 三行、一个 leader、零 learner、ERRORS 为空。该查询验证当前成员服务状态，不是快照备份。

## 6. 部署临时普通 Pod

```bash
k apply -f ops/01-kubernetes/bootstrap/acceptance/network-smoke.yaml \
  2>&1 | tee "$CNPL_ACCEPT_DIR/11-network-apply.txt"
k -n cnpl-phase01-acceptance rollout status daemonset/network-smoke --timeout=5m \
  2>&1 | tee "$CNPL_ACCEPT_DIR/12-network-rollout.txt"
k -n cnpl-phase01-acceptance get pods -o wide | tee "$CNPL_ACCEPT_DIR/13-network-pods.txt"
```

apply 创建专用 Namespace、DaemonSet 和 ClusterIP Service；这是本轮唯一部署步骤。每节点一个小型 HTTP Pod，响应自身节点名；使用已锁定且十节点缓存的 Harbor BusyBox 镜像。Namespace 使用 restricted Pod Security，Pod 非 root、只读根文件系统、无主机网络/挂载/ServiceAccount 凭据，临时 www 在 emptyDir 中。

仅诊断 Pod 显式容忍控制平面与 storage 污点，让全部十节点参加测试；节点污点保留。rollout 等待十个 Pod 就绪，get 应看到每节点一个 Ready、IP 属于 `10.244.0.0/16`。

## 7. 执行普通 Pod 网络、Service、DNS 验收

```bash
"$HOME/.venvs/cnpl-ansible/bin/python" ops/01-kubernetes/bootstrap/acceptance/check-network.py \
  2>&1 | tee "$CNPL_ACCEPT_DIR/14-network-matrix.txt"
```

脚本只对现有诊断 Pod 执行客户端命令，不创建或删除资源。先验证十个预期节点恰好各一 Pod、普通网络、地址唯一及 Ready，再从每个 Pod 发起：

- 对十个 Pod IP 的 HTTP，并校验响应节点名；共 100 条路径，其中 90 条跨节点，覆盖每个方向。
- 指定集群 DNS `.20.10` 查询测试 Service、`kubernetes.default.svc.cluster.local`、Harbor 与 `kubernetes.io`；前三种核对预期地址，外部域检查解析成功。
- 通过 Service ClusterIP 和 Service 全名各发起一次 HTTP，校验后端身份。

预期最后一行为 `NETWORK ACCEPTANCE PASS: 10 sources, 100 Pod HTTP paths (90 cross-node), 40 DNS checks, 20 Service HTTP requests.`。任一失败返回非零，并打印出错源节点及输出；普通 Pod 发起的测试不能用主机网络或 Cilium 专用健康端点替代。[Kubernetes DNS 检查方法](https://kubernetes.io/docs/tasks/administer-cluster/dns-debugging-resolution/)

## 8. 保存后端与事件

```bash
k -n cnpl-phase01-acceptance get endpointslices -l kubernetes.io/service-name=network-smoke -o wide \
  | tee "$CNPL_ACCEPT_DIR/15-network-backends.txt"
k get events -A --field-selector type=Warning --sort-by=.metadata.creationTimestamp \
  | tee "$CNPL_ACCEPT_DIR/16-warning-events.txt"
```

EndpointSlice 记录 Service 实际后端；Warning 记录异常线索。启动期间已恢复的历史 Warning 不等于当前失败，应按对象、时间、重复次数与现状判断；不能简单要求集群从未出现 Warning。

## 9. 成功后清理

只有第 7 步出现完整 PASS 后才执行；失败时保留测试 Pod，便于检查日志、DNS 和网络。

```bash
k delete -f ops/01-kubernetes/bootstrap/acceptance/network-smoke.yaml --ignore-not-found=true --wait=true --timeout=180s \
  2>&1 | tee "$CNPL_ACCEPT_DIR/17-network-cleanup.txt"
k get namespace cnpl-phase01-acceptance --ignore-not-found \
  | tee "$CNPL_ACCEPT_DIR/18-cleanup-confirm.txt"
printf '证据目录：%s\n' "$CNPL_ACCEPT_DIR"
```

delete 删除本清单创建的临时资源及专用 Namespace；该 Namespace 只用于本验收，不放其他对象。第二条无输出表示已清理，最后一条显示本轮证据位置。全部基础项通过后，将结果汇总至本批 acceptance.md；受限管理身份、备份与隔离恢复、单控制平面故障实验及其他 Phase 01 用例仍逐项执行。
