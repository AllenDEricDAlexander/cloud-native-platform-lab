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
printf '[ceph_comparison]\nphase03-offline-syntax ansible_connection=local\n' > "$work/comparison.ini"
while IFS= read -r file; do
    inventory=$root/../00-preparation/ansible/inventories/lab/hosts.yml
    [[ $file != */managed-preflight-playbook.yml ]] || inventory=$work/comparison.ini
    "$ansible" -i "$inventory" "$file" --syntax-check
done < <(find "$root" -type d -name records -prune -o -type f -name '*playbook.yml' -print | sort)
if [[ -f $root/tests/guards.sh ]]; then bash "$root/tests/guards.sh"; fi
if [[ -f $root/tests/render.sh ]]; then bash "$root/tests/render.sh"; fi
if [[ -f $root/coverage.json ]]; then
    ruby -rjson -e 'ids=File.read(ARGV[0]).scan(/^### (03\.\d{2}\.\d{2}) /).flatten; rows=JSON.parse(File.read(ARGV[1])).fetch("steps"); abort "48 步索引不全" unless ids.size==48 && rows.map{|r|r.fetch("id")}.sort==ids.sort; rows.each{|r|r.fetch("files").each{|f|abort "缺少交付文件 #{f}" unless File.file?(File.join(ARGV[2],f))}}; puts "PASS 48 步交付文件索引"' "$root/../../plan/03-ceph-middleware.md" "$root/coverage.json" "$root"
fi
if [[ -f $root/09/operator/main_test.go ]]; then bash "$root/09/run.sh" test; fi
printf 'PASS Shell/Ansible 离线语法；未连接内网，未执行运行验收。\n'
