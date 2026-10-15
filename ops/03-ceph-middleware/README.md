# Phase 03 实验操作手册

与 [阶段正文](../../plan/03-ceph-middleware.md) 配合执行，下面按原专题编号展开。当前均为计划，提到的配置和脚本应在实施时编写；命令只是操作/检查入口，不表示本仓库已经具备部署实现。

每个专题沿“确认输入 → 编写和校验配置 → 单项执行 → 正常/失败验证 → 恢复与归档”推进。报告放 `ops/03-ceph-middleware/records/<执行批次>/`，引用原步骤号、参数、版本和实际结果；修改范围只限本实验对象。

## 命令与示例的使用方式

以下写明实验时大概要执行的命令、目的和预期变化，不是现在就能整段运行的一键脚本。`LAB_*`、`<...>`、版本、资源名和文件路径在开始实验时按实际环境填写；文件须先根据示例补齐，凭据通过受控配置注入。YAML 标为“片段”时应合并到完整对象，不能单独 apply；示例值不是性能或容量承诺。

`kubectl` 在选定集群的管理终端执行，`kubeadm`/主机命令在文中指定节点执行。每次变更前用 `kubectl config current-context` 核对目标。`--dry-run=server` 用于已经存在的集群/API；CRD 尚未安装时先安装匹配版本。`kubectl diff` 返回 1 通常表示有差异，应阅读差异后再 apply。故障、恢复和清理命令分段执行并观察结果，当前不执行任何部署。

测试 Namespace、样例应用、Chart/CRD 和引用文件应先创建到就绪；已由 GitOps 托管的对象通过仓库变更和同步更新，文中的直接 patch/scale/apply 用于隔离实验对象或受控诊断。

<a id="03-01"></a>

## 03.01 确认设备与恢复条件

输入：00 磁盘保护记录、三物理故障域和独立备份。

1. 逐盘关联 OSD 规划、稳定 ID、VM/VMDK、Datastore/RAID 和 ESXi；用 lsblk/findmnt 等只读检查排除已有文件系统、LVM 和数据。
2. 为每个池制定副本/min_size、CRUSH 故障域与空间预算，计算失去一域后的可用性和重建空间；把虚拟盘故障与裸盘故障的证据边界写清楚。
3. 给 storage 节点留出 cephadm 的 CPU/内存/网络预算，检查时间、受控 SSH、所选容器引擎和镜像物料。

### 操作命令与目的

在每台 storage 节点执行只读检查；Ceph CLI 尚未建立前不运行初始化命令：

```bash
lsblk -e7 -o NAME,PATH,SIZE,TYPE,FSTYPE,UUID,MOUNTPOINTS,MODEL,SERIAL
findmnt --verify --verbose
sudo pvs                               # 检查候选盘是否属于现有 LVM
sudo wipefs --no-act "$LAB_OSD_DEVICE"   # 只检查签名，不清除
chronyc tracking
free -h
sudo cephadm check-host                 # 检查所选版本的主机前置
```

### 配置示例

OSD 设备台账的结构示意，不是直接 apply 的 Ceph spec：

```yaml
host: storage01
hypervisor: esxi01
osd_devices:
  - stable_id: /dev/disk/by-id/<已核实设备>
    datastore: <实际Datastore>
    backing_disk: <实际VMDK或物理映射>
    contains_existing_data: false
    approved_for_osd: false
```

`approved_for_osd` 只有完成实物映射和数据核对后才改为 true，不能把示例里的 false/空值当成批准。

### 预期结果

候选设备来源唯一可追溯，无文件系统、挂载和被遗漏的 LVM/数据；时间和主机前置符合要求。只读命令发现签名时应停在核实阶段，不能自动执行 wipefs、zap 或格式化。

交付：`ops/03-ceph-middleware/cephadm/` 盘位映射和服务规格；容量与独立备份检查。

检查与失败处理：只有逐盘确认可用的设备可进入初始化；任何来源未知的盘保持阻塞，禁止 all-available-devices 式盲选。

<a id="03-02"></a>

## 03.02 部署 cephadm 外部集群

输入：已锁定 Ceph 版本/镜像与可用设备清单。

1. 在 storage01 按固定 MON 地址 bootstrap，保管 FSID/管理凭据；将 storage02/03 加入，声明 MON/MGR 放置并检查跨物理域分布。
2. 编写显式设备选择的 OSD service spec，逐台小批量 apply，观察发现、创建、加入和 PG 状态；管理凭据单独保存。
3. 使用 `ceph -s`、`ceph orch ps`、`ceph osd tree`、`ceph df` 建立健康基线；检查 OS/VM 的启停不依赖本 Ceph 自己供应的卷。

### 操作命令与目的

先在 storage01 bootstrap；后续 `ceph` 命令在已配置管理身份的 CLI 或 `cephadm shell` 内执行。添加主机前通过 Ansible 分发受控 cephadm SSH 身份。

```bash
sudo cephadm --image "$LAB_CEPH_IMAGE" bootstrap --mon-ip 192.168.9.106
sudo cephadm shell -- ceph -s
ceph orch host add storage02 192.168.9.107
ceph orch host add storage03 192.168.9.108
ceph orch host ls
ceph orch apply -i ceph-services.yaml             # 声明 MON/MGR 放置
ceph orch apply -i osd-spec.yaml --dry-run        # 先查看将使用哪些设备
ceph orch apply -i osd-spec.yaml                  # 仅执行已核实的 OSD spec
ceph orch ps
ceph osd tree
ceph -s
```

### 配置示例

单个主机的显式 OSD spec；storage02/03 使用各自核实后的独立文件：

```yaml
service_type: osd
service_id: storage01-data
placement:
  hosts: [storage01]
spec:
  data_devices:
    paths:
      - /dev/disk/by-id/<storage01已核实的空设备>
```

### 预期结果

三主机被纳管，MON/OSD 落在三物理故障域；dry-run 仅选中指定设备。OSD 加入后 PG 逐步收敛，健康状态和任何告警均能解释。失败保留 FSID 和现场，不通过重新 bootstrap 覆盖原集群。

交付：`ops/03-ceph-middleware/cephadm/` bootstrap 输入、host/service/OSD spec 和恢复资料索引。

检查与失败处理：守护进程和 PG 达到约定健康状态；失败先排设备/网络/时钟，保留 FSID，不重新 bootstrap 一个混合新集群。

<a id="03-03"></a>

## 03.03 提供块、文件与对象服务

输入：Ceph 健康和已核定的空间预算。

1. 建立 RBD 池并初始化应用属性，明确副本/回收/配额；建立 CephFS 的 metadata/data 池与 MDS，验证文件读写。
2. 部署 RGW，配置内部域名/TLS，创建受限用户和测试桶，执行 put/get/list/delete 并校验对象哈希。
3. 测试客户端权限拒绝及使用量增长，为各类数据保留独立身份；不要将 RGW、CephFS 和 RBD 视为同一种卷。

### 操作命令与目的

```bash
# Ceph 管理环境：创建本实验专用的块池、文件系统和对象服务
ceph osd pool create lab-rbd
ceph osd pool set lab-rbd size 3
ceph osd pool set lab-rbd min_size 2
rbd pool init lab-rbd
ceph fs volume create lab-cephfs
ceph fs status
ceph orch apply -i rgw-spec.yaml
ceph df

# 已配置受限 S3 profile 的客户端：实际上传、下载和比较内容
aws --profile "$LAB_S3_PROFILE" --endpoint-url "$LAB_RGW_ENDPOINT" s3 mb s3://lab-probe
aws --profile "$LAB_S3_PROFILE" --endpoint-url "$LAB_RGW_ENDPOINT" s3 cp payload.txt s3://lab-probe/payload.txt
aws --profile "$LAB_S3_PROFILE" --endpoint-url "$LAB_RGW_ENDPOINT" s3 cp s3://lab-probe/payload.txt restored.txt
cmp payload.txt restored.txt
```

### 配置示例

RGW service spec 的基本结构；公网/内网入口 TLS 和认证按实验补齐：

```yaml
service_type: rgw
service_id: lab-rgw
placement:
  hosts: [storage01]
spec:
  rgw_frontend_port: 8080
```

### 预期结果

RBD 池和 CephFS 可用，MDS 正常，RGW 能用受限身份读写测试桶；下载内容与原文件一致。池大小、副本和 min_size 需结合容量及故障目标确认，不能对已有业务池套用示例命令。

交付：`ops/03-ceph-middleware/cephadm/` 池/文件系统/RGW 声明；存储客户端用例。

检查与失败处理：块、文件、对象均实际读写并能追溯池和权限；失败恢复原池策略，避免误删已有池。

<a id="03-04"></a>

## 03.04 Rook External 与 Ceph CSI

输入：K8s/Ceph 连通，已匹配 Rook/CSI/Ceph 版本。

1. 由外部 Ceph 生成受限 consumer 连接材料，安全导入 Rook External；Kubernetes 只消费，不部署第二套 MON/OSD 接管主集群。
2. 配置 CSI 节点/控制器资源、节点挂载前置和必要网络规则，检查 provisioner/node plugin 状态。
3. 声明 RBD/CephFS StorageClass，明确 default、reclaimPolicy、allowVolumeExpansion、binding/access mode；若配置快照，同步安装匹配 CRD/controller/VolumeSnapshotClass。

### 操作命令与目的

```bash
# 外部 Ceph 管理端：核对匹配版本的导出脚本参数后，安全导出受限材料
python3 "$LAB_ROOK_EXPORT_SCRIPT" --help
umask 077
python3 "$LAB_ROOK_EXPORT_SCRIPT" --rbd-data-pool-name lab-rbd \
  --namespace rook-ceph-external --format bash > "$LAB_ROOK_EXPORT_FILE"

# Kubernetes 管理端：部署 Operator；用匹配的导入脚本/受控配置导入上述材料
helm upgrade --install rook-ceph "$LAB_ROOK_CHART" -n rook-ceph \
  --create-namespace --version "$LAB_ROOK_VERSION" -f rook-operator-values.yaml --wait
bash "$LAB_ROOK_IMPORT_SCRIPT"                # 先按所选脚本设置其需要的环境输入
kubectl -n rook-ceph-external apply -f external-cluster.yaml
kubectl apply -f storageclasses.yaml
kubectl -n rook-ceph get pods -o wide
kubectl -n lab-data apply -f pvc-smoke.yaml
kubectl -n lab-data describe pvc smoke-rbd
```

导出文件可能包含密钥，不输出到普通日志或 Git。脚本路径、namespace、RBD/CephFS 参数和 CSI 前缀在实验时按同一 Rook 版本补齐。

### 配置示例

外部消费集群，以及 StorageClass 的关键片段：

```yaml
apiVersion: ceph.rook.io/v1
kind: CephCluster
metadata: {name: rook-ceph-external, namespace: rook-ceph-external}
spec:
  external:
    enable: true
```

```yaml
provisioner: <实际RBD-CSI-provisioner名称>
parameters:
  clusterID: rook-ceph-external
  pool: lab-rbd
  imageFeatures: layering
reclaimPolicy: Retain
allowVolumeExpansion: true
volumeBindingMode: Immediate
```

完整 StorageClass 还需从导入结果填写 provisioner/node-stage 的 Secret 名称与 namespace；不要用外部 Ceph 管理员 keyring 作为普通业务凭据。

### 预期结果

Rook External 消费外部 Ceph，Kubernetes 中没有新建一套主 Ceph MON/OSD；CSI 控制器和节点组件健康，测试 PVC 由指定 StorageClass 动态供应。导入成功但 PVC Pending 时继续查事件、池权限、网络和 CSI Secret。

交付：`ops/03-ceph-middleware/storage/rook-external/`、`csi/`、`storageclasses/`。

检查与失败处理：动态申请测试 PVC 并成功挂载；失败分别排查凭据、连通、CSI 事件和池权限，不能给所有客户端 admin key。

<a id="03-05"></a>

## 03.05 卷生命周期与数据校验

输入：CSI 可用、带序号与校验和的测试数据。

1. 分别申请 RBD 与 CephFS PVC，写入文件和哈希，删除/重建或迁移测试 Pod 后重读；测试 RWX 并发权限和块卷访问限制。
2. 扩大测试 PVC 并检查 PVC/PV/文件系统容量，观察在线/离线扩容约束；记录失败事件再按驱动要求修复。
3. 创建 VolumeSnapshot，从新 PVC 恢复并校验；用独立临时卷测试 Retain/Delete 后端残留，说明本地 snapshot 不等于独立备份。

### 操作命令与目的

```bash
kubectl -n lab-data apply -f pvc-demo.yaml -f pvc-writer.yaml
kubectl -n lab-data wait --for=condition=Ready pod/pvc-writer --timeout=120s
kubectl -n lab-data exec pvc-writer -- sh -c 'echo storage-probe > /data/probe; sha256sum /data/probe'
kubectl -n lab-data delete pod pvc-writer
kubectl -n lab-data apply -f pvc-writer.yaml
kubectl -n lab-data exec pvc-writer -- sha256sum /data/probe
kubectl -n lab-data patch pvc data-rbd --type=merge \
  -p '{"spec":{"resources":{"requests":{"storage":"2Gi"}}}}'
kubectl -n lab-data apply -f snapshot-demo.yaml
kubectl -n lab-data get pvc,volumesnapshot
# 用快照作 dataSource 创建新的恢复 PVC，再挂载并比对 probe
kubectl -n lab-data apply -f pvc-from-snapshot.yaml -f restored-writer.yaml
```

### 配置示例

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata: {name: data-rbd, namespace: lab-data}
spec:
  storageClassName: lab-rbd
  accessModes: [ReadWriteOnce]
  resources:
    requests: {storage: 1Gi}
---
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata: {name: data-rbd-snapshot, namespace: lab-data}
spec:
  volumeSnapshotClassName: <实际RBD快照类>
  source:
    persistentVolumeClaimName: data-rbd
```

### 预期结果

重建/重新挂载后哈希相同；扩容后 PVC/PV 与文件系统按驱动要求达到新大小；快照 ReadyToUse，恢复卷数据一致。CephFS 另测 RWX；快照仍在原 Ceph 时，不计作独立备份。

交付：`ops/03-ceph-middleware/storage/volume-lifecycle/`；`ops/03-ceph-middleware/tests/integration/` 数据校验与快照恢复。

检查与失败处理：Pod 重建后数据一致，扩容、快照和回收行为均有后端证据；仅清理本次测试卷。

<a id="03-06"></a>

## 03.06 OSD/CSI 故障与 Rook 自管理对照

输入：健康基线、备份、单次故障范围与停止阈值。

1. 每次只隔离一个选定 OSD/存储路径，持续业务读写，记录 degraded、PG、恢复/重平衡与延迟；恢复后等待健康再下一次。
2. 单独测试 CSI controller/node plugin 中断，区分新卷供应失败与已有挂载的行为，再验证组件恢复。
3. 为 Rook 自管理建立另一组明确设备、FSID 和命名空间；部署相同小用例，对比生命周期管理；结束按数据保护顺序清理，不能共用 cephadm 设备。

### 操作命令与目的

各组命令之间保留观测窗口，持续读写测试 PVC；一次只处理一个已选定 OSD：

```bash
ceph -s
ceph osd tree
ceph orch daemon stop "osd.$LAB_OSD_ID"       # 测试单 OSD 服务中断
ceph health detail
ceph pg stat
# 重平衡场景单独进行：确认余量后才将该 OSD 标记 out
ceph osd out "$LAB_OSD_ID"
ceph -w                                     # 在观察终端查看变化，结束后退出
# 恢复该 OSD，并等待健康收敛
ceph orch daemon start "osd.$LAB_OSD_ID"
ceph osd in "$LAB_OSD_ID"
ceph -s

# CSI 场景：单独重建选定的测试组件 Pod，观察新卷供应与已有挂载
kubectl -n "$LAB_CSI_NAMESPACE" delete pod "$LAB_CSI_TEST_POD"
kubectl -n lab-data describe pvc "$LAB_TEST_PVC"
```

### 配置示例

Rook 自管理对照的 `CephCluster.spec.storage` 片段；Operator/CSI 管理范围与设备均隔离：

```yaml
useAllNodes: false
useAllDevices: false
nodes:
  - name: <独立实验节点>
    devices:
      - name: /dev/disk/by-id/<仅属于Rook对照的空盘>
```

对照部署入口是 `kubectl apply -f rook-managed-demo.yaml`，不是让 Rook 接管已有 cephadm FSID 或盘。

### 预期结果

故障期间能观察到 OSD/PG、客户端延迟和失败的对应变化；恢复后 PG 回到约定状态且数据校验通过。三故障域丢一域时未必能立即重建完整三副本，如实记录。Rook 对照产生独立集群，不改主 Ceph 数据。

交付：`ops/03-ceph-middleware/examples/` 故障与对照配置；`ops/03-ceph-middleware/tests/failover/` 及存储故障报告。

检查与失败处理：至少一次 OSD 故障/恢复有读写校验；硬件抽象层明确，触达数据风险/容量阈值即停止。

<a id="03-07"></a>

## 03.07 PostgreSQL、MySQL 与 ECK

输入：稳定 PVC、独立备份目的地和受限连接身份。

1. 安装 CloudNativePG 并声明 PostgreSQL Cluster，配置副本放置、存储、服务、备份/WAL 和恢复目标；写入可核对的事务数据。
2. 执行受控主备切换和主节点故障，观察只写主服务与客户端重连；将原生备份恢复到独立测试集群，核对业务表/事务范围。
3. 扩展 MySQL 的存储/复制/备份实验；ECK 验证 Operator 与小型 Elasticsearch CR 生命周期，完整日志链路留到 05，避免重复部署竞争。

### 操作命令与目的

```bash
helm upgrade --install cnpg "$LAB_CNPG_CHART" -n cnpg-system \
  --create-namespace --version "$LAB_CNPG_VERSION" -f cnpg-values.yaml --wait
kubectl -n lab-data apply -f postgres-demo.yaml
kubectl cnpg status pg-demo -n lab-data
kubectl cnpg psql pg-demo -n lab-data -- -c 'SELECT current_timestamp, pg_is_in_recovery();'
kubectl cnpg promote pg-demo "$LAB_PG_REPLICA" -n lab-data  # 受控切换目标副本

# 使用受控 pg_service 配置；先做可理解的逻辑备份/隔离恢复
pg_dump --dbname='service=lab-primary' --format=custom --file="$LAB_PG_BACKUP"
pg_restore --dbname='service=lab-restore' --no-owner "$LAB_PG_BACKUP"
psql 'service=lab-restore' -c 'SELECT count(*) FROM lab_probe;'

# 扩展路线采用各自的配置/客户端，不共用 PostgreSQL 的恢复命令
kubectl -n lab-data apply -f mysql-demo.yaml -f elasticsearch-demo.yaml
mysql --defaults-extra-file="$LAB_MYSQL_CLIENT_CONFIG" --execute='SELECT VERSION();'
kubectl -n lab-data get elasticsearch
```

`lab_probe` 由测试应用事先建立并写入已知序号；两个 pg_service 分别指向原 `lab` 数据库和隔离恢复的 `lab` 数据库，先确认测试数据再备份。逻辑备份示例不能代替 WAL/PITR。原生备份与恢复另外使用选定 CNPG 版本支持的插件/配置和独立对象存储，恢复到新 Cluster 后核对恢复时间点。

### 配置示例

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata: {name: pg-demo, namespace: lab-data}
spec:
  instances: 3
  storage:
    storageClass: lab-rbd
    size: 2Gi
  bootstrap:
    initdb:
      database: lab
      owner: lab
```

完整配置补物理故障域分布、受限凭据、备份目的地和资源，不能仅凭三副本数认定高可用。

### 预期结果

一个写主、其余副本健康；受控切换后写入口指向新主，测试事务保持正确。恢复集群的记录数/业务校验与备份点一致。MySQL、ECK 分别有实际连接和持久化结果，未运行的扩展保持未验收。

交付：`ops/03-ceph-middleware/middleware/{postgresql,mysql,elasticsearch}/` CR；数据库恢复 Runbook。

检查与失败处理：至少一次数据库独立恢复通过，切换后无双主写入；失败先隔离旧写主并保护数据，不能直接覆盖原库。

<a id="03-08"></a>

## 03.08 Redis、Kafka、RabbitMQ 与 NATS

输入：配额、存储、域名、身份和每套服务的资源预算。

1. 逐套部署 Redis、Strimzi/Kafka、RabbitMQ Operator、NATS/JetStream，声明持久化、副本/故障域、服务端口、认证和资源；不在未知容量下一次全部启动。
2. 使用序号/业务键消息测试生产、消费、确认与重投；区分应用幂等、at-least-once 和系统提供的交付语义。
3. 分别故障一个 Kafka Broker、RabbitMQ/NATS 成员或 Redis 主实例，观察多数派/选主/积压，恢复后核对丢失、重复、顺序与持久数据。

### 操作命令与目的

下面按组件分别执行，凭据由客户端配置/环境注入。先有存储、认证和受限测试空间，再发测试数据：

```bash
kubectl -n lab-data apply -f redis-demo.yaml -f kafka-demo.yaml -f rabbitmq-demo.yaml
helm upgrade --install nats "$LAB_NATS_CHART" -n lab-data \
  --version "$LAB_NATS_VERSION" -f nats-values.yaml --wait
redis-cli --tls --cacert "$LAB_CA_FILE" -h "$LAB_REDIS_HOST" SET lab:probe phase03
redis-cli --tls --cacert "$LAB_CA_FILE" -h "$LAB_REDIS_HOST" GET lab:probe

"$LAB_KAFKA_BIN/kafka-topics.sh" --bootstrap-server "$LAB_KAFKA_BOOTSTRAP" \
  --command-config "$LAB_KAFKA_CLIENT_CONFIG" --create --topic lab-probe \
  --partitions 3 --replication-factor 3
printf 'id=1\nid=2\n' | "$LAB_KAFKA_BIN/kafka-console-producer.sh" \
  --bootstrap-server "$LAB_KAFKA_BOOTSTRAP" --topic lab-probe --producer.config "$LAB_KAFKA_CLIENT_CONFIG"
"$LAB_KAFKA_BIN/kafka-console-consumer.sh" --bootstrap-server "$LAB_KAFKA_BOOTSTRAP" \
  --topic lab-probe --from-beginning --max-messages 2 --consumer.config "$LAB_KAFKA_CLIENT_CONFIG"

# RabbitMQ 管理 API：创建专用持久队列，客户端认证放在 curl 配置文件
curl --config "$LAB_RABBIT_CURL_CONFIG" -H 'Content-Type: application/json' \
  -X PUT "$LAB_RABBIT_API/api/queues/lab/orders" --data @queue.json
# NATS CLI 已选定受限 context；建立流并写入带业务 ID 的事件
nats stream add LAB --subjects lab.events --storage file --replicas 3 --defaults
nats pub lab.events 'id=1'
nats stream info LAB
```

RabbitMQ 再用测试生产者/消费者或管理 API 的 publish/get 验证路由与确认；对 Kafka Broker、RabbitMQ/NATS 成员或 Redis 主实例分别注入单实例故障，恢复后重复消费并校验序号。

### 配置示例

`queue.json`：

```json
{"durable": true, "auto_delete": false, "arguments": {"x-queue-type": "quorum"}}
```

RabbitMQ Operator CR 的基本结构；其余组件使用自己的 Operator/Chart，不复用该 API：

```yaml
apiVersion: rabbitmq.com/v1beta1
kind: RabbitmqCluster
metadata: {name: mq-demo, namespace: lab-data}
spec:
  replicas: 3
  persistence:
    storageClassName: lab-rbd
    storage: 2Gi
```

### 预期结果

Redis 读回写入值；Kafka 消息序号可消费；RabbitMQ 队列持久且能确认消息；NATS Stream 记录增长。故障恢复后分别统计丢失、重复、顺序与积压，不把客户端重试自动等同“恰好一次”。三副本示例要求实际有足够成员和容量。

交付：`ops/03-ceph-middleware/middleware/{redis,kafka,rabbitmq,nats}/`；消息持久化/失败/恢复用例。

检查与失败处理：各套消息和缓存方案有实际功能及恢复记录；恢复前不强制清空数据目录或把多数派缩到零。

<a id="03-09"></a>

## 03.09 自研 Operator 与数据平台交接

输入：小型 DemoApp 资源模型及测试 Namespace。

1. 定义 DemoApp spec/status/conditions/schema，选择一种已选定工具链实现 Deployment/Service/ConfigMap 调谐；不额外实现第二套同功能框架。
2. 用重复事件、子资源丢失、API 短暂失败、权限不足、非法 spec 和删除测试幂等/重试/Finalizer；状态变化不应无限自触发。
3. 记录 CRD 版本演进与 RBAC，建立存储→CSI→Operator→数据库/消息→应用的启动顺序及反向安全停机；完成数据恢复交接。

### 操作命令与目的

以 Go/Kubebuilder 展示操作路线；若实验时选择 Java/Rust，替换脚手架和测试命令，仍验证同一 API 与调谐契约：

```bash
# 在预定的 Operator 工程目录执行
kubebuilder init --domain egon.top --repo "$LAB_OPERATOR_MODULE"
kubebuilder create api --group lab --version v1alpha1 --kind DemoApp --resource=true --controller=true
make manifests                              # 从实现生成 CRD/RBAC
make test                                   # 验证调谐/校验逻辑
make install                                # 安装到选定实验集群
make deploy IMG="$LAB_OPERATOR_IMAGE"
kubectl -n lab-operator apply -f demoapp.yaml
kubectl -n lab-operator get demoapps,deployments,services
kubectl -n lab-operator delete deployment demo-web  # 删除子对象后观察重建
kubectl -n lab-operator delete demoapp demo-web --wait=false
```

这些 make 目标来自脚手架工程，只有先完成控制器实现与镜像构建后才执行；本次并未生成或测试 Operator 代码。

### 配置示例

项目拟设计的 DemoApp，字段由对应 CRD 定义，不是内置资源：

```yaml
apiVersion: lab.egon.top/v1alpha1
kind: DemoApp
metadata: {name: demo-web, namespace: lab-operator}
spec:
  image: "<内网应用 Digest>"
  replicas: 2
  port: 8080
```

### 预期结果

DemoApp 驱动生成关联 Deployment/Service/ConfigMap；删子资源后重新收敛，重复事件不生成重复对象；删除时先完成约定清理再解除 Finalizer。非法 spec/权限不足表现为可解释事件和 Conditions，不能无限快速重试。

交付：`ops/03-ceph-middleware/operators/demoapp/` 源码、CRD/RBAC/部署清单；`ops/03-ceph-middleware/tests/integration/` 调谐测试。

检查与失败处理：自研控制器可重复收敛且最小权限，03 全部数据测试/备份闭环；未启用服务保持未完成状态。

## 命令参考

[cephadm OSD 声明与 dry-run](https://docs.ceph.com/en/latest/cephadm/services/osd/) · [Rook External](https://rook.io/docs/rook/latest-release/CRDs/Cluster/external-cluster/external-cluster/) · [原官方资料入口](../../arch/references.md)
