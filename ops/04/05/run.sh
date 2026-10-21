#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P04/validate.sh" 05 ;;
    export) shift; exec ruby "$P04/05/export.rb" "$@" ;;
    matrix) shift; exec ruby "$P04/05/matrix.rb" "$@" ;;
    *) die '用法：05/run.sh validate|export <language> <new-directory>|matrix <14 receipts>' ;;
esac
