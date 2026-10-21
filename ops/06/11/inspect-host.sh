#!/usr/bin/env bash
# 只读检查；不会加载内核模块、启动虚拟机或修改安全机制。
set -euo pipefail
expected=$1 expected_ip=$2
[[ $(hostname -f) == "$expected" ]] || exit 1
ip -j addr | python3 -c 'import json,sys; expected=sys.argv[1]; assert any(a.get("local")==expected for i in json.load(sys.stdin) for a in i.get("addr_info",[]))' "$expected_ip"
[[ $(getenforce) == Enforcing ]]
firewall-cmd --state
lscpu
test -c /dev/kvm
test -r /dev/kvm
test -w /dev/kvm
printf 'KVM 可见；EVC/迁移/CPU 暴露和来宾性能仍需现场验证。\n'
