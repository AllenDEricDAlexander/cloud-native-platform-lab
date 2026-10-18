"""高影响实验的资源边界、真实终止回执、归档完整性和可执行续跑入口回归。"""
import copy
from datetime import datetime, timezone, timedelta
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1] / 'core-resources/probes'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


lab = module('probe_lab', HERE / 'lab.py')
build = module('probe_build', HERE / 'build.py')
IMAGE = 'cnpl.local/phase01/probe-lab:sha256-' + 'a' * 64


class ProbeContracts(unittest.TestCase):
    def test_all_runtime_references_resolve_and_restricted_boundaries_hold(self):
        objects = lab.objects(IMAGE)
        for name in ['p05-broker-pod', 'p05-broker', 'p05-dependency', 'p05-dependency-service', 'p05-start-6', 'p05-start-12', 'p05-start-20']:
            self.assertIn(name, objects)
        for obj in objects.values():
            if obj['kind'] != 'Pod': continue
            spec = obj['spec']; self.assertFalse(spec['automountServiceAccountToken'])
            self.assertIn(spec['nodeSelector']['kubernetes.io/hostname'], lab.WORKERS)
            self.assertTrue(spec['securityContext']['runAsNonRoot'])
            for c in spec['containers']:
                self.assertEqual(['ALL'], c['securityContext']['capabilities']['drop'])
                self.assertTrue(c['securityContext']['readOnlyRootFilesystem'])
                if c['image'] == IMAGE: self.assertEqual('Never', c['imagePullPolicy'])
                for env in c.get('env', []):
                    if env.get('name') in ['BROKER_URL', 'DEPENDENCY_URL']:
                        host = env['value'].split('/')[2].split(':')[0]
                        self.assertEqual('Service', objects[host]['kind'])

    def test_forced_case_has_real_grace_budget_and_native_grpc_uses_numeric_port(self):
        objects = lab.objects(IMAGE)
        for name, grace, hook in [('p05-term-main', 25, 5), ('p05-force', 6, 4)]:
            obj = objects[name]; c = obj['spec']['containers'][0]
            self.assertEqual(grace, obj['spec']['terminationGracePeriodSeconds'])
            self.assertEqual(str(hook), c['lifecycle']['preStop']['exec']['command'][-1])
            self.assertEqual('Never', obj['spec']['restartPolicy'])
            self.assertEqual('File', c['terminationMessagePolicy'])
        for name in ['p05-grpc-good', 'p05-grpc-wrong-service']:
            obj = objects[name]; c = obj['spec']['containers'][0]
            self.assertIsInstance(c['readinessProbe']['grpc']['port'], int)
            self.assertEqual(lab.ETCD, c['image'])
            self.assertEqual('256Mi', obj['spec']['volumes'][0]['emptyDir']['sizeLimit'])
            self.assertIn('--data-dir=/work/etcd', c['command'])

    def termination(self):
        now = datetime.now(timezone.utc)
        return {'metadata': {'uid': 'uid-a', 'deletionTimestamp': now.isoformat()}, 'status': {'phase': 'Succeeded',
                'containerStatuses': [{'name': 'app', 'state': {'terminated': {'exitCode': 0, 'reason': 'Completed',
                'message': json.dumps({'uid': 'uid-a', 'signal': 'TERM', 'drained': True, 'completed': ['graceful'],
                                      'prestop_at': (now-timedelta(seconds=5)).isoformat(), 'term_at': now.isoformat(),
                                      'finished_at': (now+timedelta(seconds=2)).isoformat()})}}}]}}

    def test_termination_requires_uid_signal_completed_message_and_hook_timing(self):
        actual = self.termination(); self.assertTrue(lab.validate_term(actual, 'graceful')['drained'])
        for change in ['uid', 'signal', 'drained', 'completed', 'prestop_at']:
            obj = copy.deepcopy(actual); state = obj['status']['containerStatuses'][0]['state']['terminated']
            receipt = json.loads(state['message'])
            receipt[change] = {'uid': 'another-pod', 'signal': 'INT', 'drained': False, 'completed': [], 'prestop_at': receipt['term_at']}[change]
            state['message'] = json.dumps(receipt)
            with self.subTest(change=change), self.assertRaises(ValueError): lab.validate_term(obj, 'graceful')
        obj = copy.deepcopy(actual); obj['status']['containerStatuses'][0]['state']['terminated']['message'] = ''
        with self.assertRaises(ValueError): lab.validate_term(obj, 'graceful')

    def test_wrong_run_and_foreign_finalizer_refuse_all_mutations(self):
        args = SimpleNamespace(records=Path('/unused')); state = {'run': 'ours'}
        with self.assertRaises(ValueError): lab.owned({'metadata': {'name': 'foreign', 'labels': {lab.LABEL: 'other'}}}, state)
        items = [{'kind': 'Pod', 'metadata': {'name': 'ours', 'labels': {lab.LABEL: 'ours'}}},
                 {'kind': 'Pod', 'metadata': {'name': 'also-ours', 'labels': {lab.LABEL: 'ours'}, 'finalizers': ['external/protect']}}]
        with patch.object(lab, 'api', return_value=json.dumps({'items': items})) as api:
            with self.assertRaises(ValueError): lab.remove(args, state, 'termination')
            self.assertEqual(1, api.call_count)
            self.assertNotIn('delete', api.call_args.args)

    def test_create_binds_service_and_policy_to_run(self):
        state = {'run': 'our-run', 'artifact': {'image': IMAGE}}
        with patch.object(lab, 'api') as api:
            lab.create('p05-route', None, state)
            obj = api.call_args.kwargs['payload']
            self.assertEqual('our-run', obj['spec']['selector'][lab.LABEL])
            lab.create('p05-isolation', None, state)
            obj = api.call_args.kwargs['payload']
            self.assertEqual('our-run', obj['spec']['podSelector']['matchLabels'][lab.LABEL])
            self.assertEqual('our-run', obj['spec']['ingress'][0]['from'][0]['podSelector']['matchLabels'][lab.LABEL])

    def test_capture_saves_queue_and_application_state_before_volume_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            args=SimpleNamespace(records=Path(directory));items=[]
            for mode in ['broker','server']:
                obj=lab.pod(mode,'termination',IMAGE);obj['metadata']['uid']=mode+'-uid'
                obj['spec']['containers'][0]['command']=['/probe-lab',mode]
                obj['status']={'containerStatuses':[{'name':'app','state':{'running':{ 'startedAt':'now'}},'restartCount':0}]}
                items.append(obj)
            def api(*args,**kwargs):return json.dumps({'items':items if lab.KINDS in args else []})
            with patch.object(lab,'api',side_effect=api),patch.object(lab,'command',return_value=SimpleNamespace(returncode=0,stdout='{}',stderr='')) as command:
                output=lab.capture(args,{'run':'ours'},'before-reset')
                self.assertEqual('{}',(output/'p05-broker.queue.json').read_text())
                self.assertEqual('{}',(output/'p05-server.metrics.json').read_text())
                targets=[call.args[0][-1] for call in command.call_args_list if 'exec' in call.args[0]]
                self.assertEqual(['http://127.0.0.1:9090/status','http://127.0.0.1:8080/metrics'],targets)

    def test_endpoints_reject_old_service_uid_after_recreation(self):
        slices = {'items': [{'metadata': {'ownerReferences': [{'uid': uid}]}, 'endpoints': []} for uid in ['old', 'new']]}
        with patch.object(lab, 'get', return_value={'metadata': {'uid': 'new'}}), patch.object(lab, 'api', return_value=json.dumps(slices)):
            value = lab.endpoints('p05-route')
            self.assertEqual(1, len(value['items']))
            self.assertEqual('new', value['items'][0]['metadata']['ownerReferences'][0]['uid'])

    def test_partial_prepare_recovers_policy_without_overwriting_foreign_objects(self):
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(records=Path(directory)); artifact = {'image': IMAGE}; identity = {'cluster_uid': 'uid', 'version': 'v1.36.5'}
            state = dict(identity, run='our-run', passed=['startup'], artifact=artifact)
            lab.save(args.records/'state.json', state)
            with patch.object(lab, 'check', return_value=identity), patch.object(lab, 'api', return_value=''), patch.object(lab, 'create') as create:
                self.assertEqual(state, lab.prepare(args, artifact)); create.assert_called_once()
            with patch.object(lab, 'check', return_value=identity), patch.object(lab, 'api', return_value=json.dumps({'metadata': {'name': 'p05-isolation', 'labels': {lab.LABEL: 'foreign'}}})), patch.object(lab, 'create') as create:
                with self.assertRaises(ValueError): lab.prepare(args, artifact)
                create.assert_not_called()
            with patch.object(lab, 'check', return_value=identity):
                with self.assertRaises(ValueError): lab.prepare(args, {'image': 'different'})

    def test_oci_all_descriptors_match_hashes_and_binary_layer_is_executable(self):
        archive, image, manifest = build.oci(b'linux-static-binary', '1'*64)
        self.assertIn(hashlib.sha256(b'linux-static-binary').hexdigest(), image)
        self.assertEqual(archive, build.oci(b'linux-static-binary', '1'*64)[0])
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            index = json.load(tar.extractfile('index.json'))
            def read(desc):
                data = tar.extractfile('blobs/sha256/'+desc['digest'].split(':')[1]).read()
                self.assertEqual(desc['size'], len(data)); self.assertEqual(desc['digest'], 'sha256:'+hashlib.sha256(data).hexdigest()); return data
            document = json.loads(read(index['manifests'][0])); self.assertEqual(manifest, index['manifests'][0]['digest'])
            config = json.loads(read(document['config'])); self.assertEqual('1000:1000', config['config']['User'])
            raw = gzip.decompress(read(document['layers'][0]))
            self.assertEqual(config['rootfs']['diff_ids'], ['sha256:'+hashlib.sha256(raw).hexdigest()])
            with tarfile.open(fileobj=io.BytesIO(raw)) as layer:
                self.assertEqual(0o555, layer.getmember('probe-lab').mode)
                self.assertEqual(b'linux-static-binary', layer.extractfile('probe-lab').read())

    def test_shell_runs_real_checkpoint_skip_and_preserves_previous_logs(self):
        # 只替换 HOME 中两个执行入口；实际运行仓库 run.sh，不调用集群/SSH/编译器。
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory); binpath = home/'.venvs/cnpl-ansible/bin'; binpath.mkdir(parents=True)
            wrapper = '''#!REAL_PYTHON
import json,os,subprocess,sys
from pathlib import Path
args=sys.argv[1:]
if not args or not args[0].endswith(('/build.py','/lab.py')):
 os.execv(REAL_EXEC,[REAL_EXEC]+args)
script=Path(args[0]).name
def val(flag): return Path(args[args.index(flag)+1])
if script=='build.py': val('--output').write_text('{"test":"fixed"}\\n');sys.exit(0)
action=args[1];records=val('--records');records.mkdir(parents=True,exist_ok=True)
with (Path(os.environ['HOME'])/'actions.txt').open('a') as f:f.write(action+'\\n')
state=records/'state.json'
if action in ['check','render']:sys.exit(0)
if action=='prepare':
 if not state.exists():state.write_text('{"passed":[]}')
 sys.exit(0)
if action=='readiness' and not (records/'failed-once').exists():
 (records/'failed-once').touch();sys.exit(2)
data=json.loads(state.read_text());data['passed'].append(action);state.write_text(json.dumps(data));print(action.upper()+' PASS')
'''.replace('REAL_PYTHON',sys.executable).replace('REAL_EXEC',repr(sys.executable))
            (binpath/'python').write_text(wrapper); (binpath/'python').chmod(0o755)
            (binpath/'ansible-playbook').write_text('#!/bin/sh\nexit 0\n'); (binpath/'ansible-playbook').chmod(0o755)
            records = home/'evidence'; env = dict(os.environ, HOME=str(home))
            first = subprocess.run(['bash', HERE/'run.sh', records], env=env, text=True, capture_output=True, timeout=20)
            self.assertNotEqual(0, first.returncode)
            old = {p:p.read_bytes() for p in records.glob('attempt-*/*.txt')}
            second = subprocess.run(['bash', HERE/'run.sh', records, '--resume'], env=env, text=True, capture_output=True, timeout=20)
            self.assertEqual(0, second.returncode, second.stdout+second.stderr)
            actions = (home/'actions.txt').read_text().splitlines()
            self.assertEqual(1, actions.count('startup')); self.assertEqual(1, actions.count('liveness')); self.assertEqual(2, actions.count('readiness'))
            self.assertEqual(lab.STAGES, json.loads((records/'state.json').read_text())['passed'])
            for path,data in old.items(): self.assertEqual(data,path.read_bytes())


if __name__ == '__main__': unittest.main()
