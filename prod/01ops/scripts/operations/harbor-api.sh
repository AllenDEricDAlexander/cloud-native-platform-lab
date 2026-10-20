#!/usr/bin/env bash
source "$(dirname "$0")/../lib/common.sh"
source "$(dirname "$0")/../lib/http.sh"
root; expect_host harbor; need jq
umask 077; work=$(mktemp -d); trap 'rm -rf -- "$work"' EXIT
secrets=/etc/cnpl/secrets; base=https://harbor.k8s.internal.egon.top/api/v2.0
HTTP_NETRC=$secrets/harbor-admin.netrc
[[ -s $secrets/harbor-admin.password ]] || die '缺少正式管理员凭据'
password=$(cat "$secrets/harbor-admin.password")
printf 'machine harbor.k8s.internal.egon.top\nlogin admin\npassword %s\n' "$password" > "$work/admin.netrc"; unset password
put "$work/admin.netrc" "$HTTP_NETRC" 0600
case "${1:-}" in
  projects)
    for project in bootstrap business; do
        public=false; [[ $project != bootstrap ]] || public=true
        http GET "$base/projects?name=$project" '' "$work/project.json"; http_ok
        count=$(jq --arg name "$project" '[.[]|select(.name==$name)]|length' "$work/project.json")
        if [[ $count == 0 ]]; then
            jq -n --arg name "$project" --arg public "$public" '{project_name:$name,metadata:{public:$public}}' > "$work/create.json"
            http POST "$base/projects" "$work/create.json" "$work/response.json"; http_ok; CNPL_CHANGED=1
        else
            jq -e --arg name "$project" --arg public "$public" '[.[]|select(.name==$name and .metadata.public==$public)]|length==1' "$work/project.json" >/dev/null || die '已有项目公开属性不符'
        fi
    done
    ;;
  robots)
    for access in publisher reader; do
        file=$secrets/harbor-$access.json
        if [[ -s $file ]]; then
            id=$(jq -er '.id' "$file")
            http GET "$base/robots/$id" '' "$work/robot.json"; http_ok
            jq -e --argjson now "$(date +%s)" '.disable==false and (.expires_at==-1 or .expires_at>$now+86400)' "$work/robot.json" >/dev/null || die '机器人被停用或将到期，先走凭据维护'
        else
            http GET "$base/robots?page_size=100" '' "$work/robots.json"; http_ok
            jq -e --arg name "bootstrap-$access" '[.[]|select(.name|endswith($name))]|length==0' "$work/robots.json" >/dev/null || die '已有机器人但本机缺少一次性秘密，停止而不创建重复账号'
            actions='[{"resource":"repository","action":"pull"}]'
            [[ $access != publisher ]] || actions='[{"resource":"repository","action":"pull"},{"resource":"repository","action":"push"}]'
            jq -n --arg name "bootstrap-$access" --argjson access "$actions" '{name:$name,description:"Preparation image supply",duration:90,level:"project",permissions:[{kind:"project",namespace:"bootstrap",access:$access}]}' > "$work/create.json"
            http POST "$base/robots" "$work/create.json" "$work/new-robot.json"; http_ok
            jq -e '.id and .name and .secret' "$work/new-robot.json" >/dev/null || die '机器人响应缺少一次性秘密'
            put "$work/new-robot.json" "$file" 0600; CNPL_CHANGED=1
        fi
        id=$(jq -er '.id' "$file")
        http GET "$base/robots/$id" '' "$work/robot-current.json"; http_ok
        actions='[{"resource":"repository","action":"pull"}]'
        [[ $access != publisher ]] || actions='[{"resource":"repository","action":"pull"},{"resource":"repository","action":"push"}]'
        jq -e --argjson actions "$actions" '.level=="project" and (.permissions|length)==1 and .permissions[0].kind=="project" and .permissions[0].namespace=="bootstrap" and ([.permissions[0].access[]|{resource,action}]|sort_by(.resource,.action))==($actions|sort_by(.resource,.action))' "$work/robot-current.json" >/dev/null || die '机器人具有非预期的项目或权限'
    done
    ;;
  scan)
    digest=${2:?需要已供应的 busybox 摘要}
    [[ $digest =~ ^sha256:[0-9a-f]{64}$ ]] || die '摘要不合法'
    printf '{}' > "$work/request.json"
    http POST "$base/projects/bootstrap/repositories/busybox/artifacts/$digest/scan" "$work/request.json" "$work/scan.json"; http_ok
    for attempt in $(seq 1 60); do
        http GET "$base/projects/bootstrap/repositories/busybox/artifacts/$digest?with_scan_overview=true" '' "$work/artifact.json"; http_ok
        if jq -e '[.scan_overview[]?.scan_status]|any(.=="Success")' "$work/artifact.json" >/dev/null; then printf 'PASS Trivy 实际扫描成功\n'; exit 0; fi
        jq -e '[.scan_overview[]?.scan_status]|all(.!="Error")' "$work/artifact.json" >/dev/null || die 'Trivy 扫描失败，检查代理和扫描库'
        sleep 5
    done
    die '扫描未在验收窗口完成'
    ;;
  *) die '用法：harbor-api.sh projects|robots|scan busybox摘要';;
esac
result
