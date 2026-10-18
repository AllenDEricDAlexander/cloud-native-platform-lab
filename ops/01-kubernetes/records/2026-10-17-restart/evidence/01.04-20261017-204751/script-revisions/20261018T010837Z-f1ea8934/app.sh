#!/bin/sh
# 同一镜像提供启动、健康、延迟及 TERM 观测点；01.05 可继续复用。
set -eu
work=${APP_WORK:-/work}
if test "${1:-}" = cgi; then
  mode=${QUERY_STRING:-identity}
  case "$mode" in
    startup|live|ready)
      if ! test -f "$work/$mode"; then
        printf 'Status: 503 Service Unavailable\r\nContent-Type: text/plain\r\n\r\n%s=false\n' "$mode"
        exit 0
      fi ;;
    delay)
      seconds=$(cat "$work/delay")
      case "$seconds" in 0|1|2|3|4|5) sleep "$seconds" ;; *) exit 1 ;; esac ;;
    identity) ;;
    *) printf 'Status: 400 Bad Request\r\n\r\nunknown mode\n'; exit 0 ;;
  esac
  printf 'Content-Type: text/plain\r\n\r\nmode=%s pod=%s node=%s\n' "$mode" "$POD_NAME" "$NODE_NAME"
  exit 0
fi
case "${START_DELAY:-2}" in 0|1|2|3|4|5|10|20|30) sleep "${START_DELAY:-2}" ;; *) exit 2 ;; esac
mkdir -p /work/www/cgi-bin
printf '#!/bin/sh\nexec /bin/sh /app/app.sh cgi\n' > /work/www/cgi-bin/check
chmod 755 /work/www/cgi-bin/check
printf 'pod=%s node=%s\n' "$POD_NAME" "$NODE_NAME" > /work/www/index.html
touch /work/startup /work/live /work/ready
echo 0 > /work/delay
httpd -f -p 8080 -h /work/www &
server=$!
stop() {
  echo "TERM received; draining"
  kill "$server"
  wait "$server" || :
  echo "TERM complete; exit=0"
  exit 0
}
trap stop TERM INT
echo "START ready pod=$POD_NAME node=$NODE_NAME"
wait "$server"
