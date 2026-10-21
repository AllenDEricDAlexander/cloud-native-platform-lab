#!/usr/bin/env bash
# 仅由管理端 remote 函数通过标准输入执行；保留主机安全基线。
set -euo pipefail
set +x
umask 077
expected=$1; shift
[[ $EUID == 0 && $(hostname -s) == "$expected" ]] || exit 1
[[ $(getenforce) == Enforcing ]] || exit 1
systemctl is-active --quiet firewalld || exit 1
exec "$@"
