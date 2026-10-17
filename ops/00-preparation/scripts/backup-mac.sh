#!/usr/bin/env bash
# 管理端备份（00.10.03）：在管理 Mac 上运行，把只存在于 Mac 或 OpenWrt 上的内容备份到 restic 仓库。
#   ~/cnpl-pki        内部 CA 私钥（已加密）与签发的证书
#   ~/.cnpl-secrets   各服务口令、机器人密钥、restic 口令本身
#   OpenWrt 配置      sysupgrade -b 生成的配置包（不含 /etc/mihomo 下的订阅地址）
# 随后清理本机快照、prune 并检查仓库。用法：bash ops/00-preparation/scripts/backup-mac.sh [--init]
#   --init  仓库不存在时初始化（由 playbooks/backup.yml 调用）
# 仓库口令在 ~/.cnpl-secrets/restic_password；务必另存一份到 Mac 之外，否则 Mac 损坏后无法解密任何备份。
set -euo pipefail

VERSION=0.19.1
SEED=${SEED_DIR:-$HOME/Downloads/cloud-native-lab-seed-2026-10-14}/restic
RESTIC=$SEED/restic_${VERSION}_darwin_arm64
KEY=${LAB_SSH_KEY:-$HOME/.ssh/cnpl_lab_ed25519}
HOST_IP=192.168.9.16
STAGE=$HOME/.cnpl-backup-staging
export RESTIC_REPOSITORY=sftp:restic@${HOST_IP}:/srv/backup/restic/lab
export RESTIC_PASSWORD_FILE=$HOME/.cnpl-secrets/restic_password
SFTP=(-o "sftp.command=ssh -i $KEY -o IdentitiesOnly=yes -o BatchMode=yes restic@${HOST_IP} -s sftp")
r() { "$RESTIC" "${SFTP[@]}" --retry-lock 30m "$@"; }

[ -x "$RESTIC" ] || { echo "缺少 ${RESTIC}，请先运行 scripts/fetch-restic.sh" >&2; exit 1; }
[ -s "$RESTIC_PASSWORD_FILE" ] || { echo "缺少 ${RESTIC_PASSWORD_FILE}（由 playbooks/backup.yml 生成）" >&2; exit 1; }

if [ "${1:-}" = --init ]; then
  if "$RESTIC" "${SFTP[@]}" cat config >/dev/null 2>&1; then
    echo "仓库已存在"
  else
    "$RESTIC" "${SFTP[@]}" init
  fi
  exit 0
fi

install -d -m 0700 "$STAGE"
ssh openwrt -o BatchMode=yes 'sysupgrade -b -' > "$STAGE/openwrt-config.tar.gz"
[ -s "$STAGE/openwrt-config.tar.gz" ] || { echo "OpenWrt 配置包为空" >&2; exit 1; }
echo "OpenWrt 配置包：$(wc -c < "$STAGE/openwrt-config.tar.gz") 字节"

r backup --host cnpl-mgmt-mac --tag mac "$HOME/cnpl-pki" "$HOME/.cnpl-secrets" "$STAGE"
r forget --host cnpl-mgmt-mac --keep-daily 7 --keep-weekly 4 --keep-monthly 6
r prune
echo "== 快照"
r snapshots --compact
echo "== 仓库检查"
r check
