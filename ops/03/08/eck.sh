#!/usr/bin/env bash
set -euo pipefail
if [[ $ACTION == eck ]]; then
    data_domains; component_chart cnpl03-eck eck "$ns"
    info=$(material elasticsearch)
    jq -n --arg image "$(image elasticsearch)" --arg version "$(jq -r .version <<< "$info")" --arg class "$SC_RBD" '{apiVersion:"elasticsearch.k8s.elastic.co/v1",kind:"Elasticsearch",metadata:{name:"search"},spec:{version:$version,image:$image,nodeSets:[{name:"data",count:3,config:{"node.store.allow_mmap":false},podTemplate:{spec:{nodeSelector:{"cnpl.io/phase03-data":"true"},tolerations:[{operator:"Exists",effect:"NoSchedule"}],containers:[{name:"elasticsearch",resources:{requests:{cpu:"100m",memory:"1Gi"},limits:{memory:"1Gi"}}}],affinity:{podAntiAffinity:{requiredDuringSchedulingIgnoredDuringExecution:[{topologyKey:"cnpl.io/esxi",labelSelector:{matchLabels:{"elasticsearch.k8s.elastic.co/cluster-name":"search"}}}]}}}},volumeClaimTemplates:[{metadata:{name:"elasticsearch-data"},spec:{storageClassName:$class,accessModes:["ReadWriteOnce"],resources:{requests:{storage:"2Gi"}}}}]}]}}' > "$ATTEMPT/search.json"
    apply "$ATTEMPT/search.json" "$ns"
    wait_json 900 '.status.health=="green"' k -n "$ns" get elasticsearch search -o json
else
    k -n "$ns" get elasticsearch search -o json > "$ATTEMPT/search.json"
    jq -e '.status.health=="green" and .status.availableNodes==3' "$ATTEMPT/search.json" >/dev/null
    k -n "$ns" create configmap eck-probe --from-file=probe.sh="$P03/08/eck-probe.sh" --dry-run=client -o json > "$ATTEMPT/eck-script.json"
    apply "$ATTEMPT/eck-script.json" "$ns"
    name=eck-probe-$(date -u +%H%M%S)
    jq -n --arg name "$name" --arg run "$RUN" --arg image "$(image message_tools)" '{apiVersion:"batch/v1",kind:"Job",metadata:{name:$name},spec:{backoffLimit:0,activeDeadlineSeconds:180,template:{spec:{restartPolicy:"Never",containers:[{name:"probe",image:$image,command:["sh","/script/probe.sh"],env:[{name:"CNPL_RUN",value:$run}],volumeMounts:[{name:"script",mountPath:"/script",readOnly:true},{name:"auth",mountPath:"/auth",readOnly:true},{name:"ca",mountPath:"/ca",readOnly:true},{name:"app",mountPath:"/app",readOnly:true}]}],volumes:[{name:"script",configMap:{name:"eck-probe"}},{name:"auth",secret:{secretName:"search-es-elastic-user"}},{name:"ca",secret:{secretName:"search-es-http-certs-public"}},{name:"app",secret:{secretName:"cache-auth"}}]}}}}' > "$ATTEMPT/eck-probe.json"
    apply "$ATTEMPT/eck-probe.json" "$ns"
    k -n "$ns" wait --for=condition=Complete "job/$name" --timeout=210s
    k -n "$ns" logs "job/$name" > "$ATTEMPT/eck-test.txt"
fi
