#!/usr/bin/env bash
# 通过函数替身只走清单构造分支；既不调用真实客户端，也不执行容器内命令。
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
FIXTURE_ROOT=$(mktemp -d)
trap 'rm -rf -- "$FIXTURE_ROOT"; if [[ -n $CLEANUP_DIRECTORY ]]; then rm -rf -- "$CLEANUP_DIRECTORY"; fi' EXIT
ATTEMPT=$FIXTURE_ROOT; RUN=fixture; ns=cnpl03-08; SC_RBD=fixture-rbd; SC_FS=fixture-cephfs
printf '%064d' 0 > "$FIXTURE_ROOT/password"; chmod 0600 "$FIXTURE_ROOT/password"
required() {
    case "$1" in
        .postgres.app_password_file|.mysql.password_file|.middleware.password_file) printf '%s\n' "$FIXTURE_ROOT/password" ;;
        .middleware.kafka_metadata_version) printf '3.9-IV0\n' ;;
        *) printf 'fixture\n' ;;
    esac
}
image() { printf 'harbor.k8s.internal.egon.top/test/%s@sha256:%064d\n' "$1" 0; }
material() { printf '{"version":"8.4.5","imageRepository":"harbor.k8s.internal.egon.top/test","command":["/perf_test/bin/runjava","com.rabbitmq.perf.PerfTest"]}\n'; }
component_chart() { :; }
component_manifest() { :; }
data_domains() { :; }
namespace() { :; }
secret_from_files() { :; }
wait_json() { :; }
k() {
    case " $* " in
        *' create configmap '*) printf '{"apiVersion":"v1","kind":"ConfigMap","metadata":{"name":"fixture"},"data":{}}\n' ;;
        *' get pods '*) jq -n --arg digest "sha256:$(printf '%064d' 0)" '{items:[range(3)|{status:{containerStatuses:[{name:"mysql",imageID:$digest}]}}]}' ;;
        *' get elasticsearch '*) printf '{"status":{"health":"green","availableNodes":3}}\n' ;;
        *) : ;;
    esac
}
count=0
apply() {
    jq -e . "$1" >/dev/null
    ruby "$P03/lib/review.rb" images-json "$1"
    while IFS= read -r encoded; do
        printf '%s\n' "$encoded" | ruby -rbase64 -e 'print Base64.decode64(STDIN.read)' > "$FIXTURE_ROOT/container-command.sh"
        sh -n "$FIXTURE_ROOT/container-command.sh"
    done < <(jq -r '..|objects|.command? // empty|select(type=="array" and .[0]=="sh" and (.[1]=="-c" or .[1]=="-ceu"))|.[2]|@base64' "$1")
    count=$((count+1))
}
for action in mysql mysql-test; do ACTION=$action; source "$P03/07/mysql.sh" > "$FIXTURE_ROOT/$action.txt"; done
ns=cnpl03-08
for action in credentials redis redis-sentinel valkey; do ACTION=$action; source "$P03/08/redis.sh" > "$FIXTURE_ROOT/$action.txt"; done
ACTION=kafka; source "$P03/08/kafka.sh" > "$FIXTURE_ROOT/kafka.txt"
for action in rabbitmq rabbitmq-test rabbitmq-confirm; do ACTION=$action; source "$P03/08/rabbitmq.sh" > "$FIXTURE_ROOT/$action.txt"; done
ACTION=nats; source "$P03/08/nats.sh" > "$FIXTURE_ROOT/nats.txt"
for action in eck eck-test; do ACTION=$action; source "$P03/08/eck.sh" > "$FIXTURE_ROOT/$action.txt"; done
[[ $count -ge 15 ]] || die '渲染分支未全部覆盖'
printf 'PASS %s 个清单的 JSON/镜像及内嵌 Shell 构造；函数替身未调用真实客户端。\n' "$count"
