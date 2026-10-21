#!/usr/bin/env bash
set -euo pipefail
[[ $(hostname -f) == "$1" ]] || exit 1
ip -j addr | python3 -c 'import json,sys; assert any(a.get("local")==sys.argv[1] for i in json.load(sys.stdin) for a in i.get("addr_info",[]))' "$2"
[[ $(getenforce) == Enforcing ]]
firewall-cmd --state
uname -r
lspci -nnk
if command -v nvidia-smi >/dev/null; then nvidia-smi --query-gpu=name,pci.bus_id,memory.total,driver_version --format=csv; else printf 'GPU 驱动未就绪；仅 PCI 清单，不能验收计算。\n'; fi
