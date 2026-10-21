#!/usr/bin/env bash
# 管理端共用函数。加载本文件不访问网络，不执行安装或部署。
set -euo pipefail
set +x
umask 077
P03=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPO=$(cd "$P03/../.." && pwd)
INPUTS=${CNPL03_INPUTS:-$P03/inputs.json}
DEVICES=${CNPL03_DEVICES:-$P03/devices.json}
MATERIALS=${CNPL03_MATERIALS:-$P03/materials.json}
die() { printf '失败：%s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null || die "缺少命令：$1"; }
get() { jq -er "$1 | select(. != null and . != \"\")" "$INPUTS"; }
required() { get "$1" || die "输入未确认：$1"; }
sha() { shasum -a 256 "$1" | awk '{print $1}'; }
verify_file() {
    [[ -f $1 && ! -L $1 && $2 =~ ^[0-9a-f]{64}$ ]] || die '文件或 SHA256 输入无效'
    [[ $(sha "$1") == "$2" ]] || die "SHA256 不一致：$1"
}
private_file() {
    [[ $1 == /* && -f $1 && ! -L $1 && -s $1 ]] || die '秘密必须引用绝对路径的非空普通文件'
    case "$1" in "$REPO"/*) die '秘密文件必须放在仓库外' ;; esac
    ruby -e 's=File.stat(ARGV[0]); abort "秘密文件所有者或权限不符" unless s.uid==Process.uid && (s.mode & 077)==0' "$1"
}
hex_secret() {
    private_file "$1"
    ruby -e 'abort "口令须为单行 32-128 位十六进制" unless File.read(ARGV[0]).match?(/\A[a-f0-9]{32,128}\n?\z/)' "$1"
}
host_value() {
    ruby -ryaml -e 'h=YAML.load_file(ARGV[0]); n=(h.fetch("kubernetes_nodes")+h.fetch("lab_clients",[])).find{|v|v["id"]==ARGV[1]}; abort "未登记主机" unless n; v=n[ARGV[2]]; abort "台账字段未知" if v.nil?; puts v' "$REPO/ops/inventory/hosts.yaml" "$1" "$2"
}
run_id() {
    RUN=$(required .run_id)
    [[ $RUN =~ ^[a-z][a-z0-9-]{2,19}$ ]] || die 'run_id 需为 3–20 位小写字母、数字或横线，首位字母'
    RBD_POOL=cnpl03-$RUN-rbd
    CEPH_FS=cnpl03-$RUN-fs
    SC_RBD=cnpl03-$RUN-rbd
    SC_FS=cnpl03-$RUN-cephfs
    ROOK_NS=cnpl03-rook
    EXTERNAL_NS=cnpl03-external
}
start() {
    STAGE=$1 ACTION=$2
    need jq; need ruby; run_id
    ATTEMPT=$(mktemp -d "$P03/$STAGE/records-${RUN}-XXXXXX")
    # 证据进入忽略目录；每次调用独立保留，失败不覆盖。
    mkdir -p "$P03/$STAGE/records/$RUN"
    mv "$ATTEMPT" "$P03/$STAGE/records/$RUN/"
    ATTEMPT="$P03/$STAGE/records/$RUN/$(basename "$ATTEMPT")"
    export P03 REPO INPUTS DEVICES MATERIALS ATTEMPT RUN STAGE ACTION
    jq -n --arg stage "$STAGE" --arg action "$ACTION" --arg run "$RUN" --arg sha "$(sha "$INPUTS")" --arg time "$(date -u +%FT%TZ)" '{stage:$stage,action:$action,run:$run,inputs_sha256:$sha,started_at:$time,validation_scope:"runtime_invocation"}' > "$ATTEMPT/context.json"
    trap finish EXIT
}
finish() {
    local rc=$?
    trap - EXIT
    if [[ -n ${RECOVERY_FUNCTION:-} ]]; then
        if ! "$RECOVERY_FUNCTION"; then rc=1; printf '自动恢复未完成，按当前批次 recovery.json 执行 recover。\n' >&2; fi
    fi
    if [[ -n ${CLEANUP_DIRECTORY:-} ]]; then rm -rf -- "$CLEANUP_DIRECTORY" || rc=1; fi
    jq -n --argjson rc "$rc" --arg action "$ACTION" --arg time "$(date -u +%FT%TZ)" '{exit_code:$rc,action:$action,finished_at:$time,phase_acceptance:false}' > "$ATTEMPT/result.json"
    printf '证据：%s（exit=%s）\n' "$ATTEMPT" "$rc"
    exit "$rc"
}
material() {
    local item
    item=$(jq -ec --arg key "$1" '.components[$key] | select(.version != null and .compatibility_file != null and .compatibility_sha256 != null)' "$MATERIALS") || die "物料尚未锁定：$1"
    verify_file "$(jq -r .compatibility_file <<< "$item")" "$(jq -r .compatibility_sha256 <<< "$item")"
    ruby -ryaml -e 'c=YAML.load_file(ARGV[0]).fetch("components",{}).fetch(ARGV[1],{}); abort "组件尚未在主版本锁确认" unless c["version"].to_s==ARGV[2] && !ARGV[2].empty?' "$REPO/ops/versions.lock.yaml" "$1" "$(jq -r .version <<< "$item")"
    printf '%s\n' "$item"
}
image() {
    local value
    value=$(material "$1" | jq -er .image)
    [[ $value =~ ^harbor\.k8s\.internal\.egon\.top/.+@sha256:[0-9a-f]{64}$ ]] || die "镜像必须锁定内网 Digest：$1"
    printf '%s\n' "$value"
}
backup_gate() {
    [[ $(required .backup.independent) == true ]] || die '独立备份未确认；现有 esxi01 上的 backup VM 不满足本门槛'
    verify_file "$(required .backup.evidence_file)" "$(required .backup.evidence_sha256)"
}
remote() {
    local host=$1 script=$2 ip command arg quoted
    shift 2
    ip=$(host_value "$host" ip)
    command='bash -s --'
    for arg in "$@"; do printf -v quoted ' %q' "$arg"; command+=$quoted; done
    ssh -T -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 \
        -i "${CNPL03_SSH_IDENTITY:-$HOME/.ssh/cnpl_lab_ed25519}" "root@$ip" "$command" < "$script"
}
ceph() {
    local adm ref fsid
    adm=$(required .ceph.cephadm) || return 1
    ref=$(image ceph) || return 1
    fsid=$(required .ceph.fsid) || return 1
    remote storage01 "$P03/lib/exec-host.sh" storage01 "$adm" --image "$ref" shell --fsid "$fsid" -- ceph "$@"
}
ceph_ok() {
    local status
    status=$(ceph status --format json) || return 1
    printf '%s\n' "$status" > "$ATTEMPT/ceph-health-$(date -u +%H%M%S)-$RANDOM.json"
    jq -e --arg fsid "$(required .ceph.fsid)" '.fsid==$fsid and .health.status=="HEALTH_OK" and (.pgmap.degraded_objects // 0)==0 and (.pgmap.misplaced_objects // 0)==0' <<< "$status" >/dev/null || die 'Ceph 身份或健康基线不符'
    local used limit
    used=$(ceph df --format json | jq '.stats.total_used_raw_ratio * 100')
    limit=$(required .ceph.max_used_percent)
    jq -en --argjson used "$used" --argjson limit "$limit" '$used < $limit and $limit <= 75' >/dev/null || die '达到容量停止阈值'
}
k() { kubectl --kubeconfig "$(required .kubernetes.kubeconfig)" --context "$(required .kubernetes.context)" --request-timeout=30s "$@"; }
cluster_identity_gate() {
    need kubectl
    private_file "$(required .kubernetes.kubeconfig)"
    local uid
    uid=$(k get namespace kube-system -o jsonpath='{.metadata.uid}')
    [[ $uid == "$(required .kubernetes.cluster_uid)" ]] || die 'Kubernetes 集群 UID 不符'
}
cluster_gate() {
    cluster_identity_gate
    local nodes expected
    nodes=$(k get nodes -o json)
    expected=$(ruby -ryaml -rjson -e 'puts JSON.generate(YAML.load_file(ARGV[0]).fetch("kubernetes_nodes").map{|n|[n["id"],n["ip"]]}.sort)' "$REPO/ops/inventory/hosts.yaml")
    jq -en --argjson live "$nodes" --argjson expected "$expected" '([$live.items[] | [.metadata.name, ([.status.addresses[]|select(.type=="InternalIP")|.address][0])]]|sort)==$expected and all($live.items[]; any(.status.conditions[]; .type=="Ready" and .status=="True"))' >/dev/null || die '十节点身份、地址或 Ready 状态不符'
}
namespace() {
    local ns=$1 current
    current=$(k get namespace "$ns" --ignore-not-found -o json)
    if [[ -z $current ]]; then
        jq -n --arg ns "$ns" --arg run "$RUN" '{apiVersion:"v1",kind:"Namespace",metadata:{name:$ns,labels:{"cnpl.io/phase":"03","cnpl.io/run":$run}}}' > "$ATTEMPT/namespace-$ns.json"
        k create -f "$ATTEMPT/namespace-$ns.json"
    else
        jq -e --arg run "$RUN" '.metadata.labels["cnpl.io/phase"]=="03" and .metadata.labels["cnpl.io/run"]==$run' <<< "$current" >/dev/null || die "命名空间归属不符：$ns"
    fi
}
yaml_json() { ruby -ryaml -rjson -e 'puts JSON.generate({"apiVersion"=>"v1","kind"=>"List","items"=>YAML.load_stream(File.read(ARGV[0])).compact})' "$1"; }
apply() {
    local file=$1 ns=$2 rendered kind name scope existing
    rendered=$(mktemp)
    if [[ $file == *.json ]]; then cat "$file"; else yaml_json "$file"; fi |
        jq --arg ns "$ns" --arg run "$RUN" 'if .kind=="List" then . else {apiVersion:"v1",kind:"List",items:[.]} end | .items |= map(.metadata.labels["cnpl.io/run"]=$run | .metadata.labels["cnpl.io/phase"]="03" | if (.kind|IN("Namespace","PersistentVolume","StorageClass","CSIDriver","VolumeSnapshotClass","CustomResourceDefinition","ClusterRole","ClusterRoleBinding","PriorityClass","MutatingWebhookConfiguration","ValidatingWebhookConfiguration","APIService")) then . else .metadata.namespace=$ns end)' > "$rendered"
    if ! ruby "$P03/lib/review.rb" images-json "$rendered"; then rm -f "$rendered"; return 1; fi
    while IFS=$'\t' read -r kind name scope; do
        if [[ $scope == '-' ]]; then existing=$(k get "$kind" "$name" --ignore-not-found -o json); else existing=$(k -n "$scope" get "$kind" "$name" --ignore-not-found -o json); fi
        [[ -z $existing ]] || jq -e --arg run "$RUN" '.metadata.labels["cnpl.io/run"]==$run and .metadata.labels["cnpl.io/phase"]=="03"' <<< "$existing" >/dev/null || die "拒绝接管已有对象：$kind/$name"
    done < <(jq -r '.items[] | [.kind,.metadata.name,(.metadata.namespace // "-")]|@tsv' "$rendered")
    local rc=0
    k apply -f "$rendered" || rc=$?
    rm -f "$rendered"
    return "$rc"
}
chart() {
    local release=$1 key=$2 ns=$3 values=$4 info path version
    need helm
    info=$(material "$key")
    path=$(jq -er .file <<< "$info"); version=$(jq -er .version <<< "$info")
    verify_file "$path" "$(jq -er .sha256 <<< "$info")"
    namespace "$ns"
    helm template "$release" "$path" -n "$ns" --version "$version" -f "$values" --include-crds > "$ATTEMPT/$release-rendered.yaml"
    ruby "$P03/lib/review.rb" images "$ATTEMPT/$release-rendered.yaml"
    [[ $(helm show chart "$path" | ruby -ryaml -e 'puts YAML.load(STDIN.read).fetch("version")') == "$version" ]] || die '本地 Chart 版本与锁不符'
    local crd live
    while IFS= read -r crd; do
        live=$(k get crd "$crd" --ignore-not-found -o json)
        [[ -z $live ]] || jq -e --arg release "$release" --arg ns "$ns" '.metadata.annotations["meta.helm.sh/release-name"]==$release and .metadata.annotations["meta.helm.sh/release-namespace"]==$ns' <<< "$live" >/dev/null || die "已有 CRD 未归属本 release，先核对复用/升级：$crd"
    done < <(yaml_json "$ATTEMPT/$release-rendered.yaml" | jq -r '.items[]|select(.kind=="CustomResourceDefinition")|.metadata.name')
    helm --kubeconfig "$(required .kubernetes.kubeconfig)" --kube-context "$(required .kubernetes.context)" upgrade --install "$release" "$path" -n "$ns" --version "$version" -f "$values" --wait --timeout 10m --history-max 5
}
component_chart() {
    local info values
    info=$(material "$2") || return 1
    values=$(jq -er .values_file <<< "$info") || return 1
    verify_file "$values" "$(jq -er .values_sha256 <<< "$info")"
    chart "$1" "$2" "$3" "$values"
}
component_manifest() {
    local info file
    info=$(material "$1") || return 1
    file=$(jq -er .file <<< "$info") || return 1
    verify_file "$file" "$(jq -er .sha256 <<< "$info")"
    ruby "$P03/lib/review.rb" images "$file"
    namespace "$2"; apply "$file" "$2"
}
data_domains() {
    local host domain current
    for host in storage01 storage02 storage03; do
        domain=$(host_value "$host" actual_hypervisor)
        [[ $domain =~ ^esxi0[1-3]$ ]] || die '实际故障域未确认'
        current=$(k get node "$host" -o jsonpath='{.metadata.labels.cnpl\.io/esxi}')
        [[ -z $current || $current == "$domain" ]] || die '已有物理域标签冲突'
        k label node "$host" "cnpl.io/esxi=$domain" cnpl.io/phase03-data=true --overwrite
    done
}
secret_from_files() {
    local ns=$1 name=$2; shift 2
    local arg path file
    for arg in "$@"; do path=${arg#*=}; private_file "$path"; done
    file=$(mktemp "$ATTEMPT/secret.XXXXXX.json")
    local args=(); for arg in "$@"; do args+=(--from-file="$arg"); done
    k -n "$ns" create secret generic "$name" "${args[@]}" --dry-run=client -o json | jq '.immutable=true' > "$file"
    apply "$file" "$ns" >/dev/null
    rm -f "$file"
}
wait_json() {
    local seconds=$1 predicate=$2; shift 2
    local until_time=$((SECONDS + seconds)) body
    while ((SECONDS < until_time)); do
        body=$("$@") || return 1
        if jq -e "$predicate" <<< "$body" >/dev/null; then return 0; fi
        sleep 5
    done
    printf '等待超时：%s\n' "$predicate" >&2
    return 1
}
