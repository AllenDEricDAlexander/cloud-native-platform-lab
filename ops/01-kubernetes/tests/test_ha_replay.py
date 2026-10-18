"""HA 故障窗口和人工等待的有限回归；无真实关机、网络监听或集群写入。"""
import copy
from datetime import datetime,timezone
import importlib.util
import json
import os
import subprocess
import tempfile
from types import SimpleNamespace
from contextlib import nullcontext,contextmanager
from pathlib import Path
import socket
import unittest
from unittest.mock import patch
import yaml

BASE=Path(__file__).resolve().parents[1]


def load(name):
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),BASE/'checks'/name)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


ha=load('ha-check.py');traffic=load('traffic.py')


def evidence():
    base=datetime(2026,10,18,tzinfo=timezone.utc).timestamp()
    binding={'run':'run','cluster_uid':'cluster','target':'cp03','target_ip':'192.168.9.103','target_uid':'node-uid',
             'initial_holder':'cp03.k8s.internal.egon.top','survivors':['cp01','cp02'],'server_uids':['app-a','app-b']}
    iso=lambda seconds:datetime.fromtimestamp(base+seconds,timezone.utc).isoformat()
    rows=[{'at':base+offset,'code':200,'ok':True,'body':{'uid':'app-a','version':'v1'}} for offset in [1,5,11,15,31,35]]
    return {'context':{'run':'run','cluster_uid':'cluster'},'binding':binding,'recovered_uid':'node-uid',
            'fault_started_at':iso(10),'fault_confirmed_at':iso(20),'recovered_at':iso(30),'new_holder':'cp02.k8s.internal.egon.top',
            'port_checks':[[{'port':p,'state':'stopped'} for p in [22,6443]] for _ in range(2)],
            'quorum':[{'endpoint':'https://'+ha.CP[n]+':2379','health':True} for n in ['cp01','cp02']],
            'restored_etcd':[{'endpoint':'https://'+ip+':2379','health':True} for ip in ha.CP.values()],
            'proof_pod':{'metadata':{'uid':'proof','labels':{'cnpl.io/replay-run':'run'},'creationTimestamp':iso(12)},
                         'status':{'phase':'Succeeded'},'spec':{'nodeName':'worker02.k8s.internal.egon.top'}},
            'observer':{'target':'cp03','stopped_by_ansible':True,'app_errors':0,'rows':rows,
                        'api_rows':[{'at':base+12,'api':{'cp01':True,'cp02':True,'cp03':False,'vip':True}}]}}


class HAReplayTest(unittest.TestCase):
    def test_full_fault_window_and_recovery(self):
        result=ha.verify(evidence())
        self.assertTrue(result['passed']);self.assertEqual(result['target_api_down_samples'],1)

    def test_expired_observer_cannot_pass_despite_ready_marker(self):
        d=evidence();d['observer']['stopped_by_ansible']=False
        with self.assertRaisesRegex(ValueError,'超时'):ha.verify(d)

    def test_samples_only_before_fault_cannot_pass(self):
        d=evidence();d['observer']['rows']=[dict(d['observer']['rows'][0],at=1) for _ in range(6)]
        with self.assertRaisesRegex(ValueError,'完整覆盖'):ha.verify(d)

    def test_node_down_without_both_ports_stopped_cannot_pass(self):
        d=evidence();d['port_checks'][1][0]['state']='started'
        with self.assertRaisesRegex(ValueError,'端口'):ha.verify(d)

    def test_no_actual_target_api_failure_cannot_pass(self):
        d=evidence();d['observer']['api_rows'][0]['api']['cp03']=True
        with self.assertRaisesRegex(ValueError,'独立采样'):ha.verify(d)

    def test_stale_proof_or_wrong_owner_cannot_pass(self):
        for replacement in ['2026-10-17T23:59:00Z','2026-10-18T00:00:21Z']:
            d=evidence();d['proof_pod']['metadata']['creationTimestamp']=replacement
            with self.assertRaisesRegex(ValueError,'新创建'):ha.verify(d)
        d=evidence();d['proof_pod']['metadata']['labels']['cnpl.io/replay-run']='other'
        with self.assertRaisesRegex(ValueError,'归属'):ha.verify(d)

    def test_changed_node_uid_or_unhealthy_quorum_cannot_pass(self):
        d=evidence();d['recovered_uid']='replacement'
        with self.assertRaisesRegex(ValueError,'原 Node'):ha.verify(d)
        d=evidence();d['quorum'][0]['health']=False
        with self.assertRaisesRegex(ValueError,'etcd'):ha.verify(d)

    def test_business_error_or_wrong_backend_cannot_pass(self):
        for field,value in [('ok',False),('code',503)]:
            d=evidence();d['observer']['rows'][2][field]=value
            with self.assertRaisesRegex(ValueError,'应用请求失败'):ha.verify(d)
        d=evidence();d['observer']['rows'][2]['body']['uid']='foreign'
        with self.assertRaisesRegex(ValueError,'实际副本'):ha.verify(d)

    def test_port_diagnostics_probe_both_ports_even_if_ssh_up(self):
        def connect(address,timeout):
            if address[1]==6443:raise socket.timeout('API closed')
            manager=unittest.mock.MagicMock();return manager
        with patch.object(traffic.socket,'create_connection',side_effect=connect) as call:
            result=traffic.port_states('192.168.9.103')
        self.assertEqual([x.args[0][1] for x in call.call_args_list],[22,6443])
        self.assertTrue(result['22']['tcp_open']);self.assertFalse(result['6443']['tcp_open'])

    def test_preparation_wait_is_before_observer_and_power_detection_is_native(self):
        tasks=yaml.safe_load((BASE/'ansible/tasks/replay/case-03-ha.yml').read_text())
        pause=[i for i,t in enumerate(tasks) if 'ansible.builtin.pause' in t]
        start=next(i for i,t in enumerate(tasks) if t.get('ansible.builtin.include_tasks')=='start-observer.yml')
        self.assertEqual(len(pause),1);self.assertLess(pause[0],start)
        self.assertEqual(tasks[start]['vars']['observer_seconds'],2400)
        ports=[t for t in tasks if t.get('ansible.builtin.wait_for',{}).get('state')=='stopped']
        self.assertEqual(len(ports),2)
        for t in ports:
            self.assertEqual(t['loop'],[22,6443]);self.assertEqual(t['delegate_to'],'{{ ha_survivor }}')
        live=[t for t in tasks if t.get('ansible.builtin.include_tasks')=='observer-live.yml']
        self.assertGreaterEqual(len(live),4)
        self.assertFalse(any('unavailable' in json.dumps(t) for t in tasks))


    def test_ready_file_does_not_prevent_collector_from_expiring(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);a=SimpleNamespace(pod='client',target='cp03',seconds=0,output=str(root/'out'),ready=str(root/'ready'),stop=str(root/'stop'),timeline=str(root/'timeline'))
            r=SimpleNamespace(context={'run':'run'},get=lambda *args:{'metadata':{'labels':{'cnpl.io/replay-run':'run'}}})
            with patch.object(traffic,'tunnel',return_value=nullcontext(1)),patch.object(traffic,'tls',return_value=nullcontext(None)):
                traffic.ha(a,r)
            result=json.loads(Path(a.output).read_text())
            self.assertTrue(Path(a.ready).exists());self.assertTrue(result['expired']);self.assertFalse(result['stopped_by_ansible'])


    def test_late_stop_file_cannot_turn_expiry_into_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);a=SimpleNamespace(pod='client',target='cp03',seconds=0,output=str(root/'out'),ready=str(root/'ready'),stop=str(root/'stop'),timeline=str(root/'timeline'))
            r=SimpleNamespace(context={'run':'run'},get=lambda *args:{'metadata':{'labels':{'cnpl.io/replay-run':'run'}}})
            @contextmanager
            def late_stop():
                try:yield 1
                finally:Path(a.stop).write_text('late')
            with patch.object(traffic,'tunnel',return_value=late_stop()),patch.object(traffic,'tls',return_value=nullcontext(None)):
                traffic.ha(a,r)
            result=json.loads(Path(a.output).read_text())
            self.assertTrue(Path(a.stop).exists());self.assertTrue(result['expired']);self.assertFalse(result['stopped_by_ansible'])

    def test_collector_retains_output_if_tls_initialization_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);a=SimpleNamespace(pod='client',target='cp03',seconds=10,output=str(root/'out'),ready=str(root/'ready'),stop=str(root/'stop'),timeline=str(root/'timeline'))
            r=SimpleNamespace(context={'run':'run'},get=lambda *args:{'metadata':{'labels':{'cnpl.io/replay-run':'run'}}})
            with patch.object(traffic,'tunnel',return_value=nullcontext(1)),patch.object(traffic,'tls',side_effect=ValueError('TLS fixture failure')):
                with self.assertRaisesRegex(ValueError,'TLS fixture'):traffic.ha(a,r)
            self.assertIn('TLS fixture',json.loads(Path(a.output).read_text())['observer_error'])

    def test_actual_ansible_observer_lifecycle_offline(self):
        project=BASE.parents[1];python=Path.home()/'.venvs/cnpl-ansible/bin/python'
        with tempfile.TemporaryDirectory(prefix='cnpl-observer-test-') as temporary:
            root=Path(temporary).resolve()
            values={'replay_root':str(project),'replay_python':str(python),'replay_traffic':str(BASE/'tests/replay-observer-fixture.py'),'replay_records':str(root),'replay_attempt':str(root),'replay_topic':'03','replay_case':'ha'}
            # helper uses observations/; point its prefix back to this isolated root through a symlink.
            (root/'observations').symlink_to(root,target_is_directory=True)
            varfile=root/'vars.json';varfile.write_text(json.dumps(values))
            env=dict(os.environ,ANSIBLE_CONFIG=str(project/'ops/00-preparation/ansible/ansible.cfg'))
            result=subprocess.run([str(python.parent/'ansible-playbook'),str(BASE/'tests/replay-observer-smoke.yml'),'-e','@'+str(varfile)],capture_output=True,text=True,env=env,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout[-7000:]+result.stderr[-1000:])


    def test_quorum_command_renders_exact_surviving_endpoints(self):
        from ansible.parsing.dataloader import DataLoader
        from ansible.template import Templar,trust_as_template
        tasks=yaml.safe_load((BASE/'ansible/tasks/replay/case-03-ha.yml').read_text())
        command=next(t['ansible.builtin.command']['argv'] for t in tasks if t['name']=='两个存活 etcd 必须健康并返回结构化结果')
        for target in ha.CP:
            survivors=[n for n in ha.CP if n!=target]
            value=','.join('https://'+ha.CP[n]+':2379' for n in survivors)
            templar=Templar(loader=DataLoader(),variables={'replay_a':['kubectl'],'ha_cp_ips':ha.CP,'ha_survivor':survivors[0],'ha_quorum_endpoints':value})
            argv=templar.template(trust_as_template(command))
            self.assertIn('--endpoints='+value,argv);self.assertNotIn('https://'+ha.CP[target]+':2379',','.join(argv))

    def test_default_observer_budget_remains_for_other_cases_and_failed_case_aborts(self):
        source=(BASE/'ansible/tasks/replay/start-observer.yml').read_text()
        self.assertIn('default(420)',source);self.assertNotIn("'--seconds', '420'",source)
        cases=yaml.safe_load((BASE/'ansible/tasks/replay/case.yml').read_text())
        rescue=next(t['rescue'] for t in cases if 'rescue' in t)
        self.assertIn('abort-observer.yml',[t.get('ansible.builtin.include_tasks') for t in rescue])


if __name__=='__main__':unittest.main()
