#!/bin/bash
set -euo pipefail
exec bash "$(dirname "$0")/phase02.sh" resource-governance 02.08 "$@"
