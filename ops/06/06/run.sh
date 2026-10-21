#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P06/validate.sh" 06 ;;
    render) export STAGE=06; exec ruby "$P06/06/render.rb" ;;
    install|apply|check|traffic|request|events|cleanup-plan) ;;
    *) die '用法：06/run.sh validate|render|install <knative_serving|knative_network|knative_eventing>|apply|check|traffic|request|events|cleanup-plan' ;;
esac
start 06 "$action"
if [[ $action == cleanup-plan ]]; then cleanup_plan; exit; fi
if [[ $action == request || $action == events ]]; then
    private_file "$(required .serverless.curl_config)"
    if [[ $action == request ]]; then url=$(required .serverless.url); else url=$(required .serverless.broker_url); fi
    [[ $url =~ ^https://[a-z0-9.-]+\.internal\.egon\.top(:[0-9]+)?(/.*)?$ ]] || die '测试入口必须为内网 HTTPS'
    if [[ $action == request ]]; then
        curl --config "$(required .serverless.curl_config)" --proto '=https' --fail --silent --show-error --max-time 30 --output /dev/null --write-out '%{http_code} %{time_starttransfer} %{time_total}\n' "$url" > "$ATTEMPT/request.txt"
    else
        # 同一 CloudEvents ID 重放两次；业务效果另用 05/messages.rb 对照。
        for attempt in 1 2; do
            curl --config "$(required .serverless.curl_config)" --proto '=https' --fail --silent --show-error --max-time 30 --output /dev/null --write-out '%{http_code}\n' "$url" -H 'Content-Type: application/json' -H 'Ce-Specversion: 1.0' -H 'Ce-Type: cnpl.lab' -H 'Ce-Source: /cnpl06' -H "Ce-Id: $RUN-001" --data '{"order_id":1}' > "$ATTEMPT/event-$attempt.txt"
        done
    fi
    exit
fi
if [[ $action == install ]]; then
    component=${2:-}; case "$component" in knative_serving|knative_network|knative_eventing) ;; *) die '未知 Knative 组件' ;; esac
    ruby "$P06/lib/config.rb" material "$component" >/dev/null
fi
cluster_gate
case "$action" in
    install) install_component "$component" ;;
    apply) render > "$ATTEMPT/serverless.json"; apply_file "$ATTEMPT/serverless.json" ;;
    check)
        check_namespace
        for ref in services.serving.knative.dev/hello brokers.eventing.knative.dev/lab-broker triggers.eventing.knative.dev/orders; do k -n "$NS" wait "$ref" --for=condition=Ready --timeout=300s; done
        k -n "$NS" get revisions.serving.knative.dev,services.serving.knative.dev,brokers.eventing.knative.dev,triggers.eventing.knative.dev -o json | redact_objects > "$ATTEMPT/readiness.json"
        ;;
    traffic)
        state=$(owned services.serving.knative.dev hello "$NS")
        stable=$(required .serverless.stable_revision); canary=$(required .serverless.canary_revision)
        [[ $stable != "$canary" ]] || die '两个 Revision 必须不同'
        for revision in "$stable" "$canary"; do
            k -n "$NS" get revision "$revision" -o json | jq -e --arg run "$RUN" '.metadata.labels["serving.knative.dev/service"]=="hello" and .metadata.labels["cnpl.io/run"]==$run' >/dev/null || die 'Revision 归属不符'
        done
        jq -n --arg uid "$(jq -r .metadata.uid <<< "$state")" --arg rv "$(jq -r .metadata.resourceVersion <<< "$state")" --arg stable "$stable" --arg canary "$canary" '[{op:"test",path:"/metadata/uid",value:$uid},{op:"test",path:"/metadata/resourceVersion",value:$rv},{op:"add",path:"/spec/traffic",value:[{revisionName:$stable,percent:90},{revisionName:$canary,percent:10}]}]' > "$ATTEMPT/traffic-patch.json"
        k -n "$NS" patch services.serving.knative.dev hello --type=json --patch-file "$ATTEMPT/traffic-patch.json"
        ;;
esac
