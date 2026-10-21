#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
case_name=${1:?signed|unsigned|wrong-key|registry-unavailable}
[[ $case_name =~ ^(signed|unsigned|wrong-key|registry-unavailable)$ ]] || exit 2
start 08 "admission-$case_name"
image=$(jq -er --arg key "$case_name" '.supply_chain.test_images[$key]' "$INPUTS")
[[ $image =~ ^harbor\.k8s\.internal\.egon\.top/.+@sha256:[a-f0-9]{64}$ ]] || die '测试镜像必须固定Digest'
cluster_gate
jq -n --arg image "$image" --arg run "$RUN" '{apiVersion:"v1",kind:"Pod",metadata:{name:"cnpl04-admission-probe",namespace:"apps-dev",labels:{"cnpl.io/run":$run}},spec:{restartPolicy:"Never",containers:[{name:"probe",image:$image,securityContext:{runAsNonRoot:true,runAsUser:1000,allowPrivilegeEscalation:false,capabilities:{drop:["ALL"]},seccompProfile:{type:"RuntimeDefault"}}}]}}' > "$ATTEMPT/pod.json"
rc=0; k create --dry-run=server -f "$ATTEMPT/pod.json" > "$ATTEMPT/decision.txt" 2> "$ATTEMPT/rejection.txt" || rc=$?
if [[ $case_name == signed ]]; then [[ $rc == 0 ]] || die '可信镜像未通过'; else
    [[ $rc != 0 ]] || die '不可信/仓库故障用例被放行'
    rg -q 'cnpl04-trusted-images|verify-signature-and-digest' "$ATTEMPT/rejection.txt" || die '失败非预期策略拒绝，不能算通过'
fi
