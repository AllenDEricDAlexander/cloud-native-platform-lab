#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-validate}
case "$action" in
    validate) exec bash "$P03/validate.sh" 08 ;;
    tls|credentials|redis|redis-test|redis-check|redis-restart|redis-eviction|redis-sentinel|redis-sentinel-check|redis-sentinel-failover|redis-cluster|redis-cluster-test|redis-cluster-check|redis-cluster-failback|valkey|valkey-test|valkey-check|kafka|kafka-test|kafka-failover|kafka-lag|rabbitmq|rabbitmq-test|rabbitmq-confirm|rabbitmq-failover|nats|nats-test|nats-check|nats-failover|eck|eck-test|check) ;;
    *) die '未知 08 动作；参见 08/README.md' ;;
esac
start 08 "$action"
cluster_gate; ceph_ok; backup_gate
ns=cnpl03-08; namespace "$ns"
case "$action" in
    tls)
        apply "$P03/08/tls.yaml" "$ns"
        source "$P03/lib/certificate-approval.sh"
        approve_certificate "$ns" cnpl03-middleware-ca
        k -n "$ns" wait --for=condition=Ready certificate/cnpl03-middleware-ca --timeout=60s
        k -n "$ns" wait --for=condition=Ready issuer/cnpl03-middleware-ca --timeout=60s
        approve_certificate "$ns" cnpl03-middleware
        k -n "$ns" wait --for=condition=Ready certificate/cnpl03-middleware --timeout=180s
        ;;
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
