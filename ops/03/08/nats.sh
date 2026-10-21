#!/usr/bin/env bash
set -euo pipefail
nats_cli() { k -n "$ns" exec -i nats-client -- timeout 30 nats --server tls://nats.cnpl03-08.svc.cluster.local:4222 --tlsca /tls/ca.crt --tlscert /tls/tls.crt --tlskey /tls/tls.key --creds /auth/user.creds --raw "$@"; }
if [[ $ACTION == nats ]]; then
    data_domains; component_chart cnpl03-nats nats "$ns"
    jq -n --arg image "$(image nats_cli)" --arg tls "$(required .middleware.tls_secret)" --arg auth "$(required .middleware.nats_context_secret)" '{apiVersion:"v1",kind:"Pod",metadata:{name:"nats-client"},spec:{containers:[{name:"client",image:$image,command:["sh","-c","sleep 86400"],volumeMounts:[{name:"tls",mountPath:"/tls",readOnly:true},{name:"auth",mountPath:"/auth",readOnly:true}],resources:{requests:{cpu:"10m",memory:"16Mi"},limits:{memory:"64Mi"}}}],volumes:[{name:"tls",secret:{secretName:$tls}},{name:"auth",secret:{secretName:$auth}}]}}' > "$ATTEMPT/nats-client.json"
    apply "$ATTEMPT/nats-client.json" "$ns"; k -n "$ns" wait --for=condition=Ready pod/nats-client --timeout=180s
else
    stream=CNPL03_${RUN//-/_}
    if [[ $ACTION == nats-test ]]; then
        nats_cli sub cnpl03.core --count 1 > "$ATTEMPT/pubsub.txt" & subscriber=$!
        sleep 2; nats_cli publish cnpl03.core "$RUN:core" >/dev/null
        wait "$subscriber"; grep -Fx "$RUN:core" "$ATTEMPT/pubsub.txt"
        nats_cli reply cnpl03.request pong --count 1 > "$ATTEMPT/responder.txt" & responder=$!
        sleep 2; [[ $(nats_cli request cnpl03.request ping) == pong ]] || die 'Request/Reply 不符'
        wait "$responder"
        config=$(jq -cn --arg stream "$stream" '{name:$stream,subjects:["cnpl03.events"],storage:"file",num_replicas:3,retention:"limits",discard:"old",max_bytes:16777216}')
        nats_cli request "\$JS.API.STREAM.CREATE.$stream" "$config" > "$ATTEMPT/stream-created.json"
        jq -e '.error==null and .config.num_replicas==3 and .config.storage=="file"' "$ATTEMPT/stream-created.json" >/dev/null
        for i in $(seq 1 20); do nats_cli request cnpl03.events "$RUN:$i" > "$ATTEMPT/ack-$i.json"; jq -e --arg stream "$stream" '.stream==$stream and .seq>0 and .error==null' "$ATTEMPT/ack-$i.json" >/dev/null; done
    else
        nats_cli request "\$JS.API.STREAM.INFO.$stream" '{}' > "$ATTEMPT/before.json"
        leader=$(jq -er .cluster.leader "$ATTEMPT/before.json")
        k -n "$ns" get pod "$leader" -o json | jq -e 'any(.metadata.ownerReferences[]?;.kind=="StatefulSet")' >/dev/null || die 'NATS 领导者不是受控 StatefulSet Pod'
        k -n "$ns" delete pod "$leader" --wait=false
        sleep 5
    fi
    nats_cli request "\$JS.API.STREAM.INFO.$stream" '{}' > "$ATTEMPT/stream-info.json"
    jq -e '.error==null and .state.messages==20' "$ATTEMPT/stream-info.json" >/dev/null || die 'JetStream 消息数量不符'
    for i in $(seq 1 20); do
        data=$(nats_cli request "\$JS.API.STREAM.MSG.GET.$stream" "{\"seq\":$i}" | jq -er '.message.data|@base64d')
        [[ $data == "$RUN:$i" ]] || die 'JetStream 序号或内容不符'
    done
    consumer=$(jq -cn --arg stream "$stream" '{stream_name:$stream,config:{durable_name:"CNPL03",ack_policy:"explicit",deliver_policy:"all",filter_subject:"cnpl03.events",ack_wait:5000000000,max_deliver:5}}')
    nats_cli request "\$JS.API.CONSUMER.DURABLE.CREATE.$stream.CNPL03" "$consumer" > "$ATTEMPT/consumer.json"
    jq -e '.error==null' "$ATTEMPT/consumer.json" >/dev/null
    if [[ $ACTION == nats-test ]]; then nats_cli consumer next "$stream" CNPL03 --count 20 --ack > "$ATTEMPT/replayed.txt"; fi
    nats_cli request "\$JS.API.CONSUMER.INFO.$stream.CNPL03" '{}' > "$ATTEMPT/consumer-state.json"
    jq -e '.num_ack_pending==0 and .num_pending==0' "$ATTEMPT/consumer-state.json" >/dev/null || die '持久消费者未完成确认'
fi
