#!/usr/bin/env python3
"""入群前只读检查；只输出状态和公开信息，不读取 kubeconfig/加密配置内容。"""
import argparse
import json
from pathlib import Path
import shutil
import socket
import subprocess


def run(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError(f'{args[0]} 检查失败，rc={result.returncode}')
    return result.stdout.strip()


def inspect_state(kube, kubelet, etcd, control_plane):
    joined = (kube / 'kubelet.conf').is_file()
    artifacts = [kube / 'bootstrap-kubelet.conf', kubelet / 'config.yaml',
                 kube / 'pki/ca.crt', etcd / 'member']
    manifests = ['kube-apiserver', 'kube-controller-manager', 'kube-scheduler', 'etcd']
    artifacts += [kube / f'manifests/{name}.yaml' for name in manifests]
    if not joined and any(path.exists() for path in artifacts):
        raise ValueError('发现未完成的入群产物；保留现场排查，不自动 reset 或重复 join。')
    if joined:
        required = [kubelet / 'config.yaml', kube / 'pki/ca.crt']
        if control_plane:
            required += [kube / 'admin.conf', etcd / 'member']
            required += [kube / f'manifests/{name}.yaml' for name in manifests]
        for path in required:
            if not path.exists():
                raise ValueError(f'已有 kubelet.conf，但缺少 {path}；不能当作完整入群跳过。')
    return joined


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['fqdn', 'address', 'api', 'vip', 'version', 'pod-cidr']:
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--control-plane', action='store_true')
    args = parser.parse_args()
    tools = ['kubeadm', 'kubelet', 'crictl', 'systemctl', 'hostnamectl', 'ip', 'getenforce', 'firewall-cmd']
    if args.control_plane:
        tools += ['kubectl', 'restorecon', 'matchpathcon']
    missing = [tool for tool in tools if shutil.which(tool) is None]
    if missing:
        raise ValueError('缺少命令：' + ', '.join(missing))
    if run('hostnamectl', '--static') != args.fqdn:
        raise ValueError('主机名与 inventory 不符。')
    addresses = json.loads(run('ip', '-j', '-4', 'address', 'show'))
    if args.address not in [item['local'] for link in addresses for item in link.get('addr_info', [])]:
        raise ValueError('节点 IP 与 inventory 不符。')
    if run('kubeadm', 'version', '-o', 'short') != 'v' + args.version:
        raise ValueError('kubeadm 版本与版本锁不符。')
    if run('kubelet', '--version') != 'Kubernetes v' + args.version:
        raise ValueError('kubelet 版本与版本锁不符。')
    if run('getenforce') != 'Enforcing':
        raise ValueError('SELinux 必须保持 Enforcing。')
    for service in ['containerd', 'firewalld']:
        if run('systemctl', 'is-active', service) != 'active':
            raise ValueError(service + ' 未运行。')
    conditions = json.loads(run('crictl', 'info'))['status']['conditions']
    if not any(item['type'] == 'RuntimeReady' and item['status'] is True for item in conditions):
        raise ValueError('CRI RuntimeReady 未通过。')
    if set(socket.gethostbyname_ex(args.api)[2]) != {args.vip}:
        raise ValueError('API DNS 解析与规划 VIP 不符。')
    with socket.create_connection((args.api, 6443), timeout=5):
        pass
    kube = Path('/etc/kubernetes')
    joined = inspect_state(kube, Path('/var/lib/kubelet'), Path('/var/lib/etcd'), args.control_plane)
    state = subprocess.run(['systemctl', 'is-active', 'kubelet'], capture_output=True, text=True, timeout=15).stdout.strip()
    if state != ('active' if joined else 'inactive'):
        raise ValueError(f'kubelet 状态 {state} 与入群产物不符；保留现场排查。')
    if args.control_plane:
        run('firewall-cmd', '--zone=public', '--query-rich-rule='
            f'rule family="ipv4" source address="{args.pod_cidr}" port port="6443" protocol="tcp" accept')
        for path in [kube / 'enc/encryption-config.yaml', kube / 'audit/policy.yaml', kube / 'pki',
                     Path('/var/lib/etcd'), Path('/var/log/kubernetes/audit')]:
            run('matchpathcon', '-V', str(path))
        dropin = Path('/etc/systemd/system/kubelet.service.d/20-kubernetes-selinux.conf')
        if 'ExecStartPre=/usr/sbin/restorecon' not in dropin.read_text():
            raise ValueError('缺少 kubelet 启动前的 SELinux 标签恢复。')
    print(json.dumps({'joined': joined, 'kubelet': state, 'node': args.fqdn}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.TimeoutExpired) as error:
        raise SystemExit(str(error))
