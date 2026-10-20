#!/bin/bash
set -euo pipefail
exec bash "$(dirname "$0")/phase02.sh" scheduling 02.07 "$@"
