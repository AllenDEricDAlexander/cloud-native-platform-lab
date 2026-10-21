#!/usr/bin/env bash
# 用本地curl替身验证不可变原生包发布；不连接Nexus。
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
mkdir -p "$work/bin" "$work/source/dist" "$work/release"
printf 'native artifact fixture\n' > "$work/source/dist/native.tar"
printf 'header = "X-Offline-Fixture: yes"\n' > "$work/auth"
chmod 600 "$work/auth"
cat > "$work/bin/curl" <<'EOF'
#!/usr/bin/env ruby
args=ARGV
out=args[args.index("--output")+1]
if args.include?("--upload-file")
  File.write(ENV.fetch("CNPL04_NATIVE_UPLOAD"),File.binread(args[args.index("--upload-file")+1]))
  exit
end
scenario=ENV.fetch("CNPL04_NATIVE_CASE")
code=200
body=case scenario
when "existing" then File.binread(ENV.fetch("SOURCE_DIR")+"/dist/native.tar")
when "missing"
  if File.file?(ENV.fetch("CNPL04_NATIVE_UPLOAD")) then File.binread(ENV.fetch("CNPL04_NATIVE_UPLOAD"))
  else code=404;"not found"
  end
when "conflict" then "different contents"
when "auth-error" then code=401;"unauthorized"
else abort "unknown fixture"
end
File.binwrite(out,body)
STDOUT.write(code.to_s) if args.include?("--write-out")
exit(code==200 ? 0 : 22)
EOF
chmod +x "$work/bin/curl"
export PATH=$work/bin:$PATH NEXUS_CURL_CONFIG=$work/auth NEXUS_RELEASE_REPOSITORY=fixture-releases SOURCE_DIR=$work/source CNPL04_NATIVE_UPLOAD=$work/uploaded
cd "$work"
checksum=$(shasum -a 256 source/dist/native.tar | awk '{print $1}')
for scenario in existing missing conflict auth-error; do
    export CNPL04_NATIVE_CASE=$scenario
    jq -n --arg checksum "$checksum" '{language:"java",ci:"gitlab",source_revision:"cccccccccccccccccccccccccccccccccccccccc",build_attempt_id:"123",native_artifact_sha256:$checksum}' > release/release.json
    rc=0; bash "$root/03/shared/publish-native.sh" > "$work/result.txt" 2>&1 || rc=$?
    case "$scenario" in
        existing) [[ $rc == 0 && ! -e $CNPL04_NATIVE_UPLOAD ]] ;;
        missing) [[ $rc == 0 && -s $CNPL04_NATIVE_UPLOAD ]] ;;
        conflict|auth-error) [[ $rc != 0 ]] ;;
    esac
done
printf 'PASS 原生包相同SHA复用、404上传并取回、内容冲突拒绝、认证错误拒绝；真实Nexus调用0次\n'
