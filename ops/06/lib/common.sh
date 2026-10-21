#!/usr/bin/env bash
# 管理端函数；加载时不连接网络，兼容 macOS Bash 3.2。
set -euo pipefail
set +x
umask 077
P06=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPO=$(cd "$P06/../.." && pwd)
INPUTS=${CNPL06_INPUTS:-$P06/inputs.json}
MATERIALS=${CNPL06_MATERIALS:-$P06/materials.json}
export CNPL06_INPUTS="$INPUTS" CNPL06_MATERIALS="$MATERIALS"
TARGET=primary
PRIVATE_TEMP=''
RECOVERY_FUNCTION=''
die() { printf '失败：%s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null || die "缺少命令：$1"; }
get() { jq -er "$1 | select(. != null and . != \"\")" "$INPUTS"; }
required() { get "$1" || die "输入未确认：$1"; }
sha() { shasum -a 256 "$1" | awk '{print $1}'; }
verify_file() {
    [[ -f $1 && ! -L $1 && $2 =~ ^[0-9a-f]{64}$ ]] || die '文件/SHA256 无效'
    [[ $(sha "$1") == "$2" ]] || die "SHA256 不符：$1"
}
private_file() { ruby "$P06/lib/config.rb" private "$1"; }
private_temp() { [[ -n $PRIVATE_TEMP ]] || PRIVATE_TEMP=$(mktemp -d); }
finish() {
    local rc=$? restore_rc=0
    trap - EXIT
    if [[ -n $RECOVERY_FUNCTION ]]; then "$RECOVERY_FUNCTION" || restore_rc=$?; fi
    [[ $restore_rc -eq 0 ]] || { printf '恢复未完成，保留原始失败和恢复记录。\n' >&2; [[ $rc -ne 0 ]] || rc=$restore_rc; }
    [[ -z $PRIVATE_TEMP ]] || rm -rf -- "$PRIVATE_TEMP" || { [[ $rc -ne 0 ]] || rc=1; }
    jq -n --arg action "$ACTION" --argjson rc "$rc" --argjson restore "$restore_rc" --arg time "$(date -u +%FT%TZ)" '{action:$action,exit_code:$rc,recovery_exit_code:$restore,finished_at:$time,runtime_accepted:false,phase_complete:false}' > "$ATTEMPT/result.json"
    rmdir "$LOCK" || true
    printf '证据：%s（exit=%s；不代表阶段验收）\n' "$ATTEMPT" "$rc"
    exit "$rc"
}
start() {
    STAGE=$1 ACTION=$2; export STAGE
    need jq; need ruby
    RUN=$(required .run_id)
    [[ $RUN =~ ^[a-z][a-z0-9-]{2,19}$ ]] || die 'run_id 无效'
    NS=cnpl06-$STAGE-$RUN
    STATE=$P06/$STAGE/records/$RUN
    mkdir -p "$STATE/owned"
    LOCK=$STATE/.lock
    mkdir "$LOCK" 2>/dev/null || die '本批次已有动作或残留锁；核对进程后人工解除'
    ATTEMPT=$(mktemp -d "$STATE/${ACTION}-XXXXXX")
    export RUN NS STATE ATTEMPT
    trap finish EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    jq -n --arg stage "$STAGE" --arg run "$RUN" --arg action "$ACTION" --arg inputs "$(sha "$INPUTS")" --arg materials "$(sha "$MATERIALS")" --arg revision "$(git -C "$REPO" rev-parse HEAD)" --arg time "$(date -u +%FT%TZ)" '{stage:$stage,run:$run,action:$action,inputs_sha256:$inputs,materials_sha256:$materials,source_revision:$revision,started_at:$time}' > "$ATTEMPT/context.json"
}
k() {
    local config context
    config=$(required ".clusters.$TARGET.kubeconfig") || return $?
    context=$(required ".clusters.$TARGET.context") || return $?
    kubectl --kubeconfig "$config" --context "$context" --request-timeout=30s "$@"
}
cluster_endpoint() {
    local target=$1 config context
    config=$(required ".clusters.$target.kubeconfig") || return $?
    context=$(required ".clusters.$target.context") || return $?
    private_file "$config" || return $?
    kubectl --kubeconfig "$config" --context "$context" config view --minify -o jsonpath='{.clusters[0].cluster.server}'
}
cluster_gate() {
    case "$TARGET" in primary|secondary|management|recovery) ;; *) die '未知目标集群' ;; esac
    private_file "$(required ".clusters.$TARGET.kubeconfig")"
    verify_file "$(required .prerequisites.file)" "$(required .prerequisites.sha256)"
    [[ $(k get namespace kube-system -o jsonpath='{.metadata.uid}') == "$(required ".clusters.$TARGET.uid")" ]] || die '集群 UID 不符'
    k get nodes -o json > "$ATTEMPT/$TARGET-nodes.json"
    ruby "$P06/lib/config.rb" nodes "$TARGET" "$ATTEMPT/$TARGET-nodes.json"
    k get --raw='/readyz' > "$ATTEMPT/$TARGET-readyz.txt"
    [[ $(cat "$ATTEMPT/$TARGET-readyz.txt") == ok ]] || die 'API 未就绪'
}
backup_gate() {
    [[ $(required .backup.independent) == true ]] || die '独立备份未确认；同 ESXi 的 backup VM 不满足门槛'
    verify_file "$(required .backup.evidence_file)" "$(required .backup.evidence_sha256)"
}
node_ip() {
    ruby -ryaml -e 'n=YAML.load_file(ARGV[0]).fetch("kubernetes_nodes").find{|n| n["fqdn"]==ARGV[1]};abort "节点未登记" unless n;puts n.fetch("ip")' "$REPO/ops/inventory/hosts.yaml" "$1"
}
remote_node() {
    local node=$1 script=$2 ip command argument quoted
    shift 2
    ip=$(node_ip "$node")
    private_file "$(required .hosts.ssh_identity)"
    command='bash -s --'
    for argument in "$node" "$ip" "$@"; do printf -v quoted ' %q' "$argument"; command+=$quoted; done
    ssh -T -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 -i "$(required .hosts.ssh_identity)" "root@$ip" "$command" < "$script"
}
evidence_gate() { verify_file "$(required ".$1.${2}_file")" "$(required ".$1.${2}_sha256")"; }
render() { STAGE=$STAGE ruby "$P06/$STAGE/render.rb" "${@}"; }
owned() {
    local kind=$1 name=$2 ns=$3 value
    if [[ $ns == '-' ]]; then value=$(k get "$kind" "$name" --ignore-not-found -o json) || return $?; else value=$(k -n "$ns" get "$kind" "$name" --ignore-not-found -o json) || return $?; fi
    [[ -n $value ]] || return 44
    jq -e --arg run "$RUN" --arg stage "$STAGE" '.metadata.labels["cnpl.io/phase"]=="06" and .metadata.labels["cnpl.io/stage"]==$stage and .metadata.labels["cnpl.io/run"]==$run and (.metadata.annotations["argocd.argoproj.io/tracking-id"] // "")=="" and (.metadata.labels["argocd.argoproj.io/instance"] // "")=="" and (.metadata.labels["kustomize.toolkit.fluxcd.io/name"] // "")==""' <<< "$value" >/dev/null || die "拒绝接管其他批次/GitOps 对象：$kind/$name"
    printf '%s\n' "$value"
}
apply_file() {
    local file=$1 scope=${2:-} kind name ns current ref api path namespaced discovery resource crd
    private_temp
    if [[ -z $scope ]]; then
        scope=$PRIVATE_TEMP/scope.json
        jq -n --arg ns "$NS" '{namespaces:[$ns],cluster_resources:[]}' > "$scope"
    fi
    ruby "$P06/lib/config.rb" prepare "$file" "$scope" > "$PRIVATE_TEMP/apply.json"
    : > "$PRIVATE_TEMP/references.jsonl"
    # 使用真实 API discovery 验证 namespaced 属性，不能用伪造 metadata.namespace 绕过集群级白名单。
    while IFS=$'\t' read -r api kind name ns; do
        if [[ $api == v1 ]]; then path=/api/v1; else path=/apis/$api; fi
        discovery=$(jq -c --arg api "$api" --arg kind "$kind" '.items[]|select(.kind=="CustomResourceDefinition" and .spec.names.kind==$kind)|.metadata.name as $crd|.spec as $s|$s.versions[]|select(.served==true and ($s.group+"/"+.name)==$api)|{name:$s.names.plural,namespaced:($s.scope=="Namespaced"),crd:$crd}' "$PRIVATE_TEMP/apply.json")
        if [[ -z $discovery ]]; then discovery=$(k get --raw="$path" | jq -ec --arg kind "$kind" '.resources[]|select(.kind==$kind and (.name|contains("/")|not))|{name,namespaced,crd:"-"}'); fi
        namespaced=$(jq -er '.namespaced|tostring' <<< "$discovery")
        if [[ $namespaced == true ]]; then [[ $ns != '-' ]] || die '命名空间对象缺 Namespace'; else [[ $namespaced == false && $ns == '-' ]] || die '集群级对象不能伪装 Namespace'; fi
        resource=$(jq -er .name <<< "$discovery"); crd=$(jq -er .crd <<< "$discovery")
        if [[ $api != v1 ]]; then resource=$resource.${api%/*}; fi
        jq -nc --arg api "$api" --arg kind "$kind" --arg name "$name" --arg ns "$ns" --arg resource "$resource" --arg crd "$crd" '{api:$api,kind:$kind,name:$name,namespace:$ns,resource:$resource,crd:$crd}' >> "$PRIVATE_TEMP/references.jsonl"
    done < <(jq -r '.items[]|[.apiVersion,.kind,.metadata.name,(.metadata.namespace // "-")]|@tsv' "$PRIVATE_TEMP/apply.json")
    while IFS=$'\t' read -r resource name ns crd; do
        if [[ $crd != '-' ]]; then
            current=$(k get customresourcedefinitions.apiextensions.k8s.io "$crd" --ignore-not-found -o json) || return $?
            [[ -n $current ]] || continue
        fi
        if [[ $ns == '-' ]]; then current=$(k get "$resource" "$name" --ignore-not-found -o json); else current=$(k -n "$ns" get "$resource" "$name" --ignore-not-found -o json); fi
        if [[ -n $current ]]; then owned "$resource" "$name" "$ns" >/dev/null || die '归属检查失败'; fi
    done < <(jq -r '[.resource,.name,.namespace,.crd]|@tsv' "$PRIVATE_TEMP/references.jsonl")
    # 先 Namespace、再 CRD；其余对象在所有依赖可见后按清单顺序应用。
    while IFS= read -r ref; do
        jq --arg ref "$ref" '.items[]|select(.kind=="Namespace" and .metadata.name==$ref)' "$PRIVATE_TEMP/apply.json" > "$PRIVATE_TEMP/one.json"
        k apply --field-manager=cnpl06 -f "$PRIVATE_TEMP/one.json" >/dev/null
        remember_owned namespaces "$ref" -
    done < <(jq -r '.items[]|select(.kind=="Namespace")|.metadata.name' "$PRIVATE_TEMP/apply.json")
    while IFS= read -r ref; do
        jq --arg ref "$ref" '.items[]|select(.kind=="CustomResourceDefinition" and .metadata.name==$ref)' "$PRIVATE_TEMP/apply.json" > "$PRIVATE_TEMP/one.json"
        current=$(k get crd "$ref" --ignore-not-found -o json)
        if [[ -n $current ]]; then
            k apply --dry-run=server -f "$PRIVATE_TEMP/one.json" -o json > "$PRIVATE_TEMP/crd-desired.json"
            [[ $(jq -S -c .spec <<< "$current") == "$(jq -S -c .spec "$PRIVATE_TEMP/crd-desired.json")" ]] || die 'CRD spec 变化需单独升级核对'
        fi
        k apply --field-manager=cnpl06 -f "$PRIVATE_TEMP/one.json" >/dev/null
        remember_owned customresourcedefinitions.apiextensions.k8s.io "$ref" -
        k wait --for=condition=Established --timeout=120s "crd/$ref"
    done < <(jq -r '.items[]|select(.kind=="CustomResourceDefinition")|.metadata.name' "$PRIVATE_TEMP/apply.json")
    jq '.items |= map(select(.kind!="Namespace" and .kind!="CustomResourceDefinition"))' "$PRIVATE_TEMP/apply.json" > "$PRIVATE_TEMP/rest.json"
    if [[ $(jq '.items|length' "$PRIVATE_TEMP/rest.json") -gt 0 ]]; then
        k apply --dry-run=server -f "$PRIVATE_TEMP/rest.json" >/dev/null
        while IFS= read -r item; do
            printf '%s\n' "$item" > "$PRIVATE_TEMP/one.json"
            k apply --field-manager=cnpl06 -f "$PRIVATE_TEMP/one.json" >/dev/null
            kind=$(jq -r .kind "$PRIVATE_TEMP/one.json"); name=$(jq -r .metadata.name "$PRIVATE_TEMP/one.json"); ns=$(jq -r '.metadata.namespace // "-"' "$PRIVATE_TEMP/one.json")
            api=$(jq -r .apiVersion "$PRIVATE_TEMP/one.json")
            resource=$(jq -er --arg api "$api" --arg kind "$kind" --arg name "$name" --arg ns "$ns" 'select(.api==$api and .kind==$kind and .name==$name and .namespace==$ns)|.resource' "$PRIVATE_TEMP/references.jsonl")
            remember_owned "$resource" "$name" "$ns"
        done < <(jq -c '.items[]' "$PRIVATE_TEMP/rest.json")
    fi
    while IFS=$'\t' read -r resource name ns; do remember_owned "$resource" "$name" "$ns"; done < <(jq -r '[.resource,.name,.namespace]|@tsv' "$PRIVATE_TEMP/references.jsonl")
    printf '清单已应用；业务及失败路径仍需独立 check/实验。\n'
}
remember_owned() {
    local current key
    current=$(owned "$1" "$2" "$3") || die '应用后归属检查失败'
    key=$(printf '%s' "$TARGET/$1/$3/$2" | shasum -a 256 | awk '{print $1}')
    jq --arg target "$TARGET" '{apiVersion,kind,metadata:{name:.metadata.name,namespace:.metadata.namespace,uid:.metadata.uid,labels:.metadata.labels},target:$target}' <<< "$current" > "$STATE/owned/$key.json"
}
install_component() {
    local key=$1 item
    item=$(ruby "$P06/lib/config.rb" material "$key")
    private_temp
    jq '{namespaces,cluster_resources}' <<< "$item" > "$PRIVATE_TEMP/component-scope.json"
    apply_file "$(jq -er .manifest_file <<< "$item")" "$PRIVATE_TEMP/component-scope.json"
    while IFS=$'\t' read -r ns resource condition; do
        k -n "$ns" wait "$resource" "--for=condition=$condition" --timeout=300s
    done < <(jq -r '.wait[]|[.namespace,.resource,.condition]|@tsv' <<< "$item")
}
redact_objects() {
    jq 'walk(if type=="object" then del(.data,.binaryData,.stringData,.env,.envFrom,.command,.args,.message,.annotations,.managedFields,.password,.token,.clientSecret) else . end)'
}
check_namespace() {
    owned Namespace "$NS" - >/dev/null || die '样例空间不存在'
    k -n "$NS" get pods -o json | redact_objects > "$ATTEMPT/pods.json"
    k -n "$NS" get events -o json | redact_objects > "$ATTEMPT/events.json"
}
delete_owned() {
    local kind=$1 name=$2 ns=$3 expected=$4 current api resource path status=0
    current=$(owned "$kind" "$name" "$ns") || status=$?
    [[ $status != 44 ]] || return 0
    [[ $status == 0 ]] || return "$status"
    [[ $(jq -r .metadata.uid <<< "$current") == "$expected" ]] || { printf '失败：删除 UID 已改变\n' >&2; return 1; }
    kind=$(jq -er .kind <<< "$current") || return $?
    api=$(jq -er .apiVersion <<< "$current") || return $?
    if [[ $api == v1 ]]; then path=/api/v1; else path=/apis/$api; fi
    resource=$(k get --raw="$path" | jq -er --arg kind "$kind" '.resources[]|select(.kind==$kind and (.name|contains("/")|not))|.name') || return $?
    [[ $ns == '-' ]] || path=$path/namespaces/$ns
    private_temp || return $?
    jq -n --arg uid "$expected" '{apiVersion:"v1",kind:"DeleteOptions",preconditions:{uid:$uid},propagationPolicy:"Foreground"}' > "$PRIVATE_TEMP/delete.json" || return $?
    k delete --raw="$path/$resource/$name" -f "$PRIVATE_TEMP/delete.json" >/dev/null
}
cleanup_plan() {
    local file
    for file in "$STATE"/owned/*.json; do
        [[ -f $file ]] || continue
        jq '{kind,name:.metadata.name,namespace:.metadata.namespace,uid:.metadata.uid,target}' "$file"
    done
    printf '清理前保护数据、停止 GitOps；Namespace/CRD/PVC/VM/备份及控制器使用本阶段规程，禁止全局 prune。\n'
}
