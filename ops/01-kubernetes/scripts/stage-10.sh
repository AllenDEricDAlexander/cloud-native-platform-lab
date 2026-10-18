#!/bin/bash
set -euo pipefail
exec /bin/bash "$(dirname "$0")/core-stage.sh" 10 "$@"
