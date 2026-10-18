"""新执行模型的有限检查：无服务监听、无 VM 电源动作、无集群写入。"""
import copy
import base64
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import yaml

BASE=Path(__file__).resolve().parents[1]
ROOT=BASE.parents[1]
PYTHON=Path.home()/'.venvs/cnpl-ansible/bin/python'
ANSIBLE=Path.home()/'.venvs/cnpl-ansible/bin/ansible-playbook'


def module(name):
    s=importlib.util.spec_from_file_location(name.replace('-','_'),BASE/'checks'/name)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


check=module('lab-check.py')
backup=module('backup-check.py')
traffic=module('traffic.py')


def pod(name='a', uid='uid-a', owner='rs', deleting=False):
    p={'kind':'Pod','metadata':{'name':name,'uid':uid,'labels':{'cnpl.io/replay-run':'run'},'ownerReferences':[{'uid':owner,'controller':True}]},
       'spec':{'containers':[{'image':'v1','resources':{'requests':{'cpu':'20m'}}}]},
       'status':{'conditions':[{'type':'Ready','status':'True'}]}}
    if deleting:p['metadata']['deletionTimestamp']='2026-10-18T00:00:00Z'
    return p


class FakeReader:
    context={'run':'run'}
    def __init__(self, objects):self.objects=objects
    def items(self,kind=check.KINDS,**kw):
        return [o for o in self.objects if kind not in ['pods','replicasets'] or o['kind']=={'pods':'Pod','replicasets':'ReplicaSet'}[kind]]
    def get(self,kind,name):return next(o for o in self.objects if o['metadata']['name']==name)


class ReplayTests(unittest.TestCase):
    def test_readers_reject_mutation_before_subprocess(self):
        with patch.object(check,'call') as call:
            r=check.Reader({})
            for args in [('exec','pod'),('apply','-f','x'),('delete','pod'),('patch','pod'),('config','set-context'),('auth','reconcile')]:
                with self.assertRaises(ValueError):r.k(*args)
            call.assert_not_called()
        with self.assertRaises(ValueError):traffic.get(1,'/control?kind=ready&value=false')

    def test_graph_uses_owner_uid_generation_and_active_pods(self):
        dep={'kind':'Deployment','metadata':{'name':'dep','uid':'dep','generation':2,'labels':{'cnpl.io/replay-run':'run'}},'spec':{'replicas':2},'status':{'observedGeneration':2,'replicas':2,'updatedReplicas':2,'readyReplicas':2,'availableReplicas':2}}
        rs={'kind':'ReplicaSet','metadata':{'name':'rs','uid':'rs','ownerReferences':[{'uid':'dep','controller':True}]},'spec':{'replicas':2}}
        objects=[dep,rs,pod(),pod('b','uid-b'),pod('old','old',deleting=True),pod('foreign','foreign',owner='other-rs')]
        result=check.graph(FakeReader(objects),'dep',2,'v1')
        self.assertTrue(result['ok']);self.assertEqual(result['total_pod_objects'],3)
        dep['status']['observedGeneration']=1
        self.assertFalse(check.graph(FakeReader(objects),'dep',2)['ok'])

    def test_cleanup_refuses_foreign_finalizers_and_orders_parents(self):
        p=pod();d={'kind':'Deployment','metadata':{'name':'dep','labels':{'cnpl.io/replay-run':'run'}}}
        self.assertEqual(check.cleanup_plan(FakeReader([p,d]),'06','scale')['objects'][0]['kind'],'Deployment')
        p['metadata']['finalizers']=['foreign/owner']
        with self.assertRaises(ValueError):check.cleanup_plan(FakeReader([p]),'*','*')
        p['metadata']['finalizers']=['foregroundDeletion',check.FINALIZER]
        with self.assertRaises(ValueError):check.cleanup_plan(FakeReader([p]),'*','*')
        p['metadata']['deletionTimestamp']='2026-10-18T00:00:00Z'
        self.assertEqual(len(check.cleanup_plan(FakeReader([p]),'*','*')['objects']),1)

    def test_termination_requires_uid_term_and_real_drain_order(self):
        p=pod(deleting=True)
        receipt={'uid':'uid-a','signal':'TERM','drained':True,'term_at':'2026-10-18T00:00:05Z','prestop_at':'2026-10-18T00:00:00Z','completed':['message']}
        p['status']['containerStatuses']=[{'name':'app','state':{'terminated':{'exitCode':0,'reason':'Completed','message':json.dumps(receipt)}}}]
        document={'pod':p,'responses':[{'uid':'uid-a','result':'completed','completed_at':'2026-10-18T00:00:08Z'}],'hook_seconds':5,'job':{'id':'message','effects':1,'committed_at':'2026-10-18T00:00:09Z'}}
        self.assertEqual(check.termination(document)['pod_uid'],'uid-a')
        for key,value in [('uid','other'),('signal','KILL'),('drained',False)]:
            bad=copy.deepcopy(document);badreceipt=dict(receipt,**{key:value});bad['pod']['status']['containerStatuses'][0]['state']['terminated']['message']=json.dumps(badreceipt)
            with self.assertRaises(ValueError):check.termination(bad)
        document['responses'][0]['completed_at']='2026-10-18T00:00:04Z'
        with self.assertRaises(ValueError):check.termination(document)

    def test_backup_receipt_requires_this_run_full_restore_and_freshness(self):
        c={'run':'run','cluster_uid':'cluster'};v={'schema_version':2,'status':'verified','run':'run','cluster_uid':'cluster','offline_restore_verified':True,'off_cluster_restore_verified':True,'restic_snapshot':'a'*64,'manifest_sha256':'b'*64,'created_utc':datetime.now(timezone.utc).isoformat()}
        self.assertTrue(backup.validate_receipt(v,c)['valid'])
        for key,value in [('run','old'),('off_cluster_restore_verified',False),('restic_snapshot','latest'),('created_utc','2000-01-01T00:00:00+00:00')]:
            with self.assertRaises(ValueError):backup.validate_receipt(dict(v,**{key:value}),c)

    def test_backup_checks_tar_contents_and_every_restored_byte(self):
        with tempfile.TemporaryDirectory() as temporary:
            home=Path(temporary);secrets=home/'.cnpl-secrets';secrets.mkdir()
            ca=b'fake-public-ca';ca_sha=hashlib.sha256(ca).hexdigest()
            (secrets/'kubeconfig-lab-primary').write_text(yaml.safe_dump({'clusters':[{'name':'kubernetes','cluster':{'certificate-authority-data':base64.b64encode(ca).decode()}}]}))
            directory=home/'bundle';directory.mkdir()
            paths=['etc/kubernetes/pki/ca.key','etc/kubernetes/pki/ca.crt','etc/kubernetes/enc/encryption-config.yaml','etc/kubernetes/audit/policy.yaml','etc/kubernetes/manifests/etcd.yaml','etc/kubernetes/manifests/kube-apiserver.yaml']
            for node in ['cp01','cp02','cp03']:
                folder=directory/'nodes'/node;folder.mkdir(parents=True);sums={}
                with tarfile.open(folder/'host-files.tar.gz','w:gz') as archive:
                    for name in paths:
                        content=ca if name.endswith('ca.crt') else ('fake-'+name).encode()
                        entry=tarfile.TarInfo(name);entry.size=len(content);archive.addfile(entry,io.BytesIO(content));sums['/'+name]=hashlib.sha256(content).hexdigest()
                value={'run':'run','node':node,'ca_sha256':ca_sha,'encryption_sha256':'x','archive_sha256':backup.digest(folder/'host-files.tar.gz'),'file_sha256':sums,'offline_restore_verified':node=='cp01','snapshot_status':{'revision':12}}
                (folder/'metadata.json').write_text(json.dumps(value))
            (directory/'nodes/cp01/snapshot.db').write_bytes(b'fake-snapshot')
            context={'run':'run','cluster_uid':'cluster','implementation':{'source':'sha'}}
            with patch.object(backup.Path,'home',return_value=home):
                manifest=backup.manifest(directory,context);(directory/'manifest.json').write_text(json.dumps(manifest))
                restored=home/'restored';shutil.copytree(directory,restored)
                self.assertTrue(backup.verify(directory,restored,context)['verified'])
                (restored/'nodes/cp01/snapshot.db').write_bytes(b'wrong-byte')
                with self.assertRaises(ValueError):backup.verify(directory,restored,context)

    def test_pressure_restoration_is_armed_before_configuration_write(self):
        ts=yaml.safe_load((BASE/'ansible/tasks/replay/case-04-pressure.yml').read_text())
        guarded=next(t for t in ts if 'always' in t)
        self.assertEqual(guarded['always'][0]['ansible.builtin.include_tasks'],'pressure-recover.yml')
        names=[t['name'] for t in guarded['block']]
        self.assertLess(names.index('先建立 150 秒独立回退 timer（管理 Mac 中断也生效）'),names.index('替换为本次临时软驱逐配置'))
        restore=(BASE/'ansible/templates/pressure-restore.sh.j2').read_text()
        self.assertLess(restore.index('第三方修改'),restore.index('cp --preserve=all'))

    def test_manifest_catalog_and_include_contracts(self):
        tasks=BASE/'ansible/tasks/replay'
        signatures={
            'wait-deployment.yml':{'deployment_name','deployment_count','deployment_image'},
            'wait-ready.yml':{'ready_resource'},
            'wait-field.yml':{'wait_resource','wait_field','wait_values','wait_admin','wait_retries','wait_delay','wait_min'},
            'get.yml':{'get_kind','get_name','get_admin'},
            'store-object.yml':{'store_kind','store_name','store_id','store_admin'},
            'samples.yml':{'sample_id','sample_version','sample_status','sample_path','sample_pod'},
            'inspect.yml':{'inspect_id','inspect_pod','inspect_path','inspect_port'},
            'term-check.yml':{'term_id','term_pod','term_responses','term_hook','term_job'},
        }
        def walk(seq):
            for t in seq:
                yield t
                for branch in ['block','rescue','always']:
                    yield from walk(t.get(branch,[]))
        count=0
        for file in tasks.glob('*.yml'):
            for task in walk(yaml.safe_load(file.read_text())):
                count+=1;inc=task.get('ansible.builtin.include_tasks');variables=task.get('vars',{})
                if isinstance(inc,str) and '{{' not in inc:self.assertTrue((tasks/inc).is_file(),(file.name,inc))
                if inc in signatures:self.assertFalse(set(variables)-signatures[inc],(file.name,inc,set(variables)-signatures[inc]))
                source=variables.get('resource_source')
                if source and '{{' not in source:self.assertTrue((BASE/source).is_file(),(file.name,source))
        self.assertGreater(count,400)
        catalog=yaml.safe_load((BASE/'ansible/vars/replay-catalog.yml').read_text())['replay_catalog']
        self.assertEqual(len(catalog),68)
        self.assertTrue(all((BASE/c['source']).is_file() for c in catalog))

    def test_raw_records_and_legacy_sources_unchanged(self):
        legacy=BASE/'records/2026-10-18-ansible-replay/legacy'
        self.assertIn('ops/01-kubernetes/scripts/replay-03-06.sh',check.audit(ROOT,None)['source_sha256'])
        for manifest,prefix in [('original-records-sha256.json',ROOT),('sources-sha256.json',legacy/'sources')]:
            values=json.loads((legacy/manifest).read_text())
            for name,expected in values.items():self.assertEqual(hashlib.sha256((prefix/name).read_bytes()).hexdigest(),expected,name)


    def test_real_ansible_delegation_selects_ssh_without_network(self):
        with tempfile.TemporaryDirectory(prefix='cnpl-delegation-test-') as temporary:
            folder=Path(temporary);ssh=folder/'deny-ssh';calls=folder/'calls'
            ssh.write_text('#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$CNPL_DELEGATION_CALLS"\necho CNPL_OFFLINE_SSH_SELECTED >&2\nexit 255\n')
            ssh.chmod(0o700)
            values=folder/'vars.json';values.write_text(json.dumps({'ansible_ssh_executable':str(ssh)}))
            env=dict(os.environ,ANSIBLE_CONFIG=str(ROOT/'ops/00-preparation/ansible/ansible.cfg'),CNPL_DELEGATION_CALLS=str(calls))
            result=subprocess.run([str(ANSIBLE),str(BASE/'tests/replay-delegation.yml'),'-e','@'+str(values)],capture_output=True,text=True,env=env,timeout=45)
            self.assertEqual(result.returncode,0,result.stdout[-6000:]+result.stderr[-1000:])
            commands=calls.read_text()
            for ip in ['192.168.9.101','192.168.9.102','192.168.9.103','192.168.9.110']:
                self.assertIn(ip,commands)

    def test_actual_ansible_helpers_offline(self):
        with tempfile.TemporaryDirectory(prefix='cnpl-replay-test-') as temporary:
            folder=Path(temporary).resolve();db=folder/'api.json';fixture=BASE/'tests/replay-fixture.py'
            values={'replay_root':str(ROOT),'replay_python':str(PYTHON),'replay_check':str(fixture),'replay_k':[str(PYTHON),str(fixture)],'replay_a':[str(PYTHON),str(fixture)],'replay_namespace':'lab-core','replay_attempt':str(folder),'replay_records':str(folder),'replay_run':'20261018T000000Z-12345678','replay_cluster_uid':'fixture-cluster','replay_topic':'04','replay_case':'smoke','replay_implementation_sha':{'fixture':'sha'}}
            variable_file=folder/'vars.json';variable_file.write_text(json.dumps(values))
            env=dict(os.environ,ANSIBLE_CONFIG=str(ROOT/'ops/00-preparation/ansible/ansible.cfg'),CNPL_REPLAY_TEST_DB=str(db))
            result=subprocess.run([str(ANSIBLE),str(BASE/'tests/replay-smoke.yml'),'-e','@'+str(variable_file)],capture_output=True,text=True,env=env,timeout=90)
            self.assertEqual(result.returncode,0,result.stdout[-7000:]+result.stderr[-2000:])
            self.assertEqual(json.loads(db.read_text()),{})
            checkpoint=json.loads((folder/'checkpoints/04-smoke.json').read_text());self.assertTrue(checkpoint['passed'])


if __name__=='__main__':unittest.main()
