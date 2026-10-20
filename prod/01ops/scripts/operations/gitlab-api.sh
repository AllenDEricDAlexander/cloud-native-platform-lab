#!/usr/bin/env bash
source "$(dirname "$0")/../lib/common.sh"
source "$(dirname "$0")/../lib/http.sh"
root; expect_host gitlab; need jq
umask 077; work=$(mktemp -d); trap 'rm -rf -- "$work"' EXIT
secrets=/etc/cnpl/secrets; base=https://gitlab.svc.internal.egon.top/api/v4
HTTP_HEADER=$secrets/gitlab-bootstrap.header
case "${1:-}" in
  token)
    if [[ ! -e $secrets/gitlab-bootstrap.token ]]; then
        [[ ! -e $secrets/gitlab-bootstrap.revoked ]] || die '引导 token 已撤销；后续维护需显式重新授权'
        gitlab-rails runner 'u=User.find_by_username!("root"); raise "bootstrap token already exists" if u.personal_access_tokens.active.where(name:"cnpl-bootstrap").exists?; t=u.personal_access_tokens.create!(name:"cnpl-bootstrap",scopes:["api"],expires_at:7.days.from_now.to_date); puts t.token' > "$work/token"
        grep -Eq '^glpat-[A-Za-z0-9_-]+$' "$work/token" || die '令牌输出格式异常，不打印内容'
        put "$work/token" "$secrets/gitlab-bootstrap.token" 0600
    fi
    { printf 'PRIVATE-TOKEN: '; cat "$secrets/gitlab-bootstrap.token"; } > "$work/header"
    put "$work/header" "$HTTP_HEADER" 0600
    http GET "$base/user" '' "$work/user.json"; http_ok
    jq -e '.username=="root"' "$work/user.json" >/dev/null || die '引导身份不符'
    ;;
  project)
    [[ -s $HTTP_HEADER && -s /etc/cnpl/inputs/cnpl_git.pub ]] || die '先准备短期令牌和 admin 专用 Git 公钥'
    http GET "$base/groups/platform" '' "$work/group.json"
    if [[ $HTTP_CODE == 404 ]]; then
        printf '%s\n' '{"name":"platform","path":"platform","visibility":"private"}' > "$work/create.json"
        http POST "$base/groups" "$work/create.json" "$work/group.json"; http_ok; CNPL_CHANGED=1
    else http_ok; fi
    jq -e '.full_path=="platform" and .visibility=="private"' "$work/group.json" >/dev/null || die '已有组不符'
    group=$(jq -er .id "$work/group.json")
    http GET "$base/projects/platform%2Fconfiguration" '' "$work/project.json"
    if [[ $HTTP_CODE == 404 ]]; then
        jq -n --argjson id "$group" '{name:"configuration",path:"configuration",namespace_id:$id,visibility:"private",initialize_with_readme:true,default_branch:"main"}' > "$work/create.json"
        http POST "$base/projects" "$work/create.json" "$work/project.json"; http_ok; CNPL_CHANGED=1
    else http_ok; fi
    jq -e '.path_with_namespace=="platform/configuration" and .visibility=="private" and .default_branch=="main"' "$work/project.json" >/dev/null || die '已有项目属性不符'
    project=$(jq -er .id "$work/project.json")
    http GET "$base/projects/$project/deploy_keys?per_page=100" '' "$work/keys.json"; http_ok
    key=$(awk '{print $1" "$2}' /etc/cnpl/inputs/cnpl_git.pub)
    [[ $key == 'ssh-ed25519 '* ]] || die 'Git 公钥格式不正确'
    if ! jq -e --arg key "$key" 'any(.[];(.key|split(" ")|.[0:2]|join(" "))==$key and .can_push==true)' "$work/keys.json" >/dev/null; then
        jq -n --rawfile key /etc/cnpl/inputs/cnpl_git.pub '{title:"admin-configuration",key:($key|rtrimstr("\n")),can_push:true}' > "$work/create.json"
        http POST "$base/projects/$project/deploy_keys" "$work/create.json" "$work/key.json"; http_ok; CNPL_CHANGED=1
    fi
    http GET "$base/projects/$project/protected_branches/main" '' "$work/protected.json"
    if [[ $HTTP_CODE == 404 ]]; then
        printf '%s\n' '{"name":"main","push_access_level":0,"merge_access_level":40,"allow_force_push":false}' > "$work/create.json"
        http POST "$base/projects/$project/protected_branches" "$work/create.json" "$work/protected.json"; http_ok; CNPL_CHANGED=1
    else http_ok; fi
    jq -e '.allow_force_push==false and ([.push_access_levels[].access_level]|all(.==0)) and ([.merge_access_levels[].access_level]|all(.==40))' "$work/protected.json" >/dev/null || die 'main 分支保护不符合要求'
    printf '%s\n' "$project" > /etc/cnpl/inputs/gitlab-project-id
    ;;
  revoke)
    if [[ -e $secrets/gitlab-bootstrap.revoked ]]; then printf 'PASS 本次引导 token 已撤销\n'; exit; fi
    http DELETE "$base/personal_access_tokens/self" '' "$work/revoked.json"; http_ok
    install -m 0600 /dev/null "$secrets/gitlab-bootstrap.revoked"
    rm -f "$secrets/gitlab-bootstrap.token" "$HTTP_HEADER"
    ;;
  *) die '用法：gitlab-api.sh token|project|revoke';;
esac
result
