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
mkdir -p "$work/www/cgi-bin"
printf '#!/bin/sh\nexec /bin/sh /app/app.sh cgi\n' > "$work/www/cgi-bin/check"
chmod 755 "$work/www/cgi-bin/check"
printf 'pod=%s node=%s\n' "$POD_NAME" "$NODE_NAME" > "$work/www/index.html"
echo 0 > "$work/delay"
server=
stop() {
  trap '' TERM INT
  rm -f "$work/ready"
  echo "$1 received; draining"
  if test -n "$server"; then
    kill "$server" 2>/dev/null || :
    # 子进程收到终止信号时 wait 可以非零；必须等它结束后才写完成回执。
    wait "$server" || :
  fi
  if test -n "${TERMINATION_MESSAGE_PATH:-}"; then
    printf 'cnpl-termination-v1 signal=%s pod_uid=%s child_reaped=true exit=0\n' \
      "$1" "${POD_UID:-unknown}" > "$TERMINATION_MESSAGE_PATH"
  fi
  echo "$1 complete; exit=0"
  exit 0
}
trap 'stop TERM' TERM
trap 'stop INT' INT
"${HTTPD_BIN:-httpd}" -f -p 8080 -h "$work/www" &
server=$!
touch "$work/startup" "$work/live" "$work/ready"
echo "START ready pod=$POD_NAME node=$NODE_NAME"
wait "$server"
