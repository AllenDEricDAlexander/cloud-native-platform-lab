#!/usr/bin/env bash
# 所有潜在外部客户端由失败替身拦截；只有kubectl kustomize使用本机离线渲染子命令。
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
real_kubectl=$(command -v kubectl || true)
work=$(mktemp -d)
run=''
cleanup() {
    if [[ -n $run ]]; then for stage in 01 02 03 04 05 06 07 08 09 10; do rm -rf -- "$root/$stage/records/$run"; done; fi
    rm -rf -- "$work"
}
trap cleanup EXIT
ruby "$root/tests/fixtures.rb" "$work"
export CNPL04_INPUTS=$work/inputs.json CNPL04_MATERIALS=$work/materials.json
run=$(jq -r .run_id "$CNPL04_INPUTS")
export CNPL04_CALLS=$work/calls
mkdir "$work/stubs"
for client in kubectl helm ssh curl buildctl tofu argocd java ansible-playbook; do
    cat > "$work/stubs/$client" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$0" >> "$CNPL04_CALLS"
exit 91
EOF
    chmod +x "$work/stubs/$client"
done
export PATH=$work/stubs:$PATH
fails() { if "$@" > "$work/rejected.txt" 2>&1; then printf '应拒绝但成功：%s\n' "$*" >&2; exit 1; fi; }
for stage in 01 02 03 04 05 06 07 08 09 10; do fails bash "$root/$stage/run.sh" unknown-action; done
fails bash "$root/01/run.sh" apply
fails bash "$root/02/run.sh" deploy
fails bash "$root/03/run.sh" deploy
fails bash "$root/04/run.sh" deploy
fails bash "$root/06/run.sh" init
fails bash "$root/08/run.sh" deploy-controllers
fails bash "$root/09/run.sh" request
fails bash "$root/10/run.sh" pull direct cold
[[ ! -s $CNPL04_CALLS ]] || { echo '未确认输入触发了外部客户端' >&2; exit 1; }
fails ruby -r "$root/lib/config.rb" -e 'documents("a: 1\na: 2\n")'
fails ruby -r "$root/lib/config.rb" -e 'digest_image("harbor.k8s.internal.egon.top/x:latest")'
printf 'fixture secret\n' > "$work/secret"; chmod 644 "$work/secret"
fails bash -c 'source "$1/lib/common.sh"; private_file "$2"' _ "$root" "$work/secret"
chmod 600 "$work/secret"
bash -c 'source "$1/lib/common.sh"; private_file "$2"' _ "$root" "$work/secret"
# 正确文件权限不允许绕过同批次归属，且不覆盖原EXIT失败码。
fails bash -c 'source "$1/lib/common.sh"; start 01 exit-review; RECOVERY_FUNCTION=false; exit 7' _ "$root"
result=$(find "$root/01/records/$run" -path '*exit-review-*/result.json' -print)
jq -e '.exit_code==7 and .recovery_failed==true' "$result" >/dev/null
for stage in 01 02 04 07; do ruby "$root/$stage/render.rb" > "$work/render-$stage.yaml"; done
ruby -ryaml -rjson -e 'd=YAML.load_file(ARGV[0]);t=d.fetch("jenkins").fetch("clouds")[0].fetch("kubernetes").fetch("templates");abort "Agent数量不对" unless t.size==14;pods=t.map{|x|YAML.load(x.fetch("yaml"))};abort "Agent越权" unless pods.all?{|p|p.dig("spec","automountServiceAccountToken")==false && p.dig("spec","securityContext","runAsNonRoot")==true};puts JSON.generate({"apiVersion"=>"v1","kind"=>"List","items"=>pods})' "$work/render-04.yaml" > "$work/agents.json"
ruby "$root/01/access.rb" > "$work/access.json"
for mode in canary bluegreen metrics policy; do ruby "$root/08/render.rb" "$mode" > "$work/08-$mode.json"; done
for mode in crossplane catalog-root; do ruby "$root/09/render.rb" "$mode" > "$work/09-$mode.json"; done
ruby "$root/09/render.rb" template > "$work/backstage-template.yaml"
for mode in flux tekton tekton-run; do ruby "$root/10/render.rb" "$mode" > "$work/10-$mode.json"; done
for file in "$work/"*.json; do
    if jq -e '.kind=="List"' "$file" >/dev/null; then ruby "$root/lib/config.rb" manifests "$file"; fi
done
# 用实际Kustomize离线构建三个overlay，验证最终Digest、HPA字段和Namespace。
ruby "$root/07/render.rb" export "$work/gitops" >/dev/null
[[ -n $real_kubectl ]] || { echo '缺少既有kubectl的离线kustomize能力' >&2; exit 1; }
for environment in dev staging prod-like; do
    "$real_kubectl" kustomize "$work/gitops/environments/$environment/fixture-app" > "$work/$environment.yaml"
    ruby "$root/lib/config.rb" list "$work/$environment.yaml" > "$work/$environment.json"
    ruby "$root/lib/config.rb" manifests "$work/$environment.json"
    jq -e --arg ns "apps-$environment" 'all(.items[]; .metadata.namespace==$ns) and all(.items[]|select(.kind=="Deployment"); (.spec|has("replicas")|not))' "$work/$environment.json" >/dev/null
done
ruby "$root/05/export.rb" java "$work/source" >/dev/null
[[ -f $work/source/.gitlab-ci.yml && -f $work/source/ops/04/05/examples/java/pom.xml ]]
ruby "$root/06/module.rb" "$work/tofu" >/dev/null
jq -e '.resource.vsphere_virtual_machine.test.lifecycle.prevent_destroy==true and .provider.vsphere.allow_unverified_ssl==false' "$work/tofu/main.tf.json" >/dev/null
printf '{"complete":true,"resource_changes":[{"mode":"managed","address":"vsphere_virtual_machine.test","change":{"actions":["delete"],"before":{"name":"cnpl04-%s"}}}]}' "$run" > "$work/plan.json"
fails ruby "$root/06/plan-check.rb" "$work/plan.json"
# 验证依赖内容变化真的会改变缓存键，而非只比较文件名。
mkdir "$work/cache"
printf 'a\n' > "$work/cache/dependency"
printf '{"dependency_files":["dependency"]}\n' > "$work/cache/dependencies.lock"
source "$root/02/client.sh"
first=$(cache_key java "harbor.k8s.internal.egon.top/a@sha256:$(printf '%064d' 0)" "$work/cache/dependencies.lock" trusted)
printf 'b\n' > "$work/cache/dependency"
second=$(cache_key java "harbor.k8s.internal.egon.top/a@sha256:$(printf '%064d' 0)" "$work/cache/dependencies.lock" trusted)
[[ $first != "$second" && ! -s $CNPL04_CALLS ]]
printf 'PASS 离线拒绝路径、退出码、资源构造、三环境Kustomize、导出、IaC销毁保护、缓存指纹；外部客户端调用0次\n'
