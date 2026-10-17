#!/usr/bin/env bash
# 复用 00 已建立的加密 restic 仓库；只新增本身份目录的备份，不执行 forget/prune。
set -euo pipefail
ACCESS=$HOME/.cnpl-secrets/access/lab-primary
RESTIC=$HOME/Downloads/cloud-native-lab-seed-2026-10-14/restic/restic_0.19.1_darwin_arm64
PYTHON=$HOME/.venvs/cnpl-ansible/bin/python
KUBECTL=$HOME/.cnpl/bin/kubectl
SSH_KEY=$HOME/.ssh/cnpl_lab_ed25519
export RESTIC_REPOSITORY=sftp:restic@192.168.9.16:/srv/backup/restic/lab
export RESTIC_PASSWORD_FILE=$HOME/.cnpl-secrets/restic_password

for tool in "$RESTIC" "$PYTHON" "$KUBECTL"; do
  test -x "$tool" || { echo "缺少已锁定工具：$tool" >&2; exit 1; }
done
for file in "$ACCESS/mac.conf" "$ACCESS/adminhost.conf" "$ACCESS/recovery/recovery.conf" "$ACCESS/recovery/recovery-kit.tar.gz" "$RESTIC_PASSWORD_FILE" "$SSH_KEY"; do
  test -s "$file" || { echo "缺少受控材料：$file" >&2; exit 1; }
done
umask 077
STAGE=$(mktemp -d "$HOME/.cnpl-secrets/access-restore.XXXXXXXX")
trap 'rm -rf "$STAGE"' EXIT
r_access() {
  "$RESTIC" -o "sftp.command=ssh -i $SSH_KEY -o IdentitiesOnly=yes -o BatchMode=yes restic@192.168.9.16 -s sftp" \
    --retry-lock 30s "$@"
}

r_access backup --host cnpl-mgmt-mac --tag phase01-access --json "$ACCESS" > "$STAGE/backup.jsonl"
SNAPSHOT=$("$PYTHON" - "$STAGE/backup.jsonl" <<'PY'
import json
from pathlib import Path
import re
import sys
summary = [entry for line in Path(sys.argv[1]).read_text().splitlines()
           if (entry := json.loads(line)).get('message_type') == 'summary']
if len(summary) != 1 or not re.fullmatch(r'[0-9a-f]{8,64}', summary[0].get('snapshot_id', '')):
    raise SystemExit('未取得本次确定的 restic 快照 ID；停止，不使用不确定的 latest。')
print(summary[0]['snapshot_id'])
PY
)
printf 'Encrypted access backup snapshot: %s\n' "$SNAPSHOT"
r_access restore "$SNAPSHOT" --target "$STAGE/restore" --include "$ACCESS/recovery/recovery.conf"
RESTORED=$STAGE/restore$ACCESS/recovery/recovery.conf
test -s "$RESTORED"
cmp "$ACCESS/recovery/recovery.conf" "$RESTORED"
chmod 0600 "$RESTORED"
"$KUBECTL" --kubeconfig "$RESTORED" --context lab-primary-recovery-cp01 --request-timeout=15s get nodes -o name
echo 'ACCESS BACKUP RESTORE PASS: encrypted snapshot on .16, exact recovery file restored and API authentication verified; temporary restore cleaned on exit.'
