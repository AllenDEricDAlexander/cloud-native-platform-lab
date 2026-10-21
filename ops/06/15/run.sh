#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P06/validate.sh" 15 ;;
    plan) exec ruby "$P06/15/plan.rb" ;;
    inspect|drain|upgrade-node|complete-node|cleanup-plan) ;;
    *) die '用法：15/run.sh validate|plan|inspect|drain|upgrade-node|complete-node|cleanup-plan' ;;
esac
start 15 "$action"
if [[ $action == cleanup-plan ]]; then cleanup_plan; exit; fi
ruby "$P06/15/plan.rb" > "$ATTEMPT/plan.json"
backup_gate
node=$(required .upgrade.node); node_ip "$node" >/dev/null
# 变更窗口回执有时效，且绑定当前节点；旧回执不能授权下一台。
ruby -rjson -rtime -e 'd=JSON.parse(File.read(ARGV[0]));t=Time.iso8601(d.fetch("observed_at"));abort "维护前置未核实或已过期" unless d["node"]==ARGV[1] && %w[frozen pdb_reviewed independent_backup_restored].all?{|k|d[k]==true} && d["etcd_healthy_members"]==3 && d["ceph_health"]=="HEALTH_OK" && (Time.now-t).between?(0,900)' "$(required .upgrade.freeze_file)" "$node"
completed=$STATE/completed.jsonl
touch "$completed"
next_node=$(ruby -rjson -e 'done=File.readlines(ARGV[1]).map{|l|JSON.parse(l).fetch("node")};puts((JSON.parse(File.read(ARGV[0])).fetch("order")-done).first)' "$ATTEMPT/plan.json" "$completed")
[[ $node == "$next_node" ]] || die '必须按控制平面→Worker→基础节点→存储节点逐台执行'
cluster_gate
k get node "$node" -o json > "$ATTEMPT/node.json"
uid=$(jq -r .metadata.uid "$ATTEMPT/node.json")
case "$action" in
    inspect) k get pdb -A -o json > "$ATTEMPT/pdb.json" ;;
    drain)
        [[ ! -f $STATE/pending.json ]] || die '有未完成节点，先恢复或 complete-node'
        # 排空失败仍保留 pending，防止绕过当前节点继续。
        jq -n --arg node "$node" --arg uid "$uid" '{node:$node,uid:$uid}' > "$STATE/pending.json"
        k drain "$node" --ignore-daemonsets --timeout=300s
        ;;
    upgrade-node|complete-node)
        jq -e --arg node "$node" --arg uid "$uid" '.node==$node and .uid==$uid' "$STATE/pending.json" >/dev/null || die '维护节点 UID/状态不符'
        [[ $(jq -r '.spec.unschedulable // false' "$ATTEMPT/node.json") == true ]] || die '节点必须保持 cordon'
        target=$(required .upgrade.target_version)
        if [[ $action == upgrade-node ]]; then
            ruby "$P06/15/rpm-check.rb"
            directory=/var/lib/cnpl06/$RUN/15
            remote_node "$node" "$P06/15/prepare-host.sh" "$directory"
            ip=$(node_ip "$node")
            for package in kubeadm kubelet kubectl; do
                file=$(required ".upgrade.${package}_rpm")
                scp -q -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 -i "$(required .hosts.ssh_identity)" "$file" "root@$ip:$directory/$package.rpm"
                # 传输后在目标再次核对；参数只有公开 SHA 和受控固定目录。
                expected=$(required ".upgrade.${package}_rpm_sha256")
                command="printf '%s  %s\\n' '$expected' '$directory/$package.rpm' | sha256sum -c -"
                ssh -T -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 -i "$(required .hosts.ssh_identity)" "root@$ip" "$command"
            done
            role=$(ruby -rjson -e 'o=JSON.parse(File.read(ARGV[0]))["order"];i=o.index(ARGV[1]);puts(i==0 ? "first-control-plane" : i<3 ? "remaining-control-plane" : "worker")' "$ATTEMPT/plan.json" "$node")
            remote_node "$node" "$P06/15/upgrade-host.sh" "$role" "$(required .upgrade.source_version)" "$target" "$directory" > "$ATTEMPT/upgrade.txt" 2>&1
        else
            evidence_gate upgrade regression
            ruby -rjson -e 'd=JSON.parse(File.read(ARGV[0]));abort "节点回归证据不全" unless d["node"]==ARGV[1] && d["uid"]==ARGV[2] && d["target_version"]==ARGV[3] && %w[api etcd cilium dns csi gateway database messaging ci security observability].all?{|k|d.fetch("checks")[k]==true} && d["ceph_health"]=="HEALTH_OK"' "$(required .upgrade.regression_file)" "$node" "$uid" "$target"
            [[ $(jq -r .status.nodeInfo.kubeletVersion "$ATTEMPT/node.json") == "$target" ]] || die 'kubelet 未达到目标版本'
            k wait "node/$node" --for=condition=Ready --timeout=180s
            k get node "$node" -o json > "$ATTEMPT/node-current.json"
            jq -e --arg uid "$uid" --arg target "$target" '.metadata.uid==$uid and .status.nodeInfo.kubeletVersion==$target and .spec.unschedulable==true' "$ATTEMPT/node-current.json" >/dev/null || die '回归后节点身份/维护状态改变'
            jq '[{op:"test",path:"/metadata/uid",value:.metadata.uid},{op:"test",path:"/metadata/resourceVersion",value:.metadata.resourceVersion},{op:"test",path:"/spec/unschedulable",value:true},{op:"replace",path:"/spec/unschedulable",value:false}]' "$ATTEMPT/node-current.json" > "$ATTEMPT/uncordon.json"
            k patch node "$node" --type=json --patch-file "$ATTEMPT/uncordon.json"
            jq -nc --arg node "$node" --arg uid "$uid" --arg version "$target" '{node:$node,uid:$uid,version:$version}' >> "$completed"
            mv "$STATE/pending.json" "$ATTEMPT/pending-completed.json"
        fi
        ;;
esac
