# Phase 06 实验操作手册

配合 [阶段正文](../../plan/06-advanced-security-dr.md) 按原专题执行；所有动作当前未执行，配置路径是实施交付位置。每次先确认输入和作用域，再写配置、执行、检查正常与失败路径、恢复并归档。报告放 `ops/06-advanced-security-dr/records/<执行批次>/`。

## 命令与示例的使用方式

以下写明实验时大概要执行的命令、目的和预期变化，不是现在就能整段运行的一键脚本。`LAB_*`、`<...>`、版本、资源名和文件路径在开始实验时按实际环境填写；文件须先根据示例补齐，凭据通过受控配置注入。YAML 标为“片段”时应合并到完整对象，不能单独 apply；示例值不是性能或容量承诺。

`kubectl` 在选定集群的管理终端执行，`kubeadm`/主机命令在文中指定节点执行。每次变更前用 `kubectl config current-context` 核对目标。`--dry-run=server` 用于已经存在的集群/API；CRD 尚未安装时先安装匹配版本。`kubectl diff` 返回 1 通常表示有差异，应阅读差异后再 apply。故障、恢复和清理命令分段执行并观察结果，当前不执行任何部署。

测试 Namespace、样例应用、Chart/CRD 和引用文件应先创建到就绪；已由 GitOps 托管的对象通过仓库变更和同步更新，文中的直接 patch/scale/apply 用于隔离实验对象或受控诊断。

<a id="06-01"></a>

## 06.01 06A：统一身份、RBAC 与 ServiceAccount

输入：已有本地恢复身份、备份、基础 RBAC 和服务入口。

1. 部署 Keycloak，建立团队/客户端/角色；逐平台验证 OIDC 回调、CA、audience 和权限映射，保留与其无关的受控恢复管理员。
2. 为 Kubernetes 配置身份到 RBAC 的授权，实际测试普通开发、团队运维和平台管理员的允许/拒绝资源操作。
3. 轮换应用、CI、Operator 的 ServiceAccount/机器人凭据，验证过期与撤销，并检查敏感凭据不出现在报告。

### 操作命令与目的

```bash
helm upgrade --install keycloak "$LAB_KEYCLOAK_CHART" -n identity \
  --create-namespace --version "$LAB_KEYCLOAK_VERSION" -f keycloak-values.yaml --wait
# 在已有受控管理登录的 kcadm 环境创建实验 Realm/Client
kcadm.sh create realms -f realm-lab.json
kcadm.sh get realms/lab --fields realm,enabled
kubectl -n lab-apps apply -f oidc-rbac.yaml
# 使用实际 OIDC 用户 kubeconfig 检查身份和权限，不能仅用管理员 impersonation 代替
kubectl --kubeconfig="$LAB_USER_KUBECONFIG" auth can-i get pods -n lab-apps
kubectl --kubeconfig="$LAB_USER_KUBECONFIG" auth can-i delete secrets -n lab-apps
umask 077
kubectl -n lab-apps create token lab-reader --duration=10m > "$LAB_SA_TOKEN_FILE"
```

短时 token 只用于该实验客户端，测试完成后清理受控文件。OIDC issuer、audience、用户/组 claim 和 API Server 信任配置先匹配实际 Keycloak Client。

### 配置示例

把约定的 OIDC 组绑定到 Namespace 内已有的只读 Role，组前缀与实际认证配置保持一致：

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata: {name: lab-developers-read, namespace: lab-apps}
subjects:
  - kind: Group
    name: oidc:lab-developers
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: pod-reader
  apiGroup: rbac.authorization.k8s.io
```

### 预期结果

真实用户完成认证后只能操作授权资源；只读用户可以读 Pod 而不能删除 Secret，ServiceAccount token 的受众/时效符合约定。停用 Keycloak 时新登录受影响，但受控恢复管理员仍能使用独立入口。

交付：`ops/06-advanced-security-dr/security/identity/`、RBAC 与轮换记录。

检查与失败处理：登录与授权分别通过；IdP 停机后仍能按既定应急流程恢复，而普通权限不被放大。

<a id="06-02"></a>

## 06.02 06A：PSA、Kyverno 与准入

输入：04 的扫描/签名/准入主线和恢复入口。

1. 按 Namespace 应用 PSA 等级，验证 SecurityContext、seccomp、SELinux 与需例外的系统组件。
2. 将 Kyverno 策略从 Audit 推进到受限 Enforce，测试无资源声明、特权容器、不可信镜像及合法工作负载。
3. 中断策略所依赖仓库或验证材料，检查拒绝/恢复行为，演练有时限和审计的应急例外后撤销。

### 操作命令与目的

```bash
kubectl create namespace lab-security --dry-run=client -o yaml | kubectl apply -f -
kubectl label namespace lab-security pod-security.kubernetes.io/enforce=restricted --overwrite
kubectl -n lab-security apply -f restricted-pod.yaml
kubectl -n lab-security apply --dry-run=server -f privileged-pod.yaml  # 预期拒绝
kyverno apply "$LAB_POLICY_FILE" --resource "$LAB_NEGATIVE_POD_FILE"
kubectl apply -f kyverno-lab-policy.yaml
kubectl -n lab-security apply -f unsigned-pod.yaml                    # 准入实际拒绝测试
kubectl -n lab-security get events --sort-by=.metadata.creationTimestamp
```

先确认 Kyverno 对实验 Namespace 的 Audit/Enforce 模式，再测试信任镜像、特权字段、缺少资源声明等不同失败原因。

### 配置示例

符合 Restricted 方向的 PodSpec 片段；测试镜像需能以指定非 root UID 工作：

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  seccompProfile: {type: RuntimeDefault}
containers:
  - name: app
    image: "<可信的非root测试镜像>"
    securityContext:
      allowPrivilegeEscalation: false
      capabilities:
        drop: [ALL]
```

### 预期结果

合规 Pod 可运行，违规 Pod 在创建阶段被拒绝且指出策略原因；普通应用无需集群管理员权限。系统组件的必要例外应局限在其范围内，不能为了安装一个 DaemonSet 把全局限制解除。

交付：`ops/06-advanced-security-dr/security/policies/`；`ops/06-advanced-security-dr/tests/security/` 准入正反用例。

检查与失败处理：真实非法创建被拒绝，核心恢复路径可控；不通过无限制例外满足安装。

<a id="06-03"></a>

## 06.03 06A：秘密、审计与信任轮换

输入：已有数据加密/审计基线与独立恢复材料。

1. 以隔离业务比较 SOPS/age 和 External Secrets/Vault；验证只有授权解密者可读取，测试 Secret 后端不可用、解封/恢复和撤销。
2. 按受控多密钥过程轮换 Kubernetes 数据加密密钥，重新验证旧数据可读并更新独立备份索引。
3. 串联 Git/CI/IaC/API/身份审计；回访 SPIFFE/SPIRE 的跨服务信任与续期，测试错误身份和撤销，避免把 DNS 命名等同授权。

### 操作命令与目的

```bash
# 在受控工作目录加密测试 Secret；私钥与明文不入 Git
umask 077
age-keygen -o "$LAB_AGE_PRIVATE_KEY"
sops --encrypt --age "$LAB_AGE_PUBLIC_KEY" "$LAB_PLAIN_SECRET" > secrets.enc.yaml
sops --decrypt secrets.enc.yaml > "$LAB_PRIVATE_DECRYPTED_FILE"
# 对采用 Vault/Raft 的对照环境检查状态并保存独立快照
vault status
vault operator raft snapshot save "$LAB_VAULT_SNAPSHOT"
# 加密配置已按流程在各 API Server 更新后，只重写一个专用实验 Secret
kubectl -n lab-security get secret "$LAB_TEST_SECRET" -o json | kubectl replace -f -
kubectl -n lab-security get externalsecrets,secretstores
```

轮换顺序是：所有控制平面先具备“新写密钥 + 旧读密钥”→验证→重写实验数据→确认新旧数据可读→按保留计划撤旧。不能先删除唯一解密密钥；External Secrets/Vault 另测后端不可用与恢复。

### 配置示例

EncryptionConfiguration 的密钥顺序片段，真实文件仅保存在受控节点/备份中：

```yaml
resources:
  - resources: [secrets]
    providers:
      - aescbc:
          keys:
            - name: key-v2
              secret: <新密钥的base64值>
            - name: key-v1
              secret: <旧密钥的base64值>
```

### 预期结果

Git 内只有密文或引用，授权执行器能解密，未持有密钥者不能；轮换后旧数据与新数据都能正确读取。恢复快照/Secret 后端时权限和审计仍成立；上述管道中的 Secret 正文不复制到普通报告。

交付：秘密引用/加密声明、审计关联与轮换/恢复 Runbook。

检查与失败处理：旧新数据均可安全访问，丢失在线身份服务仍可恢复；私钥/明文不提交 Git。

<a id="06-04"></a>

## 06.04 06A：Falco 与 Tetragon

输入：锁定内核/驱动兼容性与授权测试 Namespace。

1. 分别启用 Falco 与 Tetragon 的受控规则，记录内核能力、权限与资源消耗；对照探针不要求全程同时常驻。
2. 用实验容器制造已授权 shell 启动、文件访问和出站行为，核对告警的进程/容器/节点信息与误报。
3. 把运行时事件关联到应用版本和调查记录，验证停探针与恢复，不在生产或第三方对象注入。

### 操作命令与目的

```bash
helm upgrade --install falco "$LAB_FALCO_CHART" -n falco \
  --create-namespace --version "$LAB_FALCO_VERSION" -f falco-values.yaml --wait
helm upgrade --install tetragon "$LAB_TETRAGON_CHART" -n kube-system \
  --version "$LAB_TETRAGON_VERSION" -f tetragon-values.yaml --wait
kubectl -n lab-security exec runtime-demo -- sh -c 'id; cat /etc/os-release'
kubectl -n falco logs daemonset/falco -c falco --since=5m
kubectl -n kube-system logs daemonset/tetragon -c export-stdout --since=5m
```

先加载只针对实验对象的规则，再执行授权的 shell/文件访问；使用相同动作分别比较两种探针，记录事件字段、误报与资源消耗。

### 配置示例

Falco 规则文件示意，复用其默认宏；自定义规则加载位置按 Chart 填写：

```yaml
- rule: LabShellExecution
  desc: Observe shell starts in the authorized lab namespace
  condition: spawned_process and container and proc.name = sh and k8s.ns.name = lab-security
  output: "Lab shell (user=%user.name command=%proc.cmdline pod=%k8s.pod.name)"
  priority: NOTICE
  tags: [lab]
```

### 预期结果

指定实验 shell 产生可关联到 Pod/节点/进程的事件，未纳入范围的普通维护流量不被当成该实验。驱动/内核能力不满足时表现为探针错误或缺少事件，应先修复前置，不手填“已检测”。

交付：`ops/06-advanced-security-dr/security/runtime/`；检测用例与开销/误报对照。

检查与失败处理：授权异常可检测且正常场景有对照；内核不支持则阻塞该实现，不写假告警结果。

<a id="06-05"></a>

## 06.05 06A：HPA、VPA 与 KEDA

输入：指标平台、Kafka/RabbitMQ 等已验证消息系统。

1. 比较 HPA 多指标/稳定窗口与 VPA 建议，明确同一资源维度不由冲突控制器同时调整。
2. 为 Kafka 消费者、RabbitMQ Worker 建 KEDA ScaledObject/认证，实测积压触发扩容、清空后缩容和指标源失效。
3. 结合 PDB/优先级/容量检查测试缩零与恢复，记录冷启动、任务丢失/重复、最大副本和稳定窗口。

### 操作命令与目的

```bash
helm upgrade --install keda "$LAB_KEDA_CHART" -n keda \
  --create-namespace --version "$LAB_KEDA_VERSION" -f keda-values.yaml --wait
kubectl -n lab-events apply -f kafka-trigger-auth.yaml -f kafka-scaledobject.yaml
kubectl -n lab-events get scaledobjects,hpa
kubectl -n lab-events get hpa -w                   # 配合有界测试消息观察副本
kubectl -n lab-events apply -f vpa-recommendation.yaml
kubectl -n lab-events get vpa -o yaml
# Kafka 与 RabbitMQ 伸缩分别实验，使用不同 Deployment/ScaledObject
kubectl -n lab-events apply -f rabbitmq-scaledobject.yaml
```

### 配置示例

Kafka ScaledObject，Kafka 身份/TLS 由 TriggerAuthentication 提供；VPA 初期用推荐模式，避免与 HPA/KEDA 争抢同一资源维度：

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata: {name: orders-consumer, namespace: lab-events}
spec:
  scaleTargetRef:
    name: orders-consumer
  minReplicaCount: 0
  maxReplicaCount: 4
  pollingInterval: 30
  cooldownPeriod: 60
  triggers:
    - type: kafka
      metadata:
        bootstrapServers: <实际Kafka入口>
        consumerGroup: lab-orders
        topic: lab-orders
        lagThreshold: "100"
      authenticationRef:
        name: kafka-auth
```

### 预期结果

积压增加后扩容、消费完成并经过冷却窗口后缩容；缩到零后新事件可再次触发。记录冷启动、积压恢复、重复/丢失消息和 scaler 错误；无指标/认证失败不应被记录为正常无负载。

交付：`ops/01-kubernetes/core-resources/autoscaling/` 扩展与事件伸缩用例。

检查与失败处理：负载和副本有因果证据，缩零后事件仍可被正确处理；失败撤销本次伸缩规则并恢复已知副本。

<a id="06-06"></a>

## 06.06 06B：Knative Serving/Eventing

输入：网关适配、证书、消息和资源预算通过。

1. 部署 Serving 的所需控制器与网络组件，创建 Knative Service，测试 Revision、流量分配、缩零和冷启动。
2. 部署 Eventing 的所选 Broker/Trigger/Source，发带唯一 ID 的事件，观察投递、重试、死信和消费者恢复。
3. 对比相同应用常驻与 Serverless 的延迟和资源，记录活跃/空闲两种负载；不能用只创建 CR 代替实际请求。

### 操作命令与目的

```bash
kubectl apply -f "$LAB_KNATIVE_SERVING_MANIFEST" -f "$LAB_KNATIVE_NETWORK_MANIFEST"
kubectl apply -f "$LAB_KNATIVE_EVENTING_MANIFEST"
kn service create hello -n lab-serverless --image "$LAB_HELLO_IMAGE" --scale-min=0 --scale-max=3
kn service list -n lab-serverless
curl --fail "$LAB_KNATIVE_HELLO_URL"
kn service update hello -n lab-serverless --image "$LAB_HELLO_IMAGE_V2" \
  --traffic "$LAB_STABLE_REVISION=90" --traffic @latest=10
kn broker create lab-broker -n lab-serverless
kn trigger create hello-events -n lab-serverless --broker lab-broker \
  --sink ksvc:hello --filter type=lab.order
curl -X POST "$LAB_BROKER_URL" -H 'Content-Type: application/json' \
  -H 'Ce-Specversion: 1.0' -H 'Ce-Type: lab.order' -H 'Ce-Source: /lab' \
  -H 'Ce-Id: lab-event-001' -d '{"order_id":1}'
```

安装文件、网络实现、Broker 类/通道和 Namespace 先按选定版本准备；接收事件的 hello 样例需支持对应请求。相同 Event ID 的重发用于幂等实验。

### 配置示例

```yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata: {name: hello, namespace: lab-serverless}
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/min-scale: "0"
        autoscaling.knative.dev/max-scale: "3"
    spec:
      containers:
        - image: "<内网HTTP/事件样例镜像>"
          ports: [{containerPort: 8080}]
```

### 预期结果

请求触发实例，空闲后按策略缩零；新 Revision 获得约定流量，冷启动时间有实测。Broker/Trigger 能投递匹配事件，消费者失败时观察重试/死信/重放，不把重复投递误判为事件丢失或恰好一次。

交付：`ops/06-advanced-security-dr/serverless/knative/`；CR、事件与延迟结果。

检查与失败处理：HTTP/事件链路可重复、失败可恢复；卸载前先处理事件积压和持久数据。

<a id="06-07"></a>

## 06.07 06B：Dapr 与多语言事件应用

输入：可用状态/消息组件和两种以上语言样例。

1. 部署 Dapr，显式配置受限 state/pubsub/secret 组件；用相同业务对比原生 SDK 和 Dapr API。
2. 测试服务调用、消息幂等、状态持久与 workflow 中断恢复；关联 OTel 上下文。
3. 验证 sidecar/控制面/消息后端失效的不同影响，检查重试和取消不会无限放大负载。

### 操作命令与目的

```bash
helm upgrade --install dapr "$LAB_DAPR_CHART" -n dapr-system \
  --create-namespace --version "$LAB_DAPR_VERSION" -f dapr-values.yaml --wait
kubectl -n lab-serverless apply -f dapr-components.yaml -f dapr-apps.yaml
dapr status -k
kubectl -n lab-serverless get pods
# 在带 Dapr sidecar、含 curl 的应用测试容器内访问本地 Dapr API
kubectl -n lab-serverless exec "$LAB_APP_POD" -c app -- \
  curl -fsS http://127.0.0.1:3500/v1.0/invoke/orders/method/health
kubectl -n lab-serverless exec "$LAB_APP_POD" -c app -- \
  curl -X POST http://127.0.0.1:3500/v1.0/publish/lab-pubsub/orders \
  -H 'Content-Type: application/json' -d '{"id":"lab-001"}'
kubectl -n lab-serverless rollout restart deployment/orders
```

工作流样例另外提供启动和状态查询接口：先启动一个有持久状态的任务，在中途重启应用，再查询同一实例是否续跑。Dapr API token 若启用，测试客户端也要按配置带身份。

### 配置示例

发布订阅组件通过 Secret 引用凭据；应用 Pod 模板还需 `dapr.io/enabled`、`dapr.io/app-id` 与端口注解：

```yaml
apiVersion: dapr.io/v1alpha1
kind: Component
metadata: {name: lab-pubsub, namespace: lab-serverless}
spec:
  type: pubsub.redis
  version: v1
  metadata:
    - name: redisHost
      value: <实际Redis入口>
    - name: redisPassword
      secretKeyRef: {name: redis-client, key: password}
scopes: [orders, worker]
```

### 预期结果

调用到对应 app-id，消息到达订阅者并可关联 Trace；重启后业务状态按所选组件语义恢复。对重复消息按业务 ID 去重，对原生 SDK/Dapr 使用相同负载比较，不声称所有组件有相同一致性。

交付：`ops/06-advanced-security-dr/serverless/dapr/`；组件、样例和失败/恢复记录。

检查与失败处理：跨语言业务和持久状态正确；能力不支持时注明，不把 SDK 示例成功推广为全部组件保证。

<a id="06-08"></a>

## 06.08 06B：Workflows/Events；06D 的队列前置

输入：独立工作流作用域、制品存储和 NATS/事件平台。

1. 声明 Argo Workflow/WorkflowTemplate、制品路径与受限身份，测试依赖步骤、重试、取消和失败补偿。
2. 用 Argo Events 的受控 EventSource/Sensor 触发流程，记录事件 ID/去重/重放和 NATS 持久化；比较与 Tekton/应用 CI 的责任。
3. 06.08.04 的 Kueue 队列准入归入 06D：声明 ResourceFlavor/ClusterQueue/LocalQueue，提交超配额 Job，观察排队、准入、完成与资源释放，再供训练专题使用。

### 操作命令与目的

```bash
kubectl -n lab-workflows apply -f workflow-controller.yaml -f eventbus.yaml \
  -f event-source.yaml -f event-sensor.yaml
argo submit -n lab-workflows workflow-demo.yaml --watch
argo get "$LAB_WORKFLOW_NAME" -n lab-workflows
argo logs "$LAB_WORKFLOW_NAME" -n lab-workflows
# 只有前次失败且业务允许重试时，再重试同一 Workflow
argo retry "$LAB_WORKFLOW_NAME" -n lab-workflows
curl -X POST "$LAB_EVENT_WEBHOOK_URL" -H 'Content-Type: application/json' -d '{"id":"lab-event-001"}'

# 06D 的 Kueue 前置：安装所选版本、队列和受限 Job
kubectl apply --server-side -f "$LAB_KUEUE_MANIFEST"
kubectl apply -f resource-flavor.yaml -f cluster-queue.yaml -f local-queue.yaml
kubectl -n lab-ai apply -f queued-job.yaml
kubectl -n lab-ai get workloads.kueue.x-k8s.io,jobs
```

### 配置示例

一个最小 Workflow；实际构建/制品任务再替换容器和产物路径：

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Workflow
metadata: {generateName: lab-workflow-, namespace: lab-workflows}
spec:
  entrypoint: probe
  templates:
    - name: probe
      container:
        image: "<内网诊断镜像>"
        command: [sh, -c, "echo workflow-ok"]
```

Kueue Job 的关键字段，LocalQueue `lab-queue` 需已映射到有配额的 ClusterQueue：

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: queued-probe
  namespace: lab-ai
  labels: {kueue.x-k8s.io/queue-name: lab-queue}
spec:
  suspend: true
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: job
          image: "<内网诊断镜像>"
          command: [sh, -c, "echo queue-admitted; sleep 10"]
          resources:
            requests: {cpu: "1", memory: 256Mi}
```

### 预期结果

Workflow 成功或失败有明确节点/日志，事件触发的实例可追溯到 Event ID；重放不造成不受控副作用。Kueue 配额不足时保持排队，有配额后准入并解除 suspend，完成后释放配额。排队与 kube-scheduler 的节点调度是两个阶段。

交付：`ops/06-advanced-security-dr/serverless/argo/` 与 `ops/06-advanced-security-dr/ai-gpu/kueue/`；事件和队列证据。

检查与失败处理：事件可重放且不产生不受控重复副作用；排队不等于失败，超配额任务不得绕过准入。

<a id="06-09"></a>

## 06.09 06C：CAPI/CAPV 创建第二集群

输入：vCenter 权限、模板/许可证、额外容量、独立节点/VIP/CIDR。

1. 先核实十节点主集群之外的资源，锁定 CAPV/CAPI/Kubernetes/镜像组合，创建独立 VM 文件夹/作用域；不收编 kubeadm 主集群。
2. 部署管理组件，声明 Cluster/MachineDeployment 和机器模板，先 Plan/检查再创建最小可用实验集群。
3. 验证 Machine 扩容、受控修复和升级，备份管理状态；测试清理只针对实验集群，避免 orphan VM/磁盘。

### 操作命令与目的

```bash
clusterctl init --core "cluster-api:$LAB_CAPI_VERSION" --infrastructure "vsphere:$LAB_CAPV_VERSION"
clusterctl generate cluster lab-secondary --infrastructure "vsphere:$LAB_CAPV_VERSION" \
  --kubernetes-version "$LAB_SECONDARY_K8S_VERSION" --list-variables
kubectl create namespace lab-multicluster --dry-run=client -o yaml | kubectl apply -f -
# 补齐模板需要的 vCenter/Datastore/网络/凭据引用和资源预算后生成
clusterctl generate cluster lab-secondary --infrastructure "vsphere:$LAB_CAPV_VERSION" \
  --target-namespace lab-multicluster --kubernetes-version "$LAB_SECONDARY_K8S_VERSION" \
  --control-plane-machine-count="$LAB_SECONDARY_CP_COUNT" \
  --worker-machine-count="$LAB_SECONDARY_WORKER_COUNT" > "$LAB_SECONDARY_MANIFEST"
kubectl apply --dry-run=server -f "$LAB_SECONDARY_MANIFEST"
kubectl apply -f "$LAB_SECONDARY_MANIFEST"
kubectl -n lab-multicluster get clusters,machinedeployments,machines
umask 077
clusterctl get kubeconfig lab-secondary --namespace lab-multicluster > "$LAB_SECONDARY_KUBECONFIG"
kubectl --kubeconfig="$LAB_SECONDARY_KUBECONFIG" get nodes
```

离线环境先配置 clusterctl 本地 Provider/template 仓库和已同步镜像。主集群继续由 kubeadm 管理，不对它执行 CAPV 纳管。生成文件可能包含敏感引用，保存范围要受控。

### 配置示例

生成 Cluster 中的网络/入口片段；VSphereCluster、MachineTemplate、ControlPlane 等对象由匹配版本模板提供：

```yaml
clusterNetwork:
  pods:
    cidrBlocks: [10.245.0.0/16]
  services:
    cidrBlocks: [10.96.0.0/16]
  serviceDomain: cluster.local
controlPlaneEndpoint:
  host: <已核实的第二集群API地址>
  port: 6443
```

### 预期结果

Provider 控制器健康，Machine 实际创建对应 VM，装好 CNI 后第二集群节点 Ready。使用 `kubectl scale machinedeployment ...` 验证扩容，观察 Machine/VM 一起变化；只有 CR 已创建而 VM 失败不算成功。清理前保护管理状态和该集群的数据。

交付：`ops/06-advanced-security-dr/multicluster/capi/`；第二集群台账与机器生命周期记录。

检查与失败处理：第二集群真实可用且可恢复/清理；没有 vCenter 或容量就明确阻塞，不能用 CRD 存在代替集群创建。

<a id="06-10"></a>

## 06.10 06C：多集群交付、网络与故障切换

输入：第二集群健康；不同 CIDR、cluster ID 与网络可达。

1. 用 ApplicationSet 发布同一 Digest 到两个集群；Flux 在独立对象上对照。按 cluster/environment 标签接入 05 遥测并检查跨集群查询。
2. 部署 Cluster Mesh 并验证服务发现、MCS API 适配、跨集群策略和拒绝访问；实际连接证明路由与身份一致。
3. 持续跨集群请求，隔离一端的应用或网络，记录流量恢复、数据访问和恢复时间；明确流量切换不自动复制数据库状态。

### 操作命令与目的

```bash
# 两边 Cilium 的 cluster name/ID、CIDR 与连接前置已分别配置
cilium clustermesh enable --context "$LAB_PRIMARY_CONTEXT" --service-type LoadBalancer
cilium clustermesh enable --context "$LAB_SECONDARY_CONTEXT" --service-type LoadBalancer
cilium clustermesh connect --context "$LAB_PRIMARY_CONTEXT" --destination-context "$LAB_SECONDARY_CONTEXT"
cilium clustermesh status --context "$LAB_PRIMARY_CONTEXT" --wait
kubectl -n argocd apply -f secondary-cluster-secret.yaml -f multicluster-applicationset.yaml
kubectl --context="$LAB_PRIMARY_CONTEXT" -n lab-multicluster apply -f global-service.yaml
kubectl --context="$LAB_SECONDARY_CONTEXT" -n lab-multicluster apply -f global-service.yaml
curl --fail "$LAB_MULTI_CLUSTER_URL"
# 单独让一侧测试应用无后端，观察流量变化；之后恢复原副本数
kubectl --context="$LAB_SECONDARY_CONTEXT" -n lab-multicluster scale deployment/global-echo --replicas=0
kubectl --context="$LAB_SECONDARY_CONTEXT" -n lab-multicluster scale deployment/global-echo --replicas="$LAB_SECONDARY_APP_REPLICAS"
```

Argo CD 的集群凭据使用受限身份且通过私密文件/既定秘密管理导入；不要把 Secret 明文提交 Git。连接故障、策略隔离、MCS ServiceExport/ServiceImport 与 Flux 对照分别作为扩展场景执行。

### 配置示例

Cilium 全局 Service 示例，两个集群中名称/namespace 一致，后端响应应包含所在 cluster 标识：

```yaml
apiVersion: v1
kind: Service
metadata:
  name: global-echo
  namespace: lab-multicluster
  annotations:
    service.cilium.io/global: "true"
spec:
  selector: {app: global-echo}
  ports: [{port: 8080, targetPort: 8080}]
```

### 预期结果

Cluster Mesh 连接健康，允许的服务跨集群访问，未授权流量仍拒绝；一侧无后端后请求按配置走可用端点并有真实恢复时间。05 的查询能够按 cluster 标签区分来源。应用流量切换不代表数据库已跨集群复制。

交付：`ops/06-advanced-security-dr/multicluster/`、`ops/06-advanced-security-dr/multicluster/examples/`；交付/隔离/切换与跨集群观测记录。

检查与失败处理：允许与拒绝用例、流量故障切换有实测；故障恢复后检查对等连接、路由和数据一致性。

<a id="06-11"></a>

## 06.11 06D：KubeVirt

输入：ESXi 允许嵌套虚拟化，客体可见 KVM，存储/网络具备目标功能。

1. 检查客体 CPU 虚拟化标志和 `/dev/kvm`，明确 ESXi 支持与资源前置，再部署 KubeVirt/CDI。
2. 从固定镜像创建 VM/VMI/DataVolume，测试启动/停止、控制台、网络、Ceph 磁盘与重建后的数据。
3. 仅在 CPU/网络/共享存储等迁移前置满足时测试 live migration；记录迁移前后请求与数据，不支持则标阻塞。

### 操作命令与目的

```bash
# 在目标 Rocky 客体核实嵌套虚拟化能力
lscpu
ls -l /dev/kvm
# 管理端安装锁定清单，等待控制器可用
kubectl apply -f "$LAB_KUBEVIRT_OPERATOR_MANIFEST"
kubectl wait --for=condition=Established crd/kubevirts.kubevirt.io --timeout=120s
kubectl apply -f "$LAB_KUBEVIRT_CR"
kubectl apply -f "$LAB_CDI_OPERATOR_MANIFEST"
kubectl wait --for=condition=Established crd/cdis.cdi.kubevirt.io --timeout=120s
kubectl apply -f "$LAB_CDI_CR"
kubectl -n kubevirt wait kubevirt/kubevirt --for=condition=Available --timeout=300s
kubectl -n lab-vm apply -f data-volume.yaml -f virtualmachine.yaml
virtctl start vm-demo -n lab-vm
kubectl -n lab-vm get vm,vmi,datavolumes,pvc
virtctl console vm-demo -n lab-vm
# 仅在 CPU/网络/存储迁移前置满足时执行
virtctl migrate vm-demo -n lab-vm
virtctl stop vm-demo -n lab-vm
```

console 连接是单独的交互会话；结束并验证虚拟机状态后再进行下一动作。数据盘导入完成后才启动，访客登录/cloud-init 参数在实验时填写。

### 配置示例

VirtualMachine 的核心字段，`vm-root` 是此前 CDI 导入得到的持久卷：

```yaml
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata: {name: vm-demo, namespace: lab-vm}
spec:
  runStrategy: Halted
  template:
    spec:
      domain:
        resources:
          requests: {memory: 1Gi}
        devices:
          disks:
            - name: root
              disk: {bus: virtio}
      volumes:
        - name: root
          persistentVolumeClaim: {claimName: vm-root}
```

### 预期结果

KVM 前置真实可用，DataVolume/PVC 就绪，启动后 VMI Running，停止再启动后访客数据保持。迁移只有在存储、CPU 和网络都支持时才验收；普通 RWO 卷或 /dev/kvm 不可用不能被忽略。

交付：`ops/06-advanced-security-dr/kubevirt/`；VM/CDI 清单与迁移限制报告。

检查与失败处理：VM 实际运行和数据保持可验证；不支持 KVM 时不把功能模拟等同目标性能。

<a id="06-12"></a>

## 06.12 06D：GPU、驱动与 DRA

输入：实际 GPU 型号、显存、直通方式和驱动支持矩阵。

1. 核实 ESXi/IOMMU/直通与 Rocky 客体可见设备，比较内核、GPU 驱动、CUDA、Operator 与工作负载版本，不假设所有老显卡可用。
2. 安装受支持的 GPU Operator 或明确受控驱动链，运行设备检查与小型计算任务；设置专用节点标签/污点/资源上限。
3. 对比 Device Plugin 和适用 DRA 的资源声明、调度、失败与回收；记录节点/设备不可用时行为。

### 操作命令与目的

```bash
# 目标 GPU 节点：确认真实硬件/驱动；无设备时停止该分支
lspci -nnk
nvidia-smi
# 选择 Operator 管理驱动或预装驱动中的一种，再安装
helm upgrade --install gpu-operator "$LAB_GPU_OPERATOR_CHART" -n gpu-operator \
  --create-namespace --version "$LAB_GPU_OPERATOR_VERSION" -f gpu-operator-values.yaml --wait
kubectl get nodes -o custom-columns='NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu'
kubectl -n lab-ai apply -f gpu-smoke-job.yaml
kubectl -n lab-ai logs job/gpu-smoke
# DRA 独立对照：先看当前 API 与实际设备类，再写对应 Claim/Job
kubectl api-resources --api-group=resource.k8s.io
kubectl get deviceclasses.resource.k8s.io
kubectl explain resourceclaim.spec --recursive
kubectl -n lab-ai apply -f gpu-resourceclaim.yaml -f dra-job.yaml
```

### 配置示例

Device Plugin 路线的 GPU Job；DRA 使用所选驱动支持的 ResourceClaim/资源声明，不能把该 limit 写法当作 DRA：

```yaml
apiVersion: batch/v1
kind: Job
metadata: {name: gpu-smoke, namespace: lab-ai}
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: probe
          image: "<匹配驱动的内网CUDA测试镜像>"
          command: [nvidia-smi]
          resources:
            limits:
              nvidia.com/gpu: 1
```

### 预期结果

节点报告实际 GPU 数量，测试容器可访问分配设备并完成计算/诊断；Claim 按驱动能力分配和回收。无硬件、驱动不兼容或缺许可证时保留阻塞，不使用模拟输出填补结果。

交付：`ops/06-advanced-security-dr/ai-gpu/devices/`；硬件矩阵、驱动和调度结果。

检查与失败处理：真实设备可分配/使用/回收；无 GPU、许可或驱动支持就阻塞相关用例，不生成假性能。

<a id="06-13"></a>

## 06.13 06D：模型服务、训练与分布式推理

输入：Kueue 已验证，模型/运行时物料和硬件容量符合要求。

1. 先部署 KServe CPU 小模型，验证请求/版本/缩扩与模型制品访问；GPU 可用后部署匹配模型的 vLLM，测首 token、吞吐和显存。
2. 仅启用所需 Kubeflow 模块，用 Kueue 为训练/批任务设队列和配额；验证排队、取消、重试及制品保留。
3. 硬件和网络满足时开展 llm-d 分布式推理，记录分工、路由、缓存/失败和成本；与单实例在相同模型与负载下比较。

### 操作命令与目的

```bash
kubectl apply -f "$LAB_KSERVE_CONTROLLER_MANIFEST"
kubectl -n lab-ai apply -f cpu-inferenceservice.yaml
kubectl -n lab-ai get inferenceservices
curl -H 'Content-Type: application/json' -X POST "$LAB_CPU_PREDICT_URL" --data @predict-request.json
# 在已分配设备和本地模型文件的实验容器中启动 vLLM；另一个终端发请求
vllm serve "$LAB_MODEL_PATH" --host 0.0.0.0 --port 8000 --served-model-name lab-model
curl -H 'Content-Type: application/json' -X POST "$LAB_VLLM_URL/v1/chat/completions" \
  -d '{"model":"lab-model","messages":[{"role":"user","content":"Reply with OK"}],"max_tokens":16}'
# Kubeflow 仅渲染选定模块；训练任务先进入 Kueue
kustomize build "$LAB_KUBEFLOW_OVERLAY" > "$LAB_KUBEFLOW_RENDERED"
kubectl apply --server-side -f "$LAB_KUBEFLOW_RENDERED"
kubectl -n lab-ai apply -f queued-training-job.yaml
# llm-d 使用所选官方配方渲染出的独立声明
kubectl -n lab-ai apply -f "$LAB_LLMD_RENDERED"
```

vLLM 启动是独立运行会话，实际 Kubernetes 部署再把参数写入 workload。模型文件/Tokenizer/镜像预先同步；llm-d 的路由、调度、模型和网络配套按对应版本配方填写。

### 配置示例

CPU KServe 示例，前提是已安装支持该格式的 ServingRuntime，且其身份可读取模型物料：

```yaml
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata: {name: cpu-model, namespace: lab-ai}
spec:
  predictor:
    model:
      modelFormat: {name: sklearn}
      storageUri: <内网S3模型URI>
```

### 预期结果

CPU 模型能返回正确预测；GPU 分支能实际加载匹配模型并回答请求，记录首 token 延迟、吞吐、显存和错误。训练按配额排队/运行/保留制品，llm-d 在同一模型与负载下对比单实例。CPU 用例通过不能替代 GPU/分布式用例。

交付：`ops/06-advanced-security-dr/ai-gpu/{kserve,vllm,kubeflow,llm-d}/`；任务/模型清单及性能/成本报告。

检查与失败处理：每模块真实请求或任务通过并可清理；只完成 CPU 用例不能勾选 GPU/分布式推理通过。

<a id="06-14"></a>

## 06.14 06A：Chaos Mesh 与故障工程

输入：00–05 健康、独立备份与可用观测；一次单一故障假设。

1. 为每个实验写预期影响、对象选择、持续时间、停止阈值和恢复动作；安装限制作用域的 Chaos Mesh。
2. 按 Pod→网络→压力→仓库/DNS/VPN→ESXi/存储域逐级执行，后者需先验证恢复材料和多数派余量。
3. 持续记录请求、数据、告警和资源；达到停止条件立即撤销注入，恢复后跑主线 smoke 并核对没有持续故障规则。

### 操作命令与目的

```bash
helm upgrade --install chaos-mesh "$LAB_CHAOS_CHART" -n chaos-mesh \
  --create-namespace --version "$LAB_CHAOS_VERSION" -f chaos-values.yaml --wait
kubectl -n lab-chaos apply --dry-run=server -f one-pod-failure.yaml
kubectl -n lab-chaos apply -f one-pod-failure.yaml
kubectl -n lab-chaos describe podchaos one-pod-failure
kubectl -n lab-chaos get pods -o wide
curl --max-time 5 "$LAB_CHAOS_TEST_URL"       # 与注入前持续请求结果比较
# 到达停止条件或完成观察后恢复，仅删除本次实验对象
kubectl -n lab-chaos delete podchaos one-pod-failure
kubectl -n lab-chaos rollout status deployment/chaos-target
```

之后再分别使用 NetworkChaos/StressChaos 等配置测试网络与资源压力。仓库/DNS/VPN/ESXi/存储域故障复用前面已经验证的单项动作，不把多个故障同时叠加到唯一数据副本。

### 配置示例

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata: {name: one-pod-failure, namespace: lab-chaos}
spec:
  action: pod-failure
  mode: one
  duration: 30s
  selector:
    namespaces: [lab-chaos]
    labelSelectors:
      app: chaos-target
```

内网环境要在 Chaos Mesh values 中指定已同步的 pause image；测试应用配置真实探针，否则“容器 Running”不一定代表仍能提供服务。

### 预期结果

只影响选中范围中的一个测试 Pod，HTTP/指标/告警显示与故障相符的变化；到期或中止后恢复。确认实验 CR 的清理已完成，数据与主线 smoke 正常，再开始下一类故障。

交付：`ops/06-advanced-security-dr/tests/failover/`、`ops/06-advanced-security-dr/tests/security/` 故障定义；实验假设与时间线。

检查与失败处理：约定故障均有实际结果和中止/恢复证据；失败不继续叠加新的故障域。

<a id="06-15"></a>

## 06.15 06E：滚动升级

输入：当前/目标相邻次版本的完整兼容矩阵、隔离预演和可读备份。

1. 核对 kubeadm/kubelet、etcd、CRI、CNI/CSI/Gateway/Operator 与目标版本；先在隔离小集群预演，再冻结主环境变更。
2. 按 kubeadm 官方流程先首个控制平面，检查 upgrade plan/apply 和健康，再逐个剩余控制平面、Worker；每次恢复 PDB/容量/多数派条件后继续。
3. storage 共置节点还需确认 Ceph 维护状态；系统/Ceph 升级另开顺序，不能同时变更多个关键层。
4. 回归网络、卷、数据库、消息、CI 和安全，记录 Memory QoS 等目标能力的实际状态；失败使用已验证恢复路线，不承诺任意次版本降级。

### 操作命令与目的

以下分“管理端”和“当前待升级节点”执行，先首台控制平面，再其他控制平面，最后 Worker：

```bash
# 管理端：确认备份、健康和 PDB 后，仅 drain 当前一个节点
kubectl get nodes
kubectl get pdb -A
kubectl drain "$LAB_UPGRADE_NODE" --ignore-daemonsets --timeout=300s

# 首台控制平面：安装锁定 kubeadm 包，查看并执行相邻次版本升级
sudo dnf install "$LAB_TARGET_KUBEADM_PACKAGE"
sudo kubeadm upgrade plan
sudo kubeadm upgrade apply "$LAB_TARGET_K8S_VERSION"
# 当前节点：随后升级 kubelet/kubectl 并恢复服务
sudo dnf install "$LAB_TARGET_KUBELET_PACKAGE" "$LAB_TARGET_KUBECTL_PACKAGE"
sudo systemctl daemon-reload
sudo systemctl restart kubelet

# 管理端：验证当前节点和集群健康后再放回调度
kubectl get --raw='/readyz?verbose'
kubectl get nodes -o wide
kubectl uncordon "$LAB_UPGRADE_NODE"
```

其他控制平面及 Worker 更新 kubeadm 后使用 `sudo kubeadm upgrade node`，不要再次执行全局 `upgrade apply`。每台恢复健康后才下一台；storage 共置节点同时检查 Ceph，系统/Ceph 升级另安排窗口。

### 配置示例

升级输入记录，属于项目计划，不是直接传给 kubeadm 的配置：

```yaml
source_kubernetes: <当前次版本及补丁>
target_kubernetes: <相邻次版本及补丁>
order:
  - first-control-plane
  - remaining-control-planes-one-at-a-time
  - workers-one-at-a-time
required_regressions: [api, cilium, dns, csi, database, messaging, ci, security]
recovery_materials: <已校验的独立备份引用>
```

### 预期结果

upgrade plan 接受目标组合；每个节点升级后恢复 Ready，etcd/API、CNI/CSI、业务和数据回归通过。版本只能按支持路线推进，失败暂停在当前节点并用验证过的恢复方案处理，不把直接安装旧 kubelet 当作完整降级。

交付：升级兼容矩阵、`ops/06-advanced-security-dr/README.md` 升级/恢复规程与前后回归。

检查与失败处理：一次安全可控的相邻次版本升级实际成功且业务数据通过；不跳次版本，不以组件版本输出替代整体回归。

<a id="06-16"></a>

## 06.16 06E：分层备份与实际数据搬运

输入：已验证的独立介质和秘密恢复方法。

1. 把基础配置/源码/仓库、State、PKI/身份、etcd、Ceph 管理信息、数据库/对象/PVC 分层登记备份目标、保留和恢复依赖。
2. 部署适配当前 CSI 的 Velero/数据搬运方案，确认实际数据离开源 Ceph；数据库采用协调后的原生一致性备份/WAL 等恢复材料。
3. 在不依赖原存储的隔离目标取回数据，测试介质不可达、密钥缺失和备份损坏；核对日志、对象/文件哈希与业务记录。

### 操作命令与目的

先按锁定版本安装 Velero、所需插件、node-agent 和匹配的数据搬运方案，并验证独立备份目的地可达：

```bash
velero backup-location get
velero backup create "$LAB_BACKUP_NAME" --include-namespaces lab-data \
  --storage-location independent --snapshot-move-data --wait
velero backup describe "$LAB_BACKUP_NAME" --details
kubectl -n velero get datauploads
aws --profile "$LAB_BACKUP_S3_PROFILE" --endpoint-url "$LAB_INDEPENDENT_S3_URL" \
  s3 ls "$LAB_BACKUP_BUCKET_URI"
# 在已准备恢复控制器、CRD/Operator、StorageClass 和同一备份位置的独立目标恢复
velero --kubecontext "$LAB_RESTORE_CONTEXT" restore create "$LAB_RESTORE_NAME" \
  --from-backup "$LAB_BACKUP_NAME" --namespace-mappings lab-data:lab-restore --wait
velero --kubecontext "$LAB_RESTORE_CONTEXT" restore describe "$LAB_RESTORE_NAME" --details
```

不支持 CSI 快照的对象使用选定文件系统备份路线，相关参数在实验时确定。数据库仍需原生备份/WAL 或一致性协调；不能把 Pod 卷可读当作事务一致性保证。

### 配置示例

BackupStorageLocation 指向真正独立于当前 Ceph/三宿主机故障域的对象存储，凭据和 CA 另外提供：

```yaml
apiVersion: velero.io/v1
kind: BackupStorageLocation
metadata: {name: independent, namespace: velero}
spec:
  provider: aws
  objectStorage:
    bucket: <独立备份桶>
  config:
    region: <实际region>
    s3ForcePathStyle: "true"
    s3Url: <独立S3端点>
```

### 预期结果

Backup 与实际 DataUpload 均完成，目的地中有可读备份；原存储不可用时，独立目标仍能恢复文件、对象与数据库记录并通过校验。只有快照元数据、PartiallyFailed 或缺少密钥不能作为容灾通过证据。

交付：备份计划、数据搬运配置、独立介质索引和恢复校验。

检查与失败处理：仅有 VolumeSnapshot 元数据不能通过；备份不可读或缺密钥时停止灾难注入。

<a id="06-17"></a>

## 06.17 06E：完整重建、冷启动与收尾

输入：已选择明确恢复路线与完整材料；保留原唯一副本。

1. 分别设计“原 etcd/身份恢复”和“新集群 + GitOps + 数据恢复”路线；每次只选一条执行，不混用旧对象与新对象身份。
2. 从集群外管理机按 DNS/CA/仓库→Linux/CRI→所选 K8s/Ceph→CSI/Operator→数据→应用顺序恢复；Jenkins/集群内 Runner 不作为前置。
3. 校验数据库事务、消息数量/重复、文件/对象哈希和七语言服务，记录检测、恢复启动、基础/业务可用及数据验证时间，计算真实 RTO/RPO。
4. 演练有序停机/冷启动，清理高级模块后核对 VM/盘/VIP/权限；用小规模新 VM 复现关键路径并逐项完成七阶段交付审计。

### 操作命令与目的

先从集群外恢复 DNS/CA/仓库和管理工具，再选择 A/B 中的一条路线。下面不是顺序全部执行的组合脚本。

**路线 A：按已选定快照恢复控制面状态。** 在隔离/停写的恢复环境为每个成员生成新的数据目录，保留旧数据目录；PKI、加密密钥和静态 Pod 挂载按恢复方案一起处理：

```bash
etcdutl snapshot status "$LAB_ETCD_SNAPSHOT" -w table
etcdutl snapshot restore "$LAB_ETCD_SNAPSHOT" \
  --name "$LAB_ETCD_MEMBER" --data-dir "$LAB_NEW_ETCD_DATA_DIR" \
  --initial-cluster "$LAB_ETCD_INITIAL_CLUSTER" \
  --initial-advertise-peer-urls "$LAB_ETCD_PEER_URL" \
  --initial-cluster-token "$LAB_ETCD_CLUSTER_TOKEN" \
  --bump-revision "$LAB_ETCD_REVISION_BUMP" --mark-compacted
```

三个成员使用同一快照，各自的成员名/目录/URL 不同；revision bump 和 compacted 按锁定 etcd 版本配置，使 Kubernetes watch/cache 重新建立。不能覆盖正在服务的 etcd 目录或让旧写入者重新加入恢复集群。

**路线 B：全新集群 + 声明式配置 + 数据恢复。** 复用 00/01 的主机与 kubeadm 路线，不导入旧 etcd 对象状态：

```bash
ansible-playbook -i "$LAB_RECOVERY_INVENTORY" "$LAB_NODE_PLAYBOOK" --limit "$LAB_RECOVERY_NODES"
# 首节点按 01 的 VIP/CNI/Join 顺序建立新集群，以下仅展示 init 入口
sudo kubeadm init --config "$LAB_RECOVERY_KUBEADM_CONFIG"
argocd app sync "$LAB_RECOVERY_PLATFORM_APP"
argocd app wait "$LAB_RECOVERY_PLATFORM_APP" --sync --health --timeout 600
velero --kubecontext "$LAB_RESTORE_CONTEXT" restore create "$LAB_RESTORE_NAME" \
  --from-backup "$LAB_BACKUP_NAME" --wait
```

两条路线在控制面恢复后都要完成 Ceph/CSI、Operator 和数据服务的恢复：若外部 Ceph 保留，则先检查 `ceph -s`、CSI 连接和原数据；若原存储丢失，先建立独立目标存储，再从备份恢复。不能把 etcd 快照当成 PV 或数据库数据备份。

**两条路线共同的数据与业务检查：**

```bash
kubectl --context="$LAB_RESTORE_CONTEXT" get nodes,pv
kubectl --context="$LAB_RESTORE_CONTEXT" get pods,pvc -A
psql 'service=lab-restore' -c 'SELECT count(*) FROM lab_probe;'
sha256sum -c "$LAB_RESTORED_CHECKSUM_FILE"
curl --fail "$LAB_RESTORED_APP_HEALTH_URL"
date -u '+%FT%TZ'                      # 记录实际恢复里程碑，不能代替业务校验
```

### 配置示例

执行记录的时间与数据字段，用真实时间点计算 RTO/RPO，不预填数值：

```yaml
recovery_route: <etcd-restore或fresh-cluster>
failure_started_at: null
recovery_started_at: null
infrastructure_ready_at: null
business_verified_at: null
latest_recovered_data_time: null
lost_records: null
duplicate_records: null
rto_seconds: null
rpo_seconds: null
```

### 预期结果

业务、数据库、消息、文件/对象和七语言样例都恢复正确，且有可计算的时间线与数据缺口。RTO 以约定故障起点到业务恢复为依据，RPO 依据真正恢复的数据时间点；最后验证有序停机/冷启动和临时资源清理，不能只凭界面在线宣布恢复完成。

交付：`ops/06-advanced-security-dr/tests/disaster-recovery/`；完整恢复 Runbook、RTO/RPO 与阶段/项目验收。

检查与失败处理：以业务与数据正确性作为恢复完成；任何未满足专题仍列未完成，不用“组件在线”替代完整项目验收。

## 命令参考

[KEDA Kafka Scaler](https://keda.sh/docs/2.21/scalers/apache-kafka/) · [Kueue Job 准入](https://kueue.sigs.k8s.io/docs/tasks/run/jobs/) · [CAPI 生成集群](https://cluster-api.sigs.k8s.io/clusterctl/commands/generate-cluster.html) · [Chaos Mesh Pod 故障](https://chaos-mesh.org/docs/next/simulate-pod-chaos-on-kubernetes/) · [etcd 恢复](https://etcd.io/docs/v3.6/op-guide/recovery/) · [Velero 数据搬运](https://velero.io/docs/v1.18/csi-snapshot-data-movement/)
