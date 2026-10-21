#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P05/validate.sh" 05 ;;
    render) exec ruby "$P05/05/render.rb" "${2:-resources}" ;;
    install|configure|check|kibana-import) ;;
    *) die '用法：05/run.sh validate|render [resources|ilm|index-template|query|saved-objects]|install|configure|check|kibana-import' ;;
esac
start 05 "$action"
cluster_gate
ns=$(required .elk.namespace); es=$(required .elk.elasticsearch_name)
k -n "$ns" get elasticsearch "$es" -o json > "$ATTEMPT/elasticsearch.json"
jq -e --arg uid "$(required .elk.elasticsearch_uid)" '.metadata.uid==$uid and .status.health!="red" and .status.availableNodes>0' "$ATTEMPT/elasticsearch.json" >/dev/null || die 'ECK Elasticsearch 身份/健康不符，先完成 Phase 03'
prefix=cnpl05-$RUN; url=$(required .elk.url); config=$(required .elk.curl_config)
case "$action" in
    install)
        namespace "$(required .namespaces.logging)"
        ruby "$P05/05/render.rb" resources > "$ATTEMPT/logging.json"
        apply "$ATTEMPT/logging.json"
        k -n "$(required .namespaces.logging)" rollout status daemonset/fluent-bit --timeout=180s
        if [[ $(required .elk.route) == logstash ]]; then k -n "$(required .namespaces.logging)" rollout status deployment/logstash --timeout=300s; fi ;;
    configure)
        http "$config" "$url/_index_template" > "$ATTEMPT/existing-templates.json"
        jq -e --arg name "$prefix" --arg run "$RUN" 'all(.index_templates[] | select(.name==$name); .index_template._meta.cnpl_run==$run)' "$ATTEMPT/existing-templates.json" >/dev/null || die '同名模板不归本批次'
        http "$config" "$url/_ilm/policy" > "$ATTEMPT/existing-policies.json"
        jq -e --arg name "$prefix" --arg run "$RUN" '.[$name]==null or .[$name].policy._meta.cnpl_run==$run' "$ATTEMPT/existing-policies.json" >/dev/null || die '同名 ILM 不归本批次'
        ruby "$P05/05/render.rb" ilm > "$ATTEMPT/ilm.json"
        http "$config" "$url/_ilm/policy/$prefix" -H 'Content-Type: application/json' -X PUT --data-binary "@$ATTEMPT/ilm.json" > "$ATTEMPT/ilm-response.json"
        ruby "$P05/05/render.rb" index-template > "$ATTEMPT/template.json"
        http "$config" "$url/_index_template/$prefix" -H 'Content-Type: application/json' -X PUT --data-binary "@$ATTEMPT/template.json" > "$ATTEMPT/template-response.json" ;;
    kibana-import)
        ruby "$P05/05/render.rb" saved-objects > "$ATTEMPT/search.ndjson"
        http "$(required .elk.kibana_curl_config)" "$(required .elk.kibana_url)/api/saved_objects/_import" -H 'kbn-xsrf: cnpl05' -X POST -F "file=@$ATTEMPT/search.ndjson" > "$ATTEMPT/kibana-import.json"
        jq -e '.success==true' "$ATTEMPT/kibana-import.json" >/dev/null ;;
    check)
        ruby "$P05/05/render.rb" query > "$ATTEMPT/query.json"
        http "$config" "$url/$prefix-*/_search" -H 'Content-Type: application/json' -X POST --data-binary "@$ATTEMPT/query.json" > "$ATTEMPT/search.json"
        jq -e '.hits.total.value>0 and all(.hits.hits[]; ._source.trace_id!=null)' "$ATTEMPT/search.json" >/dev/null || die '未查到真实 Trace 日志'
        ! rg -q 'CNPL_TEST_SECRET_' "$ATTEMPT/search.json" || die '日志中发现未遮盖测试秘密'
        http "$config" "$url/$prefix-*/_ilm/explain" > "$ATTEMPT/ilm-explain.json"
        jq -e '.indices|length>0 and all(.[]; .managed==true)' "$ATTEMPT/ilm-explain.json" >/dev/null || die 'ILM 未实际接管索引'
        http "$config" "$url/$prefix-*/_stats/store,docs" > "$ATTEMPT/index-stats.json" ;;
esac
