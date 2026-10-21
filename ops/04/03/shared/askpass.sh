#!/usr/bin/env bash
# Git通过独立管道读取口令；Token不进入URL、argv或环境值。
set -euo pipefail
set +x
case "${1:-}" in
    *Username*) printf '%s\n' "${GITOPS_USERNAME:-oauth2}" ;;
    *Password*) ruby -e 'STDOUT.write(File.binread(ARGV[0]).sub(/\r?\n\z/,""))' "${GITOPS_TOKEN_FILE:?}" ;;
    *) exit 1 ;;
esac
