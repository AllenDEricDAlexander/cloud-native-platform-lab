#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P05/validate.sh" 03 ;;
    render) exec ruby "$P05/03/render.rb" ;;
    fault) exec bash "$P05/lib/fault.sh" 03 ;;
    configure|check|zabbix-verify) ;;
    *) die '用法：03/run.sh validate|render|configure|check|zabbix-verify|fault' ;;
esac
[[ $action != zabbix-verify ]] || exec bash "$P05/01/run.sh" verify
start 03 "$action"
cluster_gate
if [[ $action == configure ]]; then
    ruby "$P05/03/render.rb" > "$ATTEMPT/sources.json"
    apply "$ATTEMPT/sources.json"
else
    ruby "$P05/03/check-input.rb"
    while IFS=$'\t' read -r id expr; do
        query "$expr" "$ATTEMPT/$id-$(printf '%s' "$expr" | shasum -a 256 | cut -c1-10).json"
    done < <(jq -r '.sources[] | .id as $id | .checks[] | [$id,.] | @tsv' "$INPUTS")
    while IFS= read -r id; do
        query "up{cnpl_source=\"$id\"}" "$ATTEMPT/$id-up.json"
        jq -e 'all(.data.result[]; .value[1]=="1")' "$ATTEMPT/$id-up.json" >/dev/null || die "采集失败：$id"
    done < <(jq -r '.sources[].id' "$INPUTS")
fi
