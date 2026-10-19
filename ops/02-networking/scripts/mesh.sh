#!/bin/bash
set -euo pipefail
exec bash "$(dirname "$0")/phase02.sh" mesh 02.10 "$@"
