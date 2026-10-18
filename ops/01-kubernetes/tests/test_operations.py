"""01.03 离线回归：伪集群采集、临时本地 restic、备份门禁与资源所有权；不运行真实 etcd/VM。"""
from datetime import datetime, timedelta, timezone
from concurrent.futures import Future
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch


OPS = Path(__file__).resolve().parents[1] / 'operations'


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, OPS / filename)
    loaded = importlib.util.module_from_spec(spec);spec.loader.exec_module(loaded)
    return loaded


backup = module('control_plane_backup', 'backup.py')
collector = module('collector', 'collect-control-plane.py')
ha = module('ha', 'ha.py')
IDENTITY = {'cluster_uid': 'offline-test-cluster', 'ca_sha256': 'a' * 64}
REQUIRED = ['etc/kubernetes/pki/ca.key', 'etc/kubernetes/pki/ca.crt', 'etc/kubernetes/enc/encryption-config.yaml',
            'etc/kubernetes/audit/policy.yaml', 'etc/kubernetes/manifests/etcd.yaml', 'etc/kubernetes/manifests/kube-apiserver.yaml']


def bundle(directory):
    for node in ['cp01', 'cp02', 'cp03']:
        root = directory / 'nodes' / node;root.mkdir(mode=0o700, parents=True)
        with tarfile.open(root / 'host-files.tar.gz', 'w:gz') as archive:
            for name in REQUIRED:
                content = b'offline-fixture-only';info = tarfile.TarInfo(name);info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
        info = {'ca_sha256': IDENTITY['ca_sha256'], 'encryption_sha256': 'b' * 64,
                'archive_sha256': backup.digest(root / 'host-files.tar.gz'), 'offline_restore_verified': node == 'cp01', 'snapshot_status': {'revision': 42}}
        (root / 'metadata.json').write_text(json.dumps(info))
    (directory / 'nodes/cp01/snapshot.db').write_bytes(b'offline-snapshot-fixture')


class OperationsTest(unittest.TestCase):
    def test_receipt_requires_fresh_complete_backup_for_same_cluster(self):
        receipt = {'schema_version': 1, 'status': 'verified', **IDENTITY, 'created_utc': datetime.now(timezone.utc).isoformat(),
                   'offline_restore_verified': True, 'off_cluster_restore_verified': True, 'restic_snapshot': 'c' * 64, 'manifest_sha256': 'd' * 64}
        ha.validate_receipt(receipt, IDENTITY)
        for updates in [{'off_cluster_restore_verified': False}, {'offline_restore_verified': 'false'}, {'cluster_uid': 'other'},
                        {'created_utc': (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()}, {'restic_snapshot': ''}]:
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                ha.validate_receipt({**receipt, **updates}, IDENTITY)

    def test_bundle_rejects_encryption_drift_and_archive_corruption(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);bundle(root)
            self.assertEqual(backup.verify_bundle(root, IDENTITY), {'revision': 42})
            path = root / 'nodes/cp02/metadata.json';data = json.loads(path.read_text());data['encryption_sha256'] = 'c' * 64;path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, '不一致'): backup.verify_bundle(root, IDENTITY)
            data['encryption_sha256'] = 'b' * 64;path.write_text(json.dumps(data))
            (root / 'nodes/cp03/host-files.tar.gz').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, '传输校验失败'): backup.verify_bundle(root, IDENTITY)

    def test_collector_restores_only_unique_scratch_and_preserves_live_member(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);etcd = root / 'etcd';(etcd / 'member').mkdir(parents=True)
            live = etcd / 'member/live';live.write_text('KEEP LIVE ETCD')
            source = root / 'config';source.write_text('offline-fixture-only')
            identifier = '20261017T120000Z-1234abcd';calls = []
            original_digest = collector.digest
            def digest(path):
                if str(path).startswith('/etc/kubernetes/'): return 'a' * 64
                return original_digest(path)
            def native(argv, timeout=150):
                calls.append(argv)
                if argv[0] == 'hostnamectl': return 'cp01.k8s.internal.egon.top'
                if argv[0] == 'getenforce': return 'Enforcing'
                if argv[0] == 'systemctl': return 'active'
                if argv[-1] == 'version': return 'etcdutl version: 3.6.8'
                if 'member' in argv: return json.dumps({'members': [{}, {}, {}]})
                if 'save' in argv: Path(argv[-1]).write_bytes(b'snapshot')
                if 'restore' in argv:
                    destination = Path(argv[argv.index('--data-dir') + 1]);(destination / 'member/snap').mkdir(parents=True)
                    (destination / 'member/snap/db').write_bytes(b'restored')
                if 'status' in argv: return json.dumps({'revision': 42})
                return 'ok'
            previous = os.umask(0o077)
            try:
                with patch.object(collector, 'ROOT', root / 'backups'), patch.object(collector, 'ETCD', etcd), \
                     patch.object(collector, 'RESOLV', source), \
                     patch.object(collector, 'FILES', [str(source)]), patch.object(collector, 'file_state', return_value={'config': 'same'}), \
                     patch.object(collector, 'digest', side_effect=digest), patch.object(collector, 'run', side_effect=native), \
                     patch.object(collector.os, 'geteuid', return_value=0), patch.object(collector.shutil, 'disk_usage', return_value=type('Disk', (), {'free': 10 * 1024 ** 3})()), \
                     patch.object(sys, 'argv', ['collector', '--mode', 'collect', '--run', identifier, '--node', 'cp01', '--etcd-version', '3.6.8']):
                    collector.main()
            finally: os.umask(previous)
            self.assertEqual(live.read_text(), 'KEEP LIVE ETCD')
            self.assertFalse((etcd / ('cnpl-backup-' + identifier)).exists())
            self.assertTrue((root / 'backups' / identifier / 'snapshot.db').is_file())
            self.assertTrue(any('etcdutl' in argv and 'restore' in argv for argv in calls))
            self.assertFalse(any('etcd' in argv for argv in calls))
            self.assertFalse(any('--skip-hash-check' in argv for argv in calls))

    def test_cleanup_refuses_foreign_deployment_before_delete(self):
        state = {'target': 'cp01', 'run': 'owned'}
        with patch.object(ha, 'healthy'), patch.object(ha, 'call', return_value=json.dumps({'metadata': {'annotations': {ha.LABEL: 'foreign'}}})) as call:
            with self.assertRaisesRegex(ValueError, '所有权'): ha.cleanup(type('Args', (), {'records': Path('/unused')})(), state)
            self.assertTrue(all('delete' not in invocation.args[0] for invocation in call.call_args_list))

    def test_watch_requires_observed_failure_recovery_and_no_app_loss(self):
        class Pool:
            def __init__(self, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def submit(self, function, *args):
                future = Future()
                try: future.set_result(function(*args))
                except Exception as error: future.set_exception(error)
                return future
        for scenario in ['pass', 'app-loss', 'no-shutdown', 'wrong-node']:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary);clock = [0.0];owners = [0]
                state = {'run': '20261017T120000Z-1234abcd', 'target': 'cp01', 'phase': 'prepared', 'receipt': {}, 'fault_checks': False, 'app_failures': 0}
                pods = [{'spec': {'nodeName': name}, 'status': {'podIP': f'10.244.{i}.2', 'conditions': [{'type': 'Ready', 'status': 'True'}]}} for i, name in enumerate(ha.WORKERS)]
                def api(argv, *args, **kwargs):
                    return json.dumps({'items': pods}) if 'pods' in argv else '192.168.20.30'
                def unavailable(target):
                    if scenario == 'wrong-node': return target == 'cp02' and clock[0] == 10
                    return target == 'cp01' and scenario != 'no-shutdown' and clock[0] == 10
                def holder(target):
                    owners[0] += 1
                    return ('cp01' if owners[0] == 1 else 'cp02') + '.k8s.internal.egon.top'
                def probe(url, *args):
                    return {'ok': not (scenario == 'app-loss' and url == 'service' and clock[0] == 10), 'code': 200}
                output = io.StringIO()
                with patch.object(ha, 'validate_receipt'), patch.object(ha, 'identity', return_value=IDENTITY), patch.object(ha, 'healthy'), \
                     patch.object(ha, 'holder', side_effect=holder), patch.object(ha, 'call', side_effect=api), \
                     patch.object(ha, 'tls_context', return_value=None), patch.object(ha, 'tunnel', side_effect=lambda pod, processes, records, service_ip=None: 'service' if service_ip else pod['spec']['nodeName']), \
                     patch.object(ha, 'probe', side_effect=probe), patch.object(ha, 'unavailable', side_effect=unavailable), \
                     patch.object(ha, 'fault_checks', return_value={'scheduled_pod': 'new-pod'}), patch.object(ha, 'ThreadPoolExecutor', Pool), \
                     patch.object(ha.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(ha.time, 'sleep', side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)), redirect_stdout(output):
                    if scenario == 'pass': ha.watch(type('Args', (), {'records': root, 'seconds': 120})(), state)
                    else:
                        with self.assertRaises(ValueError): ha.watch(type('Args', (), {'records': root, 'seconds': 120})(), state)
                self.assertEqual(state['phase'], 'complete' if scenario == 'pass' else 'recovery_required')
                self.assertEqual('HA ACCEPTANCE PASS' in output.getvalue(), scenario == 'pass')

    def test_real_local_restic_roundtrip_creates_receipt_only_after_verification(self):
        binary = Path.home() / 'Downloads/cloud-native-lab-seed-2026-10-14/restic/restic_0.19.1_darwin_arm64'
        if not binary.is_file(): self.skipTest('locked restic missing')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);home = root / 'client';home.mkdir();repository = root / 'project';repository.mkdir()
            for relative in ['.cnpl-secrets/restic_password', '.cnpl-secrets/k8s-encryption.key', '.ssh/cnpl_lab_ed25519', '.cnpl-secrets/access/lab-primary/recovery/recovery.conf']:
                path = home / relative;path.parent.mkdir(parents=True, exist_ok=True);path.write_text('offline-fixture-only')
            for relative in ['ops/versions.lock.yaml', 'ops/inventory/hosts.yaml', 'ops/inventory/networks.yaml', 'ops/inventory/resources.yaml',
                             'ops/01-kubernetes/operations/backup.py', 'ops/01-kubernetes/operations/collect-control-plane.py', 'ops/01-kubernetes/ansible/playbooks/backup-control-plane.yml']:
                path = repository / relative;path.parent.mkdir(parents=True, exist_ok=True);path.write_text('offline-fixture-only')
            env = dict(os.environ, RESTIC_REPOSITORY=str(root / 'restic'), RESTIC_PASSWORD_FILE=str(home / '.cnpl-secrets/restic_password'), RESTIC_CACHE_DIR=str(root / 'cache'))
            subprocess.run([str(binary), 'init'], env=env, capture_output=True, check=True)
            original = backup.run
            def execute(argv, env=None, timeout=600):
                if argv[0] == 'git': return '0' * 40
                return original(argv, env={**env, 'RESTIC_REPOSITORY': str(root / 'restic'), 'RESTIC_CACHE_DIR': str(root / 'cache')} if env else None, timeout=timeout)
            def collect(mode, identifier, directory, records):
                if mode == 'collect': bundle(directory)
            previous = os.umask(0o077)
            try:
                with patch.object(backup, 'REPOSITORY', repository), patch.object(backup, 'PRIVATE', home / '.cnpl-secrets/phase01-backups'), \
                     patch.object(backup, 'RESTIC', binary), patch.object(backup, 'KUBECTL', Path('/usr/bin/true')), patch.object(backup, 'ANSIBLE', Path('/usr/bin/true')), \
                     patch.object(backup.Path, 'home', return_value=home), patch.object(backup, 'cluster', return_value=IDENTITY), \
                     patch.object(backup, 'ansible', side_effect=collect), patch.object(backup, 'run', side_effect=execute), \
                     patch.object(sys, 'argv', ['backup', 'run', '--records', str(root / 'records')]):
                    backup.main()
            finally: os.umask(previous)
            receipt = json.loads((root / 'records/backup-receipt.json').read_text())
            self.assertEqual(receipt['status'], 'verified')
            self.assertIs(receipt['off_cluster_restore_verified'], True)
            self.assertEqual(receipt['cluster_uid'], IDENTITY['cluster_uid'])
            ha.validate_receipt(receipt, IDENTITY)


if __name__ == '__main__':
    unittest.main()
