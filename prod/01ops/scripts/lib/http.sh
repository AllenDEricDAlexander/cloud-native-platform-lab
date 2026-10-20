#!/usr/bin/env bash
# 响应保存在调用方 0700 临时目录；日志只输出 HTTP 状态，不显示令牌/响应正文。
http() {
    local method=$1 url=$2 input=${3:-} out=$4
    local args=(--noproxy '*' --silent --show-error --connect-timeout 5 --max-time 120 --request "$method" --output "$out" --write-out '%{http_code}')
    [[ -z ${HTTP_NETRC:-} ]] || args+=(--netrc-file "$HTTP_NETRC")
    [[ -z ${HTTP_HEADER:-} ]] || args+=(--header "@$HTTP_HEADER")
    [[ -z $input ]] || args+=(--header 'Content-Type: application/json' --data-binary "@$input")
    HTTP_CODE=$(curl "${args[@]}" "$url") || die 'HTTPS 请求传输失败'
}
http_ok() { case $HTTP_CODE in 200|201|202|204) ;; *) die "HTTP=$HTTP_CODE，请检查本机应用日志，停止后续步骤";; esac; }
