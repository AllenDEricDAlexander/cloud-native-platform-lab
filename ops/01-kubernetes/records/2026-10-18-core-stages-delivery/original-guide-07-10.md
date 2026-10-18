# 07–10 原教学片段归档

现行执行入口见各阶段独立手册；本文件保留原示意内容。

<a id="01-07"></a>

## 01.07 StatefulSet 与 DaemonSet

输入：不依赖 Ceph 的身份实验；明确数据暂不持久的限制。

1. 编写 Headless Service + StatefulSet，比较有序/并行策略、扩缩容和分区更新；删除单 Pod 后比较名称、序号、DNS 与 UID。
2. 用 DaemonSet 记录各节点覆盖，测试 nodeSelector/污点兼容；升级一个可观察版本并回滚，比较 ControllerRevision 和实际日志。
3. 为 03 的 PVC 数据实验预留独立变体，明确本阶段 emptyDir/无卷结果不证明数据持久化。

### 操作命令与目的

```bash
kubectl -n lab-core apply -f statefulset-demo.yaml
kubectl -n lab-core get statefulset,pod,service -o wide
kubectl -n lab-core get pod state-demo-0 -o jsonpath='{.metadata.uid}'
kubectl -n lab-core delete pod state-demo-0      # 观察名称不变而 UID 重建
kubectl -n lab-core scale statefulset/state-demo --replicas=3
kubectl -n lab-core apply -f daemonset-demo.yaml
kubectl -n lab-core set image daemonset/node-demo agent="$LAB_IMAGE_V2"
kubectl -n lab-core rollout status daemonset/node-demo
kubectl -n lab-core rollout undo daemonset/node-demo
```

### 配置示例

StatefulSet 与 Headless Service；本阶段不加 PVC，后续再增加持久化变体：

```yaml
apiVersion: v1
kind: Service
metadata: {name: state-headless, namespace: lab-core}
spec:
  clusterIP: None
  selector: {app: state-demo}
  ports: [{name: http, port: 8080, targetPort: 8080}]
---
apiVersion: apps/v1
kind: StatefulSet
metadata: {name: state-demo, namespace: lab-core}
spec:
  serviceName: state-headless
  replicas: 2
  selector:
    matchLabels: {app: state-demo}
  template:
    metadata:
      labels: {app: state-demo}
    spec:
      containers:
        - name: app
          image: "<内网应用镜像>"
          ports: [{containerPort: 8080}]
```

### 预期结果

Pod 重建后名称/序号与 Service DNS 稳定，UID 改变；这不证明本地数据持久化。DaemonSet 在符合节点约束的每个节点各有一个 Pod，更新/回退后实际镜像和 ControllerRevision 对应。节点污点不满足时缺少 Pod 应能从事件解释。

交付：`ops/01-kubernetes/core-resources/statefulset/`、`daemonset/`；身份和覆盖矩阵。

检查与失败处理：StatefulSet 稳定身份、DaemonSet 更新/回滚得到验证；失败检查更新策略和节点约束，保留原 ControllerRevision。

<a id="01-08"></a>

## 01.08 删除传播、垃圾回收与 Finalizer

输入：只有实验资源的隔离命名空间。

1. 为同一小型父子资源分别执行 foreground/background/orphan 删除，保存父子 UID、ownerReferences 和删除时间；Orphan 后观察子对象继续存在。
2. 创建带实验 Finalizer 的对象，删除后观察 deletionTimestamp；按设计清理外部模拟资源再移除 Finalizer，不把强删所有 Finalizer 当成通用修复。
3. 核对垃圾回收后的孤儿 Service/ConfigMap/PVC，区别 Kubernetes 对象删除和外部数据释放。

### 操作命令与目的

下面三种传播策略分别在重新创建的实验对象上运行：

```bash
kubectl -n lab-core apply -f gc-demo.yaml
kubectl -n lab-core delete deployment/gc-demo --cascade=foreground
# 重建后比较后台删除
kubectl -n lab-core apply -f gc-demo.yaml
kubectl -n lab-core delete deployment/gc-demo --cascade=background
# 再重建后比较孤儿保留
kubectl -n lab-core apply -f gc-demo.yaml
kubectl -n lab-core delete deployment/gc-demo --cascade=orphan
kubectl -n lab-core get rs,pods -o yaml          # 比较 ownerReferences
kubectl -n lab-core apply -f finalizer-demo.yaml
kubectl -n lab-core delete configmap/finalizer-demo --wait=false
kubectl -n lab-core get configmap/finalizer-demo -o yaml
```

### 配置示例

专用 ConfigMap 模拟 Finalizer 阻塞；它没有生产数据或真实控制器副作用：

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: finalizer-demo
  namespace: lab-core
  finalizers: [lab.egon.top/cleanup]
data:
  external-resource: simulated
```

### 预期结果

foreground 等待依赖删除，background 异步清理，orphan 保留子对象；Finalizer 对象出现 deletionTimestamp 并等待清理。在模拟外部资源已经清理、且对象仅含该实验 Finalizer 后，可用 `kubectl patch configmap/finalizer-demo -n lab-core --type=merge -p '{"metadata":{"finalizers":[]}}'` 完成演示。正常控制器的 Finalizer 应由其流程解除。

交付：`ops/01-kubernetes/examples/garbage-collection/`；删除前后资源关系及清理检查。

检查与失败处理：三种传播行为和 Finalizer 阻塞/完成均可解释，清理完成后无本次遗留对象。

<a id="01-09"></a>

## 01.09 Job、CronJob 与基础 HPA

输入：独立实验资源；HPA 需要实际可用的资源指标 API。

1. 编写成功/失败 Job，指定 backoffLimit、activeDeadlineSeconds 和完成条件；对照串行/并行及重试，任务写入带业务键避免重复副作用。
2. 配置 CronJob 的 schedule/timeZone/concurrencyPolicy/deadline/history，测试重叠、暂停和恢复；查看实际创建 Job 的时刻和去重结果。
3. 部署所选资源指标组件并验证 API，再给应用设置 requests 与 HPA；施加受控负载，记录扩缩容、稳定窗口和资源限制。

### 操作命令与目的

```bash
kubectl -n lab-core apply -f job-demo.yaml -f cronjob-demo.yaml
kubectl -n lab-core wait --for=condition=complete job/job-demo --timeout=120s
kubectl -n lab-core logs job/job-demo
kubectl -n lab-core create job cronjob-manual --from=cronjob/cron-demo
kubectl -n lab-core get jobs,cronjobs
kubectl -n lab-core patch cronjob/cron-demo --type=merge -p '{"spec":{"suspend":true}}'
kubectl top pods -n lab-core                      # 先确认指标 API 可用
kubectl -n lab-core apply -f hpa-demo.yaml
kubectl -n lab-core get hpa -w                    # 配合受控负载观察扩缩容
```

### 配置示例

CronJob 的执行策略：

```yaml
apiVersion: batch/v1
kind: CronJob
metadata: {name: cron-demo, namespace: lab-core}
spec:
  schedule: "*/2 * * * *"
  timeZone: Asia/Shanghai
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 60
  jobTemplate:
    spec:
      backoffLimit: 2
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: job
              image: "<内网诊断镜像>"
              command: [sh, -c, "date; sleep 20"]
```

HPA 的 `spec` 片段，CPU 利用率依赖目标容器配置 requests：

```yaml
scaleTargetRef: {apiVersion: apps/v1, kind: Deployment, name: controller-demo}
minReplicas: 1
maxReplicas: 4
metrics:
  - type: Resource
    resource:
      name: cpu
      target: {type: Utilization, averageUtilization: 60}
```

### 预期结果

正常 Job 为 Complete，失败变体按 backoffLimit 重试后失败；CronJob 遵守时区/并发/暂停约定。HPA 的 TARGETS 应为有效指标，负载上升后扩容、负载恢复后按窗口缩容；`<unknown>` 不是通过结果。

交付：`ops/01-kubernetes/core-resources/jobs/`、`autoscaling/`；执行次数和副本曲线。

检查与失败处理：可区分调度、重试和业务幂等；无指标时不把 HPA YAML 创建成功算扩缩容通过。

<a id="01-10"></a>

## 01.10 配置、身份与阶段交接

输入：核心资源实验完成，具备受控管理身份。

1. 对比 ConfigMap/Secret 以环境变量与卷注入后的更新行为，说明 subPath 等限制；以实际应用读取结果验证，不在日志输出秘密。
2. 创建最小 RBAC/ServiceAccount 与镜像拉取身份，通过 `kubectl auth can-i` 和实际允许/拒绝请求检查，区分身份认证与资源授权。
3. 执行阶段 smoke、HA 和资源实验回归，归档可复用清单、测试、备份与未完成项；撤销临时管理员和故障资源。

### 操作命令与目的

```bash
kubectl -n lab-core apply -f config-demo.yaml -f config-consumer.yaml
kubectl -n lab-core exec deployment/config-consumer -- cat /etc/demo/config.yaml
kubectl -n lab-core apply -f config-demo-v2.yaml    # 对比卷更新与环境变量不自动更新
kubectl -n lab-core apply -f reader-rbac.yaml
kubectl auth can-i get pods -n lab-core --as=system:serviceaccount:lab-core:reader
kubectl auth can-i delete pods -n lab-core --as=system:serviceaccount:lab-core:reader
kubectl -n lab-core get pods --as=system:serviceaccount:lab-core:reader
kubectl get nodes
```

### 配置示例

读取 Pod 的 Role；`reader-rbac.yaml` 还应包含对应 ServiceAccount 与 RoleBinding：

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata: {name: pod-reader, namespace: lab-core}
rules:
  - apiGroups: [""]
    resources: [pods]
    verbs: [get, list, watch]
```

配置消费者的 PodSpec 片段，用同一 ConfigMap 对比两种注入方式：

```yaml
containers:
  - name: app
    image: "<内网诊断镜像>"
    envFrom: [{configMapRef: {name: config-demo}}]
    volumeMounts: [{name: config, mountPath: /etc/demo, readOnly: true}]
volumes:
  - name: config
    configMap: {name: config-demo}
```

### 预期结果

非 subPath 的配置卷最终更新，环境变量需重新创建容器才能改变；记录传播延迟。reader 可以读取 Pod 而不能删除，实际请求与 `can-i` 一致。Secret 用相同注入方式测试，但只检查可用性和元数据，不输出秘密正文。最后集群恢复 10 个 Ready。

交付：`ops/01-kubernetes/core-resources/config/`、`rbac/`；阶段 acceptance 与清理结果。

检查与失败处理：全部核心资源要求有证据，十节点健康并有恢复入口；保留 03 持久化衔接，不误记为未部署的能力已通过。

