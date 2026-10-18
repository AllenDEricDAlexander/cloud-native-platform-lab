#!/usr/bin/env python3
"""由 Ansible 在控制平面运行：只读前检/私有备份/清理本次暂存；从不启动 etcd 或覆盖在用数据。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile


ROOT = Path('/root/cnpl-control-plane-backups')
ETCD = Path('/var/lib/etcd')
RESOLV = Path('/etc/resolv.conf')
FILES = ['/etc/kubernetes', '/var/lib/kubelet/config.yaml', '/var/lib/kubelet/kubeadm-flags.env',
         '/var/lib/kubelet/pki', '/etc/systemd/system/kubelet.service.d',
         '/etc/selinux/targeted/contexts/files/file_contexts.local']
STAGE = 'input'


def run(argv, timeout=150):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError(f'{Path(argv[0]).name} rc={result.returncode}；原始输出保持隐藏')
    return result.stdout.strip()


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def file_state():
    paths = []
    for name in FILES:
        path = Path(name)
        if not path.exists():
            raise ValueError('缺少备份必需路径：' + name)
        paths.extend([path] if path.is_file() else [item for item in path.rglob('*') if item.is_file()])
    return {str(path): digest(path) for path in sorted(paths)}


def main():
    global STAGE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['check', 'collect', 'cleanup'], default='check')
    parser.add_argument('--run', required=True)
    parser.add_argument('--node', choices=['cp01', 'cp02', 'cp03'], required=True)
    parser.add_argument('--etcd-version', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'\d{8}T\d{6}Z-[a-f0-9]{8}', args.run):
        raise ValueError('备份批次格式不正确')
    if os.geteuid() != 0 or run(['hostnamectl', '--static']) != args.node + '.k8s.internal.egon.top':
        raise ValueError('root/节点身份不符')
    output = ROOT / args.run
    if args.mode == 'cleanup':
        if output.exists():
            owner = json.loads((output / 'owner.json').read_text())
            if owner != {'run': args.run, 'node': args.node}:
                raise ValueError('暂存所有权不符，拒绝清理')
            shutil.rmtree(output)
        print(json.dumps({'status': 'ok', 'node': args.node, 'mode': args.mode}))
        return
    STAGE = 'preflight'
    if run(['getenforce']) != 'Enforcing' or run(['systemctl', 'is-active', 'firewalld']) != 'active':
        raise ValueError('安全基线不符')
    if shutil.disk_usage(ETCD).free < 5 * 1024 ** 3:
        raise ValueError('etcd 所在文件系统不足 5GiB 空闲，拒绝在此做快照/离线恢复暂存')
    ip = {'cp01': '192.168.9.101', 'cp02': '192.168.9.102', 'cp03': '192.168.9.103'}[args.node]
    kubectl = ['kubectl', '--kubeconfig', '/etc/kubernetes/admin.conf', '--server=https://' + ip + ':6443', '--request-timeout=130s']
    run(kubectl + ['get', '--raw=/readyz'])
    execute = kubectl + ['-n', 'kube-system', 'exec', 'etcd-' + args.node + '.k8s.internal.egon.top', '--']
    etcd = ['etcdctl', '--endpoints=https://127.0.0.1:2379', '--cacert=/etc/kubernetes/pki/etcd/ca.crt',
            '--cert=/etc/kubernetes/pki/etcd/healthcheck-client.crt', '--key=/etc/kubernetes/pki/etcd/healthcheck-client.key']
    for tool in ['etcdctl', 'etcdutl']:
        if args.etcd_version not in run(execute + [tool, 'version']).split():
            raise ValueError(tool + ' 与版本锁不一致')
    members = json.loads(run(execute + etcd + ['member', 'list', '-w', 'json']))['members']
    if len(members) != 3 or any(member.get('isLearner', False) for member in members):
        raise ValueError('必须先有三个非 learner 的 etcd 成员')
    run(execute + etcd + ['endpoint', 'health', '--cluster'])
    before = file_state()
    metadata = {'node': args.node, 'run': args.run, 'status': 'ok',
                'ca_sha256': digest('/etc/kubernetes/pki/ca.crt'),
                'encryption_sha256': digest('/etc/kubernetes/enc/encryption-config.yaml'),
                'etcd_version': args.etcd_version, 'file_sha256': before}
    metadata['node_resolvers'] = [line for line in RESOLV.read_text().splitlines() if line.startswith(('nameserver ', 'search ', 'options '))]
    if args.mode == 'check':
        print(json.dumps({'status': 'ok', 'node': args.node, 'mode': 'check', 'etcd_version': args.etcd_version}))
        return
    os.umask(0o077)
    ROOT.mkdir(mode=0o700, exist_ok=True)
    output.mkdir(mode=0o700)
    (output / 'owner.json').write_text(json.dumps({'run': args.run, 'node': args.node}))
    STAGE = 'snapshot' if args.node == 'cp01' else 'archive'
    if args.node == 'cp01':
        scratch = ETCD / ('cnpl-backup-' + args.run)
        scratch.mkdir(mode=0o700)
        try:
            run(['restorecon', '-RF', str(scratch)])
            snapshot = scratch / 'snapshot.db'
            run(execute + etcd + ['--command-timeout=120s', 'snapshot', 'save', str(snapshot)])
            metadata['snapshot_status'] = json.loads(run(execute + ['etcdutl', 'snapshot', 'status', str(snapshot), '-w', 'json']))
            # 仅离线生成新数据目录，不运行 etcd，不接入真实集群；保留默认哈希验证。
            STAGE = 'offline-restore'
            restored = scratch / 'isolated-data'
            run(execute + ['etcdutl', 'snapshot', 'restore', str(snapshot), '--data-dir', str(restored),
                           '--name', 'cnpl-offline-check', '--initial-cluster', 'cnpl-offline-check=http://127.0.0.1:12380',
                           '--initial-advertise-peer-urls', 'http://127.0.0.1:12380', '--initial-cluster-token', args.run])
            if not (restored / 'member/snap/db').is_file():
                raise ValueError('离线恢复未产生预期数据文件')
            metadata['offline_restore_verified'] = True
            shutil.copyfile(snapshot, output / 'snapshot.db')
        finally:
            shutil.rmtree(scratch)
    STAGE = 'archive'
    with tarfile.open(output / 'host-files.tar.gz', 'w:gz') as archive:
        for path in FILES:
            archive.add(path, arcname=path.lstrip('/'))
    if before != file_state():
        raise ValueError('打包期间配置发生变化；保留本次暂存，重新备份')
    metadata['archive_sha256'] = digest(output / 'host-files.tar.gz')
    (output / 'metadata.json').write_text(json.dumps(metadata, indent=2))
    print(json.dumps({'status': 'ok', 'node': args.node, 'mode': args.mode, 'offline_restore_verified': metadata.get('offline_restore_verified', False)}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as error:
        # 这里只处理公开步骤/命令状态，不解析或输出私钥/加密配置正文。
        print(json.dumps({'status': 'error', 'stage': STAGE, 'reason': str(error)}, ensure_ascii=False))
        raise SystemExit(1)
