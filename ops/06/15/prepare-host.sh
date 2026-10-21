#!/usr/bin/env bash
set -euo pipefail
[[ $(hostname -f) == "$1" ]]
ip -j addr | python3 -c 'import json,sys;assert any(a.get("local")==sys.argv[1] for i in json.load(sys.stdin) for a in i.get("addr_info",[]))' "$2"
directory=$3
[[ $directory =~ ^/var/lib/cnpl06/[a-z][a-z0-9-]{2,19}/15$ ]]
test ! -e "$directory"
install -d -m 0700 "$directory"
