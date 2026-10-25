#!/usr/bin/env bash
set -euo pipefail
kafka_cli() { local command=$1; shift; k -n "$ns" exec -i kafka-client -- "/opt/kafka/bin/$command" --bootstrap-server kafka-kafka-bootstrap:9093 "$@"; }
if [[ $ACTION == kafka ]]; then
    data_domains; component_chart cnpl03-strimzi strimzi "$ns"
    info=$(material kafka)
    yaml_json "$P03/08/kafka.yaml" | jq --arg image "$(image kafka)" --arg version "$(jq -r .version <<< "$info")" --arg metadata "$(required .middleware.kafka_metadata_version)" --arg class "$SC_RBD" '.items|=map(if .kind=="Kafka" then .spec.kafka.image=$image|.spec.kafka.version=$version|.spec.kafka.metadataVersion=$metadata elif .kind=="KafkaNodePool" then .spec.storage.volumes[0].class=$class else . end)' > "$ATTEMPT/kafka.json"
    apply "$ATTEMPT/kafka.json" "$ns"
    k -n "$ns" wait --for=condition=Ready kafka/kafka --timeout=900s
    k -n "$ns" wait --for=condition=Ready kafkauser/cnpl03-client --timeout=180s
    jq -n --arg image "$(image kafka)" '{apiVersion:"v1",kind:"Pod",metadata:{name:"kafka-client"},spec:{containers:[{name:"client",image:$image,command:["sh","-ceu","umask 077; printf \"security.protocol=SSL\\nssl.endpoint.identification.algorithm=https\\nssl.keystore.type=PKCS12\\nssl.keystore.location=/auth/user.p12\\nssl.keystore.password=%s\\nssl.truststore.type=PKCS12\\nssl.truststore.location=/ca/ca.p12\\nssl.truststore.password=%s\\n\" \"$(cat /auth/user.password)\" \"$(cat /ca/ca.password)\" > /tmp/client.properties; sleep 86400"],resources:{requests:{cpu:"10m",memory:"128Mi"},limits:{memory:"512Mi"}},volumeMounts:[{name:"auth",mountPath:"/auth",readOnly:true},{name:"ca",mountPath:"/ca",readOnly:true}]}],volumes:[{name:"auth",secret:{secretName:"cnpl03-client"}},{name:"ca",secret:{secretName:"kafka-cluster-ca-cert"}}]}}' > "$ATTEMPT/kafka-client.json"
    apply "$ATTEMPT/kafka-client.json" "$ns"; k -n "$ns" wait --for=condition=Ready pod/kafka-client --timeout=180s
elif [[ $ACTION == kafka-test || $ACTION == kafka-failover ]]; then
    topic=cnpl03-$RUN-$(date -u +%Y%m%d%H%M%S); group=$topic-group
    kafka_cli kafka-topics.sh --command-config /tmp/client.properties --create --topic "$topic" --partitions 3 --replication-factor 3 --config min.insync.replicas=2 > "$ATTEMPT/topic.txt"
    if [[ $ACTION == kafka-failover ]]; then
        pods=$(k -n "$ns" get pods -l strimzi.io/pool-name=brokers -o json)
        jq -e '.items|length==3 and all(.[];.status.phase=="Running")' <<< "$pods" >/dev/null || die 'Broker 基线不足'
        pod=$(jq -r '.items|sort_by(.metadata.name)|.[0].metadata.name' <<< "$pods")
        k -n "$ns" delete pod "$pod" --wait=false
    fi
    for i in $(seq 1 20); do printf '%s:%06d\n' "$RUN" "$i"; done > "$ATTEMPT/expected.txt"
    k -n "$ns" exec -i kafka-client -- /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server kafka-kafka-bootstrap:9093 --topic "$topic" --command-config /tmp/client.properties --command-property acks=all --command-property enable.idempotence=true --command-property delivery.timeout.ms=60000 < "$ATTEMPT/expected.txt" > "$ATTEMPT/producer.txt"
    kafka_cli kafka-console-consumer.sh --topic "$topic" --group "$group" --from-beginning --max-messages 20 --timeout-ms 60000 --command-config /tmp/client.properties > "$ATTEMPT/consumed.txt"
    sort "$ATTEMPT/expected.txt" > "$ATTEMPT/expected-sorted.txt"; sort "$ATTEMPT/consumed.txt" > "$ATTEMPT/consumed-sorted.txt"
    cmp "$ATTEMPT/expected-sorted.txt" "$ATTEMPT/consumed-sorted.txt"
    [[ $(sort -u "$ATTEMPT/consumed.txt" | wc -l | tr -d ' ') == 20 ]] || die '消息丢失或重复'
    kafka_cli kafka-consumer-groups.sh --command-config /tmp/client.properties --describe --group "$group" > "$ATTEMPT/offsets.txt"
    jq -n --arg topic "$topic" --arg group "$group" '{topic:$topic,group:$group}' > "$P03/08/records/$RUN/kafka-latest.json"
    k -n "$ns" wait --for=condition=Ready kafka/kafka --timeout=600s
else
    latest=$(cat "$P03/08/records/$RUN/kafka-latest.json")
    topic=$(jq -er .topic <<< "$latest"); group=$(jq -er .group <<< "$latest")
    for i in $(seq 21 40); do printf '%s:%06d\n' "$RUN" "$i"; done | k -n "$ns" exec -i kafka-client -- /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server kafka-kafka-bootstrap:9093 --topic "$topic" --command-config /tmp/client.properties --command-property acks=all --command-property enable.idempotence=true
    kafka_cli kafka-consumer-groups.sh --command-config /tmp/client.properties --describe --group "$group" > "$ATTEMPT/lag.txt"
    awk -v topic="$topic" '$2==topic && $6~/^[0-9]+$/ {lag+=$6} END {exit !(lag>=20)}' "$ATTEMPT/lag.txt" || die '未观察到预期积压'
fi
