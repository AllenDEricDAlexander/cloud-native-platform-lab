#!/usr/bin/env bash
set -euo pipefail
ns=cnpl03-mysql; namespace "$ns"
if [[ $ACTION == mysql ]]; then
    component_chart cnpl03-mysql mysql_operator "$ns"
    password=$(required .mysql.password_file); hex_secret "$password"
    work=$(mktemp -d)
    printf root > "$work/rootUser"; printf '%%' > "$work/rootHost"
    tr -d '\n' < "$password" > "$work/rootPassword"
    secret_from_files "$ns" mysql-root "rootUser=$work/rootUser" "rootHost=$work/rootHost" "rootPassword=$work/rootPassword"
    rm -rf -- "$work"
    info=$(material mysql)
    jq -n --arg version "$(jq -r .version <<< "$info")" --arg class "$SC_RBD" --arg image "$(image mysql)" '{apiVersion:"mysql.oracle.com/v2",kind:"InnoDBCluster",metadata:{name:"mysql"},spec:{secretName:"mysql-root",instances:3,version:$version,tlsUseSelfSigned:false,tlsSecretName:"mysql-tls",tlsCASecretName:"mysql-ca",router:{instances:2},datadirVolumeClaimTemplate:{storageClassName:$class,accessModes:["ReadWriteOnce"],resources:{requests:{storage:"2Gi"}}},podSpec:{affinity:{podAntiAffinity:{requiredDuringSchedulingIgnoredDuringExecution:[{topologyKey:"cnpl.io/esxi",labelSelector:{matchLabels:{"mysql.oracle.com/cluster":"mysql"}}}]}}}}}' > "$ATTEMPT/mysql.json"
    # Oracle Operator 本版本必须支持受控 imageRepository；先渲染核对，不让 tag 默认访问外网。
    image_repository=$(jq -r .imageRepository <<< "$info")
    [[ $image_repository == harbor.k8s.internal.egon.top/* ]] || die 'MySQL 需锁定该版本 Operator 支持的内网 imageRepository'
    jq --arg repo "$image_repository" '.spec.imageRepository=$repo' "$ATTEMPT/mysql.json" > "$ATTEMPT/mysql-final.json"
    apply "$ATTEMPT/mysql-final.json" "$ns"
    wait_json 900 '.status.cluster.status=="ONLINE" and .status.cluster.onlineInstances==3' k -n "$ns" get innodbcluster mysql -o json
    digest=$(image mysql); digest=${digest##*@}
    k -n "$ns" get pods -o json | jq -e --arg digest "$digest" '[.items[].status.containerStatuses[]?|select(.name=="mysql")]|length==3 and all(.[]; .imageID|endswith($digest))' >/dev/null || die 'MySQL 实际 imageID 与锁定 Digest 不符'
else
    source "$P03/07/mysql-test.sh"
fi
