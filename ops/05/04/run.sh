#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P05/validate.sh" 04 ;;
    render) exec ruby "$P05/04/render.rb" "${2:-resources}" ;;
    fault) exec bash "$P05/lib/fault.sh" 04 ;;
    install|check-config|trace-check|scenario) ;;
    *) die '用法：04/run.sh validate|render [resources|agent-config|gateway-config]|check-config|install|scenario|trace-check|fault' ;;
esac
start 04 "$action"
if [[ $action == check-config ]]; then
    info=$(material otel_collector_cli); tool=$(jq -er .file <<< "$info")
    private_temp
    for role in agent gateway; do
        ruby "$P05/04/render.rb" "$role-config" > "$PRIVATE_TEMP/$role.yaml"
        "$tool" validate --config="$PRIVATE_TEMP/$role.yaml" > "$ATTEMPT/$role-validate.txt" 2>&1
    done
    exit
fi
cluster_gate
case "$action" in
    install)
        ns=$(required .namespaces.telemetry); namespace "$ns"
        ruby "$P05/04/render.rb" > "$ATTEMPT/collector.json"
        apply "$ATTEMPT/collector.json"
        k -n "$ns" rollout status daemonset/otel-agent --timeout=180s
        k -n "$ns" rollout status deployment/otel-gateway --timeout=180s ;;
    scenario)
        file=$(required .otel.scenario_file)
        verify_file "$file" "$(required .otel.scenario_sha256)"
        ruby "$P05/04/scenario.rb" "$file" "$ATTEMPT" ;;
    trace-check)
        id=$(required .otel.trace_id); [[ $id =~ ^[a-f0-9]{32}$ ]] || die 'trace_id 无效'
        http "$(required .backends.curl_config)" "$(required .backends.tempo_url)/api/traces/$id" -H 'Accept: application/json' > "$ATTEMPT/trace.json"
        other=$(required .otel.async_trace_id); [[ $other =~ ^[a-f0-9]{32}$ ]] || die 'async_trace_id 无效'
        http "$(required .backends.curl_config)" "$(required .backends.tempo_url)/api/traces/$other" -H 'Accept: application/json' > "$ATTEMPT/async-trace.json"
        ruby "$P05/04/verify-trace.rb" "$ATTEMPT/trace.json" "$ATTEMPT/async-trace.json" > "$ATTEMPT/trace-check.txt" ;;
esac
