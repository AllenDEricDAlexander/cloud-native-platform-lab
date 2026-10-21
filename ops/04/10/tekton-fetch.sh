#!/usr/bin/env bash
set -euo pipefail
set +x
[[ $SOURCE_URL =~ ^https://gitlab\.svc\.internal\.egon\.top/[a-zA-Z0-9_./-]+\.git$ && $SOURCE_REVISION =~ ^[a-f0-9]{40}$ ]] || exit 2
cd "$(workspaces.source.path)"
private=$(mktemp -d)
trap 'rm -rf -- "$private"' EXIT
cat > "$private/askpass" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "$1" in
    *Username*) printf 'oauth2\n' ;;
    *Password*) cat /source-auth/token ;;
    *) exit 1 ;;
esac
EOF
chmod 700 "$private/askpass"
export GIT_ASKPASS=$private/askpass GIT_TERMINAL_PROMPT=0 LC_MESSAGES=C
git init repository
git -C repository fetch --depth=1 "$SOURCE_URL" "$SOURCE_REVISION"
git -C repository checkout --detach FETCH_HEAD
[[ $(git -C repository rev-parse HEAD) == "$SOURCE_REVISION" ]]
