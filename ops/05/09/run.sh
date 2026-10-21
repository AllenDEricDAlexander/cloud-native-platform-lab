#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P05/validate.sh" 09 ;;
    archive) exec ruby "$P05/09/archive.rb" ;;
    evidence-report) exec ruby "$P05/09/evidence.rb" ;;
    pause|resume) exec bash "$P05/09/pause.sh" "$action" ;;
    regression|restore-dashboard) ;;
    *) die '用法：09/run.sh validate|archive|evidence-report|regression|restore-dashboard|pause|resume' ;;
esac
start 09 "$action"
if [[ $action == regression ]]; then
    bash "$P05/01/run.sh" verify > "$ATTEMPT/zabbix.txt" 2>&1
    bash "$P05/02/run.sh" check > "$ATTEMPT/metrics.txt" 2>&1
    bash "$P05/03/run.sh" check > "$ATTEMPT/infrastructure.txt" 2>&1
    bash "$P05/04/run.sh" trace-check > "$ATTEMPT/trace.txt" 2>&1
    selected=$(required .handoff.selected_log_backend)
    case "$selected" in elk) bash "$P05/05/run.sh" check > "$ATTEMPT/logs.txt" 2>&1 ;; loki) bash "$P05/06/run.sh" check > "$ATTEMPT/logs.txt" 2>&1 ;; *) die '主日志后端必须明确' ;; esac
    bash "$P05/07/run.sh" check > "$ATTEMPT/slo.txt" 2>&1
    bash "$P05/08/run.sh" cost-check > "$ATTEMPT/cost.txt" 2>&1
else
    private_temp
    config=$(required .metrics.grafana_curl_config); url=$(required .metrics.grafana_url)
    code=$(http "$config" "$url/api/dashboards/uid/cnpl05-platform" --output "$PRIVATE_TEMP/current.json" --write-out '%{http_code}') || [[ $code == 404 ]] || die '不能核对现有 Dashboard'
    if [[ $code != 404 ]]; then
        jq -e --arg tag "cnpl05-$RUN" '.dashboard.tags|index($tag)!=null' "$PRIVATE_TEMP/current.json" >/dev/null || die '拒绝覆盖其他批次 Dashboard'
    fi
    jq --arg run "cnpl05-$RUN" '{dashboard:(. + {tags:(.tags+[$run]|unique)}),overwrite:true}' "$P05/02/dashboard.json" > "$ATTEMPT/dashboard-import.json"
    http "$config" "$url/api/dashboards/db" -H 'Content-Type: application/json' -X POST --data-binary "@$ATTEMPT/dashboard-import.json" > "$ATTEMPT/dashboard-restored.json"
    jq -e '.status=="success" and .uid=="cnpl05-platform"' "$ATTEMPT/dashboard-restored.json" >/dev/null
fi
