"""软驱逐与断点续跑回归；使用有限 API 替身，不改变真实节点或集群。"""
import copy
from datetime import datetime,timezone,timedelta
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import yaml

BASE=Path(__file__).resolve().parents[1]
ROOT=BASE.parents[1]
PYTHON=Path.home()/'.venvs/cnpl-ansible/bin/python'
spec=importlib.util.spec_from_file_location('pressure_check',BASE/'checks/lab-check.py')
check=importlib.util.module_from_spec(spec);spec.loader.exec_module(check)
GIB=1024**3
CAPACITY=16*GIB
NODE='worker02.k8s.internal.egon.top'


def sample(evicted=False, pressured=True, available=15*GIB):
    return {
        'node':{'metadata':{'uid':'node-uid'},'status':{'conditions':[{'type':'MemoryPressure','status':'True' if pressured else 'False'}]}},
        'stats':{'node':{'nodeName':NODE,'memory':{'time':datetime.now(timezone.utc).isoformat(),'availableBytes':available,'workingSetBytes':CAPACITY-available}}},
        'pod':{'metadata':{'uid':'pod-uid','labels':{'cnpl.io/replay-run':'run'}},'spec':{'nodeName':NODE},
               'status':{'phase':'Failed' if evicted else 'Running',**({'reason':'Evicted','message':'The node was low on resource: memory.'} if evicted else {})}}}


class Reader:
    context={'run':'run'}
    def __init__(self,rows):
        self.rows=rows;self.index=0;self.calls=[];self.read_failures=0
        self.config={'evictionSoft':{'memory.available':str(CAPACITY)},'evictionSoftGracePeriod':{'memory.available':'45s'},'evictionMaxPodGracePeriod':5,'evictionHard':{'memory.available':'500Mi'}}
    def k(self,*parts,admin=False,timeout=25):
        self.calls.append(parts)
        if self.read_failures:
            self.read_failures-=1;raise ValueError('transient kubelet proxy unavailable')
        if parts[1].endswith('/configz'):return json.dumps({'kubeletconfig':self.config})
        if parts[1]=='pod':return json.dumps(self.get(*parts[1:]))
        return json.dumps(self.rows[min(self.index,len(self.rows)-1)]['node' if parts[1]=='node' else 'stats'])
    def get(self,*parts):
        self.calls.append(('get',)+parts)
        row=self.rows[min(self.index,len(self.rows)-1)];self.index+=1;return copy.deepcopy(row['pod'])


class Clock:
    elapsed=0
    def now(self):return self.elapsed
    def sleep(self,seconds):self.elapsed+=seconds


class PressureReplayTests(unittest.TestCase):
    def observe(self,reader,output):
        clock=Clock()
        with patch.object(check.time,'monotonic',side_effect=clock.now),patch.object(check.time,'sleep',side_effect=clock.sleep):
            return check.pressure(reader,NODE,'node-uid','pod-uid',CAPACITY,12,str(output))

    def test_available_memory_can_cross_old_16mi_margin_and_still_evict(self):
        rows=[sample(pressured=False),sample(available=15*GIB+32*1024**2),sample(evicted=True,available=15*GIB+64*1024**2)]
        with tempfile.TemporaryDirectory() as temporary:
            r=Reader(rows);result=self.observe(r,Path(temporary)/'proof.json')
            self.assertTrue(result['passed']);self.assertEqual(len(result['samples']),3)
            self.assertTrue(all(s['below_soft_threshold'] for s in result['samples']))
            self.assertTrue(all(c[0]=='get' for c in r.calls))

    def test_memory_pressure_without_eviction_times_out_and_retains_timeline(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'proof.json'
            with self.assertRaisesRegex(ValueError,'没有取得同 UID'):
                self.observe(Reader([sample(),sample(pressured=False)]),path)
            result=json.loads(path.read_text());self.assertFalse(result['passed'])
            self.assertGreater(len(result['samples']),1);self.assertTrue(result['samples'][0]['memory_pressure'])
            self.assertFalse(result['samples'][-1]['memory_pressure'])

    def test_wrong_identity_deletion_other_failure_and_real_exhaustion_cannot_pass(self):
        changes=[('pod',['metadata','uid'],'replacement'),('node',['metadata','uid'],'replacement'),
                 ('pod',['metadata','labels','cnpl.io/replay-run'],'other'),('pod',['spec','nodeName'],'other'),
                 ('pod',['metadata','deletionTimestamp'],'2026-10-18T00:00:00Z'),
                 ('pod',['status','reason'],'OOMKilled'),('pod',['status','phase'],'Succeeded'),
                 ('pod',['status','message'],'The node was low on resource: ephemeral-storage.'),
                 ('stats',['node','nodeName'],'other'),
                 ('stats',['node','memory','time'],(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat())]
        for kind,parts,value in changes:
            with self.subTest(kind=kind,parts=parts),tempfile.TemporaryDirectory() as temporary:
                row=sample(evicted=True);target=row[kind]
                for key in parts[:-1]:target=target[key]
                target[parts[-1]]=value;path=Path(temporary)/'proof.json'
                with self.assertRaises(ValueError):self.observe(Reader([row]),path)
                self.assertFalse(json.loads(path.read_text())['passed'])
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError,'不足 4GiB'):
                self.observe(Reader([sample(evicted=True,available=3*GIB)]),Path(temporary)/'proof.json')

    def test_unloaded_configuration_and_eviction_without_pressure_are_rejected(self):
        for field,value in [('evictionSoft',{'memory.available':str(15*GIB+16*1024**2)}),('evictionSoftGracePeriod',{'memory.available':'0s'}),('evictionHard',{'memory.available':'100Mi'})]:
            with self.subTest(field=field),tempfile.TemporaryDirectory() as temporary:
                r=Reader([sample(evicted=True)]);r.config[field]=value
                with self.assertRaises(ValueError):self.observe(r,Path(temporary)/'proof.json')
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError,'未取得真实 MemoryPressure'):
                self.observe(Reader([sample(evicted=True,pressured=False)]),Path(temporary)/'proof.json')

    def test_transient_proxy_failure_is_recorded_before_valid_eviction(self):
        with tempfile.TemporaryDirectory() as temporary:
            r=Reader([sample(),sample(evicted=True)]);r.read_failures=1
            result=self.observe(r,Path(temporary)/'proof.json')
            self.assertTrue(result['passed']);self.assertIn('read_error',result['samples'][0])

    def test_each_api_call_respects_remaining_window_at_transport_boundary(self):
        with patch.object(check,'call',return_value='{}') as call:
            check.Reader({}).k('get','nodes',timeout=3)
            self.assertIn('--request-timeout=3s',call.call_args.args[0])
            self.assertEqual(call.call_args.kwargs['timeout'],3)
        with tempfile.TemporaryDirectory() as temporary:
            clock=Clock();r=Reader([sample()]);reads=[]
            def stalled(*parts,**kwargs):
                reads.append(kwargs['timeout']);clock.sleep(kwargs['timeout']);raise ValueError('read timed out')
            with patch.object(r,'k',side_effect=stalled),patch.object(check.time,'monotonic',side_effect=clock.now),patch.object(check.time,'sleep',side_effect=clock.sleep):
                with self.assertRaisesRegex(ValueError,'没有取得同 UID'):
                    check.pressure(r,NODE,'node-uid','pod-uid',CAPACITY,15,str(Path(temporary)/'proof.json'))
            self.assertEqual(clock.elapsed,15);self.assertEqual(reads,[10,3])

    def test_real_ansible_templates_use_capacity_keep_grace_and_hard_threshold(self):
        from ansible.parsing.dataloader import DataLoader
        from ansible.template import Templar,trust_as_template
        tasks=yaml.safe_load((BASE/'ansible/tasks/replay/case-04-pressure.yml').read_text())
        block=next(t['block'] for t in tasks if 'always' in t)
        fact=next(t['ansible.builtin.set_fact']['pressure_threshold'] for t in block if 'pressure_threshold' in t.get('ansible.builtin.set_fact',{}))
        config=next(t['ansible.builtin.copy']['content'] for t in block if t.get('delegate_to')=='worker02' and 'ansible.builtin.copy' in t and 'content' in t['ansible.builtin.copy'])
        variables={'pressure_stats':{'stdout':json.dumps(sample()['stats'])},'pressure_config':{'evictionHard':{'memory.available':'500Mi'},'kubeReserved':{'memory':'1Gi'}}}
        template=Templar(loader=DataLoader(),variables=variables)
        threshold=template.template(trust_as_template(fact));self.assertEqual(threshold,CAPACITY)
        variables['pressure_threshold']=threshold
        rendered=json.loads(Templar(loader=DataLoader(),variables=variables).template(trust_as_template(config)))
        self.assertEqual(rendered['evictionSoft'],{'memory.available':str(CAPACITY)})
        self.assertEqual(rendered['evictionSoftGracePeriod'],{'memory.available':'45s'})
        self.assertEqual(rendered['evictionHard'],variables['pressure_config']['evictionHard'])
        self.assertEqual(rendered['kubeReserved'],variables['pressure_config']['kubeReserved'])
        self.assertTrue(any(t.get('ansible.builtin.command',{}).get('argv',[])[-3:]==['105','--output','{{ replay_attempt }}/observations/04-pressure-eviction.json'] for t in block))

    def test_actual_ansible_skips_all_eight_passed_groups_without_rewriting_them(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);(folder/'checkpoints').mkdir()
            checkpoints=['03-dns','03-backup','03-ha','04-base','04-states','04-sidecars','04-debug','04-memory']
            for case in checkpoints:
                (folder/'checkpoints'/(case+'.json')).write_text(json.dumps({'run':'run','cluster_uid':'cluster','passed':True}))
            before={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (folder/'checkpoints').glob('*')}
            inputs=folder/'vars.json';inputs.write_text(json.dumps({'replay_root':str(ROOT),'replay_records':str(folder),'replay_run':'run','replay_cluster_uid':'cluster','passed_cases':checkpoints}))
            env=dict(os.environ,ANSIBLE_CONFIG=str(ROOT/'ops/00-preparation/ansible/ansible.cfg'))
            result=subprocess.run([str(PYTHON.parent/'ansible-playbook'),str(BASE/'tests/replay-checkpoint-skip.yml'),'-e','@'+str(inputs)],capture_output=True,text=True,env=env,timeout=45)
            self.assertEqual(result.returncode,0,result.stdout[-6000:]+result.stderr[-1500:])
            for group in checkpoints:self.assertIn(group.replace('-','/')+' 已通过，跳过',result.stdout)
            self.assertEqual(before,{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (folder/'checkpoints').glob('*')})


if __name__=='__main__':unittest.main()
