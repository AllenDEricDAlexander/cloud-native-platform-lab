#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P03/validate.sh" 08 ;;
    credentials|redis|redis-test|redis-restart|redis-eviction|redis-sentinel|redis-sentinel-failover|redis-cluster|redis-cluster-test|valkey|valkey-test|kafka|kafka-test|kafka-failover|kafka-lag|rabbitmq|rabbitmq-test|rabbitmq-confirm|rabbitmq-failover|nats|nats-test|nats-failover|eck|eck-test|check) ;;
    *) die '未知 08 动作；参见 08/README.md' ;;
esac
start 08 "$action"
cluster_gate; ceph_ok; backup_gate
ns=cnpl03-08; namespace "$ns"
case "$action" in
    credentials|redis*|valkey*) source "$P03/08/redis.sh" ;;
    kafka*) source "$P03/08/kafka.sh" ;;
    rabbitmq*) source "$P03/08/rabbitmq.sh" ;;
    nats*) source "$P03/08/nats.sh" ;;
    eck*) source "$P03/08/eck.sh" ;;
    check)
        k -n "$ns" get pods,pvc,svc -o json > "$ATTEMPT/middleware.json"
        k -n "$ns" get events -o json > "$ATTEMPT/events.json"
        ;;
esac
