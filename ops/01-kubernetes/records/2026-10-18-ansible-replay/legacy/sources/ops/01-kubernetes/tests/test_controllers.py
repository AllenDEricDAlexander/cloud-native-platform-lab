"""01.06 版本物料、收敛/归属、清理边界和可执行续跑入口回归；不启动集群工作负载。"""
import copy
import gzip
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1] / 'core-resources/controllers'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


lab = load('controller_lab', HERE / 'lab.py'); build = load('controller_build', HERE / 'build.py')
BUNDLE = {'schema_version': 1, 'images': {v: {'image': 'cnpl.local/phase01/controller-lab@sha256:' + c*64} for v, c in [('v1', '1'), ('v2', '2'), ('bad', '3')]}}
STATE = {'run': 'test-run', 'bundle': BUNDLE, 'passed': []}


def healthy(uid='pod-uid'):
    return {'metadata': {'name': 'p06-pod', 'uid': uid, 'labels': {lab.LABEL: STATE['run']}},
            'status': {'conditions': [{'type': 'Ready', 'status': 'True'}]}}


class ControllerContracts(unittest.TestCase):
    def test_oci_versions_have_distinct_configs_and_identical_binary_layer(self):
        digests = []; layers = []
        for version in ['v1', 'v2', 'bad']:
            blob, meta = build.oci(b'static-controller', 'f'*64, version); digests.append(meta['manifest_digest'])
            self.assertEqual(meta['image'], build.REPOSITORY + '@' + meta['manifest_digest'])
            self.assertEqual(blob, build.oci(b'static-controller', 'f'*64, version)[0])
            with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
                index = json.load(tar.extractfile('index.json'))
                def read(d):
                    b = tar.extractfile('blobs/sha256/' + d['digest'].split(':')[1]).read()
                    self.assertEqual(d['size'], len(b)); self.assertEqual(d['digest'], 'sha256:' + build.digest(b)); return b
                manifest = json.loads(read(index['manifests'][0])); config = json.loads(read(manifest['config']))
                self.assertEqual(['APP_VERSION=' + version], config['config']['Env']); self.assertEqual('1000:1000', config['config']['User'])
                raw = gzip.decompress(read(manifest['layers'][0])); layers.append(build.digest(raw))
                with tarfile.open(fileobj=io.BytesIO(raw)) as layer:
                    self.assertEqual(b'static-controller', layer.extractfile('controller-app').read()); self.assertEqual(0o555, layer.getmember('controller-app').mode)
        self.assertEqual(3, len(set(digests))); self.assertEqual(1, len(set(layers)))

    def test_all_rendered_variants_are_restricted_and_have_disjoint_selectors(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(lab, 'api') as api:
            lab.render(SimpleNamespace(records=Path(directory)), BUNDLE)
            resources = [c.kwargs['payload'] for c in api.call_args_list]
            self.assertGreater(len(resources), 30)
            for obj in resources:
                if obj['kind'] not in ['Pod', 'Deployment', 'ReplicaSet', 'ReplicationController']: continue
                spec = obj['spec'] if obj['kind'] == 'Pod' else obj['spec']['template']['spec']
                self.assertFalse(spec['automountServiceAccountToken']); self.assertTrue(spec['securityContext']['runAsNonRoot'])
                for c in spec['containers']:
                    self.assertFalse(c['securityContext']['allowPrivilegeEscalation']); self.assertTrue(c['securityContext']['readOnlyRootFilesystem'])
                    self.assertEqual(['ALL'], c['securityContext']['capabilities']['drop']); self.assertEqual('Never', c['imagePullPolicy'])
            split = [o for o in resources if o['kind'] == 'Service' and o['metadata']['name'] in ['p06-stable', 'p06-canary']]
            self.assertEqual(2, len(split)); self.assertNotEqual(split[0]['spec']['selector'], split[1]['spec']['selector'])
            recreate = next(o for o in resources if o['kind'] == 'Deployment' and o['spec']['strategy']['type'] == 'Recreate')
            self.assertNotIn('rollingUpdate', recreate['spec']['strategy'])

    def test_rollout_rejects_stale_generation_old_replicas_or_unready_pods(self):
        dep = {'metadata': {'generation': 2}, 'spec': {'replicas': 2}, 'status': {'observedGeneration': 2, 'replicas': 2, 'updatedReplicas': 2, 'readyReplicas': 2, 'availableReplicas': 2}}
        self.assertTrue(lab.converged(dep, [healthy('a'), healthy('b')]))
        for key in ['observedGeneration', 'updatedReplicas', 'readyReplicas', 'availableReplicas']:
            altered = copy.deepcopy(dep); altered['status'][key] = 1
            self.assertFalse(lab.converged(altered, [healthy('a'), healthy('b')]), key)
        bad = healthy(); bad['status']['conditions'][0]['status'] = 'False'
        self.assertFalse(lab.converged(dep, [healthy(), bad])); self.assertFalse(lab.converged(dep, [healthy()]))
        dep['spec']['replicas'] = 0; dep['status'] = {'observedGeneration': 2}; self.assertTrue(lab.converged(dep, []))

    def test_owner_uid_filter_does_not_count_same_label_foreign_children(self):
        own = healthy('a'); foreign = healthy('b')
        own['metadata']['ownerReferences'] = [{'uid': 'parent-uid', 'controller': True}]
        foreign['metadata']['ownerReferences'] = [{'uid': 'foreign-uid', 'controller': True}]
        with patch.object(lab, 'listing', return_value=[own, foreign]):
            self.assertEqual([own], lab.children({'metadata': {'uid': 'parent-uid'}}, 'pods', STATE))
        self.assertEqual(20, lab.cpu('20m')); self.assertEqual(8000, lab.cpu('8'))

    def test_complete_rc_rs_scenario_checks_adoption_mismatch_and_new_uid(self):
        objects = {}; sequence = 0
        def insert(obj):
            nonlocal sequence
            value = copy.deepcopy(obj); sequence += 1; value['metadata']['uid'] = 'uid-' + str(sequence)
            if value['kind'] == 'Pod': value['status'] = healthy()['status']
            objects[value['metadata']['name']] = value; return copy.deepcopy(value)
        def reconcile():
            for parent in list(objects.values()):
                if parent['kind'] not in ['ReplicationController', 'ReplicaSet']: continue
                spec = parent['spec']; selector = spec['selector']; equal = selector.get('matchLabels', selector)
                def matches(p):
                    values = p['metadata']['labels']
                    return all(values.get(k) == v for k,v in equal.items()) and all(values.get(e['key']) in e['values'] for e in selector.get('matchExpressions', []))
                for pod in list(objects.values()):
                    if pod['kind'] == 'Pod' and matches(pod) and lab.controller_ref(pod) is None:
                        pod['metadata']['ownerReferences'] = [{'uid': parent['metadata']['uid'], 'name': parent['metadata']['name'], 'kind': parent['kind'], 'controller': True}]
                owned = [p for p in objects.values() if p['kind'] == 'Pod' and (lab.controller_ref(p) or {}).get('uid') == parent['metadata']['uid']]
                while len(owned) < spec['replicas']:
                    item = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': dict(copy.deepcopy(spec['template']['metadata']), name=parent['metadata']['name'] + '-child-' + str(sequence+1)), 'spec': spec['template']['spec']}
                    item['metadata']['ownerReferences'] = [{'uid': parent['metadata']['uid'], 'kind': parent['kind'], 'name': parent['metadata']['name'], 'controller': True}]
                    owned.append(insert(item))
        def create(obj, state):
            result = insert(obj); reconcile(); return result
        def listing(kind, state, stage=None):
            allowed = {'pods': ['Pod'], 'replicasets': ['ReplicaSet'], 'replicationcontrollers': ['ReplicationController']}
            return [copy.deepcopy(o) for o in objects.values() if o['kind'] in allowed[kind]]
        def api(*args, **kwargs):
            self.assertEqual('delete', args[2]); del objects[args[4]]; reconcile(); return 'deleted'
        with patch.object(lab, 'remove'), patch.object(lab, 'snapshot'), patch.object(lab, 'finish') as finish, \
                patch.object(lab, 'create', side_effect=create), patch.object(lab, 'listing', side_effect=listing), \
                patch.object(lab, 'get', side_effect=lambda kind,name: copy.deepcopy(objects[name])), patch.object(lab, 'api', side_effect=api):
            lab.replicas(SimpleNamespace(), copy.deepcopy(STATE))
            data = finish.call_args.args[3]
            for short in ['rc', 'rs']:
                self.assertIn(data[short]['adopted_uid'], {p['metadata']['uid'] for p in data[short]['before']})
                self.assertNotIn(data[short]['deleted_uid'], {p['metadata']['uid'] for p in data[short]['after']})
                self.assertIsNone(lab.controller_ref(data[short]['mismatch']))

    def test_finalizers_use_merge_and_cleanup_validates_whole_group_first(self):
        obj = healthy(); obj['kind'] = 'Pod'
        with patch.object(lab, 'get', return_value=obj), patch.object(lab, 'api') as api:
            lab.patch('pod', 'p06-pod', {'metadata': {'finalizers': []}}, STATE)
            self.assertIn('--type=merge', api.call_args.args)
        foreign = copy.deepcopy(obj); foreign['metadata']['finalizers'] = ['external/protect']
        with patch.object(lab, 'listing', return_value=[obj, foreign]), patch.object(lab, 'api') as api, patch.object(lab, 'snapshot') as capture:
            with self.assertRaises(ValueError): lab.remove(None, STATE)
            api.assert_not_called(); capture.assert_not_called()
        deleting = copy.deepcopy(obj); deleting['metadata'].update(deletionTimestamp='now', finalizers=[lab.FINALIZER, 'foregroundDeletion'])
        with patch.object(lab, 'listing', side_effect=[[deleting], []]), patch.object(lab, 'snapshot'), patch.object(lab, 'patch') as mutate, patch.object(lab, 'api'):
            lab.remove(None, STATE)
            self.assertEqual(['foregroundDeletion'], mutate.call_args.args[2]['metadata']['finalizers'])

    def test_cleanup_stops_parent_controllers_before_deleting_pods(self):
        items = []
        for kind in ['Pod', 'ReplicaSet', 'Deployment', 'ReplicationController']:
            items.append({'kind': kind, 'metadata': {'name': 'p06-' + kind.lower(), 'labels': {lab.LABEL: STATE['run']}}})
        with patch.object(lab, 'listing', side_effect=[items, []]), patch.object(lab, 'snapshot'), patch.object(lab, 'api') as api:
            lab.remove(SimpleNamespace(), STATE)
            self.assertEqual(['Deployment', 'ReplicationController', 'ReplicaSet', 'Pod'], [c.args[3] for c in api.call_args_list])
            self.assertIn('--cascade=foreground', api.call_args_list[0].args)

    def test_undo_requires_full_template_not_only_the_image(self):
        dep = lab.deploy('p06-main', 'rollbacks', STATE, BUNDLE['images']['v2']['image']); original = copy.deepcopy(dep['spec']['template'])
        with patch.object(lab, 'get', return_value=dep), patch.object(lab, 'api') as api, patch.object(lab, 'rollout', return_value=(dep, [])):
            self.assertEqual(dep, lab.undo(None, STATE, 7, original)); self.assertIn('--to-revision=7', api.call_args.args)
        changed = copy.deepcopy(dep); changed['spec']['template']['spec']['containers'][0]['resources']['requests']['cpu'] = '8'
        with patch.object(lab, 'get', return_value=dep), patch.object(lab, 'api'), patch.object(lab, 'rollout', return_value=(changed, [])):
            with self.assertRaises(ValueError): lab.undo(None, STATE, 7, original)

    def test_observer_uses_current_cluster_ip_and_has_no_server_prestop(self):
        with patch.object(lab, 'get', return_value={'spec': {'clusterIP': '192.168.20.201'}}), patch.object(lab, 'create') as create:
            lab.create_observer('p06-client', 'history', STATE, 'p06-entry')
            obj = create.call_args.args[0]; c = obj['spec']['containers'][0]
            self.assertEqual('192.168.20.201:8080', c['env'][0]['value']); self.assertNotIn('lifecycle', c)
            self.assertIn('tcpSocket', c['readinessProbe']); self.assertNotEqual('main', obj['metadata']['labels'][lab.POOL])

    def test_term_message_rejects_wrong_uid_signal_or_failed_drain(self):
        pod = healthy(); pod['metadata']['deletionTimestamp'] = 'now'
        msg = {'uid': pod['metadata']['uid'], 'signal': 'TERM', 'drained': True}
        pod['status']['containerStatuses'] = [{'name': 'app', 'state': {'terminated': {'exitCode': 0, 'reason': 'Completed', 'message': json.dumps(msg)}}}]
        self.assertEqual(msg, lab.term_receipt(pod))
        for key, value in [('uid', 'foreign'), ('signal', 'INT'), ('drained', False)]:
            altered = copy.deepcopy(pod); data = dict(msg); data[key] = value
            altered['status']['containerStatuses'][0]['state']['terminated']['message'] = json.dumps(data)
            with self.assertRaises(ValueError): lab.term_receipt(altered)

    def test_prepare_recovers_missing_policy_but_refuses_foreign_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(records=Path(directory)); state = dict(STATE, cluster_uid='uid', version='v1.36.5')
            lab.save(args.records/'state.json', state)
            with patch.object(lab, 'check', return_value={'cluster_uid': 'uid', 'version': 'v1.36.5'}), patch.object(lab, 'api', return_value=''), patch.object(lab, 'create') as create:
                self.assertEqual(state, lab.prepare(args, BUNDLE)); create.assert_called_once()
            with patch.object(lab, 'check', return_value={'cluster_uid': 'uid', 'version': 'v1.36.5'}), patch.object(lab, 'api', return_value=json.dumps({'metadata': {'name': 'p06-isolation', 'labels': {lab.LABEL: 'foreign'}}})), patch.object(lab, 'create') as create:
                with self.assertRaises(ValueError): lab.prepare(args, BUNDLE)
                create.assert_not_called()
            lab.observation(args, 'partial.json', {'uid': 'original'})
            lab.observation(args, 'partial.json', {'uid': 'replacement'})
            self.assertEqual({'uid': 'replacement'}, json.loads((args.records/'partial.json').read_text()))
            archived = list((args.records/'observations').glob('partial-*.json'))
            self.assertEqual(1, len(archived)); self.assertEqual({'uid': 'original'}, json.loads(archived[0].read_text()))

    def test_capacity_requires_current_uid_failed_scheduling_and_insufficient_cpu(self):
        candidate = healthy(); candidate['spec'] = {'containers': [{'resources': {'requests': {'cpu': '8'}}}]}
        event = {'items': [{'reason': 'FailedScheduling', 'message': '0/10 nodes available: 2 Insufficient cpu'}]}
        with patch.object(lab, 'get', return_value={}), patch.object(lab, 'active_pods', return_value=[candidate]), patch.object(lab, 'api', return_value=json.dumps(event)) as api, patch.object(lab, 'wait_for', side_effect=lambda text, fn, seconds: fn()):
            result = lab.capacity_failure(STATE, 'p06-capacity'); self.assertEqual(candidate, result['pod'])
            self.assertIn('--field-selector=involvedObject.uid=pod-uid', api.call_args.args)

    def test_actual_shell_resume_skips_passed_groups_and_preserves_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory); tools = home/'.venvs/cnpl-ansible/bin'; tools.mkdir(parents=True)
            wrapper = '''#!PYTHON_BIN
import json,os,sys
from pathlib import Path
args=sys.argv[1:]
if not args or not args[0].endswith(('/lab.py','/build.py')):os.execv(PYTHON_EXEC,[PYTHON_EXEC]+args)
def val(flag):return Path(args[args.index(flag)+1])
if args[0].endswith('/build.py'):val('--output').write_text('{"fixed":true}\\n');sys.exit(0)
action=args[1];r=val('--records');r.mkdir(parents=True,exist_ok=True);s=r/'state.json'
with (Path(os.environ['HOME'])/'actions.txt').open('a') as f:f.write(action+'\\n')
if action in ['check','render']:sys.exit(0)
if action=='prepare':
 if not s.exists():s.write_text('{"passed":[]}')
 sys.exit(0)
if action=='strategies' and not (r/'failed-once').exists():(r/'failed-once').touch();sys.exit(3)
d=json.loads(s.read_text());d['passed'].append(action);s.write_text(json.dumps(d));print(action+' PASS')
'''.replace('PYTHON_BIN', sys.executable).replace('PYTHON_EXEC', repr(sys.executable))
            (tools/'python').write_text(wrapper); (tools/'python').chmod(0o755)
            (tools/'ansible-playbook').write_text('#!/bin/sh\nexit 0\n'); (tools/'ansible-playbook').chmod(0o755)
            records = home/'evidence'; env = dict(os.environ, HOME=str(home))
            first = subprocess.run(['bash', HERE/'run.sh', records], env=env, capture_output=True, text=True, timeout=20)
            self.assertNotEqual(0, first.returncode); old = {p:p.read_bytes() for p in records.glob('attempt-*/*.txt')}
            second = subprocess.run(['bash', HERE/'run.sh', records, '--resume'], env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(0, second.returncode, second.stdout+second.stderr)
            actions = (home/'actions.txt').read_text().splitlines()
            for stage in ['replicas', 'history', 'scale']: self.assertEqual(1, actions.count(stage))
            self.assertEqual(2, actions.count('strategies')); self.assertEqual(lab.STAGES, json.loads((records/'state.json').read_text())['passed'])
            for path, data in old.items(): self.assertEqual(data, path.read_bytes())


if __name__ == '__main__': unittest.main()
