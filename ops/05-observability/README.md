# Phase 05 实验操作手册

配合 [阶段正文](../../plan/05-observability.md) 按原专题执行；所有动作当前未执行，配置路径是实施交付位置。每次先确认输入和作用域，再写配置、执行、检查正常与失败路径、恢复并归档。报告放 `ops/05-observability/records/<执行批次>/`。

<a id="zabbix-design"></a>

## Zabbix VM 监控部署方案（2026-10-20，待实施）

按本轮要求复用现有 VM，先把监控用起来。Zabbix 与构建工具共用 build01，不新增 VM、IP 或数据盘；当前仅调整方案，尚未编写部署剧本或执行安装。主机信息来自现有台账与执行记录，安装前检查实际可用内存、磁盘空间和端口即可。

### 部署位置与组件

| 项目 | 方案 |
| --- | --- |
| 部署主机 | 现有 build01，192.168.9.160，4 vCPU / 8 GiB；[台账](../inventory/hosts.yaml)已有登记，[构建客户端基线记录](../00-preparation/records/2026-10-14/evidence/00.10.04-build01-base.txt)已有初始化执行证据 |
| 共用方式 | 保留现有构建工具和文件，增加 Zabbix Server、PostgreSQL、Nginx/PHP-FPM；使用 RPM + systemd，不重新执行服务 VM 初始化或卸载原软件 |
| 数据 | PostgreSQL 使用现有文件系统下的专用目录，优先采用发行版默认 /var/lib/pgsql；不格式化、不重新挂盘，目录已存在时先检查并保留原数据 |
| 页面 | 使用现有域名 https://build01.svc.internal.egon.top:8443，沿用内部 CA；不增加 DNS 记录，安装前确认端口可用 |
| 版本 | Zabbix 7.0 LTS 的官方 Rocky 10 软件包，精确补丁版本与物料在实施时登记版本锁；数据库/PHP 使用兼容的发行版软件包 |
| 资源起步 | 沿用现有 4 核 8 GiB，普通指标 60 秒一次，History 7 天、数值 Trends 90 天；按实际磁盘增长再调整 |
| 阶段归属 | 05.01.04 集群外探测 + 05.03.02 基础设施监控，提前实施；其他日志、追踪、Prometheus 实验按原计划继续 |

build01 是现有集群外构建/验收机，Phase 04 持续构建尚未开始，适合先共用。后续构建与监控会共享 CPU、内存和磁盘；lab 接受这种影响，资源紧张时先减少并行构建或采集量。该方案不依赖 Kubernetes/Ceph，也不要求另建监控高可用、独立探测设备或专用存储。

### 首期监控范围

| 主机 | 地址（192.168.9.0/24） | 采集方式 |
| --- | --- | --- |
| cp01–cp03 | .101–.103 | Agent 2 |
| infra01–infra02 | .104–.105 | Agent 2 |
| storage01–storage03 | .106–.108 | Agent 2，先采集 OS 指标 |
| worker01–worker02 | .109–.110 | Agent 2 |
| dns / harbor / gitlab / nexus / backup | .11 / .12 / .13 / .14 / .16 | Agent 2 |
| build01 | .160 | Agent 2，同时承载 Zabbix Server/Web/数据库和自监控 |

共 **16 台现有 Rocky VM**，build01 只登记一次。OpenWrt .10 先检查连通性和代理端口；vCenter/ESXi 的宿主机、Datastore 等指标后续有需要再接。关机模板和尚未创建的主机不纳入安装范围。

首期使用官方 Linux 主动采集模板，展示 CPU、Load、可用内存、文件系统容量/inode、虚拟磁盘 I/O、网卡流量、运行时间和重启状态。过滤临时容器挂载与 veth 等接口，关键数据挂载点单独检查；按主机角色补充 kubelet/containerd、DNS、仓库和备份等实际服务状态。配上主机/Agent 无数据、磁盘不足、持续高负载和服务异常告警，先在 Zabbix 页面查看问题与恢复，外部通知按需要再接。

### Ansible 怎么落地

沿用项目现有的 Playbook + Role 结构，使用 Phase 00 已生成的 Inventory 和 SSH 配置；部署目标直接选 build01，Agent 目标为 `k8s_nodes:bootstrap_services:lab_clients` 中的 Rocky 主机，不另建一套主机清单。

| 计划交付位置（仓库根目录起算） | 用途 |
| --- | --- |
| `ops/05-observability/ansible/playbooks/zabbix.yml` | 一次编排基础检查、build01 上的 Server/数据库/Web、API 主机配置和 Agent 安装 |
| `ops/05-observability/ansible/roles/zabbix_server/` | 安装锁定版本，配置专用数据库、Web、必要的 SELinux/防火墙规则 |
| `ops/05-observability/ansible/roles/zabbix_agent/` | 安装 Agent 2、配置主动采集和 PSK、按配置变更触发重启 |
| `ops/05-observability/ansible/playbooks/zabbix-verify.yml` | 检查页面/API、主机覆盖和核心指标是否更新 |
| `ops/05-observability/records/<批次>/` | 保存执行输出和验收结果 |

以上文件尚未创建。API 配置直接放在主剧本的管理端任务中，用 ansible.builtin.uri 创建或更新主机组、主机、模板和宏；不再增加单独的 API 角色或额外 Ansible 集合。

执行顺序：

1. 检查 build01 的可用内存、磁盘、端口和已有数据库配置；只安装监控所需组件，保留构建机现有软件源、网络、防火墙和工作目录。
2. 在 build01 部署 PostgreSQL、Zabbix Server 和 Web；仅对确认为空的新库导入初始 schema，重跑复用数据库与口令。
3. 从现有 Inventory 生成主机组/主机，在服务端先配好主动模板与每机 PSK，再分批安装 Agent；Host 字段与 Agent Hostname 使用台账 FQDN，build01 同时接入自监控。
4. 核对页面、16 台目标的实际接入结果和数据新鲜度，再重跑一次检查幂等；故障恢复测试由操作者在选定测试主机上进行。

保留现有 SELinux Enforcing、firewalld 和内部 CA。Agent 主动连接 build01 的 10051/TCP，使用每机 PSK；不开放各主机的 10050，数据库仅本机监听，Web 8443 限制现有管理来源。秘密放管理端受控目录，敏感任务 no_log，重跑不重置秘密或覆盖原数据库。不会重启 kubelet/containerd、业务服务或清理构建机文件。

### 首期验收

- Zabbix 页面可访问，Server、数据库、Web 和 Agent 状态正常。
- 16 台目标逐台核对，CPU、内存、磁盘、网络等核心指标持续更新；连接失败的主机明确列出。
- 操作者短暂停止一台测试主机的 Agent 后能看到异常，恢复后能看到恢复事件。
- 相同输入重复运行，不重复创建主机、不重建数据库、不无故重启服务，原构建工具与文件保留。

首期先完成这些检查。外部通知、vSphere 指标、数据库备份与恢复演练作为后续补充，不作为先看 VM 指标的前置条件。当前仅完成方案调整，运行结果在实施后据实记录。

## 命令与示例的使用方式

以下写明实验时大概要执行的命令、目的和预期变化，不是现在就能整段运行的一键脚本。`LAB_*`、`<...>`、版本、资源名和文件路径在开始实验时按实际环境填写；文件须先根据示例补齐，凭据通过受控配置注入。YAML 标为“片段”时应合并到完整对象，不能单独 apply；示例值不是性能或容量承诺。

`kubectl` 在选定集群的管理终端执行，`kubeadm`/主机命令在文中指定节点执行。每次变更前用 `kubectl config current-context` 核对目标。`--dry-run=server` 用于已经存在的集群/API；CRD 尚未安装时先安装匹配版本。`kubectl diff` 返回 1 通常表示有差异，应阅读差异后再 apply。故障、恢复和清理命令分段执行并观察结果，当前不执行任何部署。

测试 Namespace、样例应用、Chart/CRD 和引用文件应先创建到就绪；已由 GitOps 托管的对象通过仓库变更和同步更新，文中的直接 patch/scale/apply 用于隔离实验对象或受控诊断。

<a id="05-01"></a>

## 05.01 遥测契约与资源预算

输入：完整遥测需 04 样例服务/版本标识及最小指标源；05.01.04 的先行 Zabbix 复用 build01、现有管理网络、DNS/CA 和文件系统，见 [部署方案](#zabbix-design)。

1. 规定 service.name、namespace、environment、cluster、version 和 trace/span 关联字段；为七语言分别定义日志格式和敏感字段处理。
2. 先为指标序列、日志量、Trace/Profile 采样、Retention、对象存储和压测制定上限，写出估算输入；不全量双写两个日志后端。
3. 按先行方案在 build01 部署 HTTP/DNS/API/仓库探测，先验证单目标中断/恢复；整集群故障和独立探测按后续需要补充。

### 操作命令与目的

```bash
# 从集群外管理机记录解析、HTTPS 与响应时间
getent hosts "$LAB_APP_HOST"
curl --cacert "$LAB_CA_FILE" --max-time 5 -o /dev/null \
  -w 'status=%{http_code} time=%{time_total}\n' "$LAB_APP_HEALTH_URL"
# 发起一个带可追溯 ID 的测试请求，随后查询日志
curl -H "X-Request-ID: $LAB_REQUEST_ID" "$LAB_REFERENCE_URL"
kubectl -n lab-observability logs deployment/reference --since=5m
kubectl -n lab-observability get pods --show-labels
```

### 配置示例

应用 Pod 的环境变量片段；SDK/自动插桩先按语言接入，再使用这些配置：

```yaml
env:
  - name: OTEL_SERVICE_NAME
    value: reference-java
  - name: OTEL_RESOURCE_ATTRIBUTES
    value: deployment.environment.name=dev,k8s.cluster.name=lab-primary,service.version=v1
  - name: OTEL_EXPORTER_OTLP_ENDPOINT
    value: https://otel-collector.monitoring.svc:4318
```

各语言日志统一包含时间、级别、服务、版本、环境、request_id，以及存在时的 trace_id/span_id；没有当前 Trace 时不要编造 ID。

### 预期结果

同一请求能关联到服务与版本，外部探测输出实际状态码/延迟。后续集群或观测后端失效时，集群外探测仍能记录失败窗口。仅设置 OTEL 环境变量不会自动让未接入 SDK 的程序产生遥测。

交付：`ops/05-observability/observability/` 契约/预算；集群外探测配置。

检查与失败处理：同一请求与版本可识别，缺失数据和采集失败有独立信号；前置预算不足先缩小采样场景。

<a id="05-02"></a>

## 05.02 指标、Dashboard 与告警

输入：可用持久存储、最小权限采集和基本 DNS/TLS。

1. 扩展 04 的最小指标源为版本化 Prometheus/Grafana/Alertmanager 部署，避免两套重复告警；配置持久化、抓取间隔、保留与资源限制。
2. 接入节点/集群状态与应用 ServiceMonitor/PodMonitor，编写 recording/alert rules；导入 Dashboard 并核对标签/查询。
3. 触发可控告警，验证分组、抑制、恢复通知及路由；测试一个观测组件不可用，区分业务健康与监控失明。

### 操作命令与目的

沿用或迁移 04 的最小指标源；迁移时确认抓取、规则和数据保留，避免重复告警：

```bash
helm upgrade --install "$LAB_MONITORING_RELEASE" "$LAB_MONITORING_CHART" -n monitoring \
  --create-namespace --version "$LAB_MONITORING_VERSION" -f monitoring-values.yaml --wait
promtool check rules prometheus-rules.yaml        # 校验原生规则文件
amtool check-config alertmanager.yaml             # 校验告警路由配置
kubectl -n monitoring apply -f service-monitors.yaml -f prometheus-rules-cr.yaml
curl --get "$LAB_PROMETHEUS_URL/api/v1/query" --data-urlencode 'query=up'
amtool --alertmanager.url "$LAB_ALERTMANAGER_URL" alert query
```

随后仅停止测试 exporter/测试服务，等待规则触发，再恢复并检查 resolved。Grafana Dashboard 从版本化 JSON 导入，数据源身份由受控配置提供。

### 配置示例

`prometheus-rules.yaml` 的原生规则；若使用 Operator，把 `groups` 放入 `PrometheusRule.spec` 再 apply，不能把 CRD 包装直接传给 promtool：

```yaml
groups:
  - name: lab-reference
    rules:
      - alert: LabReferenceTargetDown
        expr: up{job="reference"} == 0
        for: 1m
        labels: {severity: warning}
        annotations:
          summary: Reference scrape target is down
```

### 预期结果

规则/路由校验通过，目标正常时 up=1，测试目标停止后 up=0 并出现告警，恢复后告警解除。目标被完全移出抓取配置时需另测 absent/缺失数据规则，不能用这个 up=0 规则覆盖所有监控失明情况。

交付：`ops/05-observability/observability/{prometheus,grafana,alertmanager}/`；告警触发/恢复记录。

检查与失败处理：面板与实际请求/资源匹配，告警按约定投递；未真正发送的通知不能计为链路通过。

<a id="05-03"></a>

## 05.03 覆盖基础设施、Ceph 与中间件

输入：Rocky VM 先行监控沿用现有台账/Inventory；Ceph、中间件与 vSphere 扩展分别需要已部署服务和受限指标身份。

1. 先按 [Zabbix 方案](#zabbix-design) 接入 Rocky VM 操作系统与关键服务，再接入 Ceph 容量/PG/I/O、vSphere/网络设备、数据库、消息和仓库/CI 指标，逐源核对权限与目标健康。以下 Ceph/中间件命令只在相应前置就绪后执行。
2. 制造受控 Ceph I/O/容量趋势及 Kafka 消费积压，观察具体告警和恢复；数据库连接数、Redis 内存、RabbitMQ/NATS backlog 配同样可解释规则。
3. 保存 Dashboard 到版本库，标注缺失 exporter、许可证限制和采集盲区；不可采集的设备不伪造曲线。

### 操作命令与目的

```bash
ceph mgr module enable prometheus
curl --fail "$LAB_CEPH_METRICS_URL/metrics"
kubectl -n monitoring apply -f middleware-service-monitors.yaml
"$LAB_KAFKA_BIN/kafka-consumer-groups.sh" --bootstrap-server "$LAB_KAFKA_BOOTSTRAP" \
  --command-config "$LAB_KAFKA_CLIENT_CONFIG" --describe --group lab-observability
# 暂停专用测试消费者以产生 Lag，再恢复到原副本数
kubectl -n lab-observability scale deployment/lab-consumer --replicas=0
kubectl -n lab-observability scale deployment/lab-consumer --replicas="$LAB_CONSUMER_REPLICAS"
# 在临时 PVC 的普通文件上施加小规模 I/O；不对 OSD 或裸设备运行
fio --name=ceph-io --filename=/data/lab-observability/fio.bin --size=128M \
  --rw=randread --bs=4k --iodepth=4 --runtime=30 --time_based --direct=1
```

暂停和恢复之间保留产生积压/观察告警的窗口。Ceph I/O 告警使用适当实验阈值；有限压力不保证必然触发生产阈值。

### 配置示例

ServiceMonitor 选择已声明 metrics 端口的 Service；监控实例的 selector/namespace 范围需要匹配：

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: reference
  namespace: monitoring
  labels: {release: lab-monitoring}
spec:
  namespaceSelector:
    matchNames: [lab-observability]
  selector:
    matchLabels: {app: reference}
  endpoints:
    - port: metrics
      interval: 15s
```

### 预期结果

Ceph、基础设施和中间件各有可解释指标；停止消费者后 Lag 增长，恢复后下降；I/O 指标与受控压力同步变化。告警能定位具体集群/服务/实例，缺失 exporter 或权限时明确显示采集失败。

交付：组件 Dashboard、Exporter/抓取配置、Ceph I/O 和 Kafka Lag 用例。

检查与失败处理：每个核心组件有有效指标和至少关键告警验证；故障测试遵守存储停止阈值。

<a id="05-04"></a>

## 05.04 OTel 与跨语言上下文

输入：可调用的多语言同步/异步参考链路。

1. 部署 Collector 接收/处理/导出层，配置 TLS/认证、batch、memory limit、重试和队列，明确数据丢弃条件。
2. 逐语言接入可用 SDK/自动插桩，传递标准 trace context；串接 HTTP/gRPC 和消息生产/消费，日志输出 trace_id/span_id。
3. 比较采样比例、属性基数和后端中断时的缓冲/重试，记录负载和丢弃计数；无 SDK 支持的部分如实说明手工边界。

### 操作命令与目的

```bash
otelcol-contrib validate --config=otel-collector.yaml  # 用锁定发行版校验配置
kubectl -n monitoring apply -f otel-collector-resources.yaml
kubectl -n monitoring rollout status deployment/otel-collector
curl -H "traceparent: $LAB_TEST_TRACEPARENT" "$LAB_REFERENCE_URL"
kubectl -n monitoring logs deployment/otel-collector --since=5m
curl --fail -H 'Accept: application/json' "$LAB_TEMPO_URL/api/traces/$LAB_TRACE_ID"
```

`LAB_TEST_TRACEPARENT` 必须符合 W3C 格式，或者让第一个已插桩服务自动生成。测试调用链至少包含两种语言，并增加消息生产/消费；逐跳检查同一 Trace/关联关系。

### 配置示例

Collector 的 traces 管道示例；TLS 文件由 Secret 挂载，后端地址按实际部署替换。日志/指标另建对应 pipeline 和支持它们的 exporter，不能发给只接收 Trace 的 Tempo：

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
        tls:
          cert_file: /etc/otel/tls/tls.crt
          key_file: /etc/otel/tls/tls.key
processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 128
  batch: {}
exporters:
  otlp/tempo:
    endpoint: tempo-distributor.monitoring.svc:4317
    tls:
      ca_file: /etc/otel/ca.crt
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp/tempo]
```

### 预期结果

Collector 配置有效且无持续导出错误，真实请求可查询到跨服务 spans，日志 trace_id 可回到该 Trace。后端中断时观察队列、重试和丢弃计数；采样、缓存和故障恢复效果来自实际测试，不把所有请求都假定完整保留。

交付：`ops/05-observability/observability/otel/`；七语言插桩配置和调用拓扑。

检查与失败处理：实际请求能跨服务和消息关联，不能只看到某一个入口 span；敏感 payload 不进入常规遥测。

<a id="05-05"></a>

## 05.05 ELK 日志链路

输入：03 的 ECK 及受控小规模存储预算。

1. 复用 ECK 管理的 Elasticsearch，配置索引/容量与 Kibana；Fluent Bit 采集节点容器日志并补 Kubernetes 元数据。
2. Logstash 解析约定的结构化/多行日志，配置缓冲和失败索引；分别测试错误格式、背压、后端中断和恢复。
3. 建立索引模板、字段类型、Retention/生命周期和 Kibana 查询，按 trace_id 查找同一次故障；观察过高基数与索引增长。

### 操作命令与目的

```bash
kubectl -n logging apply -f elasticsearch.yaml -f kibana.yaml
helm upgrade --install fluent-bit "$LAB_FLUENTBIT_CHART" -n logging \
  --version "$LAB_FLUENTBIT_VERSION" -f fluent-bit-values.yaml --wait
fluent-bit --dry-run -c fluent-bit.yaml
logstash --config.test_and_exit -f logstash.conf
curl --config "$LAB_ES_CURL_CONFIG" -H 'Content-Type: application/json' \
  -X PUT "$LAB_ES_URL/_index_template/lab" --data @index-template.json
curl --config "$LAB_ES_CURL_CONFIG" -H 'Content-Type: application/json' \
  -X POST "$LAB_ES_URL/lab-*/_search" --data @trace-query.json
kubectl -n logging logs deployment/logstash --since=5m
```

复用 03 的 ECK 实例/CR，清单按其真实 namespace 合并。Fluent Bit→Logstash 的传输格式、TLS 和缓冲两端一致，再测试错误 JSON、多行堆栈与背压。

### 配置示例

Elasticsearch 索引模板和按真实 Trace 查询的结构：

```json
{
  "index_patterns": ["lab-*"],
  "template": {
    "mappings": {
      "properties": {
        "@timestamp": {"type": "date"},
        "trace_id": {"type": "keyword"},
        "service_name": {"type": "keyword"},
        "message": {"type": "text"}
      }
    }
  }
}
```

```json
{"query": {"term": {"trace_id": "<真实trace_id>"}}}
```

Retention/索引生命周期通过单独的 ILM/适用数据流策略配置，不能从索引模板存在推断已启用自动清理。

### 预期结果

结构化字段按指定类型入索引，Kibana/搜索 API 可查到同一 Trace 的日志；错误解析保留在可排查路径。日志源数、采集数、解析失败与后端写入数可对照，后端恢复后不出现无说明的数据缺口。

交付：`ops/05-observability/observability/elk/`；查询模板、解析样例和生命周期配置。

检查与失败处理：日志可检索、故障数据可追溯，解析失败不会静默丢失；超预算先限速/降采样，不无限扩索引。

<a id="05-06"></a>

## 05.06 Loki、Tempo 与 Pyroscope

输入：对象存储已验证、客户端插桩和容量预算。

1. 配置 Loki 的受控标签、保留与查询，Tempo 的 Trace 存储和 Grafana 关联；将 trace_id 放检索字段而非默认高基数 Loki 标签。
2. 接入 Pyroscope，先做 Java 的可控 CPU/分配热点实验；从实际火焰图定位方法，再验证修正或负载变化。
3. 用相同样本、采集时长和请求负载比较 ELK/Loki 的写入、查询、资源和存储；模拟对象存储/后端中断，观察重试/丢弃。

### 操作命令与目的

```bash
helm upgrade --install loki "$LAB_LOKI_CHART" -n logging \
  --version "$LAB_LOKI_VERSION" -f loki-values.yaml --wait
helm upgrade --install tempo "$LAB_TEMPO_CHART" -n monitoring \
  --version "$LAB_TEMPO_VERSION" -f tempo-values.yaml --wait
helm upgrade --install pyroscope "$LAB_PYROSCOPE_CHART" -n monitoring \
  --version "$LAB_PYROSCOPE_VERSION" -f pyroscope-values.yaml --wait
curl --get "$LAB_LOKI_URL/loki/api/v1/query_range" \
  --data-urlencode "query={service_name=\"reference-java\"} | json | trace_id=\"$LAB_TRACE_ID\""
curl --fail -H 'Accept: application/json' "$LAB_TEMPO_URL/api/traces/$LAB_TRACE_ID"
# Java 容器内：JFR 作为局部剖析对照，同时观察 Pyroscope 的持续采样
jcmd "$LAB_JAVA_PID" JFR.start name=lab settings=profile duration=30s filename="$LAB_JFR_FILE"
jfr summary "$LAB_JFR_FILE"                    # 等待录制完成后再读取
```

### 配置示例

Java Pyroscope Agent 接入的环境变量片段；Jar 路径、启动参数和所选 Agent 版本先匹配：

```yaml
env:
  - name: JAVA_TOOL_OPTIONS
    value: -javaagent:/opt/pyroscope/pyroscope.jar
  - name: PYROSCOPE_APPLICATION_NAME
    value: reference-java
  - name: PYROSCOPE_SERVER_ADDRESS
    value: https://pyroscope.k8s.internal.egon.top
```

Loki 用 service/environment 等低基数标签定位，trace_id 放日志字段/结构化元数据。分别保存 ELK/Loki 的相同数据集、采集窗口和资源上限。

### 预期结果

日志能按 Trace 找到，Tempo 返回对应 spans，Pyroscope 按 application name 和时段可看到真实热点；JFR 与持续剖析结论相互印证。比较 ELK/Loki 时给出查询耗时、写入量、CPU/内存和占用，不用不同负载下的结果直接排名。

交付：`ops/05-observability/observability/{loki,tempo,pyroscope}/`；ELK/Loki 比较与 Java Profiling 报告。

检查与失败处理：Logs/Metrics/Traces/Profiles 有可用关联入口，比较有共同负载和版本；未测维度留空。

<a id="05-07"></a>

## 05.07 SLI/SLO、错误预算与灰度分析

输入：04 已通过的真实指标灰度与完整采集。

1. 为参考业务定义成功率/延迟 SLI，明确窗口、排除规则、目标与错误预算；查询无数据应显式处理。
2. 编写错误预算消耗与燃尽告警，用正常、短尖峰和持续异常数据验证；阈值来自约定与测量，不编造生产 SLO。
3. 把 SLO 查询接入既有 Rollouts AnalysisTemplate，重新测试放行/中止/回退；关联部署版本、告警、日志、Trace 和恢复时间线。

### 操作命令与目的

```bash
promtool check rules slo-rules.yaml
promtool test rules slo-rule-tests.yaml             # 用构造时序先验证规则逻辑
kubectl -n monitoring apply -f slo-prometheus-rule.yaml
curl --get "$LAB_PROMETHEUS_URL/api/v1/query" \
  --data-urlencode 'query=lab:http_error_ratio:5m'
kubectl -n lab-apps apply -f slo-analysis-template.yaml
kubectl -n lab-apps get analysisruns
kubectl argo rollouts get rollout demo -n lab-apps --watch
```

构造时序只验证查询/规则逻辑；真实验收仍需对参考业务施加正常、短暂尖峰、持续失败和指标缺失四类场景。

### 配置示例

原生 Prometheus 规则片段；示例 1%/2 分钟用于实验，实际 SLO、窗口和燃尽率另按业务约定：

```yaml
groups:
  - name: lab-slo
    rules:
      - record: lab:http_error_ratio:5m
        expr: |
          (sum(rate(http_requests_total{job="reference",status=~"5.."}[5m])) or vector(0))
          /
          sum(rate(http_requests_total{job="reference"}[5m]))
      - alert: LabErrorBudgetBurn
        expr: lab:http_error_ratio:5m > 0.01
        for: 2m
        labels: {severity: warning}
```

### 预期结果

查询对应真实请求的错误率，规则按约定窗口触发/恢复，Rollouts 的放行/中止可回溯到同一版本与时间线。无请求、缺失序列、NaN 不当作“零错误”；多窗口燃尽规则在实验时补充相应测试。

交付：SLO/SLI 文档、查询/告警规则、发布分析更新与失败样例。

检查与失败处理：自动发布决策能追溯真实指标，指标失明不会假通过；保留 04 已知可用分析配置以便回退。

<a id="05-08"></a>

## 05.08 压力、容量与成本

输入：固定硬件/资源预算、相同负载模型和无敏感数据的样本。

1. 编写 k6/Locust 场景，明确预热、并发、请求分布、持续时间和停止阈值；分开测试七语言表现与业务逻辑差异。
2. 对比双 CI 冷/暖缓存、Ceph I/O 与应用竞争，采集吞吐、P95/P99、错误率、CPU/内存、网络和磁盘；报告注明不可直接比较的条件。
3. 接入 OpenCost，明确本地硬件/电力/折旧的自定义成本假设，关联 requests、实际用量和空闲；容量建议区分估算与实测。

### 操作命令与目的

```bash
k6 run --env LAB_TARGET_URL="$LAB_TARGET_URL" \
  --summary-export "$LAB_K6_REPORT" ops/05-observability/tests/performance/reference.js
# 选择 Locust 时使用同等负载条件，不要求两套工具同时运行
locust -f ops/05-observability/tests/performance/locustfile.py --headless -u 5 -r 1 -t 30s \
  --host "$LAB_TARGET_URL" --csv "$LAB_LOCUST_REPORT_PREFIX"
kubectl top pods -n lab-observability
ceph osd perf
helm upgrade --install opencost "$LAB_OPENCOST_CHART" -n opencost \
  --create-namespace --version "$LAB_OPENCOST_VERSION" -f opencost-values.yaml --wait
curl --get "$LAB_OPENCOST_URL/allocation" --data-urlencode 'window=1h' \
  --data-urlencode 'aggregate=namespace'
```

### 配置示例

小规模 k6 场景；延迟/错误阈值是示范，实验前根据容量与目标调整：

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';
export const options = {
  vus: 5,
  duration: '30s',
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500'],
  },
};
export default function () {
  const response = http.get(__ENV.LAB_TARGET_URL);
  check(response, { 'HTTP 200': (r) => r.status === 200 });
  sleep(1);
}
```

### 预期结果

得到吞吐、P95/P99、错误率和同窗口资源/存储指标，阈值失败有非零退出结果。OpenCost 成本必须结合本地 CPU/RAM/存储/电力价格假设；数据为零或缺失时不能解释成“没有成本”。七语言及双 CI 比较使用相同基准条件。

交付：`ops/05-observability/tests/performance/` 场景；`ops/05-observability/records/` 性能/容量/成本报告。

检查与失败处理：原始输入和聚合结果可复核，不把实验机结果外推为生产承诺；达停止阈值先撤压。

<a id="05-09"></a>

## 05.09 观测平台交接

输入：全部配置、故障案例、版本及采样/保留策略。

1. 从版本化文件重建一组 Dashboard/告警/Collector 配置，核对凭据引用和持久数据保留；恢复配置不依赖浏览器手工状态。
2. 整理发布失败、节点压力、Ceph 降级、消息积压和证书故障各自的可复用诊断路线。
3. 暂停闲置重型对照，保留核心监控和集群外探测；交给 06 统一 RTO/RPO 计时方法及第二集群遥测接入契约。

### 操作命令与目的

```bash
kubectl diff -f "$LAB_OBSERVABILITY_RENDERED"       # 检查配置重建差异
# 新建隔离验证环境时 apply；已由 GitOps 管理则提交配置并同步
kubectl apply -f "$LAB_OBSERVABILITY_RENDERED"
# 从版本化文件恢复一个 Grafana Dashboard
curl --config "$LAB_GRAFANA_CURL_CONFIG" -H 'Content-Type: application/json' \
  -X POST "$LAB_GRAFANA_URL/api/dashboards/db" --data @dashboard-import.json
curl --get "$LAB_PROMETHEUS_URL/api/v1/query" --data-urlencode 'query=up'
amtool --alertmanager.url "$LAB_ALERTMANAGER_URL" alert query
curl --fail "$LAB_REFERENCE_URL"                  # 再执行日志/Trace/Profile 关联检查
```

### 配置示例

Grafana HTTP API 导入请求的结构；Dashboard 应使用实际导出并校验的数据源引用和 panels：

```json
{
  "dashboard": {
    "uid": "lab-reference",
    "title": "Lab Reference",
    "schemaVersion": 39,
    "panels": []
  },
  "overwrite": true
}
```

这里只展示导入包装，空 panels 不算交付了可用 Dashboard。

### 预期结果

从仓库配置可重建实际面板、查询与告警；新请求仍能关联日志/指标/Trace/Profile，核心告警和集群外探测可用。暂停重型对照后资源下降且最低监控保留；第二集群观测由 06C 建成后再实测。

交付：观测恢复 Runbook、故障案例、资源清理与阶段 acceptance。

检查与失败处理：05 已建环境的关联、告警、压测和成本分析通过；06C 尚未建立的第二集群不提前标实测。

## 命令参考

[OpenTelemetry Collector 配置](https://opentelemetry.io/docs/collector/configuration/) · [Fluent Bit 配置校验](https://docs.fluentbit.io/manual/4.2/administration/configuring-fluent-bit) · [OpenCost API 示例](https://opencost.io/docs/integrations/api-examples/) · [原官方资料入口](../../arch/references.md)
