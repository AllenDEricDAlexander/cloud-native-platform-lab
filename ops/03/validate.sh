#!/usr/bin/env bash
# 只解析源码，不执行 SSH、kubectl、Helm、任务或物料下载。
set -euo pipefail
root=$(cd "$(dirname "$0")" && pwd)
stage=${1:-all}
[[ $stage == all || $stage =~ ^0[1-9]$ ]] || exit 2
while IFS= read -r file; do bash -n "$file" || exit 1; done < <(find "$root" -type d \( -name records -o -name private -o -name bin \) -prune -o -type f -name '*.sh' -print | sort)
ruby "$root/lib/review.rb" source
ansible=${CNPL03_ANSIBLE:-$HOME/.venvs/cnpl-ansible/bin/ansible-playbook}
[[ -x $ansible ]] || { echo '缺少现有专用 Ansible：设置 CNPL03_ANSIBLE' >&2; exit 1; }
work=$(mktemp -d); trap 'rm -rf -- "$work"' EXIT
export ANSIBLE_CONFIG="$work/ansible.cfg"
printf '[defaults]\nhost_key_checking=True\nretry_files_enabled=False\nlocal_tmp=%s/local\n' "$work" > "$ANSIBLE_CONFIG"
while IFS= read -r file; do
    "$ansible" -i "$root/../00-preparation/ansible/inventories/lab/hosts.yml" "$file" --syntax-check
done < <(find "$root" -type d -name records -prune -o -type f -name '*playbook.yml' -print | sort)
printf 'PASS Shell/Ansible 离线语法；未连接内网，未执行运行验收。\n'
