#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P05/validate.sh" 02 ;;
    render) exec ruby "$P05/02/render.rb" "${2:-resources}" ;;
    fault) exec bash "$P05/lib/fault.sh" 02 ;;
    install|configure|check|alert-test|check-rules) ;;
    *) die '用法：02/run.sh validate|render [values|resources]|install|configure|check|alert-test|fault|check-rules' ;;
esac
start 02 "$action"
if [[ $action == check-rules ]]; then
    info=$(material prometheus_tools); tool=$(jq -er .file <<< "$info")
    "$tool" check rules "$P05/02/rules.yaml" > "$ATTEMPT/promtool.txt"
    exit
fi
cluster_gate
ns=$(required .namespaces.metrics)
if [[ $action == install ]]; then
    private_temp
    ruby "$P05/02/render.rb" values > "$PRIVATE_TEMP/values.yaml"
    chart prometheus cnpl05 "$ns" "$PRIVATE_TEMP/values.yaml"
elif [[ $action == configure ]]; then
    ruby "$P05/02/render.rb" > "$ATTEMPT/resources.json"
    apply "$ATTEMPT/resources.json"
elif [[ $action == alert-test ]]; then
    url=$(required .metrics.alertmanager_url); config=$(required .metrics.alertmanager_curl_config)
    jq -n --arg start "$(date -u +%FT%TZ)" --arg run "$RUN" '[{labels:{alertname:"CNPL05NotificationTest",severity:"warning",service:"test",environment:"lab",team:"platform",run:$run},annotations:{summary:"Bounded notification test; verify receiver and resolved delivery"},startsAt:$start,endsAt:(now+90 | strftime("%Y-%m-%dT%H:%M:%SZ"))}]' > "$ATTEMPT/alerts.json"
    http "$config" "$url/api/v2/alerts" -H 'Content-Type: application/json' -X POST --data-binary "@$ATTEMPT/alerts.json" > "$ATTEMPT/notification-response.json"
    printf '测试事件 90 秒内过期；接收方确认 firing/resolved 后才可判定通知通过。\n'
else
    query 'up' "$ATTEMPT/up.json"
    jq -e 'all(.data.result[]; .value[1]=="1")' "$ATTEMPT/up.json" >/dev/null || die '存在抓取失败目标'
    query 'kube_node_info' "$ATTEMPT/kubernetes.json"
    query 'node_memory_MemAvailable_bytes' "$ATTEMPT/node.json"
    query 'prometheus_build_info' "$ATTEMPT/self.json"
    http "$(required .metrics.grafana_curl_config)" "$(required .metrics.grafana_url)/api/health" > "$ATTEMPT/grafana.json"
    jq -e '.database=="ok"' "$ATTEMPT/grafana.json" >/dev/null
    http "$(required .metrics.alertmanager_curl_config)" "$(required .metrics.alertmanager_url)/api/v2/status" > "$ATTEMPT/alertmanager.json"
fi
