#!/usr/bin/env bash
# 从管理端对 hosts.yaml 中的 Kubernetes 节点执行只读 node-readiness 检查，并汇总为矩阵。
#
# 节点侧：只经 SSH 推送运行 ops/00-preparation/tests/smoke/node-readiness.sh（只读）。
# 管理端：只写输出目录（每节点 <id>.expect / <id>.txt，以及 matrix.md）。
# 期望值来自 ops/inventory/hosts.yaml、resources.yaml 与 ops/versions.lock.yaml；
# 台账变更后重跑即可，脚本内不复制节点清单。
#
# 依赖：OpenSSH（密钥登录，BatchMode，不会提示输入密码）、ruby 标准库 YAML（macOS 自带）、python3。
# 用法：ops/00-preparation/scripts/collect-node-readiness.sh [输出目录]
#   LAB_SSH_KEY   私钥路径，默认 ~/.ssh/cnpl_lab_ed25519
#   LAB_SSH_USER  远程用户，默认 root
# 退出码：0 全部通过；1 有未通过项或采集失败；2 前置条件缺失。
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
KEY=${LAB_SSH_KEY:-$HOME/.ssh/cnpl_lab_ed25519}
USER_NAME=${LAB_SSH_USER:-root}
OUT=${1:-$ROOT/ops/00-preparation/records/2026-10-14/evidence/00.10.02-node-readiness-$(date +%Y%m%d-%H%M%S)}
NODE_SCRIPT=$ROOT/ops/00-preparation/tests/smoke/node-readiness.sh
SUMMARIZER=$ROOT/ops/00-preparation/scripts/summarize-node-readiness.py

for need in ssh ruby python3; do
  command -v "$need" >/dev/null || { echo "缺少命令：$need" >&2; exit 2; }
done
[ -r "$KEY" ] || { echo "找不到私钥：$KEY（可用 LAB_SSH_KEY 指定）" >&2; exit 2; }
mkdir -p "$OUT"

# 为每个节点写 <id>.expect，并输出 "id ip" 列表。
NODES=$(cd "$ROOT" && ruby -ryaml -e '
  out = ARGV[0]
  hosts = YAML.load_file("ops/inventory/hosts.yaml")
  profiles = YAML.load_file("ops/inventory/resources.yaml")["node_profiles"]
  net = YAML.load_file("ops/inventory/networks.yaml")["lan"]
  lock = YAML.load_file("ops/versions.lock.yaml")["components"]
  runtime_uuid = hosts["bootstrap_template"]["runtime_disk"]["filesystem_uuid"]
  prefix = net["cidr"].split("/").last
  hosts["kubernetes_nodes"].each do |n|
    p = profiles.fetch(n["resource_profile"])
    File.write(File.join(out, "#{n["id"]}.expect"), {
      "expect_id" => n["id"], "expect_fqdn" => n["fqdn"], "expect_ip" => n["ip"],
      "expect_prefix" => prefix, "expect_role" => n["role"],
      "expect_hypervisor" => n["planned_hypervisor"],
      "expect_vcpu" => p["vcpu"], "expect_mem_gib" => p["memory_gib"],
      "expect_gateway" => net["default_gateway"], "expect_runtime_uuid" => runtime_uuid,
      "expect_containerd" => lock["containerd"]["version"], "expect_runc" => lock["runc"]["version"],
      "expect_crictl" => lock["cri_tools"]["version"], "expect_kubeadm" => lock["kubeadm"]["version"],
      "expect_kubelet" => lock["kubelet"]["version"], "expect_kubectl" => lock["kubectl"]["version"],
      "expect_pause" => lock["pause"]["reference"],
    }.map { |k, v| "#{k}=#{v}\n" }.join)
    puts "#{n["id"]} #{n["ip"]}"
  end
' "$OUT")

echo "输出目录：$OUT"
while read -r id ip; do
  printf '  %-10s %-15s ' "$id" "$ip"
  ssh_rc=0
  ssh -i "$KEY" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=5 \
    "$USER_NAME@$ip" 'bash -s' < "$NODE_SCRIPT" > "$OUT/$id.txt" 2> "$OUT/$id.err" || ssh_rc=$?
  # 管理端元数据：SSH 中途断开时输出可能不完整，汇总据此判定采集失败。
  echo "collect_exit=$ssh_rc" >> "$OUT/$id.txt"
  if [ "$ssh_rc" -eq 0 ]; then echo "已采集"; else echo "采集失败（ssh 退出码 $ssh_rc，见 $id.err）"; fi
  [ -s "$OUT/$id.err" ] || rm -f "$OUT/$id.err"
done <<< "$NODES"

python3 -I "$SUMMARIZER" "$OUT" > "$OUT/matrix.md" && rc=0 || rc=$?
echo "矩阵：$OUT/matrix.md"
sed -n '/^## 结果/,/^## 明细/p' "$OUT/matrix.md" | sed '$d'
exit "$rc"
