# Phase 04 实验操作手册

**当前脚本入口：[ops/04/01–10](../04/README.md)**。以下保留原专题设计与命令参考；新脚本按两位数字子目录组织，输入、离线检查和待验证边界以新入口为准。当前仅源码交付，未执行内网部署与验收。

配合 [阶段正文](../../plan/04-devops-platform.md) 按原专题执行；所有动作当前未执行，配置路径是原设计交付位置。每次先确认输入和作用域，再写配置、执行、检查正常与失败路径、恢复并归档。新脚本报告放 `ops/04/<子阶段>/records/<执行批次>/`。

## 命令与示例的使用方式

以下写明实验时大概要执行的命令、目的和预期变化，不是现在就能整段运行的一键脚本。`LAB_*`、`<...>`、版本、资源名和文件路径在开始实验时按实际环境填写；文件须先根据示例补齐，凭据通过受控配置注入。YAML 标为“片段”时应合并到完整对象，不能单独 apply；示例值不是性能或容量承诺。

`kubectl` 在选定集群的管理终端执行，`kubeadm`/主机命令在文中指定节点执行。每次变更前用 `kubectl config current-context` 核对目标。`--dry-run=server` 用于已经存在的集群/API；CRD 尚未安装时先安装匹配版本。`kubectl diff` 返回 1 通常表示有差异，应阅读差异后再 apply。故障、恢复和清理命令分段执行并观察结果，当前不执行任何部署。

测试 Namespace、样例应用、Chart/CRD 和引用文件应先创建到就绪；已由 GitOps 托管的对象通过仓库变更和同步更新，文中的直接 patch/scale/apply 用于隔离实验对象或受控诊断。

<a id="04-01"></a>

## 04.01 定义七语言交付契约

输入：可用仓库、网关、持久存储和至少一套已验证数据服务。

1. 在 `ops/04-devops-platform/examples/` 建立 java/rust/c/cpp/csharp/jsts/python 七类示例，每类约定构建、测试、制品、容器启动与健康检查；CLI/库保留原生制品，同时准备可部署的验收样例。
2. 统一源码 revision、版本、镜像 Digest、SBOM、测试报告和环境标识；声明 HTTP/消息接口、外部依赖和退出行为。
3. 为 dev/staging/prod-like 定义配置差异与晋级规则，同一已验证 Digest 晋级，环境间不重新构建未验证镜像。

### 操作命令与目的

分别进入对应语言样例目录执行，不能在同一个目录连续运行全部命令：

```bash
# Java：编译、测试和打包
./mvnw -B verify
# Rust：使用锁文件测试并生成发布二进制
cargo test --locked
cargo build --release --locked
# C / C++：两个独立样例都走各自的 CMake 项目
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
ctest --test-dir build --output-on-failure
# C#：锁定依赖后测试、发布
dotnet restore --locked-mode
dotnet test --no-restore
dotnet publish -c Release --no-restore
# JS/TS：用锁文件安装，执行项目约定的测试与构建
npm ci
npm test
npm run build
# Python：安装锁定依赖，执行测试、生成分发包
python -m pip install --require-hashes -r requirements.lock
python -m pytest
python -m build --no-isolation
```

### 配置示例

项目共用的交付结果记录示意，不是某个 CI 的原生语法：

```yaml
language: java
source_revision: <提交SHA>
builder_image: <Builder镜像Digest>
artifact: target/demo.jar
image: <应用镜像Digest>
test_report: target/surefire-reports/
smoke:
  endpoint: /health
  expected_status: 200
```

### 预期结果

每种语言都有可重复构建命令、测试结果和确定的制品；同一版本能启动并通过自己的健康/消息检查。C/C++ 是两个独立组合，CLI/库样例还保留原生制品。依赖锁文件和 build/pytest 等工具先放入对应 Builder。

交付：`ops/04-devops-platform/ci/shared/` 的交付契约、七类应用输入和验收矩阵。

检查与失败处理：每类样例可本地按指定命令构建/测试，并有实际运行检查；仅产出二进制不代表部署通过。

<a id="04-02"></a>

## 04.02 Builder、BuildKit 与依赖缓存

输入：00 的七语言物料和内网仓库已通过指定离线验收。

1. 逐语言制作固定工具链 Builder，内置公开 CA 和仓库客户端配置，运行时凭据在任务执行时注入；Builder 镜像用版本与 Digest 发布。
2. 选定受支持的 BuildKit/rootless 或隔离构建方式，设置缓存导入/导出、临时盘和清理；不向任意构建挂载宿主 Docker Socket。
3. 分别做冷缓存、暖缓存、断外网构建，清理仅限测试客户端缓存；记录耗时、流量和缺失物料，校验七语言依赖来源。

### 操作命令与目的

在已配置连接与认证的 BuildKit 执行器上构建，`LAB_*` 引用受控镜像和缓存仓库：

```bash
buildctl --addr "$LAB_BUILDKIT_ENDPOINT" build --frontend dockerfile.v0 \
  --local context=. --local dockerfile=ops/04-devops-platform/ci/builders/java \
  --opt filename=Dockerfile --opt build-arg:LAB_BASE_IMAGE="$LAB_BASE_IMAGE" \
  --output type=image,name="$LAB_BUILDER_IMAGE",push=true \
  --export-cache type=registry,ref="$LAB_CACHE_REF",mode=max \
  --import-cache type=registry,ref="$LAB_CACHE_REF"
skopeo inspect "docker://$LAB_BUILDER_IMAGE"      # 核对镜像/平台/Digest
# 用相同源码分别做冷、暖缓存和受限外网构建，记录时间与缓存命中
buildctl --addr "$LAB_BUILDKIT_ENDPOINT" du       # 查看当前缓存占用
```

### 配置示例

基于已经包含 JDK/Maven 的内网 Rocky Builder 基础镜像，Dockerfile 只展示信任和工作目录部分：

```dockerfile
ARG LAB_BASE_IMAGE
FROM ${LAB_BASE_IMAGE}
COPY lab-root-ca.crt /etc/pki/ca-trust/source/anchors/lab-root-ca.crt
RUN update-ca-trust
WORKDIR /workspace
```

Maven/npm/pip/NuGet/Cargo/Conan/vcpkg 的内部源配置分别纳入对应 Builder。访问令牌由 CI secret mount/环境注入，不 COPY 到镜像层。

### 预期结果

Builder 发布到 Harbor 并可按 Digest 拉取，构建环境可信任内部证书；暖缓存减少重复下载。离线实验必须从干净执行环境完成指定依赖构建，不能只证明已有镜像能启动。

交付：`ops/04-devops-platform/ci/builders/` 镜像定义、`ops/04-devops-platform/ci/shared/` 客户端/构建入口及缓存策略。

检查与失败处理：干净执行器仅靠已预热内网物料完成构建；失败先补齐依赖树，不把管理员工作站暖缓存作为结果。

<a id="04-03"></a>

## 04.03 GitLab CI 完整链路

输入：GitLab、Builder、集群执行器权限和制品约定。

1. 部署 Runner，区分普通构建、可信发布和 IaC 执行器；Kubernetes Executor 限定 Namespace/ServiceAccount、并发、CPU/内存与临时存储。
2. 编写可复用模板串联 checkout→依赖→测试→构建→扫描/SBOM→推镜像→更新 GitOps→等待部署→smoke；把失败输出作为制品。
3. 分别测试普通分支、MR、受保护发布与恶意/无权限分支；校验受保护凭据不会被不可信流水线读取。

### 操作命令与目的

```bash
helm upgrade --install gitlab-runner "$LAB_RUNNER_CHART" -n ci-gitlab \
  --create-namespace --version "$LAB_RUNNER_VERSION" -f runner-values.yaml --wait
kubectl -n ci-gitlab get pods
# 认证由 curl 配置提供；为选定源码 ref 触发实际流水线
curl --config "$LAB_GITLAB_CURL_CONFIG" --request POST \
  "$LAB_GITLAB_API/projects/$LAB_PROJECT_ID/pipeline" --data-urlencode "ref=$LAB_REF"
curl --config "$LAB_GITLAB_CURL_CONFIG" \
  "$LAB_GITLAB_API/projects/$LAB_PROJECT_ID/pipelines/$LAB_PIPELINE_ID/jobs"
# 发布阶段等待 GitOps 的实际交付结果
argocd app wait "$LAB_ARGO_APP" --sync --health --timeout 300
curl --fail "$LAB_APP_HEALTH_URL"
```

### 配置示例

`.gitlab-ci.yml` 的验证与镜像构建片段；`BUILDER_IMAGE`、BuildKit 连接和 Registry 凭据由可信 Runner/CI 变量提供：

```yaml
stages: [verify, package, release]
verify-java:
  stage: verify
  image: $BUILDER_IMAGE
  script:
    - ./mvnw -B verify
  artifacts:
    when: always
    reports:
      junit: target/surefire-reports/*.xml
package-image:
  stage: package
  image: $BUILDKIT_CLIENT_IMAGE
  script:
    - buildctl --addr "$BUILDKIT_HOST" build --frontend dockerfile.v0 --local context=. --local dockerfile=. --output type=image,name="$IMAGE_REF",push=true
```

release Job 再执行扫描/签名、更新 GitOps 和等待健康，禁止普通 MR 读取发布/IaC 凭据。流水线配置使用 GitLab CI Lint 先检查。

### 预期结果

Runner 注册和 Job Pod 创建正常，失败测试阻止镜像晋级；成功记录能追溯源码、Builder、镜像和部署结果。API 触发返回 pipeline ID，不代表整条流水线已通过，需继续检查 Job 和应用。

交付：`ops/04-devops-platform/ci/gitlab/` 的语言/应用/IaC 模板及 Runner 配置。

检查与失败处理：每个阶段可独立定位失败，任务终止会清理临时资源；失败发布不能直接绕过 GitOps 写业务对象。

<a id="04-04"></a>

## 04.04 Jenkins 对等实现

输入：与 GitLab 相同的 Builder、应用契约和验收用例。

1. 部署 Controller 和受限动态 Agent，固定插件/镜像版本；Controller 数据使用已验证存储并有备份，集群外恢复执行器独立保留。
2. 编写 Jenkins Shared Library 与各语言 Jenkinsfile，实现与 GitLab 相同的阶段/结果；使用受控凭据作用域、超时、并发限制和分支规则。
3. 测试 Agent 丢失、构建失败、扫描拒绝与 GitOps 更新冲突；重试遵守制品不可变和业务幂等，不重复发布不明版本。

### 操作命令与目的

```bash
helm upgrade --install jenkins "$LAB_JENKINS_CHART" -n ci-jenkins \
  --create-namespace --version "$LAB_JENKINS_VERSION" -f jenkins-values.yaml --wait
kubectl -n ci-jenkins get pods,pvc
# 使用 Jenkins CLI 的受控认证文件，触发任务并等待结果
java -jar "$LAB_JENKINS_CLI_JAR" -s "$LAB_JENKINS_URL" \
  -auth @"$LAB_JENKINS_AUTH_FILE" build "$LAB_JENKINS_JOB" -s -v -p GIT_REF="$LAB_REF"
argocd app wait "$LAB_ARGO_APP" --sync --health --timeout 300
curl --fail "$LAB_APP_HEALTH_URL"
```

### 配置示例

Jenkinsfile 的验证片段，`lab-java` 对应已声明的隔离 Agent 模板；其余阶段复用与 GitLab 相同的构建/供应链命令：

```groovy
pipeline {
    agent { label 'lab-java' }
    options {
        timestamps()
        disableConcurrentBuilds()
    }
    stages {
        stage('Verify') {
            steps { sh './mvnw -B verify' }
        }
    }
    post {
        always { junit 'target/surefire-reports/*.xml' }
    }
}
```

### 预期结果

Controller 使用持久卷，Agent 按任务创建并回收；相同源码通过与 GitLab 对等的测试/制品/部署检查。Agent 失效时流水线可解释地失败或受控重试，不能留下持有高权限凭据的长驻任务。

交付：`ops/04-devops-platform/ci/jenkins/` Shared Library、Jenkinsfile、Agent 模板和恢复说明。

检查与失败处理：与 GitLab 的构建/部署验收等价；Jenkins 不承担故障集群中无法运行时的自救前置。

<a id="04-05"></a>

## 04.05 执行七类语言 × 双 CI 矩阵

输入：两套完整流水线、七套固定源码样例与统一验收命令。

1. 建立 7 行 × 2 列矩阵：Java、Rust、C、C++、C#、JS/TS、Python；每个格保存源码 revision、Builder Digest、流水线链接、产物 Digest、部署对象与 smoke 输出。
2. 依次在 GitLab CI 和 Jenkins 执行各类构建、测试、镜像发布及 GitOps 部署；JS/TS 同一类包含约定前后端子场景，不能用同一语言的两个变体代替 C/C++。
3. 分别注入编译失败和坏应用版本，确认不会晋级，记录回退到已知 Digest 后的请求结果。

### 操作命令与目的

每次选择一类语言，分别调用两个 CI，再用同一应用验收方法检查结果；共执行 14 组：

```bash
curl --config "$LAB_GITLAB_CURL_CONFIG" --request POST \
  "$LAB_GITLAB_API/projects/$LAB_LANGUAGE_PROJECT_ID/pipeline" --data-urlencode "ref=$LAB_REF"
java -jar "$LAB_JENKINS_CLI_JAR" -s "$LAB_JENKINS_URL" \
  -auth @"$LAB_JENKINS_AUTH_FILE" build "$LAB_LANGUAGE_JOB" -s -p GIT_REF="$LAB_REF"
skopeo inspect --format '{{.Digest}}' "docker://$LAB_IMAGE_REF"
kubectl -n "$LAB_APP_NAMESPACE" get deployment "$LAB_APP" -o wide
curl --fail "$LAB_APP_HEALTH_URL"
```

### 配置示例

14 组报告的单行记录示意，当前不预填成功：

```yaml
language: rust
ci: jenkins
source_revision: <提交SHA>
pipeline_run: <实际运行链接或ID>
builder_digest: <实际Digest>
application_digest: <实际Digest>
deployment: <集群/Namespace/资源>
smoke_result: not_run
```

### 预期结果

Java、Rust、C、C++、C#、JS/TS、Python 各自拥有两套 CI 的独立构建、发布和部署证据。所有健康检查成功且负向构建被阻断；跨环境晋级使用该次已验证 Digest。拿另一条 CI 的现成镜像直接部署不算独立构建通过。

交付：`ops/04-devops-platform/records/<批次>/language-ci-matrix.md`；全部 14 格证据。

检查与失败处理：14 组必须各自构建并部署成功；只复用另一 CI 的既有镜像不算该格构建通过。

<a id="04-06"></a>

## 04.06 双 IaC 与恢复执行器

输入：OpenTofu/Ansible 模块、限定 vSphere 作用域和独立 State 后端。

1. 将 00 本地 State 按受控流程迁移到已验证可锁定的集群外后端，先备份并比较资源映射；不让两个 CI 各保一份 State 管相同 VM。
2. 两套 CI 都执行 validate→plan→审核保存的计划→apply→Ansible→验收；测试同时提交只有一个持锁成功，确认 no-op 与漂移处理。
3. 使用明确的新建测试 VM 验证创建、参数变更、失败补偿和销毁保护；有数据 VM 的销毁需要单独受控流程，不自动回滚成 destroy。
4. 在集群外管理机验证同样工具/模块/凭据恢复路径，模拟集群内 Runner/Controller 不可用时仍能读取受控配置和备份。

### 操作命令与目的

在 GitLab/Jenkins 中复用同一目录、后端和锁，先用专用测试 VM 验证：

```bash
tofu -chdir="$LAB_TOFU_DIR" init
tofu -chdir="$LAB_TOFU_DIR" fmt -check
tofu -chdir="$LAB_TOFU_DIR" validate
tofu -chdir="$LAB_TOFU_DIR" plan -out="$LAB_PLAN_FILE"
tofu -chdir="$LAB_TOFU_DIR" show "$LAB_PLAN_FILE"       # 查看实际变更范围
# 在审核过该保存的 Plan 后执行，而非重新生成另一份不明计划
tofu -chdir="$LAB_TOFU_DIR" apply "$LAB_PLAN_FILE"
ansible-playbook -i "$LAB_INVENTORY" "$LAB_NODE_PLAYBOOK" --limit "$LAB_TEST_VM"
tofu -chdir="$LAB_TOFU_DIR" plan -detailed-exitcode     # 再次检查幂等/漂移
```

`-detailed-exitcode` 的 0 表示无变更、2 表示有差异、1 表示错误；CI 应区分这些结果。迁移 State、锁冲突、Apply 中断和恢复单独演练，Plan/State 按敏感材料保管。

### 配置示例

OpenTofu 后端声明，地址与认证由受控 backend 配置提供：

```hcl
terraform {
  backend "http" {}
}
```

拟保护 VM 资源中的 lifecycle 片段：

```hcl
lifecycle {
  prevent_destroy = true
}
```

### 预期结果

两个 CI 均能创建/调整测试 VM 并运行同一 Ansible 基线；并发写同一 State 时只有持锁者 Apply，重复 Plan 无非预期变化。有数据资源的销毁被保护；失败后保留 State 并定位，而非自动 destroy 补偿。

交付：`ops/04-devops-platform/ci/gitlab/`、`ops/04-devops-platform/ci/jenkins/` 的 IaC 流程；`ops/00-preparation/` 共用模块与 State 恢复规程。

检查与失败处理：两个 CI 均实际完成可控变更，锁和幂等有证据；失败保留 State 与错误上下文，不并发强制解锁重跑。

<a id="04-07"></a>

## 04.07 GitOps、Helm/Kustomize 与环境

输入：主集群及三个逻辑环境的边界。

1. 将复用配置放 `ops/<阶段目录>/`，`ops/04-devops-platform/gitops/platform/` 引用，`ops/04-devops-platform/gitops/environments/` 只保存环境覆盖和固定版本；用 Helm lint/template 或 Kustomize build 检查渲染结果。
2. 安装 Argo CD，声明 AppProject、仓库/目标范围、CRD→控制器→CR/应用的同步顺序；检查健康、漂移和失败阻断。
3. 处理 HPA 与 GitOps 的 replicas 字段所有权，ApplicationSet 使用受控生成源并预览删除；Flux 只进入对照作用域。

### 操作命令与目的

```bash
helm lint "$LAB_APP_CHART"
helm template demo "$LAB_APP_CHART" -f "$LAB_APP_VALUES" > rendered.yaml
kustomize build ops/04-devops-platform/gitops/environments/dev > dev-rendered.yaml
kubectl apply --dry-run=server -f dev-rendered.yaml
kubectl diff -f dev-rendered.yaml
kubectl apply -f ops/04-devops-platform/gitops/bootstrap/argocd-project.yaml -f ops/04-devops-platform/gitops/platform/demo-app.yaml
argocd app diff demo-dev
argocd app sync demo-dev
argocd app wait demo-dev --sync --health --timeout 300
```

后续流水线在 GitOps 仓库选定环境目录用 `kustomize edit set image app="$LAB_IMAGE_DIGEST_REF"` 更新版本，检查 Git diff，再按仓库流程提交。一般业务对象不同时由 CI 直接 apply 和 Argo CD 管理。

### 配置示例

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata: {name: demo-dev, namespace: argocd}
spec:
  project: lab
  source:
    repoURL: <受控GitOps仓库地址>
    targetRevision: <批准的Git引用>
    path: ops/04-devops-platform/gitops/environments/dev
  destination:
    server: https://kubernetes.default.svc
    namespace: lab-apps
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
```

### 预期结果

Helm/Kustomize 渲染出目标环境配置，Argo CD 同步到选定集群且健康。错误覆盖显示 diff/失败原因，恢复 Git 中已知版本后重新收敛。HPA 管理的 replicas 需在字段所有权配置中协调，不能每次同步重置。

交付：`ops/04-devops-platform/gitops/bootstrap/`、`platform/`、`environments/{dev,staging,prod-like}/`。

检查与失败处理：同一对象没有两个控制者；渲染成功后还需实际同步与应用 smoke，错误覆盖可恢复到上一 Git revision。

<a id="04-08"></a>

## 04.08 自动灰度、回退与供应链

输入：支持所选 Rollouts 路由适配的真实网关和持续请求样例。

1. 在本阶段交付 `ops/04-devops-platform/metrics/` 的最小 Prometheus 与参考服务抓取配置；用真实错误率/延迟样本验证查询，不依赖 05、不用固定返回成功的假指标。
2. 配置 Rollout 的 Canary/BlueGreen、服务与实际路由权重、暂停点及 AnalysisTemplate；验证正常版本放行、坏版本超阈中止、流量回到稳定版本。
3. 单独测试无数据、指标源不可达和路由适配失败；无数据不自动当成功，记录暂停/失败行为及人工恢复入口。
4. 为真实镜像生成 SBOM、Trivy 结果与来源信息，用 Cosign 签名并验证内网取回；准入由 Audit 渐进到 Enforce，测试可信/无签名/错误身份/仓库失联。

### 操作命令与目的

```bash
kubectl apply -f minimal-prometheus.yaml -f reference-service-monitor.yaml
curl --get "$LAB_PROMETHEUS_URL/api/v1/query" \
  --data-urlencode 'query=sum(rate(http_requests_total{job="reference"}[1m]))'
kubectl -n lab-apps apply -f analysis-template.yaml -f rollout-demo.yaml
kubectl argo rollouts get rollout demo -n lab-apps --watch
# 故意发布坏版本后检查 AnalysisRun，再演练主动中止
kubectl -n lab-apps get analysisruns
kubectl argo rollouts abort demo -n lab-apps

trivy image --format cyclonedx --output sbom.json "$LAB_IMAGE_DIGEST_REF"
trivy image --severity HIGH,CRITICAL --exit-code 1 "$LAB_IMAGE_DIGEST_REF"
# 用受控密钥签名并按可信公钥验证；离线/bundle 参数按锁定版本补齐
cosign sign --key "$LAB_COSIGN_KEY_REF" "$LAB_IMAGE_DIGEST_REF"
cosign verify --key "$LAB_COSIGN_PUBLIC_KEY" "$LAB_IMAGE_DIGEST_REF"
kubectl -n lab-apps apply -f unsigned-test-pod.yaml   # 应被已启用的准入策略拒绝
```

上面展示签名/验证的基本接口；离线实验在执行时明确该 Cosign 版本的 bundle、透明日志和本地信任参数，不能假定默认签名流程天然离线。无论采用哪种模式，镜像 Digest 与可信签名都必须验证。离线 Trivy 先按 00 同步 DB，再使用匹配版本的离线/禁止更新选项。Rollouts 中止后的正式回退还要更新 GitOps 期望版本。

### 配置示例

AnalysisTemplate 的指标片段；这是实验阈值，正式窗口在实验时确定，查询必须匹配真实暴露的指标：

```yaml
metrics:
  - name: error-rate
    interval: 30s
    count: 5
    failureLimit: 1
    successCondition: len(result) == 1 && result[0] < 0.01
    failureCondition: len(result) != 1 || result[0] >= 0.01
    provider:
      prometheus:
        address: http://prometheus.monitoring.svc:9090
        query: |
          (sum(rate(http_requests_total{job="reference",status=~"5.."}[1m])) or vector(0))
          /
          sum(rate(http_requests_total{job="reference"}[1m]))
```

错误计数序列尚未产生时，分子用 `or vector(0)` 表示零错误；分母仍使用真实请求速率。请求序列缺失或速率为零仍得到空结果/NaN，不会伪装成健康。

### 预期结果

有流量且指标健康时灰度推进；错误率超限、空结果、NaN 或指标源故障不能默认为成功，分别观察 Failed/Error/Inconclusive 与暂停/中止。坏版本流量回到稳定版本，可信镜像可验证，错误签名/无签名样例被拒绝。

交付：`ops/04-devops-platform/metrics/` 最小指标源、`ops/04-devops-platform/gitops/` Rollout/Analysis、`ops/04-devops-platform/ci/shared/` 供应链步骤和 `ops/06-advanced-security-dr/security/` 策略。

检查与失败处理：流量、指标与 Rollout 状态一致，自动中止/回退和拒绝发布均有证据；不能等待 05 再将本阶段验收补为通过。

<a id="04-09"></a>

## 04.09 Backstage 与 Crossplane 自助服务

输入：通过验收的应用模板、双 CI 和 GitOps。

1. 部署 Backstage 并配置受限 GitLab 集成/团队权限/服务目录；Software Template 参数包括语言、CI、环境、资源规格和受限数据服务选择。
2. 模板生成仓库、源码、选定 CI、部署引用与文档；Crossplane 用版本化平台 API/Composition 创建获准资源，Argo CD 只管顶层声明，Operator 管子资源。
3. 从门户创建完整服务，逐段检查代码→CI→签名→GitOps→数据服务→健康→目录/文档；模拟创建中断，验证重试不重复建库/仓库或遗留资源。

### 操作命令与目的

```bash
helm upgrade --install backstage "$LAB_BACKSTAGE_CHART" -n platform-engineering \
  --create-namespace --version "$LAB_BACKSTAGE_VERSION" -f backstage-values.yaml --wait
helm upgrade --install crossplane "$LAB_CROSSPLANE_CHART" -n crossplane-system \
  --create-namespace --version "$LAB_CROSSPLANE_VERSION" -f crossplane-values.yaml --wait
kubectl apply -f platform-xrd.yaml -f platform-composition.yaml
# 使用部署的 Scaffolder API 发起任务；实际 endpoint 和鉴权在实验时确认
curl --config "$LAB_BACKSTAGE_CURL_CONFIG" -H 'Content-Type: application/json' \
  --request POST "$LAB_SCAFFOLDER_TASKS_ENDPOINT" --data @scaffold-request.json
kubectl -n lab-apps get devapplications
argocd app wait "$LAB_GENERATED_APP" --sync --health --timeout 300
curl --fail "$LAB_GENERATED_APP_URL/health"
```

`DevApplication` 是待实现的平台 API，只有 XRD/Composition 建立后才可使用。任务成功还要检查仓库、CI、签名、数据库和目录项。

### 配置示例

Scaffolder 请求的核心数据，模板引用和参数须与实际模板一致：

```json
{
  "templateRef": "template:default/lab-service",
  "values": {"name": "demo-service", "language": "java", "ci": "gitlab", "environment": "dev"}
}
```

Software Template 的参数片段，后续步骤分别执行取模板、发布仓库、登记目录与提交平台请求：

```yaml
parameters:
  - title: 服务参数
    required: [name, language, ci]
    properties:
      name: {type: string}
      language:
        type: string
        enum: [java, rust, c, cpp, csharp, jsts, python]
      ci:
        type: string
        enum: [gitlab, jenkins]
```

### 预期结果

一次自助请求产生可追溯任务、仓库、CI 和 GitOps 发布，生成的服务及数据依赖健康。重复/中断后重试不会重复创建同名资源；失败能定位在哪一层，控制权保持 Argo CD→顶层请求、Crossplane/Operator→子资源。

交付：`ops/04-devops-platform/backstage/`、`crossplane/`、`service-templates/`。

检查与失败处理：至少一个完整服务自助交付，模板权限与失败恢复可审计；不让门户拥有无限集群/基础设施权限。

<a id="04-10"></a>

## 04.10 Tekton、Flux、Dragonfly 与交接

输入：可控对照作用域与完成的双 CI 主线。

1. Tekton 实现同一小应用的 Task/Pipeline 与制品契约；Flux 管理独立 Namespace/对象；对照其执行、重试、凭据和回退，不与主控制器抢写。
2. 在选定节点验证 Dragonfly 镜像分发，比较冷/热拉取耗时、带宽、校验和以及 P2P 不可用时的行为。
3. 清理对照任务和控制器权限；核对 14 格、双 IaC、灰度/供应链、自助服务及恢复材料，再交接统一服务/版本标识给 05。

### 操作命令与目的

```bash
kubectl -n tekton-lab apply -f tekton-task.yaml -f tekton-pipeline.yaml
tkn pipeline start lab-build -n tekton-lab -p git-url="$LAB_SOURCE_URL" --showlog
tkn pipelinerun list -n tekton-lab
flux check
flux reconcile kustomization lab-flux -n flux-system --with-source
helm upgrade --install dragonfly "$LAB_DRAGONFLY_CHART" -n dragonfly-system \
  --create-namespace --version "$LAB_DRAGONFLY_VERSION" -f dragonfly-values.yaml --wait
# 在已配置 Dragonfly 路径的专用测试节点对比冷/暖拉取
time sudo crictl pull "$LAB_TEST_IMAGE"
```

### 配置示例

Flux 仅管理独立实验路径，不能与主 Argo CD 应用重叠：

```yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata: {name: lab-flux, namespace: flux-system}
spec:
  interval: 1m
  path: ./ops/04-devops-platform/examples/flux-demo
  prune: false
  targetNamespace: flux-lab
  sourceRef:
    kind: GitRepository
    name: lab-source
```

### 预期结果

Tekton 完成同一交付契约，Flux 独立资源收敛；Dragonfly 代理日志和网络流量证明真实命中，不能把本机已有镜像缓存误判为 P2P 提速。结束后清理对照作用域，14 组、双 IaC 和主 GitOps 结果仍可复现。

交付：`ops/04-devops-platform/ci/tekton/`、`ops/04-devops-platform/examples/` 对照；完整阶段验收。

检查与失败处理：所有主线要求独立验收；对照实验有记录，遗留控制器、凭据、镜像和资源得到处理。

## 命令参考

[Cosign 镜像签名](https://docs.sigstore.dev/cosign/signing/signing_with_containers/) · [GitLab Pipelines API](https://docs.gitlab.com/api/pipelines/) · [Argo Rollouts Analysis](https://argo-rollouts.readthedocs.io/en/stable/features/analysis/) · [原官方资料入口](../../arch/references.md)
