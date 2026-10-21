#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
source "$P04/03/shared/api.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P04/validate.sh" 09 ;;
    render) shift; exec ruby "$P04/09/render.rb" "$@" ;;
    deploy|platform-api|catalog-root|request|check) ;;
    *) die '用法：09/run.sh validate|render template|crossplane|catalog-root|deploy|platform-api|catalog-root|request|check' ;;
esac
start 09 "$action"
if [[ $action == request ]]; then
    config=$(required .portal.curl_config); private_file "$config"
    file=$(required .portal.request_file)
    jq -e '.templateRef=="template:default/lab-service" and .values.environment=="dev" and (.values.name|test("^[a-z][a-z0-9-]{2,30}$"))' "$file" >/dev/null || die '自助请求越界'
    curl_safe "$config" 'https://backstage.k8s.internal.egon.top/api/scaffolder/v2/tasks' --request POST --header 'Content-Type: application/json' --data-binary "@$file" > "$ATTEMPT/task.json"
    printf '仅记录任务ID；需跟踪后续仓库/CI/MR/签名/平台依赖和健康。\n'
    exit
fi
case "$action" in
    deploy) material backstage >/dev/null; material crossplane >/dev/null ;;
    platform-api) function_image=$(image crossplane_function); postgres_image=$(image postgresql_cnpg) ;;
esac
cluster_gate
case "$action" in
    deploy) chart crossplane crossplane crossplane-system; chart backstage backstage platform-engineering ;;
    platform-api)
        private_temp
        jq --arg function "$function_image" --arg postgres "$postgres_image" '.render_images.crossplane_function=$function | .render_images.postgresql_cnpg=$postgres' "$INPUTS" > "$PRIVATE_TEMP/inputs.json"
        CNPL04_INPUTS="$PRIVATE_TEMP/inputs.json" render crossplane > "$ATTEMPT/platform-api.json"; apply "$ATTEMPT/platform-api.json" ;;
    catalog-root) render catalog-root > "$ATTEMPT/catalog-root.json"; apply "$ATTEMPT/catalog-root.json" ;;
    check)
        name=$(required .release.name)
        k -n apps-dev get devapplication "$name" -o json > "$ATTEMPT/service.json"
        jq -e 'any(.status.conditions[]; .type=="Ready" and .status=="True")' "$ATTEMPT/service.json" >/dev/null
        if [[ $(jq -r .spec.parameters.dataService "$ATTEMPT/service.json") == postgresql ]]; then
            k -n apps-dev get cluster.postgresql.cnpg.io "$name-db" -o json > "$ATTEMPT/database.json"
            jq -e 'any(.status.conditions[]; .type=="Ready" and .status=="True")' "$ATTEMPT/database.json" >/dev/null
            primary=$(jq -er .status.currentPrimary "$ATTEMPT/database.json")
            k -n apps-dev exec "$primary" -c postgres -- psql -U postgres -d app -tAc 'SELECT 1' > "$ATTEMPT/database-query.txt"
            [[ $(tr -d '[:space:]' < "$ATTEMPT/database-query.txt") == 1 ]] || die '数据库查询失败'
        fi ;;
esac
