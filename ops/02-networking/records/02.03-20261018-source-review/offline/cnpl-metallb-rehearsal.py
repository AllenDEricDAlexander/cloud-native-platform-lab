import copy, json, os, pathlib, subprocess, sys, tempfile
import yaml
root=pathlib.Path('/Users/mario/SelfProject/cloud-native-platform-lab'); python=pathlib.Path.home()/'.venvs/cnpl-ansible/bin/python'
scenario=sys.argv[1] if len(sys.argv)>1 else 'success'
work=pathlib.Path(tempfile.mkdtemp(prefix='cnpl-metallb-'+scenario+'-'))
source_context=json.loads((root/'ops/02-networking/records/02.03-20261018-source-review/context.json').read_text())
context=copy.deepcopy(source_context);context.update(run='offline-contract',cluster_uid='offline-cluster',primary_preexisting={'IPAddressPool':False,'L2Advertisement':False})
original=context['speaker_original']; component=context['component']; context['worker_macs']={'worker01.k8s.internal.egon.top':'00:50:56:99:21:68','worker02.k8s.internal.egon.top':'00:50:56:99:22:69'}
def put(name,text,executable=False):
 p=work/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
 if executable:p.chmod(0o700)
 return str(p)
state={'daemonset/metallb-system/cnpl-metallb-speaker':{'kind':'DaemonSet','metadata':{'name':'cnpl-metallb-speaker','namespace':'metallb-system','uid':original['uid']},'spec':original['spec'],'status':{'desiredNumberScheduled':2,'numberReady':2}}}
workers=list(context['worker_macs'])
for index,node in enumerate(workers):state['pod/metallb-system/speaker-'+str(index)]={'kind':'Pod','metadata':{'name':'speaker-'+str(index),'uid':'original-speaker-'+str(index),'ownerReferences':[{'uid':original['uid']}]},'spec':{'nodeName':node},'status':{'conditions':[{'type':'Ready','status':'True'}]}}
put('store.json',json.dumps(state))
put('api.py',f'''import json,pathlib,time,uuid
W=pathlib.Path({str(work)!r});workers={workers!r};macs={context['worker_macs']!r};speaker_uid={original['uid']!r}
def read():return json.loads((W/'store.json').read_text())
def write(state):
 p=W/'store.tmp';p.write_text(json.dumps(state));p.replace(W/'store.json')
def key(kind,name,ns=''):return kind.lower()+'/'+ns+'/'+name
aliases={{'pods':'pod','daemonsets':'daemonset','ds':'daemonset','services':'service','svc':'service','endpointslices':'endpointslice'}}
def get(kind,name=None,ns=None):
 s=read();kind=aliases.get(kind,kind)
 if kind=='servicel2statuses':
  node=s['daemonset/metallb-system/cnpl-metallb-speaker']['spec']['template']['spec']['nodeSelector'].get('kubernetes.io/hostname',workers[0])
  return {{'items':[{{'kind':'ServiceL2Status','metadata':{{'name':'mock-status','ownerReferences':[{{'uid':p['metadata']['uid']}} for p in s.values() if p.get('kind')=='Pod' and p['metadata'].get('ownerReferences',[{{}}])[0].get('uid')==speaker_uid and p['spec']['nodeName']==node]}},'status':{{'serviceName':v['metadata']['name'],'serviceNamespace':'lab-metallb','node':node,'interfaces':[{{'name':'ens33'}}]}}}} for v in s.values() if v.get('kind')=='Service' and v['metadata'].get('annotations',{{}}).get('metallb.io/loadBalancerIPs')]}}
 if name:return s.get(key(kind,name,ns or ''))
 return {{'items':[v for k,v in s.items() if k.split('/')[0]==kind and (not ns or k.split('/')[1]==ns)]}}
def reconcile(s):
 ds=s['daemonset/metallb-system/cnpl-metallb-speaker'];node=ds['spec']['template']['spec']['nodeSelector'].get('kubernetes.io/hostname');nodes=[node] if node else workers
 for k,v in list(s.items()):
  if v.get('kind')=='Pod' and v['metadata'].get('ownerReferences',[{{}}])[0].get('uid')==speaker_uid and v['spec']['nodeName'] not in nodes:s.pop(k)
 for n in nodes:
  if not any(v.get('kind')=='Pod' and v['metadata'].get('ownerReferences',[{{}}])[0].get('uid')==speaker_uid and v['spec']['nodeName']==n for v in s.values()):
   name='speaker-new-'+str(uuid.uuid4())[:6];s[key('pod',name,'metallb-system')]={{'kind':'Pod','metadata':{{'name':name,'uid':str(uuid.uuid4()),'ownerReferences':[{{'uid':speaker_uid}}]}},'spec':{{'nodeName':n}},'status':{{'conditions':[{{'type':'Ready','status':'True'}}]}}}}
 ds['status']={{'desiredNumberScheduled':len(nodes),'numberReady':len(nodes)}}
''')
put('kubectl',f'''#!{python}
import json,sys,uuid
from api import *
a=sys.argv[1:];a=a[a.index('--request-timeout=20s')+1:] if '--request-timeout=20s' in a else a
mode=a[0];s=read()
if mode=='apply':
 d=json.loads(sys.stdin.read());m=d['metadata'];k=key(d['kind'],m['name'],m.get('namespace',''));m['uid']=s.get(k,{{}}).get('metadata',{{}}).get('uid',str(uuid.uuid4()))
 if '--dry-run=server' not in a:
  s[k]=d
  if d['kind']=='DaemonSet' and m.get('namespace')=='lab-metallb':
   for i,n in enumerate(workers):
    name='echo-'+str(i);s[key('pod',name,'lab-metallb')]={{'kind':'Pod','metadata':{{'name':name,'uid':'echo-uid-'+str(i),'labels':d['spec']['template']['metadata']['labels'],'ownerReferences':[{{'uid':m['uid']}}]}},'spec':dict(d['spec']['template']['spec'],nodeName=n),'status':{{'conditions':[{{'type':'Ready','status':'True'}}],'podIP':'10.244.9.'+str(i+10)}}}}
  if d['kind']=='Service' and m.get('annotations',{{}}).get('metallb.io/loadBalancerIPs'):
   d['status']={{'loadBalancer':{{'ingress':[{{'ip':'192.168.9.202'}}]}}}}
   s[key('endpointslice',m['name'],'lab-metallb')]={{'kind':'EndpointSlice','metadata':{{'name':m['name'],'namespace':'lab-metallb','labels':{{'kubernetes.io/service-name':m['name']}},'ownerReferences':[{{'uid':m['uid']}}]}},'addressType':'IPv4','ports':[{{'name':'http','port':8080,'protocol':'TCP'}}],'endpoints':[{{'addresses':[v['status']['podIP']],'conditions':{{'ready':True}},'targetRef':{{'uid':v['metadata']['uid']}}}} for v in s.values() if v.get('kind')=='Pod' and v['metadata'].get('labels',{{}}).get('app')=='metallb-echo']}}
  write(s)
 print(json.dumps(d));sys.exit(0)
ns=a[a.index('-n')+1] if '-n' in a else None
if mode=='get':
 name=a[2] if len(a)>2 and not a[2].startswith('-') else None
 value=get(a[1],name,ns);print(json.dumps(value) if value is not None else '');sys.exit(0)
if mode=='patch':
 d=s[key(a[1],a[2],ns)];ops=json.loads(a[a.index('-p')+1])
 for op in ops:
  parts=op['path'].strip('/').split('/');parent=d
  for part in parts[:-1]:parent=parent[part]
  if op['op']=='test':assert parent[parts[-1]]==op['value'],'JSON Patch precondition'
  else:parent[parts[-1]]=op['value']
 if '--dry-run=server' not in a:reconcile(s);write(s)
 print(json.dumps(d));sys.exit(0)
if mode=='delete':
 k=key(a[1],a[2],ns or '');s.pop(k,None)
 if a[1]=='namespace':s={{k:v for k,v in s.items() if k.split('/')[1]!=a[2]}}
 if a[1]=='service':s.pop(key('endpointslice',a[2],ns),None)
 write(s);print('offline deleted');sys.exit(0)
raise SystemExit('unexpected '+str(a))
''',True)
put('arping',f'''#!{python}
import sys
from api import *
if '-D' in sys.argv:sys.exit(1 if any(v.get('kind')=='Service' and v['metadata'].get('annotations',{{}}).get('metallb.io/loadBalancerIPs') for v in read().values()) else 0)
s=read();n=s['daemonset/metallb-system/cnpl-metallb-speaker']['spec']['template']['spec']['nodeSelector'].get('kubernetes.io/hostname',workers[0]);print('Unicast reply from 192.168.9.202 ['+macs[n]+']');sys.exit(0)
''',True)
put('check.py',f'''#!{python}
import importlib.util,json,pathlib,sys,time
from api import *
spec=importlib.util.spec_from_file_location('real_check',{str(root/'ops/02-networking/tests/integration/metallb/check.py')!r});c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
c.__file__=str(W/'check.py');c.K=[str(W/'kubectl'),'--request-timeout=20s'];c.get=lambda kind,name=None,namespace=None:get(kind,name,namespace);c.PRIMARY_RECORD=W/'components/primary.json'
c.source=lambda:{{'source_sha256':{{'offline':'contract'}}}}
c.protected=lambda:{{'offline':'protected'}}
c.common.base.preflight=lambda records:json.loads((records/'context.json').read_text())
def comp(context):
 ds=get('daemonset','cnpl-metallb-speaker','metallb-system');assert ds['status']['numberReady']==2
 return {{'passed':True,'speaker_ready':2}}
c.common.component_ready=comp
def neighbor(vip,macs):
 s=read();n=s['daemonset/metallb-system/cnpl-metallb-speaker']['spec']['template']['spec']['nodeSelector'].get('kubernetes.io/hostname',workers[0]);return {{'vm':n,'mac':macs[n],'observed_mono':time.monotonic(),'rc':0}}
c.monitor.arp=neighbor
def request(conn,backends,kind,epoch=0):
 t=time.monotonic()
 if not backends:return {{'kind':kind,'passed':False,'error_type':'TimeoutError'}}
 pod=next(iter(backends));return {{'kind':kind,'epoch':epoch,'started_mono':t,'finished_mono':t+.001,'local':['192.168.9.200',40000 if kind=='existing' else 50000],'connection_close':kind!='existing','passed':True,'response':{{'pod':pod,'uid':backends[pod]}}}}
c.monitor.request=request
if {scenario!r}=='failure' and sys.argv[1]=='fault-samples':raise SystemExit('deliberate offline failure after real plan and simulated speaker removal')
c.main()
''',True)
records=work/'records';attempt=records/'attempts/contract';attempt.mkdir(parents=True);(records/'state').mkdir();(work/'components').mkdir()
for name,value in [('context.json',context),('state/speaker-original.json',original),('state/source.json',{'source_sha256':{'offline':'contract'}}),('state/protected.json',{'offline':'protected'})]:(records/name).write_text(json.dumps(value))
extra={'metallb_mode':'all','metallb_root':str(root),'metallb_python':str(python),'metallb_check':str(work/'check.py'),'metallb_kubectl':str(work/'kubectl'),'metallb_records':str(records),'metallb_attempt':str(attempt),'metallb_run':context['run'],'metallb_context':context,'metallb_component_record':str(work/'components/primary.json')}
put('extra.json',json.dumps(extra));put('inventory.yml',yaml.safe_dump({'all':{'hosts':{h:{'ansible_connection':'local','ansible_python_interpreter':str(python)} for h in ['localhost','infra01']}}}))
bootstrap=[{'name':'OFFLINE ONLY - templates and isolated API','hosts':'localhost','connection':'local','gather_facts':False,'vars_files':[str(root/'ops/02-networking/ansible/vars/metallb.yml')],'tasks':[{'name':'render all YAML','ansible.builtin.template':{'src':str(root/'ops/02-networking/networking/metallb')+'/{{ item }}.yaml.j2','dest':'{{ metallb_attempt }}/{{ item }}.yaml'},'loop':['primary-pool','l2-fixtures','l2-service','l2-unallocated']}]}]
for name in (['primary','failover'] if scenario=='failure' else ['primary','failover','lifecycle','finish']):bootstrap.append({'ansible.builtin.import_playbook':str(root/'ops/02-networking/ansible/playbooks'/('metallb-'+name+'.yml'))})
put('driver.yml',yaml.safe_dump(bootstrap,sort_keys=False));env=dict(os.environ,PATH=str(work)+':'+os.environ['PATH'],ANSIBLE_CONFIG=str(root/'ops/00-preparation/ansible/ansible.cfg'))
with (work/'ansible.txt').open('w') as f:result=subprocess.run([str(python.parent/'ansible-playbook'),str(work/'driver.yml'),'-i',str(work/'inventory.yml'),'-e','@'+str(work/'extra.json')],stdout=f,stderr=subprocess.STDOUT,env=env)
state=json.loads((work/'store.json').read_text());ds=state['daemonset/metallb-system/cnpl-metallb-speaker'];restored=ds['spec']==original['spec'] and ds['status']['numberReady']==2
summary=json.loads((attempt/'monitor-summary.json').read_text()) if (attempt/'monitor-summary.json').exists() else {}
passed=(result.returncode==0 if scenario=='success' else result.returncode!=0) and restored and summary.get('stopped_by_controller') is True
report={'scenario':scenario,'harness_passed':passed,'ansible_rc':result.returncode,'speaker_spec_restored':restored,'observer_stopped':summary.get('stopped_by_controller'),'work':str(work),'network_and_kubernetes_are_stubs':True,'real_helper_guards_and_restore_plans':True}
put('report.json',json.dumps(report,indent=2));print(json.dumps(report));print('\n'.join((work/'ansible.txt').read_text().splitlines()[-25:]));sys.exit(0 if passed else 1)
