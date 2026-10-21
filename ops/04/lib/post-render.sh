#!/usr/bin/env bash
set -euo pipefail
exec ruby "$(dirname "$0")/config.rb" post-render
