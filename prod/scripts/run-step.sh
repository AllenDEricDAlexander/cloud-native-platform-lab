#!/usr/bin/env bash
# 只执行用户给出的当前一条命令，保存退出码和脱敏输出，不自动推进下一阶段。
set -euo pipefail
[[ $# -ge 2 && $1 =~ ^[0-9A-Za-z_.-]+$ ]] || { echo '用法：run-step.sh 步骤名 命令 参数...' >&2; exit 2; }
step=$1; shift
base=${CNPL_RECORDS:-/srv/cnpl/records}
if [[ $(hostname -s) == admin && $base == /srv/cnpl/records && $EUID == 0 ]]; then
    install -d -o ops -g ops -m 0750 "$base"
else
    mkdir -p "$base"; chmod 0750 "$base"
fi
directory=$(mktemp -d "$base/$step-$(date -u +%Y%m%dT%H%M%SZ).XXXXXX")
printf '本次记录目录：%s\n' "$directory"
printf '%q ' "$@" > "$directory/command.txt"
printf '\n' >> "$directory/command.txt"
set +e
"$@" 2>&1 | tee "$directory/output.log"
status=${PIPESTATUS[0]}
set -e
printf '%s\n' "$status" > "$directory/exit-code"
chmod 0640 "$directory/output.log" "$directory/exit-code" "$directory/command.txt"
if [[ $(hostname -s) == admin && $EUID == 0 ]]; then chown -R ops:ops "$directory"; fi
exit "$status"
