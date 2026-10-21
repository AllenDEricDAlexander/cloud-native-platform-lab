#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077
P05=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPO=$(cd "$P05/../.." && pwd)
INPUTS=${CNPL05_INPUTS:-$P05/inputs.json}
MATERIALS=${CNPL05_MATERIALS:-$P05/materials.json}
PRIVATE_TEMP=''
RECOVERY_FUNCTION=''
die() { printf '失败：%s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null || die "缺少命令：$1"; }
get() { jq -er "$1 | select(. != null and . != \"\")" "$INPUTS"; }
required() { get "$1" || die "尚未确认输入：$1"; }
sha() { shasum -a 256 "$1" | awk '{print $1}'; }
verify_file() { [[ -f $1 && ! -L $1 && $2 =~ ^[a-f0-9]{64}$ && $(sha "$1") == "$2" ]] || die '文件或 SHA256 不符'; }
private_file() {
    ruby -e 'p=File.realpath(ARGV[0]);r=File.realpath(ARGV[1]);s=File.stat(p);abort "私有文件必须在仓库外、当前用户所有、权限 0600/0400" unless !p.start_with?(r+"/") && !File.symlink?(ARGV[0]) && s.file? && s.size>0 && s.uid==Process.uid && [0600,0400].include?(s.mode & 0777)' "$1" "$REPO"
}
private_temp() { [[ -n $PRIVATE_TEMP ]] || PRIVATE_TEMP=$(mktemp -d); export PRIVATE_TEMP; }
finish() {
    local rc=$?
    trap - EXIT
    if [[ -n $RECOVERY_FUNCTION ]]; then "$RECOVERY_FUNCTION" || rc=1; fi
    [[ -z $PRIVATE_TEMP ]] || rm -rf -- "$PRIVATE_TEMP" || rc=1
    jq -n --arg action "$ACTION" --argjson code "$rc" --arg time "$(date -u +%FT%TZ)" '{action:$action,exit_code:$code,finished_at:$time,runtime_accepted:false,phase_complete:false}' > "$ATTEMPT/result.json"
    printf '证据：%s（exit=%s，不代表阶段验收）\n' "$ATTEMPT" "$rc"
    exit "$rc"
}
start() {
    STAGE=$1 ACTION=$2
    need jq; need ruby
    RUN=$(required .run_id)
    [[ $RUN =~ ^[a-z][a-z0-9-]{2,19}$ ]] || die 'run_id 必须为 3–20 位小写字母、数字、横线，首位字母'
    mkdir -p "$P05/$STAGE/records/$RUN"
    ATTEMPT=$(mktemp -d "$P05/$STAGE/records/$RUN/${ACTION}-XXXXXX")
    export P05 REPO INPUTS MATERIALS RUN STAGE ACTION ATTEMPT
    export CNPL05_INPUTS="$INPUTS" CNPL05_MATERIALS="$MATERIALS"
    trap finish EXIT
    jq -n --arg rev "$(git -C "$REPO" rev-parse HEAD)" --arg input "$(sha "$INPUTS")" --arg material "$(sha "$MATERIALS")" --arg time "$(date -u +%FT%TZ)" --arg run "$RUN" --arg stage "$STAGE" '{source_revision:$rev,inputs_sha256:$input,materials_sha256:$material,started_at:$time,run_id:$run,stage:$stage}' > "$ATTEMPT/context.json"
}
material() { ruby "$P05/lib/config.rb" material "$1"; }
k() { kubectl --kubeconfig "$(required .kubernetes.kubeconfig)" --context "$(required .kubernetes.context)" --request-timeout=30s "$@"; }
cluster_gate() {
    private_file "$(required .kubernetes.kubeconfig)"
    verify_file "$(required .prerequisites.file)" "$(required .prerequisites.sha256)"
    [[ $(k get ns kube-system -o jsonpath='{.metadata.uid}') == "$(required .kubernetes.cluster_uid)" ]] || die '集群 UID 不符'
    k get nodes -o json > "$ATTEMPT/nodes.json"
    ruby "$P05/lib/config.rb" nodes "$ATTEMPT/nodes.json"
}
ownership_gate() {
    local file=$1 kind name ns existing
    while IFS=$'\t' read -r kind name ns; do
        if [[ $ns == '-' ]]; then existing=$(k get "$kind" "$name" --ignore-not-found -o json); else existing=$(k -n "$ns" get "$kind" "$name" --ignore-not-found -o json); fi
        [[ -z $existing ]] || jq -e --arg run "$RUN" '.metadata.labels["cnpl.io/phase"]=="05" and .metadata.labels["cnpl.io/run"]==$run and (.metadata.annotations["argocd.argoproj.io/tracking-id"] // "")=="" and (.metadata.labels["argocd.argoproj.io/instance"] // "")==""' <<< "$existing" >/dev/null || die "拒绝接管其他批次或 GitOps 对象：$kind/$name"
    done < <(jq -r '.items[] | [.kind,.metadata.name,(.metadata.namespace // "-")] | @tsv' "$file")
}
apply() {
    private_temp
    ruby "$P05/lib/config.rb" list "$1" > "$PRIVATE_TEMP/apply.json"
    ruby "$P05/lib/config.rb" manifests "$PRIVATE_TEMP/apply.json"
    ownership_gate "$PRIVATE_TEMP/apply.json"
    k apply --field-manager=cnpl05-bootstrap -f "$PRIVATE_TEMP/apply.json"
}
namespace() {
    private_temp
    jq -n --arg ns "$1" '{apiVersion:"v1",kind:"Namespace",metadata:{name:$ns}}' > "$PRIVATE_TEMP/namespace.json"
    apply "$PRIVATE_TEMP/namespace.json"
}
chart() {
    local key=$1 release=$2 ns=$3 values=$4 info path version crd current
    info=$(material "$key"); path=$(jq -er .file <<< "$info"); version=$(jq -er .version <<< "$info")
    private_temp
    helm template "$release" "$path" -n "$ns" --include-crds -f "$values" --post-renderer "$P05/lib/post-render.sh" > "$PRIVATE_TEMP/chart.yaml"
    ruby "$P05/lib/config.rb" list "$PRIVATE_TEMP/chart.yaml" > "$PRIVATE_TEMP/chart.json"
    ruby "$P05/lib/config.rb" manifests "$PRIVATE_TEMP/chart.json"
    ownership_gate "$PRIVATE_TEMP/chart.json"
    # CRD 有独立全局生命周期；已有 CRD 不在此入口隐式升级。
    jq '.items |= map(select(.kind=="CustomResourceDefinition"))' "$PRIVATE_TEMP/chart.json" > "$PRIVATE_TEMP/crds.json"
    while IFS= read -r crd; do
        current=$(k get crd "$crd" --ignore-not-found -o json)
        if [[ -n $current ]]; then
            jq -S '.spec' <<< "$current" > "$PRIVATE_TEMP/current-spec.json"
            jq -S --arg name "$crd" '.items[] | select(.metadata.name==$name) | .spec' "$PRIVATE_TEMP/crds.json" > "$PRIVATE_TEMP/expected-spec.json"
            cmp -s "$PRIVATE_TEMP/current-spec.json" "$PRIVATE_TEMP/expected-spec.json" || die "CRD spec 有变化，需单独核对升级：$crd"
        fi
    done < <(jq -r '.items[].metadata.name' "$PRIVATE_TEMP/crds.json")
    namespace "$ns"
    if [[ $(jq '.items|length' "$PRIVATE_TEMP/crds.json") -gt 0 ]]; then
        apply "$PRIVATE_TEMP/crds.json"
        while IFS= read -r crd; do k wait --for=condition=Established --timeout=120s "crd/$crd"; done < <(jq -r '.items[].metadata.name' "$PRIVATE_TEMP/crds.json")
    fi
    helm upgrade --install "$release" "$path" --kubeconfig "$(required .kubernetes.kubeconfig)" --kube-context "$(required .kubernetes.context)" -n "$ns" --version "$version" --skip-crds -f "$values" --post-renderer "$P05/lib/post-render.sh" --wait --timeout=10m --history-max=5 > "$ATTEMPT/helm-status.txt"
}
http() {
    local config=$1 url=$2
    shift 2
    private_file "$config"
    [[ $url == https://* && $url != *'@'* && $url != *'?'* && $url != *'#'* ]] || die 'API 必须使用无内嵌凭据的 HTTPS URL'
    ruby "$P05/lib/http-config.rb" "$config" "$url"
    curl --config "$config" --fail --silent --show-error --connect-timeout 5 --max-time 60 --proto '=https' "$@" "$url"
}
query() {
    http "$(required .metrics.curl_config)" "$(required .metrics.url)/api/v1/query" --get --data-urlencode "query=$1" > "$2"
    jq -e '.status=="success" and (.data.result|length)>0' "$2" >/dev/null || die 'Prometheus 无数据或查询失败'
}
