#!/usr/bin/env bash
set -euo pipefail
rabbit_job() {
    local mode=$1 name
    name=rabbit-probe-$mode-$(date -u +%H%M%S)
    k -n "$ns" create configmap rabbit-probe --from-file=probe.sh="$P03/08/rabbit-probe.sh" --dry-run=client -o json > "$ATTEMPT/rabbit-script.json"
    apply "$ATTEMPT/rabbit-script.json" "$ns"
    jq -n --arg name "$name" --arg run "$RUN" --arg mode "$mode" --arg image "$(image message_tools)" --arg tls "$(required .middleware.tls_secret)" '{apiVersion:"batch/v1",kind:"Job",metadata:{name:$name},spec:{backoffLimit:0,activeDeadlineSeconds:180,template:{spec:{restartPolicy:"Never",containers:[{name:"probe",image:$image,command:["sh","/script/probe.sh"],env:[{name:"CNPL_RUN",value:$run},{name:"CNPL_MODE",value:$mode}],volumeMounts:[{name:"script",mountPath:"/script",readOnly:true},{name:"bootstrap",mountPath:"/bootstrap",readOnly:true},{name:"app",mountPath:"/app",readOnly:true},{name:"tls",mountPath:"/tls",readOnly:true}],resources:{requests:{cpu:"10m",memory:"32Mi"},limits:{memory:"128Mi"}}}],volumes:[{name:"script",configMap:{name:"rabbit-probe"}},{name:"bootstrap",secret:{secretName:"rabbitmq-default-user"}},{name:"app",secret:{secretName:"cache-auth"}},{name:"tls",secret:{secretName:$tls}}]}}}}' > "$ATTEMPT/$name.json"
    apply "$ATTEMPT/$name.json" "$ns"
    k -n "$ns" wait --for=condition=Complete "job/$name" --timeout=210s
    k -n "$ns" logs "job/$name" | tee "$ATTEMPT/$name.txt"
}
case "$ACTION" in
    rabbitmq)
        data_domains; component_manifest rabbitmq_operator "$ns"
        yaml_json "$P03/08/rabbitmq.yaml" | jq --arg image "$(image rabbitmq)" --arg class "$SC_RBD" --arg tls "$(required .middleware.tls_secret)" '.items[0].spec.image=$image|.items[0].spec.persistence.storageClassName=$class|.items[0].spec.tls.secretName=$tls|.items[0].spec.tls.caSecretName=$tls' > "$ATTEMPT/rabbitmq.json"
        apply "$ATTEMPT/rabbitmq.json" "$ns"
        k -n "$ns" wait --for=condition=AllReplicasReady rabbitmqcluster/rabbitmq --timeout=900s
        ;;
    rabbitmq-test) rabbit_job full ;;
    rabbitmq-failover)
        rabbit_job hold
        pods=$(k -n "$ns" get pods -l app.kubernetes.io/name=rabbitmq -o json)
        jq -e '.items|length==3 and all(.[];.status.phase=="Running")' <<< "$pods" >/dev/null || die 'RabbitMQ 初始多数派不满足'
        pod=$(jq -r '.items|sort_by(.metadata.name)|.[0].metadata.name' <<< "$pods")
        k -n "$ns" delete pod "$pod" --wait=false
        k -n "$ns" rollout status statefulset/rabbitmq-server --timeout=600s
        rabbit_job verify
        ;;
    rabbitmq-confirm)
        info=$(material rabbitmq_perf)
        command=$(jq -ec '.command|select(type=="array" and length>0)' <<< "$info") || die '锁定 perf-test 镜像的实际 Java 入口 command'
        work=$(mktemp -d); CLEANUP_DIRECTORY=$work
        password=$(required .middleware.password_file); private_file "$password"
        ruby -e 'p=File.read(ARGV[0]).strip; abort unless p.match?(/\A[a-f0-9]{32,128}\z/); print "amqps://cnpl03:#{p}@rabbitmq.cnpl03-08.svc.cluster.local:5671/cnpl03"' "$password" > "$work/uri"
        secret_from_files "$ns" rabbit-perf "uri=$work/uri"
        name=rabbit-confirm-$(date -u +%H%M%S)
        jq -n --arg name "$name" --arg image "$(image rabbitmq_perf)" --argjson command "$command" --arg tls "$(required .middleware.tls_secret)" '{apiVersion:"batch/v1",kind:"Job",metadata:{name:$name},spec:{backoffLimit:0,activeDeadlineSeconds:180,template:{spec:{restartPolicy:"Never",initContainers:[{name:"trust",image:$image,command:["keytool","-importcert","-noprompt","-alias","rabbit-ca","-file","/tls/ca.crt","-keystore","/work/trust.p12","-storetype","PKCS12","-storepass","changeit"],volumeMounts:[{name:"tls",mountPath:"/tls",readOnly:true},{name:"work",mountPath:"/work"}]}],containers:[{name:"confirm",image:$image,command:$command,args:["--confirm","1","--qos","1","--queue","cnpl03.confirm","--queue-args","x-queue-type=quorum","--flag","persistent","--producers","1","--consumers","1","--pmessages","20","--cmessages","20","--use-default-ssl-context"],env:[{name:"URI",valueFrom:{secretKeyRef:{name:"rabbit-perf",key:"uri"}}},{name:"RABBITMQ_PERF_TEST_URI",valueFrom:{secretKeyRef:{name:"rabbit-perf",key:"uri"}}},{name:"JAVA_TOOL_OPTIONS",value:"-Djavax.net.ssl.trustStore=/work/trust.p12 -Djavax.net.ssl.trustStoreType=PKCS12 -Djavax.net.ssl.trustStorePassword=changeit"}],volumeMounts:[{name:"work",mountPath:"/work"}]}],volumes:[{name:"tls",secret:{secretName:$tls}},{name:"work",emptyDir:{}}]}}}}' > "$ATTEMPT/confirm.json"
        apply "$ATTEMPT/confirm.json" "$ns"
        k -n "$ns" wait --for=condition=Complete "job/$name" --timeout=210s
        # perf-test 版本若会打印 URI，日志须在受控端脱敏后保存。
        printf 'perf-test 已退出；按锁定版本检查 20 条 confirm/ack 计数，原始日志含 URI 时禁止归档。\n'
        ;;
esac
