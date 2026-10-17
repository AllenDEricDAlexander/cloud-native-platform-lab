"""真实 Ansible 编排 + 临时文件/伪 kubeadm 回归；不连接节点、不启动服务。"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml


PHASE = Path(__file__).resolve().parents[1]
TOKEN = 'abcdef.0123456789abcdef'
KEY = '1' * 64
spec = importlib.util.spec_from_file_location('join_inspection', PHASE / 'bootstrap/scripts/inspect-join-node.py')
inspection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspection)


class JoinStateTest(unittest.TestCase):
    def test_clean_node_and_partial_join_are_distinguished(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kube = root / 'kubernetes'
            kube.mkdir()
            self.assertFalse(inspection.inspect_state(kube, root / 'kubelet', root / 'etcd', True))
            (kube / 'kubelet.conf').touch()
            with self.assertRaisesRegex(ValueError, '不能当作完整入群'):
                inspection.inspect_state(kube, root / 'kubelet', root / 'etcd', True)
            (kube / 'kubelet.conf').unlink()
            (kube / 'bootstrap-kubelet.conf').touch()
            with self.assertRaisesRegex(ValueError, '未完成的入群产物'):
                inspection.inspect_state(kube, root / 'kubelet', root / 'etcd', False)


class JoinOrchestrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ['private', 'kubernetes/manifests', 'bin']:
            (self.root / name).mkdir(parents=True)
        self.env = dict(os.environ, MOCK_ROOT=str(self.root), MOCK_MODE='success',
                        ANSIBLE_CONFIG=str(self.root / 'ansible.cfg'), ANSIBLE_NOCOLOR='1')
        self.env['PATH'] = str(self.root / 'bin') + os.pathsep + self.env['PATH']
        (self.root / 'ansible.cfg').write_text('[defaults]\nhost_key_checking=True\nretry_files_enabled=False\n')
        tasks = yaml.safe_load((PHASE / 'ansible/tasks/join-node.yml').read_text())
        # 只映射测试文件路径和 systemd 调用；其余任务、条件、凭据处理与 always 原样执行。
        tasks = json.loads(json.dumps(tasks).replace('/root/', str(self.root / 'private') + '/')
                           .replace('/etc/kubernetes/', str(self.root / 'kubernetes') + '/'))
        for task in tasks[1]['block']:
            if 'ansible.builtin.systemd_service' in task:
                del task['ansible.builtin.systemd_service']
                task['ansible.builtin.command'] = {'argv': ['systemctl', 'enable', 'kubelet']}
        (self.root / 'tasks.yml').write_text(yaml.safe_dump(tasks, allow_unicode=True, sort_keys=False))
        (self.root / 'inventory.yml').write_text(yaml.safe_dump({'all': {'hosts': {
            host: {'ansible_connection': 'local', 'ansible_python_interpreter': sys.executable,
                   'node_fqdn': host + '.k8s.internal.egon.top'}
            for host in ['cp01', 'cp02']}}}))
        self.stub('kubeadm', f'''
mode = os.environ['MOCK_MODE']
args = sys.argv[1:]
if args[:2] == ['token', 'generate']:
    operation = 'generate'
    print('{TOKEN}')
elif args[:2] == ['token', 'create']:
    operation = 'create'
    Path(os.environ['MOCK_ROOT'], 'token-created').touch()
    print('invalid-output' if mode == 'bad-output' else 'kubeadm join api.k8s.internal.egon.top:6443 --token {TOKEN} --discovery-token-ca-cert-hash sha256:' + 'a' * 64)
elif args[:3] == ['init', 'phase', 'upload-certs']:
    operation = 'upload-certs'
    print('certificate key follows\\n{KEY}\\nnon-key trailing line')
elif args[:2] == ['config', 'validate']:
    import yaml
    operation = 'validate'
    config = yaml.safe_load(Path(args[-1]).read_text())
    assert config['discovery']['bootstrapToken']['caCertHashes'] == ['sha256:' + 'a' * 64]
    assert config.get('controlPlane', {{}}).get('certificateKey', '{KEY}') == '{KEY}'
    if mode == 'invalid-config':
        print('invalid config {TOKEN}', file=sys.stderr)
        sys.exit(2)
elif args[0] == 'join':
    operation = 'join'
    Path(os.environ['MOCK_ROOT'], 'join-called').touch()
    if mode == 'join-failure':
        print('failed with {TOKEN} and {KEY}', file=sys.stderr)
        sys.exit(1)
else:
    raise SystemExit('unexpected kubeadm call')
with Path(os.environ['MOCK_ROOT'], 'calls').open('a') as output:
    output.write(operation + '\\n')
''')
        self.stub('systemctl', "Path(os.environ['MOCK_ROOT'], 'enabled').touch()")
        self.stub('kubectl', '''
if 'delete' in sys.argv:
    Path(os.environ['MOCK_ROOT'], 'token-created').unlink(missing_ok=True)
    Path(os.environ['MOCK_ROOT'], 'token-revoked').touch()
print('127.0.0.1 kubernetes ' + str(Path(os.environ['MOCK_ROOT'], 'kubernetes/admin.conf')) if any('jsonpath=' in arg for arg in sys.argv) else 'ok')
''')

    def stub(self, name, source):
        path = self.root / 'bin' / name
        path.write_text(f'#!{sys.executable}\nimport os,sys\nfrom pathlib import Path\n' + source)
        path.chmod(0o700)

    def run_join(self, control_plane=True, joined=False):
        play = [{'hosts': 'cp02', 'gather_facts': False, 'vars': {
            'phase01_root': str(PHASE), 'phase01_network': {'primary_cluster': {'api_fqdn': 'api.k8s.internal.egon.top'}},
            'phase01_stage': str(self.root / 'stage'),
            'phase01_join_control_plane': control_plane, 'phase01_profile': 'control_plane' if control_plane else 'storage',
            'phase01_join_preflight_passed': True, 'phase01_joined': {'stat': {'exists': joined}},
            'node_fqdn': 'cp02.k8s.internal.egon.top', 'ansible_host': '192.168.9.102',
            'node_planned_hypervisor': 'esxi02'}, 'tasks': [{'ansible.builtin.include_tasks': 'tasks.yml'}]}]
        (self.root / 'play.yml').write_text(yaml.safe_dump(play, allow_unicode=True))
        command = str(Path(sys.executable).with_name('ansible-playbook'))
        result = subprocess.run([command, '-i', str(self.root / 'inventory.yml'), str(self.root / 'play.yml')],
                                env=self.env, text=True, capture_output=True, timeout=60)
        self.assertNotIn(TOKEN, result.stdout + result.stderr)
        self.assertNotIn(KEY, result.stdout + result.stderr)
        self.assertFalse((self.root / 'private/cnpl-join.yaml').exists())
        self.assertFalse((self.root / 'token-created').exists())
        return result

    def test_control_plane_success_cleans_credentials_and_validates_before_enable(self):
        result = self.run_join()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.root / 'token-revoked').exists())
        self.assertTrue((self.root / 'kubernetes/manifests/kube-vip.yaml').exists())
        self.assertEqual((self.root / 'calls').read_text().splitlines(), ['generate', 'create', 'upload-certs', 'validate', 'join'])

    def test_worker_uses_native_hash_without_uploading_certificates(self):
        result = self.run_join(control_plane=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('upload-certs', (self.root / 'calls').read_text())

    def test_invalid_native_output_revokes_token_before_join(self):
        self.env['MOCK_MODE'] = 'bad-output'
        result = self.run_join()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.root / 'token-revoked').exists())
        self.assertFalse((self.root / 'join-called').exists())
        self.assertFalse((self.root / 'enabled').exists())

    def test_invalid_config_does_not_enable_kubelet(self):
        self.env['MOCK_MODE'] = 'invalid-config'
        result = self.run_join()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.root / 'token-revoked').exists())
        self.assertFalse((self.root / 'join-called').exists())
        self.assertFalse((self.root / 'enabled').exists())

    def test_join_failure_cleans_credentials_and_preserves_private_log(self):
        self.env['MOCK_MODE'] = 'join-failure'
        result = self.run_join()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.root / 'token-revoked').exists())
        logs = list((self.root / 'private').glob('kubeadm-join.*.out'))
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].stat().st_mode & 0o777, 0o600)
        self.assertIn(TOKEN, logs[0].read_text())

    def test_joined_node_reconciles_vip_without_new_token_or_join(self):
        result = self.run_join(joined=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.root / 'calls').exists())
        self.assertTrue((self.root / 'kubernetes/manifests/kube-vip.yaml').exists())


if __name__ == '__main__':
    unittest.main()
