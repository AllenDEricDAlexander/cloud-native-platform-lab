#!/usr/bin/env bash
# 本地离线校验；不会执行 playbook 任务、SSH、安装或启动服务。
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
for command in ansible-playbook ansible-inventory jq; do command -v "$command" >/dev/null || { echo "缺少 $command；在 5.7 完成后的 admin 执行" >&2; exit 1; }; done
work=$(mktemp -d); trap 'rm -rf -- "$work"' EXIT
cp "$root/inputs/hosts.ini" "$work/hosts.ini"
printf '[defaults]\nretry_files_enabled=False\nhost_key_checking=True\nlocal_tmp=%s/local\n' "$work" > "$work/ansible.cfg"
export ANSIBLE_CONFIG=$work/ansible.cfg
while IFS= read -r script; do bash -n "$script"; done < <(find "$root/scripts" "$root/ansible/files" -type f -name '*.sh' | sort)
while IFS= read -r file; do jq -e . "$file" >/dev/null; done < <(find "$root/config" -type f -name '*.json' | sort)
ansible-inventory -i "$work/hosts.ini" --list > "$work/inventory.json"
jq -e '._meta.hostvars|length==19' "$work/inventory.json" >/dev/null
jq -e '.k8s_master_nodes.hosts|length==3' "$work/inventory.json" >/dev/null
jq -e '.k8s_infra_nodes.hosts|length==2' "$work/inventory.json" >/dev/null
jq -e '.k8s_storage_nodes.hosts|length==3' "$work/inventory.json" >/dev/null
jq -e '.k8s_work_nodes.hosts|length==2' "$work/inventory.json" >/dev/null
for name in bootstrap-nodes preflight-nodes verify-nodes dns nexus harbor gitlab gitlab-project build-backup credentials network backup; do
    ansible-playbook "$root/ansible/$name.yml" -i "$work/hosts.ini" --syntax-check
    ansible-playbook "$root/ansible/$name.yml" -i "$work/hosts.ini" --list-hosts
done
if find "$root" -type f \( -name '*.py' -o -name '*.j2' -o -iname '*example*' \) | grep -q .; then echo '发现不允许交付的脚本/模板' >&2; exit 1; fi
printf 'PASS Shell/JSON/Ansible 语法及正式清单；未连接 VM，未执行部署。\n'
