#!/usr/bin/env bash
source "$(dirname "$0")/../lib/common.sh"
[[ $(role) == admin && $(id -un) == ops ]] || die '在 admin 的 ops 会话执行'
[[ -s $HOME/.ssh/cnpl_git ]] || die '先生成并解锁本项目专用 Git 密钥'
need git
work=$(mktemp -d /srv/cnpl/records/gitlab-check.XXXXXX)
export GIT_SSH_COMMAND="ssh -i $HOME/.ssh/cnpl_git -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o BatchMode=yes"
git clone git@gitlab.svc.internal.egon.top:platform/configuration.git "$work/repository"
cd "$work/repository"
branch=preparation-check-$(date -u +%Y%m%dT%H%M%S)-$(openssl rand -hex 4)
git switch -c "$branch"
printf 'CNPL GitLab preparation acceptance\n' > cnpl-preparation-check.txt
git add cnpl-preparation-check.txt
git -c user.name='CNPL Operator' -c user.email=ops@internal.egon.top commit -m 'Verify preparation repository access'
git push origin "HEAD:refs/heads/$branch"
if git push origin HEAD:main > "$work/protected.log" 2>&1; then die 'main 未拒绝直接写入，停止交付'; fi
grep -Eiq 'protected|not allowed' "$work/protected.log" || die '推送失败原因不是保护策略'
git push origin --delete "$branch"
if GIT_SSH_COMMAND='ssh -o IdentityFile=/dev/null -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes' git ls-remote git@gitlab.svc.internal.egon.top:platform/configuration.git > "$work/unauthorized.log" 2>&1; then die '无授权密钥意外读取私有项目'; fi
grep -Eiq 'Permission denied|publickey' "$work/unauthorized.log" || die '匿名失败原因不是认证拒绝'
printf 'PASS 私有项目 clone、功能分支 push、main 保护与无授权拒绝；记录=%s\n' "$work"
