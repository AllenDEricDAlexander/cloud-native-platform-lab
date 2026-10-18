#!/usr/bin/env python3
"""01.03 完整备份：三节点收集、一致性快照、.16 加密备份与逐文件取回验证。默认只读 check。"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tarfile
import tempfile

import yaml


REPOSITORY = Path(__file__).resolve().parents[3]
PRIVATE = Path.home() / '.cnpl-secrets/phase01-backups'
RESTIC = Path.home() / 'Downloads/cloud-native-lab-seed-2026-10-14/restic/restic_0.19.1_darwin_arm64'
KUBECTL = Path.home() / '.cnpl/bin/kubectl'
ADMIN = Path.home() / '.cnpl-secrets/kubeconfig-lab-primary'
ANSIBLE = Path.home() / '.venvs/cnpl-ansible/bin/ansible-playbook'


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def run(argv, env=None, timeout=600):
    result = subprocess.run([str(item) for item in argv], capture_output=True, text=True, env=env, timeout=timeout)
    if result.returncode:
        raise ValueError(Path(str(argv[0])).name + ' 失败；' + result.stderr[-3000:])
    return result.stdout


def cluster():
    config = yaml.safe_load(ADMIN.read_text())
    context = next(item['context'] for item in config['contexts'] if item['name'] == config['current-context'])
    current = next(item['cluster'] for item in config['clusters'] if item['name'] == context['cluster'])
    if current['server'] != 'https://api.k8s.internal.egon.top:6443':
        raise ValueError('引导管理配置目标不是本实验集群')
    k = [KUBECTL, '--kubeconfig', ADMIN, '--request-timeout=15s']
    run(k + ['get', '--raw=/readyz'])
    nodes = json.loads(run(k + ['get', 'nodes', '-o', 'json']))['items']
    if len(nodes) != 10 or not all(any(c['type'] == 'Ready' and c['status'] == 'True' for c in node['status']['conditions']) for node in nodes):
        raise ValueError('故障实验前备份要求十节点 Ready')
    uid = run(k + ['get', 'namespace', 'kube-system', '-o', 'jsonpath={.metadata.uid}']).strip()
    return {'cluster_uid': uid, 'ca_sha256': hashlib.sha256(base64.b64decode(current['certificate-authority-data'])).hexdigest()}


def ansible(mode, identifier, directory, records):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json') as variables:
        json.dump({'phase01_backup_mode': mode, 'phase01_backup_run': identifier, 'phase01_backup_directory': str(directory)}, variables)
        variables.flush()
        env = dict(os.environ, ANSIBLE_CONFIG=str(REPOSITORY / 'ops/00-preparation/ansible/ansible.cfg'))
        result = subprocess.run([str(ANSIBLE), str(REPOSITORY / 'ops/01-kubernetes/ansible/playbooks/backup-control-plane.yml'), '-e', '@' + variables.name],
                                capture_output=True, text=True, env=env, timeout=600)
        output = result.stdout + result.stderr
        (records / (mode + '-ansible.txt')).write_text(output)
        print(output, flush=True)
        if result.returncode:
            raise ValueError('Ansible ' + mode + ' 失败；见本次公开记录，私有暂存保留')


def verify_bundle(directory, expected_cluster):
    metadata = [json.loads((directory / 'nodes' / node / 'metadata.json').read_text()) for node in ['cp01', 'cp02', 'cp03']]
    if {item['ca_sha256'] for item in metadata} != {expected_cluster['ca_sha256']} or len({item['encryption_sha256'] for item in metadata}) != 1:
        raise ValueError('三控制平面 CA/加密配置不一致，不能签发备份通过凭据')
    if not metadata[0].get('offline_restore_verified') or not (directory / 'nodes/cp01/snapshot.db').is_file():
        raise ValueError('一致性快照或离线恢复验证缺失')
    required = {'etc/kubernetes/pki/ca.key', 'etc/kubernetes/pki/ca.crt', 'etc/kubernetes/enc/encryption-config.yaml',
                'etc/kubernetes/audit/policy.yaml', 'etc/kubernetes/manifests/etcd.yaml', 'etc/kubernetes/manifests/kube-apiserver.yaml'}
    for node, info in zip(['cp01', 'cp02', 'cp03'], metadata):
        archive = directory / 'nodes' / node / 'host-files.tar.gz'
        if digest(archive) != info['archive_sha256']:
            raise ValueError(node + ' 归档传输校验失败')
        with tarfile.open(archive) as source:
            if not required <= set(source.getnames()):
                raise ValueError(node + ' 归档缺少必要恢复材料')
    return metadata[0]['snapshot_status']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['check', 'run'], nargs='?', default='check')
    parser.add_argument('--records', type=Path)
    args = parser.parse_args()
    identifier = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + secrets.token_hex(4)
    records = (args.records or REPOSITORY / 'ops/01-kubernetes/records/2026-10-17-restart/evidence' / ('01.03-backup-' + identifier)).resolve()
    records.mkdir(parents=True, exist_ok=False)
    if records.is_relative_to(PRIVATE):
        raise ValueError('公开记录和秘密备份目录必须分开')
    for path in [RESTIC, KUBECTL, ANSIBLE]:
        if not os.access(path, os.X_OK):
            raise ValueError('缺少已有锁定客户端：' + str(path))
    for path in [Path.home() / '.cnpl-secrets/restic_password', Path.home() / '.cnpl-secrets/k8s-encryption.key',
                 Path.home() / '.ssh/cnpl_lab_ed25519', Path.home() / '.cnpl-secrets/access/lab-primary/recovery/recovery.conf']:
        if not path.is_file():
            raise ValueError('缺少恢复必需材料：' + str(path))
    identity = cluster()
    directory = PRIVATE / 'bundles' / identifier
    ansible('check', identifier, directory, records)
    if args.mode == 'check':
        print('CONTROL PLANE BACKUP PREFLIGHT PASS; no snapshot/backup/restore performed.')
        print('记录：' + str(records))
        return
    os.umask(0o077)
    directory.mkdir(mode=0o700, parents=True)
    ansible('collect', identifier, directory, records)
    if cluster() != identity:
        raise ValueError('备份期间集群身份变化，停止并保留材料')
    for path in directory.rglob('*'):
        if path.is_file(): path.chmod(0o600)
    snapshot_status = verify_bundle(directory, identity)
    shutil.copyfile(Path.home() / '.cnpl-secrets/k8s-encryption.key', directory / 'k8s-encryption.key')
    shutil.copytree(Path.home() / '.cnpl-secrets/access/lab-primary', directory / 'access')
    inputs = directory / 'repository-inputs'
    inputs.mkdir(mode=0o700)
    for relative in ['ops/versions.lock.yaml', 'ops/inventory/hosts.yaml', 'ops/inventory/networks.yaml', 'ops/inventory/resources.yaml']:
        shutil.copyfile(REPOSITORY / relative, inputs / Path(relative).name)
    implementation = directory / 'implementation';implementation.mkdir(mode=0o700)
    for relative in ['ops/01-kubernetes/operations/backup.py', 'ops/01-kubernetes/operations/collect-control-plane.py',
                     'ops/01-kubernetes/ansible/playbooks/backup-control-plane.yml']:
        shutil.copyfile(REPOSITORY / relative, implementation / Path(relative).name)
    manifest = {'schema_version': 1, **identity, 'run': identifier, 'created_utc': datetime.now(timezone.utc).isoformat(),
                'source_commit': run(['git', '-C', REPOSITORY, 'rev-parse', 'HEAD']).strip(), 'snapshot_status': snapshot_status,
                'implementation_sha256': {path.name: digest(path) for path in implementation.iterdir()},
                'offline_restore_verified': True, 'files': {str(path.relative_to(directory)): digest(path) for path in directory.rglob('*') if path.is_file()}}
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    env = dict(os.environ, RESTIC_REPOSITORY='sftp:restic@192.168.9.16:/srv/backup/restic/lab',
               RESTIC_PASSWORD_FILE=str(Path.home() / '.cnpl-secrets/restic_password'))
    restic = [RESTIC, '-o', 'sftp.command=ssh -i ' + str(Path.home() / '.ssh/cnpl_lab_ed25519') + ' -o IdentitiesOnly=yes -o BatchMode=yes restic@192.168.9.16 -s sftp', '--retry-lock', '30s']
    output = run(restic + ['backup', '--host', 'cnpl-mgmt-mac', '--tag', 'phase01-control-plane', '--json', directory], env=env)
    summaries = [item for line in output.splitlines() if (item := json.loads(line)).get('message_type') == 'summary']
    if len(summaries) != 1 or not summaries[0].get('snapshot_id'):
        raise ValueError('没有取得本次准确的 restic snapshot ID')
    snapshot = summaries[0]['snapshot_id']
    with tempfile.TemporaryDirectory(prefix='restore-', dir=PRIVATE) as temporary:
        run(restic + ['restore', snapshot, '--target', temporary, '--verify'], env=env)
        restored = Path(temporary) / str(directory).lstrip('/')
        if (restored / 'manifest.json').read_bytes() != (directory / 'manifest.json').read_bytes():
            raise ValueError('取回的备份索引不一致')
        for relative, checksum in manifest['files'].items():
            if digest(restored / relative) != checksum:
                raise ValueError('取回材料校验失败：' + relative)
        verify_bundle(restored, identity)
    receipt = {key: manifest[key] for key in ['schema_version', 'cluster_uid', 'ca_sha256', 'run', 'created_utc', 'source_commit', 'implementation_sha256', 'snapshot_status', 'offline_restore_verified']}
    receipt.update(status='verified', restic_snapshot=snapshot, off_cluster_restore_verified=True, manifest_sha256=digest(directory / 'manifest.json'))
    receipts = PRIVATE / 'receipts';receipts.mkdir(mode=0o700, exist_ok=True)
    destination = receipts / (identifier + '.json')
    destination.write_text(json.dumps(receipt, indent=2))
    shutil.copyfile(destination, records / 'backup-receipt.json')
    ansible('cleanup', identifier, directory, records)
    print('CONTROL PLANE BACKUP RESTORE PASS (offline directory restore only; no etcd server started).')
    print('备份凭据：' + str(destination))
    print('独立加密快照：' + snapshot)
    print('私有材料：' + str(directory))
    print('公开记录：' + str(records))


if __name__ == '__main__':
    try:
        main()
    except yaml.YAMLError:
        raise SystemExit('CONTROL PLANE BACKUP FAIL: 配置格式错误，私有配置正文保持隐藏。')
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as error:
        raise SystemExit('CONTROL PLANE BACKUP FAIL: ' + str(error))
