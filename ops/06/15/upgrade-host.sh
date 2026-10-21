#!/usr/bin/env bash
# 仅由用户显式调用 upgrade-node 时执行；此脚本不负责跨节点编排或降级。
set -euo pipefail
set +x
umask 077
node=$1 ip_expected=$2 mode=$3 source_version=$4 target=$5 directory=$6
[[ $(hostname -f) == "$node" && $target =~ ^v1\.[0-9]+\.[0-9]+$ ]]
ip -j addr | python3 -c 'import json,sys;assert any(a.get("local")==sys.argv[1] for i in json.load(sys.stdin) for a in i.get("addr_info",[]))' "$ip_expected"
[[ $(getenforce) == Enforcing ]]
firewall-cmd --state
[[ $directory =~ ^/var/lib/cnpl06/[a-z][a-z0-9-]{2,19}/15$ && -d $directory && ! -L $directory ]]
[[ $(kubelet --version | awk '{print $2}') == "$source_version" ]] || { printf '当前 kubelet 非源版本；停止并按失败规程核对，不自动重跑/降级。\n' >&2; exit 1; }
for package in kubeadm kubelet kubectl; do
    file=$directory/$package.rpm
    test -f "$file"; test ! -L "$file"
    rpm --checksig "$file"
    [[ $(rpm -qp --qf '%{NAME}' "$file") == "$package" ]]
    [[ v$(rpm -qp --qf '%{VERSION}' "$file") == "$target" ]]
done
dnf --disablerepo='*' --setopt=localpkg_gpgcheck=1 install -y "$directory/kubeadm.rpm"
case "$mode" in
    first-control-plane) kubeadm upgrade plan "$target"; kubeadm upgrade apply "$target" --yes ;;
    remaining-control-plane|worker) kubeadm upgrade node ;;
    *) exit 2 ;;
esac
dnf --disablerepo='*' --setopt=localpkg_gpgcheck=1 install -y "$directory/kubelet.rpm" "$directory/kubectl.rpm"
systemctl daemon-reload
systemctl restart kubelet
[[ $(kubelet --version | awk '{print $2}') == "$target" ]]
printf '当前节点软件已更新；保持 cordon，等待管理端真实业务回归后 complete-node。\n'
