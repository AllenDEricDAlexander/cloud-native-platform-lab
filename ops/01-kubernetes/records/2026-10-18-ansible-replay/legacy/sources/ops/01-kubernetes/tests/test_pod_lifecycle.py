"""01.04 离线回归；只使用临时文件与伪 API/节点命令，不创建负载或重启真实 kubelet。"""
import copy
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parents[1] / 'core-resources/pods'
sys.path.insert(0, str(HERE))
import lab
import pressure

spec = importlib.util.spec_from_file_location('pod_node_pressure', HERE / 'node-pressure.py')
node = importlib.util.module_from_spec(spec)
spec.loader.exec_module(node)
RUN = '20261018T010000Z-1234abcd'


class PodLifecycleTest(unittest.TestCase):
    def test_actual_app_signal_handler_writes_receipt_after_child_exit(self):
        # 实际运行 app.sh 的启动/信号/回收路径；假 httpd 不监听端口，只是有界子进程。
        for delivered, label in [(signal.SIGTERM, 'TERM'), (signal.SIGINT, 'INT')]:
            with self.subTest(signal=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary);binaries = root / 'bin';binaries.mkdir();work = root / 'work'
                binary = binaries / 'httpd'
                binary.write_text('#!' + sys.executable + '''
import os,signal,sys,time
from pathlib import Path
signal.signal(signal.SIGTERM, lambda *args: sys.exit(0))
Path(os.environ['FIXTURE_HTTPD_PID']).write_text(str(os.getpid()))
time.sleep(15)
''');binary.chmod(0o700)
                receipt = root / 'termination-log';child_file = root / 'child-pid'
                uid = '01234567-89ab-cdef-0123-456789abcdef'
                env = dict(os.environ, APP_WORK=str(work), POD_NAME='p04-term', POD_UID=uid, NODE_NAME='fixture-node',
                           START_DELAY='0', TERMINATION_MESSAGE_PATH=str(receipt), FIXTURE_HTTPD_PID=str(child_file),
                           HTTPD_BIN=str(binary),
                           PATH=str(binaries) + os.pathsep + os.environ['PATH'])
                process = subprocess.Popen(['/bin/sh', str(HERE/'app.sh')], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
                try:
                    deadline = time.monotonic() + 5
                    while not (work/'ready').exists() or not child_file.exists():
                        if process.poll() is not None or time.monotonic() > deadline:
                            self.fail('app.sh fixture did not become ready')
                        time.sleep(.02)
                    process.send_signal(delivered)
                    stdout, stderr = process.communicate(timeout=5)
                    self.assertEqual(process.returncode, 0, stdout + stderr)
                    self.assertEqual(receipt.read_text().strip(), 'cnpl-termination-v1 signal=' + label + ' pod_uid=' + uid + ' child_reaped=true exit=0')
                    self.assertFalse((work/'ready').exists())
                    with self.assertRaises(ProcessLookupError): os.kill(int(child_file.read_text()), 0)
                finally:
                    try: os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    process.communicate(timeout=5)

    def test_termination_verify_cleanup_survive_log_gc_and_reject_missing_evidence(self):
        for scenario in ['log-gc', 'missing-message', 'wrong-uid', 'wrong-signal', 'nonzero', 'pressure-not-restored', 'cleanup-noop']:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                args = type('Args', (), {'records': Path(temporary)})()
                state = {'run': RUN, 'cluster_uid': 'fixture-cluster', 'passed': ['prepare','states','sidecars','debug','memory','pressure']}
                data = lab.objects();db = {};deleted = [False];writes = []
                uid = '01234567-89ab-cdef-0123-456789abcdef'
                def store(obj):
                    obj = copy.deepcopy(obj);obj['metadata']['uid'] = uid
                    if obj['kind'] == 'Pod':
                        obj['status'] = {'phase':'Running','conditions':[{'type':'Ready','status':'True'}],
                                         'containerStatuses':[{'name':'app','state':{'running':{}},'restartCount':0}]}
                    db[obj['kind'],obj['metadata']['name']] = obj
                for name in ['p04-baseline','p04-entry','p04-app','p04-isolation','p04-budget','p04-defaults']:
                    obj = copy.deepcopy(data[name]);obj['metadata']['labels'][lab.LABEL] = RUN
                    if name == 'p04-app': obj['data']['app.sh'] = 'ORIGINAL RUNNING BASELINE SCRIPT'
                    store(obj)
                store({'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'foreign','namespace':lab.NS,'labels':{lab.LABEL:'foreign'}},'data':{'keep':'unchanged'}})
                pressure_receipt = {'run':RUN,'cluster_uid':'fixture-cluster','restored':scenario!='pressure-not-restored',
                                    'observed_memory_pressure':True,'evicted':{'reason':'Evicted'}}
                (args.records/'pressure.json').write_text(json.dumps(pressure_receipt))
                kinds = {'pods':'Pod','services':'Service','configmaps':'ConfigMap','networkpolicies':'NetworkPolicy','resourcequotas':'ResourceQuota','limitranges':'LimitRange'}
                def get(kind, name):
                    if kind == 'namespace': return {'metadata':{'uid':'fixture-cluster'}}
                    singular = next((v for k,v in kinds.items() if k.rstrip('s') == kind or k == kind), None)
                    if kind == 'networkpolicy': singular = 'NetworkPolicy'
                    return copy.deepcopy(db[singular,name])
                def api(*argv, payload=None, **kwargs):
                    if 'create' in argv:
                        writes.append(('create',payload['kind'],payload['metadata']['name']));store(payload);return ''
                    if 'patch' in argv:
                        name = argv[argv.index('patch')+2];obj = db['Pod',name]
                        patch_data = json.loads(argv[argv.index('-p')+1]);finalizers = patch_data['metadata']['finalizers']
                        obj['metadata']['finalizers'] = finalizers
                        if not finalizers and obj['metadata'].get('deletionTimestamp'): db.pop(('Pod',name))
                        return ''
                    if 'delete' in argv:
                        kind,name = argv[argv.index('delete')+1:argv.index('delete')+3]
                        mapped = kinds.get(kind, 'ConfigMap' if kind=='configmap' else 'Pod')
                        if name=='p04-term' and db['Pod',name]['metadata'].get('finalizers'):
                            deleted[0] = True;obj = db['Pod',name];obj['metadata']['deletionTimestamp']='2026-10-18T02:00:00Z'
                            message = 'cnpl-termination-v1 signal=TERM pod_uid='+uid+' child_reaped=true exit=0'
                            if scenario=='missing-message': message=''
                            if scenario=='wrong-uid': message=message.replace(uid,'other-pod')
                            if scenario=='wrong-signal': message=message.replace('signal=TERM','signal=INT')
                            code = 137 if scenario=='nonzero' else 0
                            obj['status']['phase'] = 'Failed' if code else 'Succeeded'
                            obj['status']['containerStatuses'][0]['state']={'terminated':{'exitCode':code,'reason':'Error' if code else 'Completed','message':message}}
                        elif scenario!='cleanup-noop': db.pop((mapped,name))
                        return ''
                    if 'describe' in argv: return 'fixture description'
                    if 'logs' in argv and deleted[0]: raise AssertionError('删除后日志已被 GC，不能作为验收依赖')
                    if 'get' in argv:
                        resource = argv[argv.index('get')+1]
                        if resource=='events': return '{"items":[]}'
                        selected = set(kinds[r] for r in resource.split(','))
                        items = [copy.deepcopy(x) for (kind,name),x in db.items() if kind in selected]
                        if '-l' in argv: items = [x for x in items if x['metadata'].get('labels',{}).get(lab.LABEL)==RUN]
                        return json.dumps({'items':items})
                    raise AssertionError(argv)
                def command(argv, **kwargs):
                    if 'p04-term' in argv and deleted[0]: raise AssertionError('禁止删除后读取 CRI 日志')
                    return subprocess.CompletedProcess([],0,'START ready\n','')
                with patch.object(lab,'api',side_effect=api),patch.object(lab,'get',side_effect=get),patch.object(lab,'command',side_effect=command), \
                     patch.object(lab,'check',return_value={'cluster_uid':'fixture-cluster'}), \
                     patch.object(lab,'execute',return_value=subprocess.CompletedProcess([],0,'mode=ready pod=p04-baseline\n','')), redirect_stdout(io.StringIO()):
                    if scenario in ['missing-message','wrong-uid','wrong-signal','nonzero']:
                        with self.assertRaisesRegex(ValueError,'终止证据不完整'): lab.termination(args,state)
                        self.assertNotIn('termination',state['passed'])
                    else:
                        lab.termination(args,state)
                        self.assertEqual(db['ConfigMap','p04-app']['data']['app.sh'],'ORIGINAL RUNNING BASELINE SCRIPT')
                        self.assertEqual(db['ConfigMap','p04-term-app']['data']['app.sh'],(HERE/'app.sh').read_text())
                        self.assertIn(('create','ConfigMap','p04-term-app'),writes)
                        if scenario=='pressure-not-restored':
                            with self.assertRaisesRegex(ValueError,'压力验收/恢复'): lab.verify(args,state)
                            self.assertNotIn('verify',state['passed'])
                        else:
                            lab.verify(args,state)
                            if scenario=='cleanup-noop':
                                with self.assertRaisesRegex(ValueError,'仍有残留'): lab.cleanup(args,state)
                                self.assertNotIn('cleanup',state['passed'])
                            else:
                                lab.cleanup(args,state)
                                self.assertEqual(json.loads((args.records/'cleanup-confirm.json').read_text())['items'],[])
                                self.assertIn('cleanup',state['passed'])
                self.assertNotIn(('Pod','p04-term'),db)
                self.assertEqual(db['ConfigMap','foreign']['data'],{'keep':'unchanged'})

    def test_pressure_ready_marker_requires_successful_load_and_size_check(self):
        c = lab.objects()['p04-pressure']['spec']['containers'][0]
        probe = c['readinessProbe']
        self.assertEqual(probe['exec']['command'][-1], 'test -f /work/loaded')
        self.assertEqual(probe['timeoutSeconds'], 5)
        self.assertNotIn('wc', probe['exec']['command'][-1])
        # 仅运行写入准备片段，dd/stat 为伪命令；不分配 96Mi 或启动 sleep/集群应用。
        for mode in ['dd-fails', 'wrong-size', 'success']:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary);binaries = root / 'bin';binaries.mkdir()
                for name, body in {'dd': "sys.exit(1 if os.environ['FIXTURE_MODE']=='dd-fails' else 0)",
                                   'stat': "print(1 if os.environ['FIXTURE_MODE']=='wrong-size' else 100663296)"}.items():
                    binary = binaries / name
                    binary.write_text('#!' + sys.executable + '\nimport os,sys\n' + body + '\n');binary.chmod(0o700)
                env = dict(os.environ, FIXTURE_MODE=mode, PATH=str(binaries) + os.pathsep + os.environ['PATH'])
                script = c['command'][-1].split('; echo pressure-ready')[0].replace('/work', str(root))
                result = subprocess.run(['/bin/sh', '-ec', script], env=env, text=True, capture_output=True)
                self.assertEqual(result.returncode == 0, mode == 'success')
                check = subprocess.run(['/bin/sh', '-ec', probe['exec']['command'][-1].replace('/work', str(root))])
                self.assertEqual(check.returncode == 0, mode == 'success')

    def test_unarmed_pressure_failure_captures_pod_without_modifying_kubelet(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = type('Args', (), {'records': Path(temporary)})()
            raw = 'original kubelet config\n';state = {'run': RUN, 'cluster_uid': 'fixture', 'passed': ['memory']}
            node_obj = {'metadata': {'uid': 'fixture-node'}, 'status': {'conditions': [
                {'type': key, 'status': value} for key, value in [('Ready', 'True'), ('MemoryPressure', 'False'), ('DiskPressure', 'False'), ('PIDPressure', 'False')]]}}
            pod = lab.objects()['p04-pressure'];pod['metadata']['labels'][lab.LABEL] = RUN
            def remote(script, payload=None):
                if script.startswith('cat '): return raw
                if script == 'systemctl is-active kubelet': return 'active'
                raise AssertionError('准备失败不应修改主机：' + script)
            with patch.object(pressure, 'preflight', return_value=({'cluster_uid': 'fixture'}, raw, {})), patch.object(lab, 'create'), \
                 patch.object(lab, 'wait', side_effect=ValueError('readiness timeout')), \
                 patch.object(lab, 'get', side_effect=lambda kind, name: node_obj if kind=='node' else pod), \
                 patch.object(pressure, 'remote', side_effect=remote), patch.object(pressure, 'system_health'), \
                 patch.object(lab, 'capture') as capture, patch.object(pressure, 'helper') as helper, patch.object(lab, 'api') as api, redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, 'readiness timeout'):
                    pressure.experiment(args, state)
                capture.assert_called_once();helper.assert_not_called();api.assert_not_called()
            saved = json.loads((args.records / 'pressure.json').read_text())
            self.assertFalse(saved['armed']);self.assertFalse(saved['cordoned']);self.assertTrue(saved['restored'])
            self.assertEqual(saved['failure']['stage'], 'preparation')
            self.assertEqual(state['passed'], ['memory'])

    def test_pressure_retry_archives_preparation_failure_and_never_starts_workload(self):
        for scenario in ['safe', 'armed', 'cordoned', 'not-restored', 'wrong-node', 'changed-config']:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                args = type('Args', (), {'records': Path(temporary)})()
                raw = 'original kubelet config\n'
                state = {'run': RUN, 'cluster_uid': 'fixture', 'passed': ['memory']}
                saved = {'run': RUN, 'cluster_uid': 'fixture', 'node_uid': 'node-fixture',
                         'original_sha256': hashlib.sha256(raw.encode()).hexdigest(), 'armed': scenario=='armed',
                         'cordoned': scenario=='cordoned', 'restored': scenario!='not-restored'}
                path = args.records / 'pressure.json';path.write_text(json.dumps(saved));original = path.read_bytes()
                current_node = {'metadata': {'uid': 'other' if scenario=='wrong-node' else 'node-fixture'}}
                def remote(script, payload=None):
                    if script.startswith('cat '): return 'third-party-change' if scenario=='changed-config' else raw
                    if script == 'systemctl is-active kubelet': return 'active'
                    raise AssertionError(script)
                with patch.object(lab, 'check', return_value={'cluster_uid': 'fixture'}), patch.object(lab, 'get', return_value=current_node), \
                     patch.object(pressure, 'remote', side_effect=remote), patch.object(pressure, 'system_health'), \
                     patch.object(lab, 'reset_pods') as reset, patch.object(lab, 'create') as create, redirect_stdout(io.StringIO()):
                    if scenario=='safe':
                        pressure.retry(args, state)
                        reset.assert_called_once()
                        self.assertFalse(path.exists())
                        self.assertEqual(list((args.records/'pressure-attempts').glob('*/pressure.json'))[0].read_bytes(), original)
                    else:
                        with self.assertRaises(ValueError): pressure.retry(args, state)
                        reset.assert_not_called();self.assertEqual(path.read_bytes(), original)
                    create.assert_not_called()
                self.assertEqual(state['passed'], ['memory'])

    def test_crash_and_init_repair_recreate_instead_of_racing_exec(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = type('Args', (), {'records': Path(temporary)})()
            state = {'run': RUN, 'passed': ['prepare']}
            pods = {};created = [];calls = []
            def store(obj):
                obj = copy.deepcopy(obj);created.append(copy.deepcopy(obj));name = obj['metadata']['name']
                obj['metadata']['uid'] = 'uid-' + str(len(created))
                script = obj['spec']['containers'][0]['command'][-1]
                terminated = lambda code: {'terminated': {'exitCode': code, 'reason': 'Completed' if not code else 'Error'}}
                status = {'name': 'app', 'state': {'running': {}}, 'ready': True, 'restartCount': 0}
                obj['status'] = {'phase': 'Running', 'conditions': [{'type': 'Ready', 'status': 'True'}], 'containerStatuses': [status]}
                if name in ['p04-success', 'p04-failed']:
                    code = 7 if name == 'p04-failed' else 0
                    obj['status']['phase'] = 'Failed' if code else 'Succeeded';status['state'] = terminated(code)
                if name == 'p04-crash' and 'application-exit=7' in script:
                    status.update(state={'waiting': {'reason': 'CrashLoopBackOff'}}, restartCount=6, lastState=terminated(7))
                if name == 'p04-bad-image' and 'intentionally-missing' in obj['spec']['containers'][0]['image']:
                    obj['status']['phase'] = 'Pending';status.update(state={'waiting': {'reason': 'ErrImageNeverPull'}}, ready=False)
                if name == 'p04-pending' and obj['spec']['containers'][0]['resources']['requests']['cpu'] == '8':
                    obj['status'].update(phase='Pending', containerStatuses=[], conditions=[{'type': 'PodScheduled', 'status': 'False', 'reason': 'Unschedulable'}])
                if name == 'p04-init':
                    initial = {'name': 'prepare', 'restartCount': 0, 'state': terminated(0)}
                    if 'exit 11' in obj['spec']['initContainers'][0]['command'][-1]:
                        obj['status']['phase'] = 'Pending';status['state'] = {'waiting': {'reason': 'PodInitializing'}}
                        initial.update(restartCount=6, state={'waiting': {'reason': 'CrashLoopBackOff'}}, lastState=terminated(11))
                    obj['status']['initContainerStatuses'] = [initial]
                if name == 'p04-ordinary':
                    status['state'] = terminated(0)
                    obj['status']['containerStatuses'].append({'name': 'side', 'state': {'running': {}}})
                if name == 'p04-native': obj['status']['phase'] = 'Succeeded'
                pods[name] = obj
            def api(*argv, payload=None, **kwargs):
                calls.append(argv)
                if 'create' in argv: store(payload);return ''
                if 'delete' in argv: pods.pop(argv[argv.index('delete') + 2]);return ''
                if 'patch' in argv:
                    obj = pods['p04-bad-image'];obj['status']['phase'] = 'Running';obj['status']['containerStatuses'][0]['state'] = {'running': {}};return ''
                if 'logs' in argv:
                    return 'init-done\nside-start\nmain-start\nmain-stop\nside-stop' if 'p04-native' in argv else 'fixed'
                return json.dumps({'items': list(pods.values())}) if 'pods' in argv else json.dumps({'items': []})
            def execute(name, script, container_name='app', **kwargs):
                self.assertEqual((name, container_name, script), ('ordinary', 'side', 'touch /work/stop'))
                pods['p04-ordinary']['status']['phase'] = 'Succeeded'
                return subprocess.CompletedProcess([], 0, '', '')
            # 原批次已有过期 crash，且原观测文件必须保留。
            old = lab.objects()['p04-crash'];old['metadata']['labels'][lab.LABEL] = RUN;store(old)
            pods['p04-crash']['status'].update(phase='Failed', reason='DeadlineExceeded')
            sentinel = args.records / 'crash-observed.json';sentinel.write_text('ORIGINAL EVIDENCE')
            with patch.object(lab, 'api', side_effect=api), patch.object(lab, 'get', side_effect=lambda kind, name, **kw: copy.deepcopy(pods[name])), \
                 patch.object(lab, 'command', return_value=subprocess.CompletedProcess([], 0, 'fixture log', '')), \
                 patch.object(lab, 'execute', side_effect=execute), redirect_stdout(io.StringIO()):
                lab.states(args, state)
                lab.sidecars(args, state)
            self.assertEqual(state['passed'], ['prepare', 'states', 'sidecars'])
            self.assertEqual(sentinel.read_text(), 'ORIGINAL EVIDENCE')
            observed = [p for p in args.records.glob('crash-observed-*.json') if not p.name.endswith('.events.json')]
            self.assertEqual(len(observed), 1)
            failed_crash = json.loads(observed[0].read_text())
            fixed_crash = json.loads((args.records / 'crash-fixed.json').read_text())
            self.assertNotEqual(failed_crash['metadata']['uid'], fixed_crash['metadata']['uid'])
            self.assertEqual(lab.state_of(failed_crash)['state']['waiting']['reason'], 'CrashLoopBackOff')
            self.assertTrue((args.records / 'crash-before-retry.json').is_file())
            self.assertFalse(pods)

    def test_reset_checks_all_ownership_before_capture_or_delete(self):
        objects = [lab.objects()['p04-crash'], lab.objects()['p04-pending']]
        objects[0]['metadata']['labels'][lab.LABEL] = RUN
        objects[1]['metadata']['labels'][lab.LABEL] = 'foreign'
        with patch.object(lab, 'api', return_value=json.dumps({'items': objects})), patch.object(lab, 'capture') as capture, patch.object(lab, 'delete') as delete:
            with self.assertRaisesRegex(ValueError, '其他批次'):
                lab.reset_pods(None, {'run': RUN}, ['crash', 'pending'])
            capture.assert_not_called();delete.assert_not_called()

    def test_resume_keeps_original_hashes_and_archives_current_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = type('Args', (), {'records': Path(temporary)})()
            state = {'run': RUN, 'cluster_uid': 'fixture', 'passed': ['prepare'], 'implementation_sha256': {'lab.py': 'original-hash'}}
            def get(kind, name):
                obj = copy.deepcopy(lab.objects()[name]);obj['metadata']['labels'][lab.LABEL] = RUN
                obj['status'] = {'conditions': [{'type': 'Ready', 'status': 'True'}]}
                return obj
            with patch.object(lab, 'check', return_value={'cluster_uid': 'fixture'}), patch.object(lab, 'api', return_value='{"items":[]}'), \
                 patch.object(lab, 'get', side_effect=get), patch.object(lab, 'command', return_value=subprocess.CompletedProcess([], 0, 'fixture-commit\n', '')), redirect_stdout(io.StringIO()):
                lab.resume(args, state)
            self.assertEqual(state['passed'], ['prepare'])
            self.assertEqual(state['implementation_sha256'], {'lab.py': 'original-hash'})
            entry = state['resume_history'][0]
            self.assertEqual((args.records / entry['source_directory'] / 'lab.py').read_bytes(), (HERE / 'lab.py').read_bytes())
            (args.records / 'pressure.json').write_text('{}')
            with patch.object(lab, 'check', return_value={'cluster_uid': 'fixture'}), self.assertRaisesRegex(ValueError, '未通过记录'):
                lab.resume(args, state)

    def test_resume_batch_skips_passed_steps_and_preserves_first_attempt_logs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);records = root / 'records';records.mkdir()
            original = records / '09-states.txt';original.write_text('ORIGINAL FAILURE')
            (records / 'state.json').write_text(json.dumps({'passed': ['prepare', 'states']}))
            binary = root / '.venvs/cnpl-ansible/bin/python';binary.parent.mkdir(parents=True)
            binary.write_text('''#!''' + sys.executable + '''
import json,sys
from pathlib import Path
if sys.argv[1] == '-c':
    code = sys.argv[2]; sys.argv = sys.argv[2:]; exec(code); raise SystemExit(0)
records = Path(sys.argv[-1]); mode = sys.argv[2]
with (records / 'calls.txt').open('a') as output: output.write(mode + '\\n')
if mode != 'resume':
    state = json.loads((records / 'state.json').read_text())
    state['passed'].append('pressure' if mode == 'run' else mode)
    (records / 'state.json').write_text(json.dumps(state))
print(mode + ' fixture pass')
''');binary.chmod(0o700)
            result = subprocess.run(['/bin/bash', str(HERE / 'run.sh'), str(records), '--resume'], env=dict(os.environ, HOME=str(root)), capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((records / 'calls.txt').read_text().splitlines(), ['resume', 'sidecars', 'debug', 'memory', 'run', 'termination', 'verify', 'cleanup'])
            self.assertEqual(original.read_text(), 'ORIGINAL FAILURE')
            self.assertEqual(len(list(records.glob('resume-*/10-sidecars.txt'))), 1)
            self.assertIn('09-states 已通过，跳过', result.stdout)

    def test_batch_stops_after_first_real_command_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / '.cnpl/bin/kubectl';binary.parent.mkdir(parents=True)
            binary.write_text('#!/bin/sh\necho fake-client-failure >&2\nexit 7\n');binary.chmod(0o700)
            python = root / '.venvs/cnpl-ansible/bin/python';python.parent.mkdir(parents=True)
            python.write_text('#!/bin/sh\necho fake-preflight-failure >&2\nexit 7\n');python.chmod(0o700)
            records = root / 'records'
            result = subprocess.run(['/bin/bash', str(HERE / 'run.sh'), str(records)],
                                    env=dict(os.environ, HOME=str(root)), capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue((records / '00-target-check.txt').is_file())
            self.assertFalse((records / '01-dns-apply.txt').exists())
            self.assertIn('批次停止', result.stderr)

    def test_cgi_health_toggle_and_invalid_delay_without_starting_server(self):
        with tempfile.TemporaryDirectory() as temporary:
            env = dict(os.environ, APP_WORK=temporary, POD_NAME='fixture', NODE_NAME='fixture-node', QUERY_STRING='ready')
            def cgi():
                return subprocess.run(['/bin/sh', str(HERE / 'app.sh'), 'cgi'], env=env, text=True, capture_output=True)
            self.assertIn('503 Service Unavailable', cgi().stdout)
            (Path(temporary) / 'ready').touch()
            self.assertIn('mode=ready pod=fixture', cgi().stdout)
            env['QUERY_STRING'] = 'delay'
            (Path(temporary) / 'delay').write_text('999')
            self.assertNotEqual(cgi().returncode, 0)

    def test_manifests_keep_security_budget_and_failure_scope(self):
        objects = lab.objects()
        self.assertEqual(len(objects), 19)
        self.assertEqual(objects['p04-baseline']['kind'], 'Pod')
        for obj in objects.values():
            self.assertEqual(obj['metadata']['namespace'], 'lab-core')
            if obj['kind'] != 'Pod':
                continue
            spec = obj['spec']
            self.assertFalse(spec['automountServiceAccountToken'])
            self.assertTrue(spec['securityContext']['runAsNonRoot'])
            self.assertNotIn('hostNetwork', spec)
            self.assertNotIn('hostPath', str(spec['volumes']))
            if obj['metadata']['name'] in ['p04-oom', 'p04-pressure']:
                self.assertEqual(spec['nodeSelector']['kubernetes.io/hostname'], lab.PRESSURE_WORKER)
            else:
                self.assertEqual(spec['nodeSelector']['kubernetes.io/hostname'], lab.WORKER)
            for c in spec['containers'] + spec.get('initContainers', []):
                self.assertEqual(c['securityContext']['capabilities']['drop'], ['ALL'])
                expected = ['NET_BIND_SERVICE'] if obj['metadata']['name'] == 'p04-shellless' else []
                self.assertEqual(c['securityContext']['capabilities'].get('add', []), expected)
                self.assertFalse(c['securityContext']['allowPrivilegeEscalation'])
                self.assertIn('memory', c['resources']['limits'])
        self.assertEqual(objects['p04-pending']['spec']['containers'][0]['resources']['requests']['cpu'], '8')
        self.assertEqual(objects['p04-bad-image']['spec']['containers'][0]['imagePullPolicy'], 'Never')
        native = objects['p04-native']['spec']
        self.assertEqual(native['initContainers'][1]['restartPolicy'], 'Always')
        self.assertIn('startupProbe', native['initContainers'][1])

    def test_foreign_pod_cannot_be_deleted(self):
        with patch.object(lab, 'get', return_value={'metadata': {'name': 'p04-foreign', 'labels': {lab.LABEL: 'foreign'}}}), patch.object(lab, 'api') as api:
            with self.assertRaisesRegex(ValueError, '其他批次'):
                lab.delete('foreign', {'run': RUN})
            api.assert_not_called()

    def test_verify_refuses_missing_pressure_and_other_experiments(self):
        with patch.object(lab, 'check') as check:
            with self.assertRaisesRegex(ValueError, '先通过'):
                lab.verify(None, {'passed': ['prepare', 'memory']})
            check.assert_not_called()

    def test_pressure_preflight_refuses_noncritical_workload(self):
        pods = {'items': [{'metadata': {'name': 'business', 'namespace': 'other'}, 'spec': {'priority': 0}, 'status': {'phase': 'Running'}}]}
        with patch.object(lab, 'check'), patch.object(lab, 'api', return_value=json.dumps(pods)), patch.object(pressure, 'remote') as remote:
            with self.assertRaisesRegex(ValueError, '非系统关键负载'):
                pressure.preflight()
            remote.assert_not_called()

    def test_pressure_arm_failure_still_restores_and_uncordons(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = type('Args', (), {'records': Path(temporary)})()
            current = {'cluster_uid': 'fixture'}
            raw = 'original kubelet config\n'
            state = {'run': RUN, 'cluster_uid': 'fixture', 'passed': ['memory']}
            node_obj = {'metadata': {'uid': 'node-fixture'}, 'status': {'conditions': [
                {'type': name, 'status': status} for name, status in [('Ready', 'True'), ('MemoryPressure', 'False'), ('DiskPressure', 'False'), ('PIDPressure', 'False')]]}}
            calls = []
            def api(*argv, **kwargs):
                calls.append(argv)
                return json.dumps({'node': {'memory': {'availableBytes': 8 * 1024 ** 3}},
                                   'pods': [{'podRef': {'uid': 'victim'}, 'memory': {'workingSetBytes': 96 * 1024 ** 2}}]}) if 'get' in argv else ''
            def remote(script, payload=None):
                if script.startswith('cat '): return raw
                if script.startswith('systemctl is-active'): return 'active'
                if script.startswith('systemctl show'): return 'not-found'
                raise AssertionError(script)
            with patch.object(pressure, 'preflight', return_value=(current, raw, {})), patch.object(lab, 'get', return_value=node_obj), \
                 patch.object(lab, 'create'), patch.object(lab, 'wait', return_value={'metadata': {'uid': 'victim'}}), patch.object(lab, 'api', side_effect=api), \
                 patch.object(lab, 'command'), patch.object(pressure, 'helper', side_effect=ValueError('arm failed')), \
                 patch.object(pressure, 'remote', side_effect=remote), patch.object(pressure, 'system_health'), redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, 'arm failed'):
                    pressure.experiment(args, state)
            saved = json.loads((args.records / 'pressure.json').read_text())
            self.assertTrue(saved['restored'])
            self.assertFalse(saved['cordoned'])
            self.assertIn(('uncordon', lab.PRESSURE_WORKER), calls)
            self.assertNotIn('pressure', state['passed'])

    def test_uncertain_restore_never_uncordons_changed_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = type('Args', (), {'records': Path(temporary)})()
            state = {'run': RUN, 'armed': True, 'cordoned': True, 'original_sha256': 'a' * 64}
            with patch.object(pressure, 'helper', side_effect=ValueError('restore failed')), patch.object(pressure, 'remote', return_value='third party edit'), patch.object(lab, 'api') as api:
                with self.assertRaisesRegex(ValueError, '保持 cordon'):
                    pressure.restore(args, state)
                api.assert_not_called()

    def test_pressure_pass_requires_observed_condition_memory_eviction_and_restore(self):
        for scenario in ['pass', 'wrong-resource', 'missing-condition']:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                args = type('Args', (), {'records': Path(temporary)})()
                state = {'run': RUN, 'cluster_uid': 'fixture', 'passed': ['memory']}
                victim = {'metadata': {'uid': 'victim'}}
                pod = {'status': {'phase': 'Failed', 'reason': 'Evicted', 'message': 'low resource: ' + ('disk' if scenario == 'wrong-resource' else 'memory')}}
                node_obj = {'metadata': {'uid': 'node'}, 'status': {'conditions': [{'type': 'MemoryPressure', 'status': 'False' if scenario == 'missing-condition' else 'True'}]}}
                summary = {'node': {'memory': {'availableBytes': 8 * 1024 ** 3}},
                           'pods': [{'podRef': {'uid': 'victim'}, 'memory': {'workingSetBytes': 96 * 1024 ** 2}}]}
                def get(kind, name, **kwargs): return pod if kind == 'pod' else node_obj
                with patch.object(pressure, 'preflight', return_value=({'cluster_uid': 'fixture'}, 'original', {})), \
                     patch.object(lab, 'get', side_effect=get), patch.object(lab, 'create'), patch.object(lab, 'wait', return_value=victim), \
                     patch.object(lab, 'api', return_value=json.dumps(summary)), patch.object(lab, 'command'), \
                     patch.object(pressure, 'helper', return_value={'armed': True}), patch.object(pressure, 'restore') as restore, \
                     patch.object(lab, 'capture', return_value=pod), patch.object(lab, 'delete'), redirect_stdout(io.StringIO()):
                    if scenario == 'pass': pressure.experiment(args, state)
                    else:
                        with self.assertRaisesRegex(ValueError, '完整证据'):
                            pressure.experiment(args, state)
                    restore.assert_called_once()
                self.assertEqual('pressure' in state['passed'], scenario == 'pass')

    def test_node_timer_is_armed_before_change_and_restore_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / 'config.yaml';original = b'original: kubelet\n';config.write_bytes(original)
            calls = []
            active = [True]
            def native(argv):
                calls.append(argv)
                if argv[0] == 'hostnamectl': return 'worker02.k8s.internal.egon.top'
                if argv[0] == 'getenforce': return 'Enforcing'
                if argv[0] == 'systemd-run':
                    self.assertEqual(config.read_bytes(), original)
                    return 'timer armed'
                if argv[:2] == ['systemctl', 'restart']: active[0] = True
                if argv == ['systemctl', 'is-active', 'kubelet'] and not active[0]:
                    raise subprocess.CalledProcessError(3, argv, output='inactive')
                return 'active'
            payload = {'original_sha256': hashlib.sha256(original).hexdigest(), 'config': {'evictionSoft': {'memory.available': '12345'}}}
            previous = os.umask(0o077)
            try:
                with patch.object(node, 'CONFIG', config), patch.object(node, 'ROOT', root / 'backups'), \
                     patch.object(node, 'run', side_effect=native), patch.object(node.os, 'geteuid', return_value=0), \
                     patch.object(sys, 'argv', ['node-pressure', 'arm', '--run', RUN]), patch.object(sys, 'stdin', io.StringIO(json.dumps(payload))), redirect_stdout(io.StringIO()):
                    node.main()
                    self.assertNotEqual(config.read_bytes(), original)
                    node.restore(root / 'backups' / RUN)
                    self.assertEqual(config.read_bytes(), original)
                    active[0] = False
                    node.restore(root / 'backups' / RUN)
                    self.assertTrue(active[0])
                    config.write_text('third-party-change')
                    with self.assertRaisesRegex(ValueError, '第三方'):
                        node.restore(root / 'backups' / RUN)
            finally:
                os.umask(previous)
            self.assertTrue(any(x[0] == 'systemd-run' for x in calls))

    def test_debug_script_requires_real_process_dns_and_finite_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = type('Args', (), {'records': Path(temporary)})()
            state = {'passed': ['sidecars']}
            result = subprocess.CompletedProcess([], 1, '', 'exec /bin/sh: no such file or directory')
            target = {'status': {'ephemeralContainerStatuses': [{'name': 'diag', 'state': {'terminated': {'exitCode': 0}}}]}}
            calls = []
            def api(*argv, **kwargs):
                calls.append(argv)
                return ''
            with patch.object(lab, 'create'), patch.object(lab, 'wait', return_value=target), patch.object(lab, 'execute', return_value=result), \
                 patch.object(lab, 'capture'), patch.object(lab, 'api', side_effect=api), patch.object(lab, 'delete'), patch.object(lab, 'reset_pods'), \
                 patch.object(lab, 'command', return_value=subprocess.CompletedProcess([], 1, 'no\n', '')), redirect_stdout(io.StringIO()):
                lab.debug(args, state)
            self.assertIn('debug', state['passed'])
            invocation = next(x for x in calls if 'debug' in x)
            self.assertIn('--profile=restricted', invocation)
            self.assertIn('--target=app', invocation)
            self.assertIn('DEBUG_COMPLETE', invocation[-1])
            self.assertIn('http://p04-entry:8080/cgi-bin/check?delay', invocation[-1])
            self.assertNotIn('sleep 600', invocation[-1])
            profile = json.loads((args.records / 'debug-profile.json').read_text())
            self.assertEqual(profile['securityContext']['runAsUser'], 1000)
            self.assertNotIn('resources', profile)


if __name__ == '__main__':
    unittest.main()
