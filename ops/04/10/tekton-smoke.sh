#!/usr/bin/env bash
set -euo pipefail
name=cnpl04-tekton-demo
image=$(jq -er .image release/release.json)
for kind in deployment service; do
    live=$(kubectl -n tekton-lab get "$kind" "$name" --ignore-not-found -o json)
    [[ -z $live ]] || jq -e --arg run "$RUN_ID" '.metadata.labels["cnpl.io/phase"]=="04" and .metadata.labels["cnpl.io/run"]==$run' <<< "$live" >/dev/null
done
jq -n --arg name "$name" --arg image "$image" --arg run "$RUN_ID" '{apiVersion:"v1",kind:"List",items:[{apiVersion:"apps/v1",kind:"Deployment",metadata:{name:$name,namespace:"tekton-lab",labels:{"cnpl.io/phase":"04","cnpl.io/run":$run}},spec:{replicas:1,selector:{matchLabels:{app:$name}},template:{metadata:{labels:{app:$name,"cnpl.io/phase":"04","cnpl.io/run":$run}},spec:{automountServiceAccountToken:false,securityContext:{runAsNonRoot:true,runAsUser:1000,seccompProfile:{type:"RuntimeDefault"}},containers:[{name:"app",image:$image,ports:[{containerPort:8080}],resources:{requests:{cpu:"100m",memory:"128Mi"},limits:{cpu:"1",memory:"512Mi"}},securityContext:{allowPrivilegeEscalation:false,capabilities:{drop:["ALL"]}},readinessProbe:{httpGet:{path:"/ready",port:8080}}}]}}}},{apiVersion:"v1",kind:"Service",metadata:{name:$name,namespace:"tekton-lab",labels:{"cnpl.io/phase":"04","cnpl.io/run":$run}},spec:{selector:{app:$name},ports:[{port:8080,targetPort:8080}]}}]}' > release/tekton-deployment.json
kubectl apply -f release/tekton-deployment.json
kubectl -n tekton-lab rollout status "deployment/$name" --timeout=300s
curl --fail --silent --show-error --max-time 10 "http://$name.tekton-lab.svc:8080/health" > release/health.json
curl --fail --silent --show-error --max-time 10 "http://$name.tekton-lab.svc:8080/version" > release/version.json
jq -e --arg revision "$(jq -r .source_revision release/release.json)" '.revision==$revision' release/version.json >/dev/null
