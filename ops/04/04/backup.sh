#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/cli.sh"
source "$P04/03/shared/api.sh"
start 04 backup
directory=$(required .jenkins.backup_directory)
ruby -e 'p=File.realpath(ARGV[0]);r=File.realpath(ARGV[1]);s=File.stat(p);abort "备份目录必须仓库外、当前用户所有、0700" unless s.directory? && !p.start_with?(r+"/") && s.uid==Process.uid && (s.mode & 0777)==0700' "$directory" "$REPO"
config=$(required .jenkins.curl_config); private_file "$config"
cluster_gate
jenkins_cli quiet-down
resume_jenkins() { jenkins_cli cancel-quiet-down; }
RECOVERY_FUNCTION=resume_jenkins
idle=false
for ((i=0; i<60; i++)); do
    curl_safe "$config" 'https://jenkins.k8s.internal.egon.top/computer/api/json' --get --data-urlencode 'tree=busyExecutors' > "$ATTEMPT/executors.json"
    if jq -e '.busyExecutors==0' "$ATTEMPT/executors.json" >/dev/null; then idle=true; break; fi
    sleep 5
done
[[ $idle == true ]] || die '现有构建未结束，停止备份并恢复接单'
file=$(mktemp "$directory/jenkins-$RUN-XXXXXX")
k -n ci-jenkins exec deployment/jenkins -c jenkins -- tar -C /var/jenkins_home -czf - . > "$file"
[[ -s $file ]] || die '备份为空'
jq -n --arg file "$file" --arg sha "$(sha "$file")" '{private_backup_file:$file,sha256:$sha,restore_tested:false}' > "$ATTEMPT/backup-reference.json"
