"""离线身份/权限边界与真实本地 restic 备份回归；不连接节点，不修改真实集群。"""
import base64
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import yaml


ACCESS = Path(__file__).resolve().parents[1] / 'bootstrap/access'
spec = importlib.util.spec_from_file_location('access_build', ACCESS / 'build-access.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class AccessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.now = datetime.now(timezone.utc)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'offline-test-ca')])
        cls.ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(cls.key.public_key())
                  .serial_number(x509.random_serial_number()).not_valid_before(cls.now - timedelta(days=30))
                  .not_valid_after(cls.now + timedelta(days=3650)).add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
                  .sign(cls.key, hashes.SHA256()))
        cls.ca_data = base64.b64encode(cls.ca.public_bytes(serialization.Encoding.PEM)).decode()

    def identity_config(self, identity, override_group=None, not_before=None, not_after=None):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = [x509.NameAttribute(NameOID.COMMON_NAME, identity['name'])]
        group = identity['group'] if override_group is None else override_group
        if group: subject.append(x509.NameAttribute(NameOID.ORGANIZATION_NAME, group))
        certificate = (x509.CertificateBuilder().subject_name(x509.Name(subject)).issuer_name(self.ca.subject)
                       .public_key(key.public_key()).serial_number(x509.random_serial_number())
                       .not_valid_before(not_before or self.now - timedelta(minutes=5))
                       .not_valid_after(not_after or self.now + timedelta(hours=int(identity['validity'][:-1])))
                       .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), False)
                       .sign(self.key, hashes.SHA256()))
        return {'clusters': [{'name': 'test', 'cluster': {'server': build.SERVER, 'certificate-authority-data': self.ca_data}}],
                'users': [{'name': identity['name'], 'user': {
                    'client-certificate-data': base64.b64encode(certificate.public_bytes(serialization.Encoding.PEM)).decode(),
                    'client-key-data': base64.b64encode(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())).decode()}}]}

    def test_normal_certificate_rejects_admin_group_and_key_mismatch(self):
        identity = yaml.safe_load((ACCESS / 'identities.yaml').read_text())['phase01_access_identities'][0]
        config = self.identity_config(identity, 'system:masters')
        with self.assertRaisesRegex(ValueError, 'CN/O'):
            build.validate_identity(config, identity, self.ca_data)
        config = self.identity_config(identity)
        config['users'][0]['user']['client-key-data'] = self.identity_config(identity)['users'][0]['user']['client-key-data']
        with self.assertRaisesRegex(ValueError, '私钥不匹配'):
            build.validate_identity(config, identity, self.ca_data)

    def test_kubeadm_ca_backdate_does_not_extend_remaining_lifetime(self):
        identities = yaml.safe_load((ACCESS / 'identities.yaml').read_text())['phase01_access_identities']
        for identity in [identities[0], identities[-1]]:
            config = self.identity_config(identity, not_before=self.ca.not_valid_before_utc)
            user, report = build.validate_identity(config, identity, self.ca_data)
            self.assertEqual(report['username'], identity['name'])
            self.assertIn('client-key-data', user)
        config = self.identity_config(identities[0], not_before=self.now - timedelta(days=30), not_after=self.now + timedelta(days=91))
        with self.assertRaisesRegex(ValueError, '剩余期限'):
            build.validate_identity(config, identities[0], self.ca_data)

    def test_future_and_expiring_certificates_remain_rejected(self):
        identity = yaml.safe_load((ACCESS / 'identities.yaml').read_text())['phase01_access_identities'][0]
        for start, end in [(self.now + timedelta(hours=1), self.now + timedelta(days=90)),
                           (self.now - timedelta(days=90), self.now + timedelta(days=6))]:
            with self.subTest(start=start), self.assertRaisesRegex(ValueError, '尚未生效或不足七天'):
                build.validate_identity(self.identity_config(identity, not_before=start, not_after=end), identity, self.ca_data)

    def test_build_separates_clients_recovery_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'issued').mkdir()
            identities = yaml.safe_load((ACCESS / 'identities.yaml').read_text())['phase01_access_identities']
            for identity in identities:
                (root / 'issued' / (identity['name'] + '.conf')).write_text(yaml.safe_dump(self.identity_config(identity)))
            admin = {'current-context': 'test', 'contexts': [{'name': 'test', 'context': {'cluster': 'test'}}],
                     'clusters': [{'name': 'test', 'cluster': {'server': build.SERVER, 'certificate-authority-data': self.ca_data}}]}
            (root / 'admin-source.conf').write_text(yaml.safe_dump(admin))
            command = [sys.executable, str(ACCESS / 'build-access.py'), '--directory', str(root), '--admin-kubeconfig', str(root / 'admin-source.conf')]
            issued_state = {path.name: (path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns) for path in (root / 'issued').iterdir()}
            checked = subprocess.run(command + ['--check-only'], capture_output=True, text=True)
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertEqual(json.loads(checked.stdout)['mode'], 'check-only')
            self.assertFalse((root / 'mac.conf').exists())
            self.assertEqual(issued_state, {path.name: (path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns) for path in (root / 'issued').iterdir()})
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn('client-key-data', result.stdout + result.stderr)
            mac = yaml.safe_load((root / 'mac.conf').read_text())
            host = yaml.safe_load((root / 'adminhost.conf').read_text())
            self.assertEqual(mac['current-context'], 'lab-primary-readonly')
            self.assertEqual(len(mac['users']), 2)
            self.assertTrue({item['name'] for item in mac['users']}.isdisjoint({item['name'] for item in host['users']}))
            self.assertNotIn('cnpl-recovery-admin', [item['name'] for item in mac['users']])
            recovery = yaml.safe_load((root / 'recovery/recovery.conf').read_text())
            self.assertEqual(len(recovery['contexts']), 4)
            self.assertEqual(recovery['current-context'], 'lab-primary-recovery-cp01')
            for path in [root / 'mac.conf', root / 'adminhost.conf', root / 'recovery/recovery.conf', root / 'recovery/recovery-kit.tar.gz']:
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            report = (root / 'certificates.json').read_text()
            self.assertNotIn('client-key-data', report)
            self.assertEqual(len(json.loads(report)), 5)
            with tarfile.open(root / 'recovery/recovery-kit.tar.gz') as archive:
                self.assertEqual(set(archive.getnames()), {'recovery.conf', 'README.txt', 'certificates.json'})
            bad = root / 'issued' / (identities[0]['name'] + '.conf')
            bad.write_text('client-key-data: [PRIVATE_SENTINEL\n')
            result = subprocess.run(command + ['--check-only'], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)['status'], 'error')
            self.assertNotIn('PRIVATE_SENTINEL', result.stdout + result.stderr)

    def test_rbac_has_no_wildcard_secret_or_cluster_write_for_normal_users(self):
        docs = list(yaml.safe_load_all((ACCESS / 'rbac.yaml').read_text()))
        role = next(item for item in docs if item['kind'] == 'Role')
        observer = next(item for item in docs if item['kind'] == 'ClusterRole')
        self.assertEqual(role['metadata']['namespace'], 'lab-core')
        for obj in [role, observer]:
            for rule in obj['rules']:
                self.assertNotIn('*', rule['resources'] + rule['verbs'] + rule['apiGroups'])
                self.assertTrue(set(rule['resources']).isdisjoint({'secrets', 'serviceaccounts', 'serviceaccounts/token', 'roles', 'rolebindings', 'clusterroles', 'clusterrolebindings', 'nodes/proxy'}))
        self.assertTrue(all(set(rule['verbs']) <= {'get', 'list', 'watch'} for rule in observer['rules']))

    def test_ansible_shows_safe_failure_without_private_parser_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'bad.conf').write_text('client-key-data: [PRIVATE_SENTINEL\n')
            (root / 'ansible.cfg').write_text('[defaults]\nretry_files_enabled=False\n')
            source = yaml.safe_load((ACCESS.parents[1] / 'ansible/playbooks/configure-access.yml').read_text())
            play = [{'hosts': 'localhost', 'gather_facts': False,
                     'vars': {'phase01_root': str(ACCESS.parents[1]), 'phase01_access_dir': str(root / 'material'),
                              'phase01_kubeconfig': str(root / 'bad.conf'), 'ansible_connection': 'local',
                              'ansible_python_interpreter': sys.executable, 'ansible_remote_tmp': str(root / 'remote')},
                     'tasks': source[-1]['tasks'][:2]}]
            path = root / 'play.yml';path.write_text(yaml.safe_dump(play, allow_unicode=True))
            env = dict(os.environ, ANSIBLE_CONFIG=str(root / 'ansible.cfg'), ANSIBLE_LOCAL_TEMP=str(root / 'local'), ANSIBLE_NOCOLOR='1')
            result = subprocess.run([str(Path(sys.executable).with_name('ansible-playbook')), '-i', 'localhost,', str(path)],
                                    env=env, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('身份组合失败', result.stdout + result.stderr)
            self.assertIn('error_type', result.stdout + result.stderr)
            self.assertNotIn('PRIVATE_SENTINEL', result.stdout + result.stderr)

    def test_access_verifier_accepts_warning_and_requires_real_forbidden(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / 'kubectl'
            fake.write_text(f'#!{sys.executable}\n' + '''
import json,os,sys
args=sys.argv[1:]
ctx=args[args.index('--context')+1] if '--context' in args else 'recovery'
operator=ctx.endswith('lab-ops')
recovery='recovery' in ctx
adminhost='adminhost' in ctx
user='cnpl-recovery-admin' if recovery else ('cnpl-adminhost-' if adminhost else 'cnpl-mac-')+('operator' if operator else 'reader')
if 'whoami' in args:
 print(json.dumps({'status':{'userInfo':{'username':user,'groups':['system:masters'] if recovery else ['system:authenticated']}}}))
elif 'can-i' in args:
 i=args.index('can-i'); verb,res=args[i+1:i+3]
 allowed=verb=='list' and res in ['nodes','pods'] or operator and verb=='create' and (res=='configmaps' and 'lab-core' in args or res=='pods' and '--subresource=exec' in args)
 if res=='nodes':print("Warning: resource 'nodes' is not namespace scoped",file=sys.stderr)
 sys.exit(0 if allowed else 1)
elif 'create' in args:
 resource=json.load(sys.stdin)
 if '--dry-run=server' in args:
  print('Unauthorized' if os.environ.get('MOCK_BAD_DENIAL') else 'Error from server (Forbidden)',file=sys.stderr);sys.exit(1)
 resource['metadata']['name']='cnpl-access-probe-test';print(json.dumps(resource))
elif 'get' in args and 'configmap' in args:
 print(json.dumps({'data':{'probe':user}}))
else: print('ok')
''')
            fake.chmod(0o700)
            command = [sys.executable, str(ACCESS / 'verify-access.py'), '--directory', directory, '--kubectl', str(fake)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('ACCESS ACCEPTANCE PASS', result.stdout)
            result = subprocess.run(command, env=dict(os.environ, MOCK_BAD_DENIAL='1'), capture_output=True, text=True, timeout=20)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('ACCESS ACCEPTANCE PASS', result.stdout)

    def test_real_local_restic_snapshot_restore_uses_exact_private_file(self):
        binary = Path('/Users/mario/Downloads/cloud-native-lab-seed-2026-10-14/restic/restic_0.19.1_darwin_arm64')
        if not binary.is_file(): self.skipTest('locked restic binary unavailable')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            access = root / '.cnpl-secrets/access/lab-primary'
            (access / 'recovery').mkdir(parents=True)
            for relative in ['mac.conf', 'adminhost.conf', 'recovery/recovery.conf', 'recovery/recovery-kit.tar.gz']:
                (access / relative).write_text('offline-fixture-only')
            password = root / '.cnpl-secrets/restic_password'
            password.write_text('offline-fixture-passphrase')
            (root / '.ssh').mkdir();(root / '.ssh/cnpl_lab_ed25519').touch();(root / '.ssh/cnpl_lab_ed25519').write_text('fixture')
            env = dict(os.environ, RESTIC_REPOSITORY=str(root / 'repository'), RESTIC_PASSWORD_FILE=str(password), RESTIC_CACHE_DIR=str(root / 'cache'))
            subprocess.run([str(binary), 'init'], env=env, capture_output=True, check=True)
            fake = root / 'kubectl'
            fake.write_text('#!/bin/sh\nexit 0\n');fake.chmod(0o700)
            source = (ACCESS / 'backup-access.sh').read_text().replace('$HOME', str(root))
            source = source.replace('RESTIC=' + str(root) + '/Downloads/cloud-native-lab-seed-2026-10-14/restic/restic_0.19.1_darwin_arm64', 'RESTIC=' + str(binary))
            source = source.replace('PYTHON=' + str(root) + '/.venvs/cnpl-ansible/bin/python', 'PYTHON=' + sys.executable)
            source = source.replace('KUBECTL=' + str(root) + '/.cnpl/bin/kubectl', 'KUBECTL=' + str(fake))
            source = source.replace('export RESTIC_REPOSITORY=sftp:restic@192.168.9.16:/srv/backup/restic/lab', 'export RESTIC_REPOSITORY=' + str(root / 'repository'))
            script = root / 'backup.sh';script.write_text(source)
            result = subprocess.run(['/bin/bash', str(script)], env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('ACCESS BACKUP RESTORE PASS', result.stdout)
            self.assertEqual(list((root / '.cnpl-secrets').glob('access-restore.*')), [])


if __name__ == '__main__':
    unittest.main()
