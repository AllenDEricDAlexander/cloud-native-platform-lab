#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P03/validate.sh" 09 ;;
    test) cd "$P03/09/operator"; exec env GOPROXY=off GOSUMDB=off GOTOOLCHAIN=local "${CNPL03_GO:-$HOME/.cnpl/toolchains/go1.27.2/go/bin/go}" test ./... ;;
    build) exec bash "$P03/09/build.sh" ;;
    handoff) exec ruby "$P03/09/handoff.rb" ;;
    backup) exec bash "$P03/09/backup-mac.sh" archive ;;
    build-vm|deploy|exercise|delete) ;;
    *) die '用法：09/run.sh validate|test|build|build-vm|deploy|exercise|delete|backup|handoff' ;;
esac
start 09 "$action"
if [[ $action == build-vm ]]; then
    [[ -x $P03/09/bin/demoapp-operator ]] || die '先执行本地 build'
    export ANSIBLE_CONFIG="$REPO/ops/00-preparation/ansible/ansible.cfg"
    "${CNPL03_ANSIBLE:-$HOME/.venvs/cnpl-ansible/bin/ansible-playbook}" "$P03/09/build-playbook.yml" 2>&1 | tee "$ATTEMPT/build-vm.txt"
    exit
fi
cluster_gate; ceph_ok
ns=cnpl03-09; namespace "$ns"
case "$action" in
    deploy)
        yaml_json "$P03/09/resources.yaml" | jq --arg image "$(image demoapp_operator)" '.items|=map(if .kind=="Deployment" then .spec.template.spec.containers[0].image=$image else . end)' > "$ATTEMPT/operator.json"
        # CRD 先建立再部署控制器，命名空间 Role 无 Secret/Node/ClusterRole 权限。
        apply "$ATTEMPT/operator.json" "$ns"
        k wait --for=condition=Established crd/demoapps.lab.egon.top --timeout=120s
        k -n "$ns" rollout status deployment/demoapp-operator --timeout=180s
        ;;
    exercise)
        jq -n --arg image "$(image demo_app)" '{apiVersion:"lab.egon.top/v1alpha1",kind:"DemoApp",metadata:{name:"demo-web"},spec:{image:$image,replicas:2,port:8080,message:"phase03"}}' > "$ATTEMPT/demo.json"
        apply "$ATTEMPT/demo.json" "$ns"
        wait_json 300 '.status.observedGeneration==.metadata.generation and any(.status.conditions[]?;.type=="Ready" and .status=="True")' k -n "$ns" get demoapp demo-web -o json
        uid=$(k -n "$ns" get demoapp demo-web -o jsonpath='{.metadata.uid}')
        deployment=$(k -n "$ns" get deploy demo-web -o json)
        jq -e --arg uid "$uid" 'any(.metadata.ownerReferences[]?;.uid==$uid and .controller==true)' <<< "$deployment" >/dev/null || die '子对象 ownerReference 不符'
        old=$(jq -r .metadata.uid <<< "$deployment")
        k -n "$ns" delete deployment demo-web --wait=true --timeout=120s
        wait_json 180 ".metadata.uid!=\"$old\" and .status.availableReplicas==2" k -n "$ns" get deployment demo-web -o json
        k -n "$ns" patch demoapp demo-web --type=merge -p '{"spec":{"message":"phase03-updated"}}'
        wait_json 180 '.data.message=="phase03-updated"' k -n "$ns" get cm demo-web -o json
        name=demo-http-$(date -u +%H%M%S)
        jq -n --arg name "$name" --arg image "$(image probe)" '{apiVersion:"batch/v1",kind:"Job",metadata:{name:$name},spec:{backoffLimit:0,activeDeadlineSeconds:120,template:{spec:{restartPolicy:"Never",containers:[{name:"http",image:$image,command:["sh","-ceu","i=0; until [ \"$(wget -qO- http://demo-web:8080)\" = phase03-updated ]; do i=$((i+1)); [ $i -lt 30 ]; sleep 3; done; printf \"phase03-updated\\n\""],resources:{requests:{cpu:"10m",memory:"16Mi"},limits:{memory:"64Mi"}}}]}}}}' > "$ATTEMPT/http.json"
        apply "$ATTEMPT/http.json" "$ns"
        k -n "$ns" wait --for=condition=Complete "job/$name" --timeout=150s
        k -n "$ns" logs "job/$name" > "$ATTEMPT/http.txt"
        grep -Fx phase03-updated "$ATTEMPT/http.txt"
        for resource in secrets nodes; do
            if k -n "$ns" auth can-i get "$resource" --as="system:serviceaccount:$ns:demoapp-operator" > "$ATTEMPT/rbac-$resource.txt"; then die "Operator 意外拥有 $resource 权限"; fi
            grep -Fx no "$ATTEMPT/rbac-$resource.txt"
        done
        jq '.spec.replicas=0' "$ATTEMPT/demo.json" > "$ATTEMPT/invalid.json"
        if k -n "$ns" apply --dry-run=server -f "$ATTEMPT/invalid.json" > "$ATTEMPT/invalid-output.txt" 2>&1; then die '非法 spec 被接受'; fi
        grep -Eq 'Invalid|greater than or equal to|minimum' "$ATTEMPT/invalid-output.txt" || die '非法 spec 未因 schema 被拒绝'
        k -n "$ns" get demoapp,deploy,svc,cm -o json > "$ATTEMPT/reconciled.json"
        ;;
    delete)
        k -n "$ns" get demoapp demo-web -o json | jq -e --arg run "$RUN" '.metadata.labels["cnpl.io/run"]==$run' >/dev/null || die 'DemoApp 归属不符'
        k -n "$ns" delete demoapp demo-web --wait=false
        k -n "$ns" wait --for=delete demoapp/demo-web --timeout=180s
        for kind in deployment service configmap; do [[ -z $(k -n "$ns" get "$kind" demo-web --ignore-not-found -o name) ]] || die "Finalizer 后仍有 $kind"; done
        ;;
esac
