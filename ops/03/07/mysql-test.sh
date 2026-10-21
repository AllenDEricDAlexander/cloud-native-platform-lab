#!/usr/bin/env bash
set -euo pipefail
password=$(required .postgres.app_password_file); private_file "$password"
grep -Eq '^[a-f0-9]{32,128}$' "$password" || die 'MySQL 测试应用口令需为 32–128 位十六进制，避免 SQL/配置转义歧义'
secret_from_files "$ns" mysql-app "password=$password"
jq -n --arg image "$(image mysql_client)" '{apiVersion:"batch/v1",kind:"Job",metadata:{name:"mysql-probe"},spec:{backoffLimit:0,template:{spec:{restartPolicy:"Never",containers:[{name:"client",image:$image,command:["sh","-ceu","umask 077; printf \"[client]\\nuser=root\\npassword=%s\\nhost=mysql-instances\\nssl-mode=VERIFY_IDENTITY\\nssl-ca=/ca/ca.pem\\n\" \"$(cat /root-auth/rootPassword)\" > /tmp/root.cnf; p=$(cat /app-auth/password); printf \"CREATE DATABASE IF NOT EXISTS app; CREATE USER IF NOT EXISTS app IDENTIFIED BY '\''%s'\''; GRANT ALL ON app.* TO app;\\n\" \"$p\" | mysql --defaults-extra-file=/tmp/root.cnf; printf \"[client]\\nuser=app\\npassword=%s\\nhost=mysql-instances\\nssl-mode=VERIFY_IDENTITY\\nssl-ca=/ca/ca.pem\\n\" \"$p\" > /tmp/app.cnf; mysql --defaults-extra-file=/tmp/app.cnf app -e \"CREATE TABLE IF NOT EXISTS probe(id INT PRIMARY KEY,payload VARCHAR(64)); INSERT IGNORE INTO probe VALUES(1,'\''phase03'\''); SELECT payload FROM probe WHERE id=1\" | grep -Fx phase03"],volumeMounts:[{name:"root",mountPath:"/root-auth",readOnly:true},{name:"app",mountPath:"/app-auth",readOnly:true},{name:"ca",mountPath:"/ca",readOnly:true}]}],volumes:[{name:"root",secret:{secretName:"mysql-root"}},{name:"app",secret:{secretName:"mysql-app"}},{name:"ca",secret:{secretName:"mysql-ca"}}]}}}}' > "$ATTEMPT/mysql-probe.json"
apply "$ATTEMPT/mysql-probe.json" "$ns"
k -n "$ns" wait --for=condition=Complete job/mysql-probe --timeout=180s
k -n "$ns" logs job/mysql-probe > "$ATTEMPT/mysql-result.txt"
