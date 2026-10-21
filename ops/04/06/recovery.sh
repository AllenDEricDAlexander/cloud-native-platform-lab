#!/usr/bin/env bash
# 在登记的集群外管理 VM 上调用；不依赖 kubeconfig/Jenkins/K8s Runner。
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
[[ $action != validate ]] || exec bash "$P04/validate.sh" 06
[[ $action == plan || $action == apply || $action == inspect-failure ]] || die '恢复入口只允许 plan|apply|inspect-failure'
host=$(required .iac.recovery_host)
ruby -ryaml -e 'h=YAML.load_file(ARGV[0]);n=(h.fetch("bootstrap_services")+h.fetch("lab_clients",[])).find{|v|v["fqdn"]==ARGV[1]};abort "恢复执行器必须登记为集群外且不依赖主Ceph" unless n && n["outside_kubernetes"] && n["depends_on_primary_ceph"]==false' "$REPO/ops/inventory/hosts.yaml" "$host"
[[ $(hostname -f) == "$host" ]] || die '必须在该登记恢复 VM 上运行，Mac 仅作管理端'
exec bash "$P04/06/run.sh" "$action"
