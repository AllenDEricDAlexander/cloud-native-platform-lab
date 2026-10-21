#!/usr/bin/env bash
# 唯一离线入口：不调用 kubectl、helm、SSH、curl 或远端服务。
set -euo pipefail
root=$(cd "$(dirname "$0")" && pwd)
stage=${1:-all}
[[ $stage == all || $stage =~ ^0[1-9]$ ]] || exit 2
while IFS= read -r file; do bash -n "$file"; done < <(find "$root" -type d -name records -prune -o -type f -name '*.sh' -print | sort)
while IFS= read -r file; do ruby -c "$file" >/dev/null; done < <(find "$root" -type d -name records -prune -o -type f -name '*.rb' -print | sort)
python3 - "$root" <<'PY'
import ast
import pathlib
import sys
for path in pathlib.Path(sys.argv[1]).rglob('*.py'):
    if 'records' not in path.parts:
        ast.parse(path.read_text(), filename=str(path))
context = pathlib.Path(sys.argv[1]) / '04/context.py'
if context.exists():
    scope = {}
    exec(compile(context.read_text(), str(context), 'exec'), scope)
    assert scope['extract']({'traceparent': '00-'+'0'*32+'-'+'1'*16+'-01'}) is None
    parent = scope['start']()['context']
    assert scope['extract'](scope['inject'](parent)) == parent
    sync = scope['start'](parent)
    async_span = scope['start'](parent, asynchronous=True)
    assert sync['context']['trace_id'] == parent['trace_id'] and sync['parent_span_id'] == parent['span_id']
    assert async_span['context']['trace_id'] != parent['trace_id'] and async_span['parent_span_id'] is None and async_span['links'] == [parent]
    print('PASS Python AST 与 W3C 同步/异步 carrier 正反检查')
PY
ruby "$root/lib/config.rb" source
ansible=${CNPL05_ANSIBLE:-$HOME/.venvs/cnpl-ansible/bin/ansible-playbook}
[[ -x $ansible ]] || { printf '缺少既有 Ansible，请设置 CNPL05_ANSIBLE\n' >&2; exit 1; }
work=$(mktemp -d); trap 'rm -rf -- "$work"' EXIT
export ANSIBLE_CONFIG="$work/ansible.cfg" ANSIBLE_ROLES_PATH="$root/01/roles"
printf '[defaults]\nhost_key_checking=True\nretry_files_enabled=False\nlocal_tmp=%s/local\ncollections_path=%s/../00-preparation/ansible/collections\ncollections_scan_sys_path=False\n' "$work" "$root" > "$ANSIBLE_CONFIG"
for playbook in inspect install configure verify; do
    "$ansible" -i "$root/../00-preparation/ansible/inventories/lab/hosts.yml" "$root/01/$playbook.yml" --syntax-check > "$work/$playbook.txt" 2>&1 || { cat "$work/$playbook.txt"; exit 1; }
done
printf 'PASS 四份 Ansible syntax-check（只解析，不执行任务）\n'
[[ ! -f $root/tests/offline.rb ]] || ruby "$root/tests/offline.rb"
[[ ! -f $root/tests/render.rb ]] || ruby "$root/tests/render.rb"
[[ ! -f $root/lib/coverage.rb ]] || ruby "$root/lib/coverage.rb"
printf 'PASS Phase 05 离线检查；未联网、未部署、未执行正式实验。\n'
