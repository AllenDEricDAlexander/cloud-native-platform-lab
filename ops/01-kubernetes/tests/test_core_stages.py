"""07–10 的身份、调度、指标和恢复边界；不向真实集群提交实验对象。"""
import base64
import copy
from datetime import datetime,timezone,timedelta
import importlib.util
import ipaddress
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import yaml

from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

BASE=Path(__file__).resolve().parents[1]
ROOT=BASE.parents[1]
spec=importlib.util.spec_from_file_location('core_checks',BASE/'checks/core-check.py')
core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)


def meta(name,uid=None):return {'name':name,'uid':uid or name,'generation':1,'labels':{'cnpl.io/core-run':'run'}}
def pod(name,parent='parent',image='v1',ready=True,node='worker01.k8s.internal.egon.top'):
    return {'kind':'Pod','metadata':dict(meta(name),ownerReferences=[{'uid':parent,'controller':True}]),'spec':{'nodeName':node,'containers':[{'image':image,'resources':{'requests':{'cpu':'50m'}}}]},'status':{'conditions':[{'type':'Ready','status':'True' if ready else 'False'}]}}


class Reader:
    context={'run':'run','namespace':'isolated'}
    namespace='isolated'
    def __init__(self,objects,metrics=None):self.objects=objects;self.metrics=metrics or {'items':[]}
    def read(self,kind,name=None,**kw):
        if kind=='certificatesigningrequests':return {'items':self.objects}
        if name:return copy.deepcopy(next(o for o in self.objects if o['metadata']['name']==name))
        return {'items':copy.deepcopy(self.objects)}
    def owned(self,kind):return [copy.deepcopy(o) for o in self.objects if o['kind'].lower()+'s'==kind]
    def raw(self,path):return self.metrics


class CoreStageTests(unittest.TestCase):
    def test_stateful_partition_uses_actual_owner_uid_and_image(self):
        parent={'kind':'StatefulSet','metadata':meta('state','parent'),'status':{'observedGeneration':1}}
        rows=[parent,pod('state-0',image='v1'),pod('state-1',image='v2'),pod('unrelated','other')]
        a=SimpleNamespace(kind='statefulset',name='state',count=2,not_ready=None,image='v2',old_image='v1',partition=1,nodes=None)
        self.assertEqual(len(core.workload(Reader(rows),a)['pods']),2)
        for change in ['uid','image','ready','generation']:
            bad=copy.deepcopy(rows)
            if change=='uid':bad[1]['metadata']['ownerReferences'][0]['uid']='other'
            elif change=='image':bad[2]['spec']['containers'][0]['image']='v1'
            elif change=='ready':bad[2]['status']['conditions'][0]['status']='False'
            else:bad[0]['status']['observedGeneration']=0
            with self.subTest(change=change),self.assertRaises(ValueError):core.workload(Reader(bad),a)

    def test_daemon_coverage_rejects_two_pods_on_one_node(self):
        parent={'kind':'DaemonSet','metadata':meta('daemon','parent'),'status':{'observedGeneration':1}}
        rows=[parent,pod('a'),pod('b')]
        a=SimpleNamespace(kind='daemonset',name='daemon',count=2,not_ready=None,image='v1',old_image=None,partition=None,nodes='worker01.k8s.internal.egon.top,worker02.k8s.internal.egon.top')
        with self.assertRaisesRegex(ValueError,'覆盖'):core.workload(Reader(rows),a)
        rows[2]['spec']['nodeName']='worker02.k8s.internal.egon.top';self.assertEqual(len(core.workload(Reader(rows),a)['pods']),2)

    def test_job_requires_terminal_condition_and_expected_cause(self):
        obj={'kind':'Job','metadata':meta('job'),'status':{'conditions':[{'type':'Failed','status':'True','reason':'DeadlineExceeded'}]}}
        a=SimpleNamespace(name='job',condition='Failed',reason='DeadlineExceeded')
        self.assertEqual(core.job(Reader([obj]),a)['job']['metadata']['name'],'job')
        obj['status']['conditions'][0]['reason']='BackoffLimitExceeded'
        with self.assertRaises(ValueError):core.job(Reader([obj]),a)

    def test_cron_requires_controller_owner_and_real_scheduled_timestamp(self):
        parents=[];jobs=[]
        for policy in ['Allow','Forbid','Replace']:
            p={'kind':'CronJob','metadata':meta(policy),'spec':{'concurrencyPolicy':policy,'timeZone':'Asia/Shanghai'}};parents.append(p)
            j={'kind':'Job','metadata':dict(meta(policy+'-job'),ownerReferences=[{'uid':policy,'controller':True}],annotations={'batch.kubernetes.io/cronjob-scheduled-timestamp':'2026-10-18T09:00:00Z'}),'status':{'active':1}};jobs.append(j)
        r=Reader(parents+jobs);first=core.cron(r,SimpleNamespace(input=None));self.assertEqual(len(first['initial_uids']),3)
        jobs[0]['metadata']['annotations']={}
        with self.assertRaisesRegex(ValueError,'真实调度'):core.cron(Reader(parents+jobs),SimpleNamespace(input=None))
        jobs[0]['metadata']['annotations']={'batch.kubernetes.io/cronjob-scheduled-timestamp':'2026-10-18T09:00:00Z'}
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'first.json';path.write_text(json.dumps(first))
            extra=copy.deepcopy(jobs[0]);extra['metadata']['name']='allow-2';extra['metadata']['uid']='allow-2'
            jobs[2]['metadata']['uid']='replace-new'
            self.assertEqual(len(core.cron(Reader(parents+jobs+[extra]),SimpleNamespace(input=path))['jobs']['Allow']),2)
            extra['metadata']['ownerReferences'][0]['uid']='Forbid'
            with self.assertRaises(ValueError):core.cron(Reader(parents+jobs+[extra]),SimpleNamespace(input=path))

    def test_hpa_needs_fresh_metrics_matching_resource_and_real_ready_scale(self):
        h={'kind':'HorizontalPodAutoscaler','metadata':meta('hpa'),'spec':{'scaleTargetRef':{'name':'load'},'minReplicas':1,'maxReplicas':4,'metrics':[{'resource':{'name':'cpu'}}]},'status':{'conditions':[{'type':'ScalingActive','status':'True'}],'currentMetrics':[{'resource':{'name':'cpu'}}],'desiredReplicas':2}}
        d={'kind':'Deployment','metadata':meta('load'),'spec':{'replicas':2},'status':{'readyReplicas':2}}
        p=pod('p');p['metadata']['labels']['app.kubernetes.io/name']='load'
        metrics={'items':[{'metadata':{'name':'p'},'timestamp':datetime.now(timezone.utc).isoformat()}]}
        a=SimpleNamespace(name='hpa',condition='up',output=None)
        self.assertEqual(core.hpa(Reader([h,d,p],metrics),a)['deployment']['spec']['replicas'],2)
        for failure in ['stale','unknown','wrong-resource','not-ready','unbounded']:
            bad=copy.deepcopy([h,d,p]);m=copy.deepcopy(metrics)
            if failure=='stale':m['items'][0]['timestamp']=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()
            elif failure=='unknown':bad[0]['status']['conditions'][0]['status']='False'
            elif failure=='wrong-resource':bad[0]['status']['currentMetrics'][0]['resource']['name']='memory'
            elif failure=='not-ready':bad[1]['status']['readyReplicas']=1
            else:bad[1]['spec']['replicas']=5
            with self.subTest(failure=failure),self.assertRaises(ValueError):core.hpa(Reader(bad,m),a)

    def make_csr(self,**overrides):
        name='worker01.k8s.internal.egon.top';key=ec.generate_private_key(ec.SECP256R1())
        subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,overrides.get('cn','system:node:'+name)),x509.NameAttribute(NameOID.ORGANIZATION_NAME,'system:nodes')])
        sans=overrides.get('sans',[x509.DNSName(name),x509.IPAddress(ipaddress.ip_address('192.168.9.109'))])
        request=x509.CertificateSigningRequestBuilder().subject_name(subject).add_extension(x509.SubjectAlternativeName(sans),critical=False).sign(key,hashes.SHA256())
        return {'metadata':{'name':'csr-owned','creationTimestamp':overrides.get('created',datetime.now(timezone.utc).isoformat())},'spec':{'username':'system:node:'+name,'groups':['system:nodes','system:authenticated'],'signerName':'kubernetes.io/kubelet-serving','request':base64.b64encode(request.public_bytes(serialization.Encoding.PEM)).decode(),'usages':overrides.get('usages',['digital signature','server auth'])},'status':{}}

    def test_csr_checks_identity_san_signature_usage_and_age_before_any_approval(self):
        a=SimpleNamespace(name='worker01.k8s.internal.egon.top',ip='192.168.9.109')
        with patch.object(core,'serving_tls',return_value=False):
            self.assertEqual(core.csr(Reader([self.make_csr()]),a)['names'],['csr-owned'])
            cases=[{'cn':'system:node:cp01.k8s.internal.egon.top'},{'sans':[x509.DNSName('other.internal.egon.top'),x509.IPAddress(ipaddress.ip_address(a.ip))]},
                   {'sans':[x509.DNSName(a.name),x509.IPAddress(ipaddress.ip_address(a.ip)),x509.UniformResourceIdentifier('spiffe://other')]},
                   {'usages':['client auth']},{'created':(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()}]
            for case in cases:
                with self.subTest(case=case),self.assertRaises(ValueError):core.csr(Reader([self.make_csr(**case)]),a)
        with patch.object(core,'serving_tls',return_value=True):self.assertEqual(core.csr(Reader([]),a),{'names':[],'already_serving':True})

    def test_tls_probe_rejects_unknown_ssh_target_before_subprocess(self):
        with patch.object(core.subprocess,'run') as call:
            with self.assertRaises(ValueError):core.serving_tls('worker01.k8s.internal.egon.top','203.0.113.9')
            call.assert_not_called()

    def test_real_ansible_node_patch_preserves_other_taints_and_checks_uid(self):
        from ansible.parsing.dataloader import DataLoader
        from ansible.template import Templar,trust_as_template
        tasks=yaml.safe_load((BASE/'ansible/tasks/core/node-restore-one.yml').read_text())
        command=next(t['ansible.builtin.command']['argv'] for t in tasks if t['name']=='只移除本次 NoSchedule 污点，原子保护其他污点')
        keep={'key':'unrelated-maintenance','effect':'NoSchedule'}
        node={'metadata':{'uid':'node-uid','labels':{'cnpl.io/core07':'run'}},'spec':{'taints':[keep,{'key':'cnpl.io/core07','value':'run','effect':'NoSchedule'}]}}
        values={'core_a':['kubectl'],'core_run':'run','node':node,'core_node_binding':{'name':'worker02.k8s.internal.egon.top','uid':'node-uid'}}
        argv=Templar(loader=DataLoader(),variables=values).template(trust_as_template(command));patches=json.loads(argv[-1])
        self.assertEqual(patches[0],{'op':'test','path':'/metadata/uid','value':'node-uid'})
        self.assertEqual(patches[1]['value'],node['spec']['taints']);self.assertEqual(patches[2]['value'],[keep])

    def test_independent_node_timer_template_is_valid_bash_and_scoped(self):
        from ansible.parsing.dataloader import DataLoader
        from ansible.template import Templar,trust_as_template
        source=(BASE/'ansible/templates/core-node-restore.sh.j2').read_text()
        result=Templar(loader=DataLoader(),variables={'core_run':'run','core_node_bindings':[{'uid':'one'},{'uid':'two'}]}).template(trust_as_template(source))
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'restore.sh';path.write_text(result)
            subprocess.run(['/bin/bash','-n',str(path)],check=True,capture_output=True)
        self.assertIn("n['metadata']['uid']=='two'",result)
        self.assertIn("all(t.get('value')=='run'",result)
        self.assertNotIn('kubectl delete',result)

    def test_cleanup_refuses_recreated_namespace_or_foreign_secret(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'state').mkdir();(root/'state/namespace.json').write_text('{"uid":"original"}')
            context={'run':'run','records':str(root),'namespace':'isolated'}
            r=SimpleNamespace(context=context,namespace='isolated',api=SimpleNamespace(k=lambda *a,**k:'[]'))
            r.read=lambda kind,*a,**k:{'metadata':meta('isolated','replacement')} if kind=='namespace' else {'items':[]}
            with self.assertRaisesRegex(ValueError,'已被替换'):core.guard(r)
            r.read=lambda kind,*a,**k:{'metadata':meta('isolated','original')} if kind=='namespace' else {'items':[]}
            r.api.k=lambda *a,**k:json.dumps([{'name':'foreign','uid':'uid','labels':{'cnpl.io/core-run':'other'},'annotations':{'private':'not-for-output'}}])
            with self.assertRaisesRegex(ValueError,'其他运行'):core.guard(r)
            r.api.k=lambda *a,**k:'[]';self.assertEqual(core.guard(r)['namespace_uid'],'original')

    def test_native_include_contracts_and_no_missing_sources(self):
        signatures={'wait.yml':{'core_wait_name','core_wait_action','core_wait_id','core_wait_args','core_wait_retries','core_wait_delay'},'exec.yml':{'core_exec_name','core_exec_pod','core_exec_args','core_exec_change'},'get.yml':{'core_kind','core_name'}}
        def walk(tasks):
            for task in tasks:
                yield task
                for key in ['block','rescue','always']:yield from walk(task.get(key,[]))
        for file in (BASE/'ansible/tasks/core').glob('*.yml'):
            for task in walk(yaml.safe_load(file.read_text())):
                include=task.get('ansible.builtin.include_tasks');variables=task.get('vars',{})
                if include and '{{' not in include:self.assertTrue((file.parent/include).is_file(),(file.name,include))
                if include in signatures:self.assertFalse(set(variables)-signatures[include],(file.name,include))
                for key in ['core_source','core_secret_source']:
                    source=variables.get(key)
                    if source and '{{' not in source:self.assertTrue((BASE/source).is_file(),source)
        self.assertTrue(all((BASE/item['source']).is_file() for entries in yaml.safe_load((BASE/'ansible/vars/core-catalog.yml').read_text())['core_catalog'].values() for item in entries))


if __name__=='__main__':unittest.main()
