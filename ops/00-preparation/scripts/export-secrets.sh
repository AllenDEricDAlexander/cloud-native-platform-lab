#!/usr/bin/env bash
# 把管理端 ~/.cnpl-secrets 中的口令按服务列到一个文本文件，便于转存到密码管理器。
# 只在管理 Mac 上由用户本人运行；转存后请删除输出文件。
# 用法：bash ops/00-preparation/scripts/export-secrets.sh [输出文件]
#   默认输出 ~/Desktop/cnpl-passwords.txt，权限 0600。桌面若开启了 iCloud 同步，请指定其他路径，
#   例如 ~/cnpl-passwords.txt，避免文件被上传。
# 紧邻中文的变量一律写成 ${var}：macOS 自带 bash 3.2 会把全角标点的首字节当成变量名的一部分。
set -euo pipefail

S=$HOME/.cnpl-secrets
OUT=${1:-$HOME/Desktop/cnpl-passwords.txt}
umask 077

v() {
  if [ -s "$S/$1" ]; then cat "$S/$1"; else printf '（尚未生成：%s）' "$1"; fi
}

{
  echo "cloud-native-platform-lab 口令清单（生成于 $(date '+%F %T')）"
  echo "转存到密码管理器后请删除本文件。"
  echo
  echo "== Harbor  https://harbor.k8s.internal.egon.top"
  echo "管理员            admin / $(v harbor_admin_password)"
  echo "只读机器人        robot\$cnpl-pull / $(v harbor_robot_cnpl_pull)"
  echo "内部数据库        postgres（harbor-db 容器内）/ $(v harbor_db_password)"
  echo
  echo "== GitLab  https://gitlab.svc.internal.egon.top"
  echo "管理员            root / $(v gitlab_root_password)"
  echo
  echo "== Nexus  https://nexus.svc.internal.egon.top"
  echo "管理员            admin / $(v nexus_admin_password)"
  echo "只读账户          cnpl-reader / $(v nexus_reader_password)"
  echo
  echo "== 备份仓库（restic）  sftp:restic@192.168.9.16:/srv/backup/restic/lab"
  echo "仓库口令          $(v restic_password)"
  echo "（Mac 损坏时解密全部备份的唯一途径，必须另存到 Mac 之外）"
  echo
  echo "== 不在 ~/.cnpl-secrets 中、由你自己保管的口令"
  echo "内部根 CA 私钥口令、中间 CA 私钥口令（~/cnpl-pki，create-ca.sh 时输入）"
  echo "OpenWrt root（控制台 passwd 设置；LuCI 登录用）"
  echo "Rocky 模板 root（克隆机首次登录与 set-vm-identity.sh 用）"
  echo "vCenter、ESXi、iDRAC 管理员"
  echo "代理订阅地址（只在 OpenWrt 的 /etc/mihomo/subscription-url）"
} > "$OUT"
chmod 600 "$OUT"
echo "已写入 ${OUT}（权限 600）。转存后请删除：rm ${OUT}"
