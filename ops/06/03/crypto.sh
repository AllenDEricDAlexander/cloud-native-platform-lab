#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
action=${1:-}
case "$action" in encrypt|decrypt) ;; *) die '用法：crypto.sh encrypt|decrypt' ;; esac
start 03 "$action"
private_temp
if [[ $action == encrypt ]]; then
    source_file=$(required .secrets.plaintext_file); private_file "$source_file"
    recipient=$(required .secrets.age_recipient)
    [[ $recipient =~ ^age1[0-9a-z]+$ ]] || die 'age recipient 无效'
    sops --encrypt --age "$recipient" --input-type yaml --output-type yaml "$source_file" > "$PRIVATE_TEMP/result"
    destination=$(required .secrets.ciphertext_file)
else
    source_file=$(required .secrets.ciphertext_file); private_file "$source_file"
    identity=$(required .secrets.age_identity_file); private_file "$identity"
    # 仅传身份文件路径，不在环境变量中放私钥正文。
    SOPS_AGE_KEY_FILE="$identity" sops --decrypt --input-type yaml --output-type yaml "$source_file" > "$PRIVATE_TEMP/result"
    destination=$(required .secrets.decrypted_file)
fi
ruby "$P06/03/private-write.rb" "$PRIVATE_TEMP/result" "$destination"
jq -n --arg action "$action" --arg sha "$(sha "$destination")" '{action:$action,output_sha256:$sha,plaintext_logged:false}' > "$ATTEMPT/crypto-result.json"
