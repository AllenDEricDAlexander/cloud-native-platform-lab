#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P05/validate.sh" 06 ;;
    render) exec ruby "$P05/06/render.rb" "${2:-resources}" ;;
    compare) exec ruby "$P05/06/compare.rb" ;;
    fault) exec bash "$P05/lib/fault.sh" 06 ;;
    install|check|profile-check) ;;
    *) die '用法：06/run.sh validate|render [resources|loki|tempo|pyroscope]|install|check|profile-check|compare|fault' ;;
esac
start 06 "$action"
cluster_gate
if [[ $action == install ]]; then
    ns=$(required .namespaces.backends); namespace "$ns"
    ruby "$P05/06/render.rb" > "$ATTEMPT/backends.json"
    apply "$ATTEMPT/backends.json"
    for backend in loki tempo pyroscope; do k -n "$ns" rollout status "deployment/$backend" --timeout=300s; done
elif [[ $action == profile-check ]]; then
    jq -n --arg type "$(required .backends.profile_type_id)" --arg selector "$(required .backends.profile_selector)" '{profileTypeID:$type,labelSelector:$selector,start:((now-300)*1000|floor),end:(now*1000|floor),step:10}' > "$ATTEMPT/profile-query.json"
    http "$(required .backends.curl_config)" "$(required .backends.pyroscope_url)/querier.v1.QuerierService/SelectSeries" -H 'Content-Type: application/json' -X POST --data-binary "@$ATTEMPT/profile-query.json" > "$ATTEMPT/profile-series.json"
    jq -e '.series|length>0' "$ATTEMPT/profile-series.json" >/dev/null || die '没有真实 profiling 数据'
else
    id=$(required .otel.trace_id); [[ $id =~ ^[a-f0-9]{32}$ ]] || die 'trace_id 无效'
    http "$(required .backends.curl_config)" "$(required .backends.loki_url)/loki/api/v1/query_range" --get --data-urlencode "query={service_name!=\"\"} | json | trace_id=\"$id\"" --data-urlencode 'limit=100' > "$ATTEMPT/logs.json"
    jq -e '.status=="success" and (.data.result|length)>0' "$ATTEMPT/logs.json" >/dev/null || die '无关联日志'
    ! rg -q 'CNPL_TEST_SECRET_' "$ATTEMPT/logs.json" || die '日志存在未遮盖测试秘密'
    http "$(required .backends.curl_config)" "$(required .backends.tempo_url)/api/traces/$id" -H 'Accept: application/json' > "$ATTEMPT/trace.json"
    jq -e '(.batches // .resourceSpans)|length>0' "$ATTEMPT/trace.json" >/dev/null || die '无真实 Trace'
fi
