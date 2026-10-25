#!/usr/bin/env bash
set -euo pipefail
ns=cnpl03-mysql; namespace "$ns"
if [[ $ACTION == mysql ]]; then
    apply "$P03/07/mysql-tls.yaml" "$ns"
    source "$P03/lib/certificate-approval.sh"
    approve_certificate "$ns" cnpl03-mysql-ca
    k -n "$ns" wait --for=condition=Ready certificate/cnpl03-mysql-ca --timeout=60s
    k -n "$ns" wait --for=condition=Ready issuer/cnpl03-mysql-ca --timeout=60s
    approve_certificate "$ns" cnpl03-mysql
    k -n "$ns" wait --for=condition=Ready certificate/cnpl03-mysql --timeout=60s
    private_temp
    k -n "$ns" get secret cnpl03-mysql-ca -o json | jq -er '.data["tls.crt"]|@base64d' > "$PRIVATE_TEMP_ROOT/mysql-ca.pem"
    secret_from_files "$ns" mysql-ca "ca.pem=$PRIVATE_TEMP_ROOT/mysql-ca.pem"
    # 该 Operator 的 Router 证书附加键按 CA Secret 键名查找；仅投影 TLS 两键。
    # 保留为可更新 Secret，让后续证书续签后重跑此入口可以同步。
    k -n "$ns" get secret mysql-tls -o json | jq '{apiVersion:"v1",kind:"Secret",metadata:{name:"mysql-router-tls"},type:"kubernetes.io/tls",data:{"tls.crt":.data["tls.crt"],"tls.key":.data["tls.key"]}}' > "$PRIVATE_TEMP_ROOT/router-tls.json"
    apply "$PRIVATE_TEMP_ROOT/router-tls.json" "$ns" >/dev/null
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
    data_domains
    jq --arg repo "$image_repository" --arg server "$(image mysql)" --arg operator "$(image mysql_operator)" --arg router "$(image mysql_router)" '.spec.imageRepository=$repo | .spec.podSpec.nodeSelector={"cnpl.io/phase03-data":"true"} | .spec.podSpec.tolerations=[{operator:"Exists",effect:"NoSchedule"}] | .spec.podSpec.initContainers=[{name:"fixdatadir",image:$operator},{name:"initconf",image:$operator},{name:"initmysql",image:$server}] | .spec.podSpec.containers=[{name:"sidecar",image:$operator,resources:{requests:{cpu:"50m",memory:"128Mi"},limits:{memory:"512Mi"}}},{name:"mysql",image:$server,resources:{requests:{cpu:"100m",memory:"512Mi"},limits:{memory:"1536Mi"}}}] | .spec.router.tlsSecretName="mysql-router-tls" | .spec.router.podSpec.containers=[{name:"router",image:$router,resources:{requests:{cpu:"50m",memory:"64Mi"},limits:{memory:"256Mi"}}}] | .spec.mycnf="[mysqld]\ninnodb_buffer_pool_size=128M\nmax_connections=100\n"' "$ATTEMPT/mysql.json" > "$ATTEMPT/mysql-final.json"
    apply "$ATTEMPT/mysql-final.json" "$ns"
    wait_json 900 '.status.cluster.status=="ONLINE" and .status.cluster.onlineInstances==3' k -n "$ns" get innodbcluster mysql -o json
    digest=$(image mysql); digest=${digest##*@}
    k -n "$ns" get pods -o json | jq -e --arg digest "$digest" '[.items[].status.containerStatuses[]?|select(.name=="mysql")]|length==3 and all(.[]; .imageID|endswith($digest))' >/dev/null || die 'MySQL 实际 imageID 与锁定 Digest 不符'
else
    source "$P03/07/mysql-test.sh"
fi
