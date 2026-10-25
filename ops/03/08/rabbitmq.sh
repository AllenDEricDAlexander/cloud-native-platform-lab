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
        source "$P03/lib/certificate-approval.sh"
        approve_certificate "$ns" cluster-operator-serving-cert
        k -n "$ns" rollout status deployment/rabbitmq-cluster-operator --timeout=180s
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
    rabbitmq-confirm) source "$P03/08/rabbit-confirm.sh" ;;
esac
