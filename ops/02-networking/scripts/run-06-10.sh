#!/bin/bash
# 可选整批入口：复用五个独立脚本，顺序执行，任何意外失败即停止。
set -euo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
mode=${1:-all}
records=${2:-"$root/ops/02-networking/records/batch-02.06-10-$(date -u +%Y%m%dT%H%M%SZ)"}
exec "$HOME/.venvs/cnpl-ansible/bin/python" "$root/ops/02-networking/tests/integration/phase02/batch.py" "$mode" "$records"
