#!/bin/bash
# 兼容目录入口；实际操作只有 Ansible。参数：模式 绝对记录目录。
set -euo pipefail
exec "$(cd "$(dirname "$0")/../.." && pwd)/scripts/replay-03-06.sh" "${1:-validate}" "${2:-}" 06
