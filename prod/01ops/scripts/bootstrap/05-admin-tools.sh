#!/usr/bin/env bash
source "$(dirname "$0")/../lib/common.sh"
root; expect_host admin
[[ -f /etc/yum.repos.d/cnpl-private.repo ]] || die '先完成 5.6 内网源和签名验收'
lock=/srv/cnpl/inputs/admin-tools.lock.json
[[ -s $lock ]] || die '先在 5.7 运行 prepare-inputs.sh admin-packages，选定真实 NEVRA'
packages=()
for name in ansible-core helm kubectl restic; do
    value=$(jq -er --arg name "$name" '.[$name]' "$lock")
    [[ $value == "$name"-[0-9]*:* && $value != *' '* ]] || die '管理工具版本锁格式异常'
    packages+=("$value")
done
private_install "${packages[@]}" git jq skopeo 'dnf-command(versionlock)'
for name in ansible-core helm kubectl restic; do
    actual=$(rpm -q --qf '%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}' "$name")
    [[ $actual == "$(jq -er --arg name "$name" '.[$name]' "$lock")" ]] || die '管理工具实际版本与锁定输入不一致'
done
dnf versionlock add "${packages[@]}"
install -d -o ops -g ops -m 0750 /srv/cnpl/inputs/host_vars /srv/cnpl/inputs/group_vars
put "$CNPL_ROOT/inputs/ansible.cfg" /srv/cnpl/inputs/ansible.cfg 0644
put "$CNPL_ROOT/inputs/hosts.ini" /srv/cnpl/inputs/hosts.ini 0644
rpm -q ansible-core helm kubectl git jq restic skopeo > /srv/cnpl/inputs/admin-rpm-versions.txt
chown ops:ops /srv/cnpl/inputs/ansible.cfg /srv/cnpl/inputs/hosts.ini /srv/cnpl/inputs/admin-rpm-versions.txt
ansible --version
helm version --short
kubectl version --client=true --output=yaml
printf 'PASS 管理工具仅在 5.7 从内网源安装；未执行集群操作\n'
