#!/usr/bin/env bash
# 只用本地临时文件和假命令；任何外部客户端调用都会使测试失败。
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d); trap 'rm -rf -- "$work"' EXIT
jq '.run_id=null|.backup.independent=false' "$root/inputs.json" > "$work/inputs.json"
printf '{"devices":[]}' > "$work/devices.json"
printf '{"components":{}}' > "$work/materials.json"
export CNPL03_INPUTS=$work/inputs.json CNPL03_DEVICES=$work/devices.json CNPL03_MATERIALS=$work/materials.json
mkdir "$work/bin"
export CNPL03_TRIPWIRE=$work/external-client-called
for tool in ssh kubectl helm curl aws podman docker; do
    cat > "$work/bin/$tool" <<'BLOCK'
#!/bin/sh
printf '%s\n' "$0" >> "$CNPL03_TRIPWIRE"
exit 97
BLOCK
    chmod 0700 "$work/bin/$tool"
done
export PATH=$work/bin:$PATH
expect_fail() {
    local status=0
    "$@" > "$work/last-output.txt" 2>&1 || status=$?
    [[ $status -ne 0 && $status -ne 97 ]] || { cat "$work/last-output.txt" >&2; echo '负向防护未生效' >&2; exit 1; }
    [[ ! -e $CNPL03_TRIPWIRE ]] || { echo '意外触及外部客户端' >&2; exit 1; }
}
for stage in 01 02 03 04 05 06 07 08 09; do expect_fail bash "$root/$stage/run.sh" invalid-action; done
expect_fail bash "$root/01/run.sh" budget
expect_fail bash -c 'source "$1/lib/common.sh"; ceph status' -- "$root"
grep -q '物料尚未锁定' "$work/last-output.txt"
printf '%064d' 0 > "$work/password"; chmod 0600 "$work/password"
bash -c 'source "$1/lib/common.sh"; hex_secret "$2"' -- "$root" "$work/password"
printf '\ninjected-line\n' >> "$work/password"
expect_fail bash -c 'source "$1/lib/common.sh"; hex_secret "$2"' -- "$root" "$work/password"
chmod 0644 "$work/password"
expect_fail bash -c 'source "$1/lib/common.sh"; private_file "$2"' -- "$root" "$work/password"
printf '{"apiVersion":"v1","kind":"Pod","metadata":{"name":"bad"},"spec":{"containers":[{"name":"app","image":""}]}}' > "$work/bad.json"
expect_fail bash -c 'source "$1/lib/common.sh"; trap '\''[[ -z $PRIVATE_TEMP_ROOT ]] || rm -rf -- "$PRIVATE_TEMP_ROOT"'\'' EXIT; ATTEMPT=$2; RUN=fixture; apply "$2/bad.json" cnpl03-09' -- "$root" "$work"
grep -q '渲染镜像未锁' "$work/last-output.txt"
printf 'image: a\nimage: b\n' > "$work/duplicate.yaml"
expect_fail ruby "$root/lib/review.rb" images "$work/duplicate.yaml"
printf '{"kind":"PersistentVolume","spec":{"csi":{"volumeAttributes":{"imageName":"static-test"}}}}' > "$work/static.json"
ruby "$root/lib/review.rb" images-json "$work/static.json"
mkdir "$work/finish"
expect_fail bash -c 'source "$1/lib/common.sh"; ATTEMPT=$2; ACTION=fixture; recover_fixture(){ return 1; }; RECOVERY_FUNCTION=recover_fixture; trap finish EXIT; exit 0' -- "$root" "$work/finish"
jq -e '.exit_code==1 and .phase_acceptance==false' "$work/finish/result.json" >/dev/null
jq '.run_id="fixture"' "$root/inputs.json" > "$work/run-inputs.json"
mkdir -p "$work/runtime/01" "$work/runtime/lib"
cp "$root/lib/review.rb" "$work/runtime/lib/review.rb"
expect_fail bash -c 'source "$1/lib/common.sh"; P03=$2/runtime; INPUTS=$2/run-inputs.json; start 01 fixture; printf "fixture-output\n"; exit 3' -- "$root" "$work"
receipt=$(find "$work/runtime" -type f -name result.json)
jq -e '.exit_code==3 and .phase_acceptance==false' "$receipt" >/dev/null
grep -Fxq fixture-output "$(dirname "$receipt")/output.txt"
expect_fail ruby -rtimeout -e 'pid=Process.spawn(*ARGV,pgroup:true);begin;_,s=Timeout.timeout(5){Process.wait2(pid)};exit(s.exitstatus || 1);rescue Timeout::Error;Process.kill("KILL",-pid);abort "redirected failure logger hung";end' -- bash -c 'source "$1/lib/common.sh"; P03=$2/runtime; INPUTS=$2/run-inputs.json; start 01 redirected-failure; fail_fixture(){ printf "redirected-output\n"; return 7; }; fail_fixture > "$ATTEMPT/redirected.txt"' -- "$root" "$work"
redirected_receipt=$(find "$work/runtime" -type f -name result.json -exec sh -c 'jq -e ".action==\"redirected-failure\" and .exit_code==7" "$1" >/dev/null && printf "%s\n" "$1"' -- {} \;)
[[ -n $redirected_receipt ]]
grep -Fxq redirected-output "$(dirname "$redirected_receipt")/redirected.txt"
expect_fail bash -c 'source "$1/lib/common.sh"; P03=$2/runtime; INPUTS=$2/run-inputs.json; start 01 fixture; kill -TERM $$; exit 0' -- "$root" "$work"
signal_receipt=$(find "$work/runtime" -type f -name result.json -exec sh -c 'jq -e ".exit_code==143" "$1" >/dev/null && printf "%s\n" "$1"' -- {} \;)
[[ -n $signal_receipt ]]
bash -c 'source "$1/lib/common.sh"; trap '\''[[ -z $PRIVATE_TEMP_ROOT ]] || rm -rf -- "$PRIVATE_TEMP_ROOT"'\'' EXIT; marker=$2/notfound-seen; sleep(){ :; }; probe(){ if [[ ! -f $marker ]]; then touch "$marker"; printf "Error from server (NotFound)\n" >&2; return 1; fi; printf "{\"ready\":true}\n"; }; wait_json 10 .ready probe' -- "$root" "$work"
for family in redis redis-sentinel redis-cluster valkey; do
    ruby "$root/08/redis-render.rb" "$family" "harbor.k8s.internal.egon.top/test/cache@sha256:$(printf '%064d' 0)" fixture-rbd fixture-tls fixture > "$work/$family.json"
    ruby "$root/lib/review.rb" images-json "$work/$family.json"
    jq -e 'all(.items[]|select(.kind=="StatefulSet");.spec.persistentVolumeClaimRetentionPolicy.whenDeleted=="Retain")' "$work/$family.json" >/dev/null
    while IFS= read -r script; do printf '%s\n' "$script" | ruby -rbase64 -e 'print Base64.decode64(STDIN.read)' > "$work/start.sh"; sh -n "$work/start.sh"; done < <(jq -r '.items[]|select(.kind=="ConfigMap")|.data["start.sh"]|@base64' "$work/$family.json")
done
ruby -rjson -rbase64 -e '
names=%w[csi-rbd-node csi-rbd-provisioner csi-cephfs-node csi-cephfs-provisioner]; items=names.map{|n|{"kind"=>"Secret","metadata"=>{"name"=>n,"namespace"=>"cnpl03-external"},"stringData"=>{"userID"=>n,"userKey"=>"fixture-not-a-key"}}}; items << {"kind"=>"Secret","metadata"=>{"name"=>"rook-ceph-mon","namespace"=>"cnpl03-external"},"stringData"=>{"ceph-username"=>"client.healthchecker","ceph-secret"=>"fixture-not-a-key"}}; items << {"kind"=>"ConfigMap","metadata"=>{"name"=>"rook-ceph-mon-endpoints","namespace"=>"cnpl03-external"},"data"=>{}}; value={"apiVersion"=>"v1","kind"=>"List","fsid"=>"fixture-fsid","items"=>items};File.write(ARGV[0],JSON.generate(value));items[0]["stringData"]["userID"]="client.admin";File.write(ARGV[1],JSON.generate(value))' "$work/connection.json" "$work/admin.json"
ruby "$root/04/connection-check.rb" "$work/connection.json" fixture-fsid
expect_fail ruby "$root/04/connection-check.rb" "$work/admin.json" fixture-fsid
[[ ! -e $CNPL03_TRIPWIRE ]]
printf 'PASS 离线入口/物料/秘密/镜像/失败回执/缓存渲染/管理员导入防护；外部客户端调用为零。\n'
