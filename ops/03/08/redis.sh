#!/usr/bin/env bash
set -euo pipefail
cache() {
    local host=$1; shift
    k -n "$ns" exec -i cache-client -- sh -ceu 'export REDISCLI_AUTH="$(cat /auth/password)"; host=$1; shift; exec redis-cli --tls --cacert /tls/ca.crt --cert /tls/tls.crt --key /tls/tls.key -h "$host" "$@"' -- "$host" "$@"
}
cache_pod_delete() {
    local pod=$1
    k -n "$ns" get pod "$pod" -o json | jq -e --arg run "$RUN" '.metadata.labels["cnpl.io/run"]==$run' >/dev/null || die '缓存 Pod 不属于本批'
    k -n "$ns" delete pod "$pod" --wait=true --timeout=120s
}
case "$ACTION" in
    credentials)
        password=$(required .middleware.password_file); hex_secret "$password"
        secret_from_files "$ns" cache-auth "password=$password"
        tls=$(required .middleware.tls_secret); k -n "$ns" get secret "$tls" >/dev/null
        jq -n --arg image "$(image redis)" --arg tls "$tls" '{apiVersion:"v1",kind:"Pod",metadata:{name:"cache-client"},spec:{containers:[{name:"client",image:$image,command:["sh","-c","sleep 86400"],volumeMounts:[{name:"auth",mountPath:"/auth",readOnly:true},{name:"tls",mountPath:"/tls",readOnly:true}],resources:{requests:{cpu:"10m",memory:"16Mi"},limits:{memory:"64Mi"}}}],volumes:[{name:"auth",secret:{secretName:"cache-auth"}},{name:"tls",secret:{secretName:$tls}}]}}' > "$ATTEMPT/cache-client.json"
        apply "$ATTEMPT/cache-client.json" "$ns"; k -n "$ns" wait --for=condition=Ready pod/cache-client --timeout=180s
        ;;
    redis|redis-sentinel|redis-cluster|valkey)
        data_domains
        key=redis; [[ $ACTION != valkey ]] || key=valkey
        ruby "$P03/08/redis-render.rb" "$ACTION" "$(image "$key")" "$SC_RBD" "$(required .middleware.tls_secret)" "$RUN" > "$ATTEMPT/cache.json"
        apply "$ATTEMPT/cache.json" "$ns"
        while IFS= read -r name; do k -n "$ns" rollout status "statefulset/$name" --timeout=300s; done < <(jq -r '.items[]|select(.kind=="StatefulSet")|.metadata.name' "$ATTEMPT/cache.json")
        if [[ $ACTION == redis-cluster ]]; then
            a=redis-cluster-a-0.redis-cluster-a; b=redis-cluster-b-0.redis-cluster-b; c=redis-cluster-c-0.redis-cluster-c
            if ! cache "$a" cluster info | grep -q 'cluster_state:ok'; then cache "$a" --cluster create "$a:6379" "$b:6379" "$c:6379" --cluster-replicas 0 --cluster-yes; fi
            for pair in d:a e:b f:c; do
                replica=redis-cluster-${pair%:*}-0.redis-cluster-${pair%:*}
                master=redis-cluster-${pair#*:}-0.redis-cluster-${pair#*:}
                id=$(cache "$master" cluster myid)
                if [[ $(cache "$replica" cluster info | tr -d '\r' | awk -F: '$1=="cluster_known_nodes"{print $2}') == 1 ]]; then cache "$a" --cluster add-node "$replica:6379" "$a:6379" --cluster-slave --cluster-master-id "$id"; fi
            done
            cache "$a" cluster nodes > "$ATTEMPT/cluster-nodes.txt"
            cache "$a" cluster info | tr -d '\r' | grep -Fx 'cluster_state:ok'
        fi
        ;;
    redis-test|valkey-test|redis-restart|redis-sentinel-failover|redis-cluster-test)
        host=redis-0.redis; [[ $ACTION != valkey-test ]] || host=valkey-0.valkey
        if [[ $ACTION == redis-cluster-test ]]; then host=redis-cluster-a-0.redis-cluster-a; fi
        if [[ $ACTION == redis-sentinel-failover ]]; then
            host=$(cache sentinel -p 26379 sentinel get-master-addr-by-name lab | head -1 | tr -d '\r')
        fi
        printf 'SET cnpl03:%s:durable %s:000001\nWAITAOF 1 0 5000\n' "$RUN" "$RUN" | cache "$host" -c --raw > "$ATTEMPT/aof-ack.txt"
        [[ $(sed -n '1p' "$ATTEMPT/aof-ack.txt") == OK && $(sed -n '2p' "$ATTEMPT/aof-ack.txt") == 1 ]] || die '同连接写入未获得本地 AOF 持久确认'
        cache "$host" -c set "cnpl03:$RUN:ttl" temporary EX 2 | grep -Fx OK
        sleep 3; [[ $(cache "$host" -c exists "cnpl03:$RUN:ttl") == 0 ]] || die 'TTL 未过期'
        if [[ $ACTION == redis-restart ]]; then cache_pod_delete redis-0; k -n "$ns" rollout status statefulset/redis --timeout=300s; fi
        if [[ $ACTION == redis-sentinel-failover ]]; then
            old=$host
            pod=${old%%.*}
            if [[ $old =~ ^[0-9]+\. ]]; then pod=$(k -n "$ns" get pods -o json | jq -er --arg ip "$old" '.items[]|select(.status.podIP==$ip)|.metadata.name'); fi
            cache_pod_delete "$pod"
            end=$((SECONDS+120))
            while :; do host=$(cache sentinel -p 26379 sentinel get-master-addr-by-name lab | head -1 | tr -d '\r'); [[ $host != "$old" ]] && break; ((SECONDS<end)) || die 'Sentinel 未切换主'; sleep 3; done
        fi
        [[ $(cache "$host" -c get "cnpl03:$RUN:durable") == "$RUN:000001" ]] || die '缓存数据不符'
        cache "$host" info persistence > "$ATTEMPT/persistence.txt"
        if [[ $ACTION == redis-cluster-test ]]; then
            for pair in a:d b:e c:f; do
                master=redis-cluster-${pair%:*}-0.redis-cluster-${pair%:*}; replica=redis-cluster-${pair#*:}-0.redis-cluster-${pair#*:}
                master_id=$(cache "$master" cluster myid)
                cache "$replica" cluster nodes | awk -v id="$master_id" '$3 ~ /myself/ && $4==id {found=1} END {exit !found}' || die '分片副本关系不符'
            done
            cache "$host" --cluster check "$host:6379" > "$ATTEMPT/slots.txt"
        fi
        ;;
    redis-eviction)
        host=redis-0.redis
        old_memory=$(cache "$host" config get maxmemory | tail -1)
        old_policy=$(cache "$host" config get maxmemory-policy | tail -1)
        restore_cache() { cache "$host" config set maxmemory "$old_memory" >/dev/null || return 1; cache "$host" config set maxmemory-policy "$old_policy" >/dev/null || return 1; }
        RECOVERY_FUNCTION=restore_cache
        before=$(cache "$host" info stats | tr -d '\r' | awk -F: '$1=="evicted_keys" {print $2}')
        cache "$host" config set maxmemory-policy volatile-lru >/dev/null
        cache "$host" config set maxmemory 2097152 >/dev/null
        k -n "$ns" exec cache-client -- sh -ceu 'export REDISCLI_AUTH="$(cat /auth/password)"; payload=$(head -c 16384 /dev/zero|tr "\000" x); i=1; while [ "$i" -le 256 ]; do redis-cli --tls --cacert /tls/ca.crt --cert /tls/tls.crt --key /tls/tls.key -h redis-0.redis SET "cnpl03:eviction:$i" "$payload" EX 60 | grep -Fx OK >/dev/null; i=$((i+1)); done'
        after=$(cache "$host" info stats | tr -d '\r' | awk -F: '$1=="evicted_keys" {print $2}')
        [[ $after -gt $before ]] || die '有界缓存写入未触发预期淘汰'
        restore_cache; RECOVERY_FUNCTION=''
        ;;
esac
