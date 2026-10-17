#!/usr/bin/env bash
# 下载并校验 restic（00.10.03）：在管理 Mac 上运行，经 Mac 的代理访问 GitHub。
#   1. 下载 SHA256SUMS 与签名，用仓库中固定的发布者公钥（指纹 CF8F18F2…A907）验证签名；
#   2. 下载 linux/amd64（服务器）与 darwin/arm64（管理 Mac）两个版本，核对 SHA256SUMS 与版本锁中的值；
#   3. 解压到种子目录，并写出解压后文件的 SHA256（剧本据此核对传到服务器的文件）。
# 可重复运行：已下载的文件不重复下载，但每次都重新校验。
set -euo pipefail

VERSION=0.19.1
FPR=CF8F18F2844575973F79D4E191A6868BD3F7A907
BASE=https://github.com/restic/restic/releases/download/v${VERSION}
HERE=$(cd "$(dirname "$0")" && pwd)
KEY=$HERE/keys/restic-${FPR}.asc
SEED=${SEED_DIR:-$HOME/Downloads/cloud-native-lab-seed-2026-10-14}/restic
# 与 versions.lock.yaml backup_tool 一致
declare_sha() { case "$1" in
  linux_amd64) echo f415415624dcc452f2a02b8c33641791a8c6d6d3b65bbb3543fcf9a25151585c ;;
  darwin_arm64) echo 7be0a144ccc377880f294204aa271d76e4b79554b42a751151d425ce6ebac143 ;;
esac; }

mkdir -p "$SEED"
cd "$SEED"
for f in SHA256SUMS SHA256SUMS.asc restic_${VERSION}_linux_amd64.bz2 restic_${VERSION}_darwin_arm64.bz2; do
  [ -s "$f" ] || { echo "下载 $f"; curl -fL --retry 3 -o "$f.part" "$BASE/$f"; mv "$f.part" "$f"; }
done

GNUPGHOME=$(mktemp -d); export GNUPGHOME
trap 'rm -rf "$GNUPGHOME"' EXIT
gpg --quiet --import "$KEY" 2>/dev/null
gpg --status-fd 1 --verify SHA256SUMS.asc SHA256SUMS 2>/dev/null | grep -q "VALIDSIG $FPR" \
  || { echo "SHA256SUMS 签名验证失败（期望指纹 ${FPR}）" >&2; exit 1; }
echo "签名：SHA256SUMS 由 $FPR 签名，验证通过"

for arch in linux_amd64 darwin_arm64; do
  f=restic_${VERSION}_${arch}.bz2
  want=$(declare_sha "$arch")
  grep -q "^${want}  ${f}$" SHA256SUMS || { echo "$f 的 SHA256 与签名文件不一致" >&2; exit 1; }
  echo "${want}  ${f}" | shasum -a 256 -c -
  out=restic_${VERSION}_${arch}
  bunzip2 -c "$f" > "$out.part" && chmod 755 "$out.part" && mv "$out.part" "$out"
  shasum -a 256 "$out" | awk '{print $1}' > "$out.sha256"
  echo "$out: $(cat "$out.sha256")"
done
"$SEED/restic_${VERSION}_darwin_arm64" version
