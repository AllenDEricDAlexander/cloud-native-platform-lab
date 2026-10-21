#!/usr/bin/env sh
set -eu
umask 077
work=$(mktemp -d); trap 'rm -rf -- "$work"' EXIT
password=$(cat /auth/elastic)
case "$password" in *'"'*|*'\'*|*'
'*) exit 1;; esac
printf 'silent\nshow-error\nfail-with-body\ncacert = "/ca/tls.crt"\nuser = "elastic:%s"\n' "$password" > "$work/root.conf"
endpoint=https://search-es-http.cnpl03-08.svc.cluster.local:9200
printf '{"cluster":[],"indices":[{"names":["cnpl03-*"],"privileges":["create_index","read","write"]}]}' > "$work/role.json"
curl --config "$work/root.conf" -X PUT -H 'Content-Type: application/json' --data-binary "@$work/role.json" "$endpoint/_security/role/cnpl03" >/dev/null
jq -n --rawfile p /app/password '{password:($p|rtrimstr("\n")),roles:["cnpl03"]}' > "$work/user.json"
curl --config "$work/root.conf" -X PUT -H 'Content-Type: application/json' --data-binary "@$work/user.json" "$endpoint/_security/user/cnpl03" >/dev/null
printf 'silent\nshow-error\nfail-with-body\ncacert = "/ca/tls.crt"\nuser = "cnpl03:%s"\n' "$(cat /app/password)" > "$work/app.conf"
jq -n --arg run "$CNPL_RUN" '{run:$run,sequence:1}' > "$work/document.json"
curl --config "$work/app.conf" -X PUT -H 'Content-Type: application/json' --data-binary "@$work/document.json" "$endpoint/cnpl03-$CNPL_RUN/_doc/1?refresh=wait_for" | jq -e '._id=="1"' >/dev/null
curl --config "$work/app.conf" "$endpoint/cnpl03-$CNPL_RUN/_doc/1" | jq -e --arg run "$CNPL_RUN" '._source.run==$run and ._source.sequence==1' >/dev/null
code=$(curl --silent --show-error --cacert /ca/tls.crt --output /dev/null --write-out '%{http_code}' "$endpoint/cnpl03-$CNPL_RUN/_doc/1")
[ "$code" = 401 ] || exit 1
printf 'PASS ECK TLS、受限 app 写读、匿名 401；独立快照恢复另行验收\n'
