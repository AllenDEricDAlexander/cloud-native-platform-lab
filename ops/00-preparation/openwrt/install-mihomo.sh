#!/usr/bin/env bash
# 在 OpenWrt 上安装 mihomo 显式代理（00.06.02）：在管理 Mac 上运行。
#   1. 种子目录中没有二进制时，从 GitHub Releases 下载（经 Mac 的代理），按版本锁的 SHA256 校验；
#   2. 经 SSH（密钥登录）写入 /usr/bin/mihomo、/etc/mihomo/config.template.yaml、/etc/init.d/mihomo；
#   3. 有订阅地址文件时启用并重启服务，否则只安装并提示。
# 订阅地址不经过本脚本：由用户直接写入 OpenWrt 的 /etc/mihomo/subscription-url（见执行记录第 86 节）；
# 输出的日志已把 URL 替换为 <url>，可直接写入证据。
# 用法：bash ops/00-preparation/openwrt/install-mihomo.sh
set -euo pipefail

VERSION=v1.19.32
ASSET=mihomo-linux-amd64-compatible-${VERSION}.gz
SHA256=ba3ce607747a07f948fc35780e108a4a7c7f552a38b9bd4d115f313ebcb89c20
URL=https://github.com/MetaCubeX/mihomo/releases/download/${VERSION}/${ASSET}
SEED=${SEED_DIR:-$HOME/Downloads/cloud-native-lab-seed-2026-10-14}/mihomo
HOST=${OPENWRT_HOST:-192.168.9.10}
KEY=${LAB_SSH_KEY:-$HOME/.ssh/cnpl_lab_ed25519}
HERE=$(cd "$(dirname "$0")" && pwd)
SSH=(ssh -i "$KEY" -o IdentitiesOnly=yes -o BatchMode=yes "root@${HOST}")

mkdir -p "$SEED"
if [ ! -f "$SEED/$ASSET" ]; then
  echo "下载 ${URL}"
  curl -fL --retry 3 -o "$SEED/$ASSET.part" "$URL"
  mv "$SEED/$ASSET.part" "$SEED/$ASSET"
fi
echo "${SHA256}  $SEED/$ASSET" | shasum -a 256 -c -

"${SSH[@]}" 'mkdir -p /etc/mihomo && chmod 700 /etc/mihomo'

# 二进制约 62 MB，而 OpenWrt 根分区约 100 MB，放不下新旧两份（第 89 节：先写 .new 再替换导致磁盘写满）。
# 已是同一文件时跳过；否则先停服务、删除旧文件，确认空间足够后直接写入，再核对哈希。
BIN_SHA=$(gunzip -c "$SEED/$ASSET" | shasum -a 256 | awk '{print $1}')
BIN_KB=$(( $(gunzip -c "$SEED/$ASSET" | wc -c) / 1024 + 1 ))
REMOTE_SHA=$("${SSH[@]}" 'rm -f /usr/bin/mihomo.new; sha256sum /usr/bin/mihomo 2>/dev/null | cut -d" " -f1')
if [ "$BIN_SHA" = "$REMOTE_SHA" ]; then
  echo "/usr/bin/mihomo 已是该版本（sha256 ${BIN_SHA}），跳过传输"
else
  "${SSH[@]}" 'if [ -x /etc/init.d/mihomo ]; then /etc/init.d/mihomo stop; fi; rm -f /usr/bin/mihomo'
  AVAIL_KB=$("${SSH[@]}" "df -k / | awk 'NR == 2 {print \$4}'")
  if [ "$AVAIL_KB" -lt $(( BIN_KB + 4096 )) ]; then
    echo "OpenWrt 根分区可用 ${AVAIL_KB} KB，不足以写入 ${BIN_KB} KB 的二进制（另留 4 MB）" >&2
    exit 1
  fi
  gunzip -c "$SEED/$ASSET" | "${SSH[@]}" 'cat > /usr/bin/mihomo && chmod 755 /usr/bin/mihomo'
  [ "$("${SSH[@]}" 'sha256sum /usr/bin/mihomo | cut -d" " -f1')" = "$BIN_SHA" ] || { echo "写入后哈希不符" >&2; exit 1; }
  echo "/usr/bin/mihomo 已写入（sha256 ${BIN_SHA}）"
fi
"${SSH[@]}" 'cat > /etc/mihomo/config.template.yaml' < "$HERE/mihomo/config.template.yaml"
"${SSH[@]}" 'cat > /etc/init.d/mihomo && chmod 755 /etc/init.d/mihomo' < "$HERE/mihomo/mihomo.init"

"${SSH[@]}" 'sh -s' <<'REMOTE'
echo "mihomo: $(/usr/bin/mihomo -v | head -n1)"
df -h / | awk 'NR == 2 {print "rootfs: size " $2 ", used " $3 ", avail " $4}'
if [ -s /etc/mihomo/subscription-url ]; then
  /etc/init.d/mihomo enable
  # 首次安装时服务尚未运行，restart 会报 "ubus call service delete ... Not found"（无害），改为按状态选择。
  if pidof mihomo >/dev/null; then /etc/init.d/mihomo restart; else /etc/init.d/mihomo start; fi
  sleep 8
  echo "service: $(pidof mihomo >/dev/null && echo running || echo stopped)"
  netstat -ltn 2>/dev/null | awk '$4 ~ /:7890$/ {print "listen:", $4}'
  # 日志中可能出现订阅地址或订阅服务器域名：去掉逐连接日志，其余行中的 URL 替换为 <url>。
  logread -e mihomo | grep -v -e '\[TCP\]' -e '\[UDP\]' | tail -n 8 | sed -E 's#[a-zA-Z]+://[^ "]+#<url>#g'
else
  echo "尚未写入 /etc/mihomo/subscription-url：服务已安装、未启用"
fi
REMOTE
