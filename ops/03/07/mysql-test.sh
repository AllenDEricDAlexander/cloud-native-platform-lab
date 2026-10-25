#!/usr/bin/env bash
set -euo pipefail
password=$(required .postgres.app_password_file); hex_secret "$password"
secret_from_files "$ns" mysql-app "password=$password"
k -n "$ns" create configmap mysql-probe --from-file=probe.sh="$P03/07/mysql-probe.sh" --dry-run=client -o json > "$ATTEMPT/mysql-script.json"
apply "$ATTEMPT/mysql-script.json" "$ns"
name=mysql-probe-$(date -u +%H%M%S)
mode=write; [[ $ACTION != mysql-check ]] || mode=verify
expected=$(ruby -rdigest -e 'puts "1000|"+Digest::SHA256.hexdigest((1..1000).map{|n|"cnpl03-#{n}"}.join(","))')
jq -n --arg name "$name" --arg mode "$mode" --arg expected "$expected" --arg image "$(image mysql_client)" '{apiVersion:"batch/v1",kind:"Job",metadata:{name:$name},spec:{backoffLimit:0,activeDeadlineSeconds:180,template:{spec:{restartPolicy:"Never",containers:[{name:"client",image:$image,command:["sh","/script/probe.sh"],env:[{name:"CNPL_EXPECTED",value:$expected},{name:"CNPL_MODE",value:$mode}],resources:{requests:{cpu:"10m",memory:"64Mi"},limits:{memory:"256Mi"}},volumeMounts:[{name:"script",mountPath:"/script",readOnly:true},{name:"root",mountPath:"/root-auth",readOnly:true},{name:"app",mountPath:"/app-auth",readOnly:true},{name:"ca",mountPath:"/ca",readOnly:true}]}],volumes:[{name:"script",configMap:{name:"mysql-probe"}},{name:"root",secret:{secretName:"mysql-root"}},{name:"app",secret:{secretName:"mysql-app"}},{name:"ca",secret:{secretName:"mysql-ca"}}]}}}}' > "$ATTEMPT/mysql-probe.json"
apply "$ATTEMPT/mysql-probe.json" "$ns"
k -n "$ns" wait --for=condition=Complete "job/$name" --timeout=210s
k -n "$ns" logs "job/$name" > "$ATTEMPT/mysql-result.txt"
grep -Fx 'PASS MySQL 1000 committed IDs and checksum through TLS Router' "$ATTEMPT/mysql-result.txt"
