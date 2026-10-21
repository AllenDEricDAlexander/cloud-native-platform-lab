#!/usr/bin/env bash
# 加载共用函数不连接网络；默认动作由子阶段选择为 validate。
set -euo pipefail
set +x
umask 077
P04=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPO=$(cd "$P04/../.." && pwd)
INPUTS=${CNPL04_INPUTS:-$P04/inputs.json}
MATERIALS=${CNPL04_MATERIALS:-$P04/materials.json}
PRIVATE_TEMP=''
RECOVERY_FUNCTION=''
die() { printf '失败：%s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null || die "缺少命令：$1"; }
get() { jq -er "$1 | select(. != null and . != \"\")" "$INPUTS"; }
required() { get "$1" || die "尚未确认输入：$1"; }
sha() { shasum -a 256 "$1" | awk '{print $1}'; }
verify_file() {
    [[ -f $1 && ! -L $1 && $2 =~ ^[0-9a-f]{64}$ ]] || die '文件/SHA256 无效'
    [[ $(sha "$1") == "$2" ]] || die "SHA256 不符：$1"
}
private_file() {
    ruby -e 'p=File.realpath(ARGV[0]);r=File.realpath(ARGV[1]);s=File.stat(p);abort "私有文件必须在仓库外、当前用户所有且权限为 0600/0400" unless p.start_with?("/") && !p.start_with?(r+"/") && !File.symlink?(ARGV[0]) && s.file? && s.size>0 && s.uid==Process.uid && [0600,0400].include?(s.mode & 0777)' "$1" "$REPO"
}
private_temp() { [[ -n $PRIVATE_TEMP ]] || PRIVATE_TEMP=$(mktemp -d); }
finish() {
    local rc=$?
    trap - EXIT
    if [[ -n $RECOVERY_FUNCTION ]]; then "$RECOVERY_FUNCTION" || rc=1; fi
    [[ -z $PRIVATE_TEMP ]] || rm -rf -- "$PRIVATE_TEMP" || rc=1
    jq -n --arg action "$ACTION" --argjson rc "$rc" --arg time "$(date -u +%FT%TZ)" '{action:$action,exit_code:$rc,finished_at:$time,runtime_accepted:false,phase_complete:false}' > "$ATTEMPT/result.json"
    printf '证据：%s（exit=%s；不代表阶段验收）\n' "$ATTEMPT" "$rc"
    exit "$rc"
}
start() {
    STAGE=$1 ACTION=$2
    need jq; need ruby
    RUN=$(required .run_id)
    [[ $RUN =~ ^[a-z][a-z0-9-]{2,19}$ ]] || die 'run_id 为 3–20 位小写字母/数字/横线，首位字母'
    mkdir -p "$P04/$STAGE/records/$RUN"
    ATTEMPT=$(mktemp -d "$P04/$STAGE/records/$RUN/${ACTION}-XXXXXX")
    export P04 REPO INPUTS MATERIALS RUN STAGE ACTION ATTEMPT
    trap finish EXIT
    jq -n --arg run "$RUN" --arg stage "$STAGE" --arg action "$ACTION" --arg source "$(git -C "$REPO" rev-parse HEAD)" --arg inputs "$(sha "$INPUTS")" --arg materials "$(sha "$MATERIALS")" --arg time "$(date -u +%FT%TZ)" '{run:$run,stage:$stage,action:$action,source_revision:$source,inputs_sha256:$inputs,materials_sha256:$materials,started_at:$time}' > "$ATTEMPT/context.json"
}
material() {
    ruby "$P04/lib/config.rb" material "$1"
}
image() { material "$1" | jq -er .image; }
k() { kubectl --kubeconfig "$(required .kubernetes.kubeconfig)" --context "$(required .kubernetes.context)" --request-timeout=30s "$@"; }
cluster_gate() {
    private_file "$(required .kubernetes.kubeconfig)"
    verify_file "$(required .prerequisites.file)" "$(required .prerequisites.sha256)"
    local uid
    uid=$(k get namespace kube-system -o jsonpath='{.metadata.uid}')
    [[ $uid == "$(required .kubernetes.cluster_uid)" ]] || die '集群 kube-system UID 不符'
    k get nodes -o json > "$ATTEMPT/nodes.json"
    ruby "$P04/lib/config.rb" nodes "$ATTEMPT/nodes.json"
}
worker_gate() {
    ruby "$P04/lib/config.rb" worker "$(required .build.node)"
}
render() { ruby "$P04/$STAGE/render.rb" "$@"; }
as_list() {
    ruby "$P04/lib/config.rb" list "$1"
}
ownership_gate() {
    local file=$1 kind name ns existing
    while IFS=$'\t' read -r kind name ns; do
        if [[ $ns == '-' ]]; then existing=$(k get "$kind" "$name" --ignore-not-found -o json); else existing=$(k -n "$ns" get "$kind" "$name" --ignore-not-found -o json); fi
        [[ -z $existing ]] || jq -e --arg run "$RUN" '.metadata.labels["cnpl.io/phase"]=="04" and .metadata.labels["cnpl.io/run"]==$run and (.metadata.annotations["argocd.argoproj.io/tracking-id"] // "")=="" and (.metadata.labels["argocd.argoproj.io/instance"] // "")==""' <<< "$existing" >/dev/null || die "拒绝接管其他批次或 GitOps 对象：$kind/$name"
    done < <(jq -r '.items[] | [.kind,.metadata.name,(.metadata.namespace // "-")] | @tsv' "$file")
}
apply() {
    private_temp
    as_list "$1" > "$PRIVATE_TEMP/apply.json"
    ruby "$P04/lib/config.rb" manifests "$PRIVATE_TEMP/apply.json"
    ownership_gate "$PRIVATE_TEMP/apply.json"
    k apply --field-manager=cnpl04-bootstrap -f "$PRIVATE_TEMP/apply.json"
}
namespace() {
    jq -n --arg name "$1" --arg run "$RUN" '{apiVersion:"v1",kind:"List",items:[{apiVersion:"v1",kind:"Namespace",metadata:{name:$name,labels:{"cnpl.io/phase":"04","cnpl.io/run":$run}}}]}' > "$ATTEMPT/namespace.json"
    apply "$ATTEMPT/namespace.json"
}
chart() {
    local key=$1 release=$2 ns=$3 info path values version
    info=$(material "$key")
    path=$(jq -er .file <<< "$info"); values=$(jq -er .values_file <<< "$info"); version=$(jq -er .version <<< "$info")
    verify_file "$path" "$(jq -er .sha256 <<< "$info")"
    verify_file "$values" "$(jq -er .values_sha256 <<< "$info")"
    private_temp
    # 预览与 Helm 实际安装共用后置处理器；不向证据目录输出 Secret/未脱敏 values。
    helm template "$release" "$path" -n "$ns" --include-crds --post-renderer "$P04/lib/post-render.sh" -f "$values" > "$PRIVATE_TEMP/chart.yaml"
    as_list "$PRIVATE_TEMP/chart.yaml" > "$PRIVATE_TEMP/chart.json"
    ruby "$P04/lib/config.rb" manifests "$PRIVATE_TEMP/chart.json"
    ownership_gate "$PRIVATE_TEMP/chart.json"
    namespace "$ns"
    jq '.items |= map(select(.kind=="CustomResourceDefinition"))' "$PRIVATE_TEMP/chart.json" > "$PRIVATE_TEMP/crds.json"
    ruby "$P04/lib/config.rb" crds "$PRIVATE_TEMP/crds.json" > "$PRIVATE_TEMP/crds-lock.json"
    local crd current expected
    while IFS=$'\t' read -r crd expected; do
        current=$(k get crd "$crd" --ignore-not-found -o json)
        if [[ -n $current ]]; then
            [[ $(jq -r '.metadata.annotations["cnpl.io/source-spec-sha256"]' <<< "$current") == "$expected" ]] || die "CRD spec 变化，需单独核对升级：$crd"
        fi
    done < <(jq -r '.items[] | [.metadata.name,.metadata.annotations["cnpl.io/source-spec-sha256"]]|@tsv' "$PRIVATE_TEMP/crds-lock.json")
    if [[ $(jq '.items|length' "$PRIVATE_TEMP/crds-lock.json") -gt 0 ]]; then
        apply "$PRIVATE_TEMP/crds-lock.json"
        while IFS= read -r crd; do k wait --for=condition=Established --timeout=120s "crd/$crd"; done < <(jq -r '.items[].metadata.name' "$PRIVATE_TEMP/crds-lock.json")
    fi
    helm upgrade --install "$release" "$path" --kubeconfig "$(required .kubernetes.kubeconfig)" --kube-context "$(required .kubernetes.context)" -n "$ns" --version "$version" --skip-crds --post-renderer "$P04/lib/post-render.sh" -f "$values" --wait --timeout=10m --history-max=5 > "$ATTEMPT/helm-status.txt"
}
