#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P04/validate.sh" 10 ;;
    render) shift; exec ruby "$P04/10/render.rb" "$@" ;;
    deploy-flux|deploy-tekton|deploy-dragonfly|bootstrap-flux|bootstrap-tekton|start-tekton|check|pull) ;;
    *) die '用法：10/run.sh validate|render flux|tekton|deploy-flux|deploy-tekton|deploy-dragonfly|bootstrap-flux|bootstrap-tekton|check|pull <direct|p2p> <cold|warm>' ;;
esac
start 10 "$action"
case "$action" in
    deploy-flux|deploy-dragonfly) material "${action#deploy-}" >/dev/null ;;
    deploy-tekton) info=$(material tekton); verify_file "$(jq -er .file <<< "$info")" "$(jq -er .sha256 <<< "$info")" ;;
    bootstrap-tekton|start-tekton) tools=$(image release_tools); builder=$(image builder_java); worker_gate ;;
    pull)
        node=$(required .comparison.node); ruby "$P04/lib/config.rb" worker "$node"
        image=$(required .comparison.image)
        [[ ${2:-} =~ ^(direct|p2p)$ && ${3:-} =~ ^(cold|warm)$ ]] || die '拉取模式无效'
        ip=$(ruby -ryaml -e 'puts YAML.load_file(ARGV[0]).fetch("kubernetes_nodes").find{|h|h["fqdn"]==ARGV[1]}.fetch("ip")' "$REPO/ops/inventory/hosts.yaml" "$node")
        config=$(required .comparison.containerd_sha256)
        [[ $config =~ ^[a-f0-9]{64}$ && $image =~ ^harbor\.k8s\.internal\.egon\.top/[a-z0-9_./-]+@sha256:[a-f0-9]{64}$ ]] || die 'Digest/配置SHA无效'
        ssh -T -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 -i "${CNPL04_SSH_IDENTITY:-$HOME/.ssh/cnpl_lab_ed25519}" "root@$ip" "bash -s -- $node $image $2 $3 $config" < "$P04/10/compare-host.sh" > "$ATTEMPT/pull.json"
        exit ;;
esac
cluster_gate
case "$action" in
    deploy-flux) chart flux flux flux-system ;;
    deploy-dragonfly) chart dragonfly dragonfly dragonfly-system ;;
    deploy-tekton) apply "$(jq -er .file <<< "$info")" ;;
    bootstrap-flux) render flux > "$ATTEMPT/flux.json"; apply "$ATTEMPT/flux.json" ;;
    bootstrap-tekton|start-tekton)
        private_temp
        jq --arg tools "$tools" --arg builder "$builder" '.render_images.release_tools=$tools | .render_images.builder_java=$builder' "$INPUTS" > "$PRIVATE_TEMP/inputs.json"
        mode=tekton; [[ $action != start-tekton ]] || mode=tekton-run
        CNPL04_INPUTS="$PRIVATE_TEMP/inputs.json" render "$mode" > "$ATTEMPT/tekton.json"; apply "$ATTEMPT/tekton.json" ;;
    check)
        k -n tekton-lab get pipelineruns,taskruns -o json > "$ATTEMPT/tekton-runs.json"
        k -n flux-lab get kustomizations.kustomize.toolkit.fluxcd.io -o json > "$ATTEMPT/flux-status.json"
        jq -e '(.items|length)>0 and all(.items[]; any(.status.conditions[]; .type=="Ready" and .status=="True"))' "$ATTEMPT/flux-status.json" >/dev/null ;;
esac
