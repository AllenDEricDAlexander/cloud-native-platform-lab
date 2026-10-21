#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P06/validate.sh" 14 ;;
    render) export STAGE=14; exec ruby "$P06/14/render.rb" "${2:-app}" ;;
    install|apply|check|fault|recover|cleanup-plan) ;;
    *) die '用法：14/run.sh validate|render <app|fault>|install|apply|check|fault|recover|cleanup-plan' ;;
esac
start 14 "$action"
if [[ $action == cleanup-plan ]]; then cleanup_plan; exit; fi
recover_fault() {
    local resources file kind name uid failed=0
    resources=$(k -n "$NS" get podchaos,networkchaos,stresschaos -l "cnpl.io/phase=06,cnpl.io/stage=14,cnpl.io/run=$RUN" -o json) || return 1
    file=$ATTEMPT/recover-list.json
    printf '%s\n' "$resources" > "$file"
    while IFS=$'\t' read -r kind name uid; do
        if ! delete_owned "$kind" "$name" "$NS" "$uid"; then failed=1; continue; fi
        k -n "$NS" wait "$kind/$name" --for=delete --timeout=120s || failed=1
    done < <(jq -r '.items[]|[.kind,.metadata.name,.metadata.uid]|@tsv' "$file")
    return "$failed"
}
probe() { k -n "$NS" exec deployment/chaos-peer -c app -- curl --fail --silent --show-error --max-time 3 http://chaos-target:8080/health >/dev/null; }
if [[ $action == install ]]; then ruby "$P06/lib/config.rb" material chaos_mesh >/dev/null; fi
if [[ $action == fault ]]; then
    backup_gate
    render fault > "$ATTEMPT/fault.json"
    threshold=$(required .chaos.max_error_ratio)
    jq -en --argjson threshold "$threshold" '$threshold>=0 and $threshold<=1' >/dev/null || die '错误率阈值无效'
fi
cluster_gate
case "$action" in
    install) install_component chaos_mesh ;;
    apply) render > "$ATTEMPT/app.json"; apply_file "$ATTEMPT/app.json" ;;
    recover) recover_fault ;;
    check)
        check_namespace
        k -n "$NS" get podchaos,networkchaos,stresschaos -o json > "$ATTEMPT/chaos-state.json"
        k -n "$NS" rollout status deployment/chaos-target --timeout=180s
        probe
        ;;
    fault)
        check_namespace
        owned Deployment chaos-target "$NS" >/dev/null
        owned Deployment chaos-peer "$NS" >/dev/null
        k -n "$NS" rollout status deployment/chaos-target --timeout=180s
        probe
        existing=$(k -n "$NS" get podchaos,networkchaos,stresschaos -o json)
        [[ $(jq '.items|length' <<< "$existing") -eq 0 ]] || die '空间仍有故障 CR，先恢复后再实验'
        RECOVERY_FUNCTION=recover_fault
        apply_file "$ATTEMPT/fault.json"
        failures=0 samples=0
        end=$((SECONDS + $(required .chaos.duration_seconds)))
        while [[ $SECONDS -lt $end ]]; do
            samples=$((samples+1)); ok=true
            if ! probe 2> "$ATTEMPT/probe-$samples.stderr"; then failures=$((failures+1)); ok=false; fi
            jq -n --arg time "$(date -u +%FT%TZ)" --argjson ok "$ok" '{at:$time,ok:$ok}' >> "$ATTEMPT/timeline.jsonl"
            jq -en --argjson bad "$failures" --argjson all "$samples" --argjson threshold "$threshold" '$bad/$all <= $threshold' >/dev/null || die '达到错误率停止阈值'
            sleep 2
        done
        recover_fault
        RECOVERY_FUNCTION=''
        k -n "$NS" rollout status deployment/chaos-target --timeout=180s
        probe
        ;;
esac
