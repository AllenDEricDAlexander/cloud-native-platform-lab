#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P04/validate.sh" 06 ;;
    render-module) shift; exec ruby "$P04/06/module.rb" "$@" ;;
    init|plan|apply|no-op|ansible-check|ansible-apply|ansible-idempotence|state-backup|inspect-failure) ;;
    *) die '用法：06/run.sh validate|render-module <new-dir>|init|plan|apply|no-op|ansible-check|ansible-apply|state-backup|inspect-failure' ;;
esac
start 06 "$action"
material opentofu >/dev/null; material opentofu_vsphere_provider >/dev/null
directory=$(required .iac.directory)
backend=$(required .iac.backend_config); variables=$(required .iac.variables_file)
plans=$(required .iac.plan_directory)
private_file "$backend"; private_file "$variables"
ruby -rjson -e 'r=File.realpath(ARGV[0]);ARGV[1..2].each{|p|v=File.realpath(p);s=File.stat(v);abort "IaC/Plan目录必须在仓库外、当前用户所有、0700" unless s.directory? && !v.start_with?(r+"/") && s.uid==Process.uid && (s.mode & 0777)==0700}' "$REPO" "$directory" "$plans"
jq -e --arg name "cnpl04-$RUN" '.vm_name==$name' "$variables" >/dev/null || die '仅允许本批临时 VM'
ruby -r "$P04/lib/config.rb" -r ipaddr -e 'v=JSON.parse(File.read(ARGV[0]));h=YAML.load_file(File.join(REPO,"ops/inventory/hosts.yaml"));hosts=h.fetch("kubernetes_nodes")+h.fetch("bootstrap_services")+h.fetch("lab_clients",[]);ip=v.fetch("test_ip");abort "测试IP必须在未占用的.160-.179客户端段" unless IPAddr.new(ip).ipv4? && ip.match?(/\A192\.168\.9\.(16\d|17\d)\z/) && hosts.none?{|n|n["ip"]==ip};vc=h.fetch("vcenter");abort "只能访问登记vCenter" unless [vc["ip"],vc["fqdn"],vc["reported_current_fqdn"]].include?(v["vsphere_server"]);abort "临时VM超预算" unless (1..4).cover?(v.fetch("cpus")) && (1024..8192).cover?(v.fetch("memory_mib")) && (16..40).cover?(v.fetch("runtime_disk_gib"))' "$variables"
tf() { tofu -chdir="$directory" "$@"; }
fingerprint() { ruby -rdigest -e 'files=Dir.glob(File.join(ARGV[0],"*.tf{,.json}"))+[File.join(ARGV[0],".terraform.lock.hcl")]+ARGV[1..-1];puts Digest::SHA256.hexdigest(files.sort.map{|f|File.basename(f)+Digest::SHA256.file(f).hexdigest}.join)' "$directory" "$variables" "$backend"; }
case "$action" in
    init)
        private_file "$directory/.terraform.lock.hcl"
        tf init -input=false -get=false -lockfile=readonly -plugin-dir="$(required .iac.plugin_directory)" -backend-config="$backend" > "$plans/init.txt" 2>&1 ;;
    plan)
        plan=$(mktemp "$plans/plan-XXXXXX.tfplan")
        if [[ $(jq -r '.iac.initial_state_confirmed_empty // false' "$INPUTS") == true ]]; then
            verify_file "$(required .iac.empty_state_evidence)" "$(required .iac.empty_state_evidence_sha256)"
        else tf state pull > "$plan.before.tfstate"; fi
        tf plan -input=false -lock-timeout=30s -var-file="$variables" -out="$plan" > "$plan.output.txt" 2>&1
        tf show -json "$plan" > "$plan.json"
        ruby "$P04/06/plan-check.rb" "$plan.json"
        jq -n --arg plan "$plan" --arg sha "$(sha "$plan")" --arg input "$(fingerprint)" '{plan_file:$plan,sha256:$sha,inputs_sha256:$input}' > "$plans/plan-reference.json"
        jq '{sha256,inputs_sha256}' "$plans/plan-reference.json" > "$ATTEMPT/plan-reference.json"
        printf 'Plan/State/完整 diff 留在仓库外；审查后以保存 Plan SHA 批准 apply。\n' ;;
    apply)
        reference=$plans/plan-reference.json
        private_file "$reference"
        plan=$(jq -er .plan_file "$reference"); private_file "$plan"
        approved=${CNPL04_APPROVED_PLAN_SHA256:-$(required .iac.approved_plan_sha256)}
        verify_file "$plan" "$approved"
        [[ $(jq -r .inputs_sha256 "$reference") == "$(fingerprint)" ]] || die '模块/变量/后端/Provider锁已改变，重新 Plan 审批'
        tf show -json "$plan" > "$plans/apply-check.json"
        ruby "$P04/06/plan-check.rb" "$plans/apply-check.json"
        if [[ $(jq -r '.iac.initial_state_confirmed_empty // false' "$INPUTS") != true ]]; then tf state pull > "$plans/pre-apply-$(date -u +%Y%m%dT%H%M%SZ).tfstate"; fi
        tf apply -input=false -lock-timeout=30s "$plan" > "$plans/apply-$(date -u +%Y%m%dT%H%M%SZ).txt" 2>&1 ;;
    no-op)
        rc=0; tf plan -input=false -lock-timeout=30s -var-file="$variables" -detailed-exitcode > "$plans/no-op.txt" 2>&1 || rc=$?
        [[ $rc == 0 ]] || die "幂等检查失败：exit=$rc（2=差异，1=错误）" ;;
    ansible-check|ansible-apply|ansible-idempotence)
        host=$(required .iac.test_host); [[ $host == "cnpl04-$RUN" ]] || die 'Ansible limit 必须为本批临时 VM'
        inventory=$(required .iac.inventory); playbook=$(required .iac.playbook)
        private_file "$inventory"
        # 初次安装前现场确认 VM UUID、IP、host key 与新 runtime 盘身份；不操作在用十节点。
        args=(--limit "$host" -e bootstrap_serial=1)
        [[ $action == ansible-apply ]] || args+=(--check --diff)
        export ANSIBLE_CONFIG="$REPO/ops/00-preparation/ansible/ansible.cfg"
        log=$(mktemp "$plans/$action-XXXXXX.txt")
        ANSIBLE_NOCOLOR=1 "${CNPL04_ANSIBLE:-$HOME/.venvs/cnpl-ansible/bin/ansible-playbook}" -i "$inventory" "$playbook" "${args[@]}" > "$log" 2>&1
        if [[ $action == ansible-idempotence ]]; then rg -q '^cnpl04-.*changed=0.*unreachable=0.*failed=0' "$log" || die 'Ansible未证明本批主机changed=0/failed=0'; fi ;;
    state-backup|inspect-failure)
        file=$(mktemp "$plans/state-XXXXXX.tfstate")
        tf state pull > "$file"
        tf state list > "$ATTEMPT/state-addresses.txt"
        printf 'State已另存私有目录。对比vCenter实际资源与已保存Plan；不自动destroy、force-unlock或新建State。\n' ;;
esac
