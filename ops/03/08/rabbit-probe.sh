#!/usr/bin/env sh
# 在一次性测试 Job 内运行；HTTP 数据校验不冒充 AMQP publisher confirm。
set -eu
umask 077
work=$(mktemp -d); trap 'rm -rf -- "$work"' EXIT
endpoint=https://rabbitmq.cnpl03-08.svc.cluster.local:15671
mode=${CNPL_MODE:-full}; queue=cnpl03.${CNPL_RUN}.probe
if [ "$mode" = hold ] || [ "$mode" = verify ]; then queue=cnpl03.${CNPL_RUN}.fault; fi
user=$(cat /bootstrap/username); password=$(cat /bootstrap/password)
case "$user$password" in *'"'*|*'\'*|*'
'*) echo '默认用户凭据不能安全转存 curl 配置' >&2; exit 1;; esac
printf 'silent\nshow-error\nfail-with-body\ncacert = "/tls/ca.crt"\ncert = "/tls/tls.crt"\nkey = "/tls/tls.key"\nuser = "%s:%s"\n' "$user" "$password" > "$work/admin.conf"
api() {
    config=$1 method=$2 path=$3 body=$4
    if curl --config "$config" --request "$method" --header 'Content-Type: application/json' --data-binary "@$body" "$endpoint$path" > "$work/response.json"; then
        cat "$work/response.json"
    else
        printf 'HTTP API 失败：%s %s\n' "$method" "$path" >&2
        jq --rawfile app /app/password --rawfile admin /bootstrap/password '{error,reason}|walk(if type=="string" then split($app|rtrimstr("\n"))|join("[redacted]")|split($admin|rtrimstr("\n"))|join("[redacted]") else . end)' "$work/response.json" >&2
        return 1
    fi
}
printf '{}' > "$work/empty.json"
api "$work/admin.conf" PUT /api/vhosts/cnpl03 "$work/empty.json" >/dev/null
jq -n --rawfile p /app/password '{password:($p|rtrimstr("\n")),tags:"management"}' > "$work/user.json"
api "$work/admin.conf" PUT /api/users/cnpl03 "$work/user.json" >/dev/null
printf '{"configure":"^cnpl03.*","write":"^$|^amq\\\\.default$|^cnpl03.*","read":"^cnpl03.*"}' > "$work/permissions.json"
api "$work/admin.conf" PUT /api/permissions/cnpl03/cnpl03 "$work/permissions.json" >/dev/null
printf 'silent\nshow-error\nfail-with-body\ncacert = "/tls/ca.crt"\ncert = "/tls/tls.crt"\nkey = "/tls/tls.key"\nuser = "cnpl03:%s"\n' "$(cat /app/password)" > "$work/app.conf"
printf '{"type":"direct","durable":true,"auto_delete":false,"internal":false,"arguments":{}}' > "$work/exchange.json"
api "$work/app.conf" PUT /api/exchanges/cnpl03/cnpl03.dlx "$work/exchange.json" >/dev/null
jq -n '{durable:true,auto_delete:false,arguments:{"x-queue-type":"quorum","x-dead-letter-exchange":"cnpl03.dlx","x-dead-letter-routing-key":"dead"}}' > "$work/queue.json"
api "$work/app.conf" PUT "/api/queues/cnpl03/$queue" "$work/queue.json" >/dev/null
printf '{"durable":true,"auto_delete":false,"arguments":{"x-queue-type":"quorum"}}' > "$work/dlq.json"
api "$work/app.conf" PUT /api/queues/cnpl03/cnpl03.dead "$work/dlq.json" >/dev/null
printf '{"routing_key":"dead","arguments":{}}' > "$work/bind.json"
api "$work/app.conf" POST /api/bindings/cnpl03/e/cnpl03.dlx/q/cnpl03.dead "$work/bind.json" >/dev/null
if [ "$mode" != verify ]; then
    attempt=0
    while :; do
        curl --config "$work/app.conf" "$endpoint/api/queues/cnpl03/$queue" > "$work/queue-state.json"
        if jq -e '.messages==0' "$work/queue-state.json" >/dev/null; then break; fi
        if jq -e '.messages!=null and .messages>0' "$work/queue-state.json" >/dev/null; then echo '测试队列有旧消息，保留现场' >&2; exit 1; fi
        attempt=$((attempt+1)); [ "$attempt" -lt 30 ] || { echo '测试队列计数尚未可读' >&2; exit 1; }
        sleep 1
    done
    i=1; while [ "$i" -le 20 ]; do
        jq -n --arg route "$queue" --arg payload "$CNPL_RUN:$i" '{properties:{delivery_mode:2},routing_key:$route,payload:$payload,payload_encoding:"string"}' > "$work/publish.json"
        api "$work/app.conf" POST /api/exchanges/cnpl03/amq.default/publish "$work/publish.json" | jq -e '.routed==true' >/dev/null
        i=$((i+1))
    done
fi
if [ "$mode" = hold ]; then printf 'PASS 持久消息已入 quorum queue，等待故障后 verify\n'; exit; fi
printf '{"count":1,"ackmode":"ack_requeue_true","encoding":"auto","truncate":10000}' > "$work/get.json"
api "$work/app.conf" POST "/api/queues/cnpl03/$queue/get" "$work/get.json" > "$work/first.json"
jq -e 'length==1' "$work/first.json" >/dev/null
first=$(jq -r '.[0].payload' "$work/first.json")
printf '{"count":1,"ackmode":"ack_requeue_false","encoding":"auto","truncate":10000}' > "$work/get.json"
api "$work/app.conf" POST "/api/queues/cnpl03/$queue/get" "$work/get.json" > "$work/redelivered.json"
jq -e --arg first "$first" 'length==1 and .[0].redelivered==true and .[0].payload==$first' "$work/redelivered.json" >/dev/null
printf '%s\n' "$first" > "$work/ids"
printf '{"count":20,"ackmode":"ack_requeue_false","encoding":"auto","truncate":10000}' > "$work/get.json"
api "$work/app.conf" POST "/api/queues/cnpl03/$queue/get" "$work/get.json" | jq -er '.[].payload' >> "$work/ids"
[ "$(sort -u "$work/ids" | wc -l | tr -d ' ')" = 20 ] || exit 1
i=1; while [ "$i" -le 20 ]; do printf '%s:%s\n' "$CNPL_RUN" "$i"; i=$((i+1)); done | sort > "$work/expected"
sort "$work/ids" > "$work/actual"; cmp "$work/expected" "$work/actual"
jq -n --arg route "$queue" '{properties:{delivery_mode:2},routing_key:$route,payload:"dead-letter-probe",payload_encoding:"string"}' > "$work/publish.json"
api "$work/app.conf" POST /api/exchanges/cnpl03/amq.default/publish "$work/publish.json" | jq -e '.routed==true' >/dev/null
printf '{"count":1,"ackmode":"reject_requeue_false","encoding":"auto"}' > "$work/get.json"
api "$work/app.conf" POST "/api/queues/cnpl03/$queue/get" "$work/get.json" >/dev/null
printf '{"count":1,"ackmode":"ack_requeue_false","encoding":"auto"}' > "$work/get.json"
api "$work/app.conf" POST /api/queues/cnpl03/cnpl03.dead/get "$work/get.json" | jq -e '.[0].payload=="dead-letter-probe"' >/dev/null
printf 'PASS quorum queue 20 个业务 ID、重投、确认消费与死信；AMQP confirm 另测\n'
