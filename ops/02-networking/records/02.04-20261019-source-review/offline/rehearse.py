"""OFFLINE ONLY: actual Ansible, guards, schemas and PKI; Kubernetes/network are stubs."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[5]
HERE = ROOT / 'ops/02-networking/tests/integration/gateway'
sys.path.insert(0, str(HERE))
import check as c
from test_check import Certificates

scenario = sys.argv[1] if len(sys.argv) > 1 else 'success'
work = Path(tempfile.mkdtemp(prefix='cnpl-gateway-' + scenario + '-')).resolve()
python = Path.home() / '.venvs/cnpl-ansible/bin/python'
records, attempt = work / 'records', work / 'records/attempts/contract'
attempt.mkdir(parents=True)
(records / 'state').mkdir()


def put(name, text, executable=False):
    path = work / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if executable:
        path.chmod(0o700)
    return str(path)


certs = Certificates()
certs.setUp()
c.pki.PRIVATE = work / 'leaves'
context = {'cluster_uid': 'offline-cluster', 'run': 'offline-contract', 'mac_ip': '192.168.9.200', 'stage': '02.04', 'active_ips': []}
context['cluster_resources'] = {d['kind'] + '/' + d['metadata']['name']: c.l2.digest(d['spec']) for d in c.mat.crds()}
tls = c.pki.issue(records, context, b'unit-only')
put('records/context.json', json.dumps(context))
put('store.json', '{}')
put('api.py', r'''
import copy,json,pathlib,subprocess,uuid,yaml
W=pathlib.Path(WORK)
CTX=CONTEXT
ROOT=pathlib.Path(REPOSITORY)
WORKERS=['worker01.k8s.internal.egon.top','worker02.k8s.internal.egon.top']
def read():return json.loads((W/'store.json').read_text())
def write(s):
 p=W/'store.tmp';p.write_text(json.dumps(s));p.replace(W/'store.json')
def key(kind,name,ns=''):return kind.lower()+'/'+ns+'/'+name
aliases={'crds':'customresourcedefinition','crd':'customresourcedefinition','pods':'pod','deploy':'deployment','deployments':'deployment','services':'service','svc':'service','replicasets':'replicaset','namespaces':'namespace','secrets':'secret','endpointslices':'endpointslice','configmaps':'configmap','serviceaccounts':'serviceaccount','roles':'role','rolebindings':'rolebinding','jobs':'job','clusterroles':'clusterrole','clusterrolebindings':'clusterrolebinding','ingresses':'ingress','gateways':'gateway','gatewayclasses':'gatewayclass','httproutes':'httproute','grpcroutes':'grpcroute','tcproutes':'tcproute','udproutes':'udproute','referencegrants':'referencegrant','backendtlspolicies':'backendtlspolicy'}
def get(kind,name=None,namespace=None):
 s=read();kinds=[aliases.get(k.lower(),k.lower()) for k in kind.split(',')]
 if name:return s.get(key(kinds[0],name,namespace or ''))
 return {'items':[v for k,v in s.items() if k.split('/')[0] in kinds and (not namespace or k.split('/')[1]==namespace)]}
def cond(obj,name,status='True',reason=None):
 return {'type':name,'status':status,'reason':reason or 'Accepted','observedGeneration':obj['metadata'].get('generation',1)}
def reconcile(s):
 for k,d in list(s.items()):
  kind=d.get('kind');m=d.get('metadata',{});ns=m.get('namespace','')
  if kind=='CustomResourceDefinition':d['status']={'conditions':[{'type':'Established','status':'True'}]}
  if kind=='GatewayClass':d['status']={'conditions':[cond(d,'Accepted')]}
  if kind=='Service' and m.get('annotations',{}).get('metallb.io/loadBalancerIPs'):
   d['status']={'loadBalancer':{'ingress':[{'ip':m['annotations']['metallb.io/loadBalancerIPs']}]}}
  if kind=='Deployment':
   n=d['spec'].get('replicas',1);d['status']={'readyReplicas':n,'availableReplicas':n,'observedGeneration':m['generation']}
   if ns in ['lab-gateway-app','lab-gateway-backends'] or m['name']=='cnpl-primary':
    rs={'kind':'ReplicaSet','metadata':{'name':m['name']+'-rs','namespace':ns,'uid':m['uid']+'-rs','labels':d['spec']['template']['metadata'].get('labels',{}),'ownerReferences':[{'uid':m['uid']}]}}
    s[key('replicaset',rs['metadata']['name'],ns)]=rs
    for i in range(n):
     node=WORKERS[i%2]
     existing=[p for p in s.values() if p.get('kind')=='Pod' and p['metadata'].get('ownerReferences',[{}])[0].get('uid')==rs['metadata']['uid'] and p['spec']['nodeName']==node]
     if not existing:
      podname=m['name']+'-'+uuid.uuid4().hex[:6]
      p={'kind':'Pod','metadata':{'name':podname,'namespace':ns,'uid':uuid.uuid4().hex,'labels':d['spec']['template']['metadata'].get('labels',{}),'ownerReferences':[{'uid':rs['metadata']['uid']}]},'spec':dict(d['spec']['template']['spec'],nodeName=node),'status':{'conditions':[{'type':'Ready','status':'True'}]}}
      s[key('pod',podname,ns)]=p
 for k,d in list(s.items()):
  kind=d.get('kind');m=d.get('metadata',{})
  if kind=='Gateway':
   foreign=d['spec']['listeners'][1]['tls']['certificateRefs'][0]['name']=='foreign-frontend'
   granted=key('referencegrant','allow-frontend-secret','lab-gateway-backends') in s
   d['status']={'conditions':[cond(d,'Accepted'),cond(d,'Programmed')],'listeners':[{'name':l['name'],'conditions':[cond(d,'ResolvedRefs','False','RefNotPermitted') if l['name']=='https' and foreign and not granted else cond(d,'ResolvedRefs')]} for l in d['spec']['listeners']]}
   ep=s.get(key('envoyproxy','primary','cnpl-gateway'))
   if ep:
    provider=ep['spec']['provider']['kubernetes'];dp=provider['envoyDeployment'];sv=provider['envoyService']
    name='cnpl-primary'; old=s.get(key('deployment',name,'envoy-gateway-system'),{})
    s[key('deployment',name,'envoy-gateway-system')]={'kind':'Deployment','metadata':{'name':name,'namespace':'envoy-gateway-system','uid':old.get('metadata',{}).get('uid','data-deployment'),'generation':1,'labels':{'cnpl.io/cluster-uid':CTX['cluster_uid']}},'status':{'readyReplicas':2,'availableReplicas':2,'observedGeneration':1},'spec':{'replicas':2,'strategy':dp['strategy'],'template':{'metadata':{'labels':dp['pod']['labels']},'spec':{'terminationGracePeriodSeconds':45,'containers':[{'name':'envoy','image':dp['container']['image']},{'name':'shutdown-manager','image':IMAGES['controller']}],'nodeSelector':dp['pod']['nodeSelector']}}}}
    old=s.get(key('service',name,'envoy-gateway-system'),{})
    s[key('service',name,'envoy-gateway-system')]={'kind':'Service','metadata':{'name':name,'namespace':'envoy-gateway-system','uid':old.get('metadata',{}).get('uid','data-service'),'generation':1,'labels':sv['labels'],'annotations':sv['annotations']},'spec':{'type':'LoadBalancer','allocateLoadBalancerNodePorts':False,'loadBalancerSourceRanges':sv['loadBalancerSourceRanges'],'ports':[{'port':l['port'],'protocol':'UDP' if l['protocol']=='UDP' else 'TCP','targetPort':l['port']+10000} for l in d['spec']['listeners']]},'status':{'loadBalancer':{'ingress':[{'ip':'192.168.9.201'}]}}}
  if kind in ['HTTPRoute','GRPCRoute','TCPRoute','UDPRoute']:
   denied=m.get('namespace')=='lab-gateway-denied'
   shared=m['name']=='shared' and key('referencegrant','allow-shared','lab-gateway-backends') not in s
   d['status']={'parents':[{'controllerName':'gateway.envoyproxy.io/cnpl-primary-controller','parentRef':d['spec']['parentRefs'][0],'conditions':[cond(d,'Accepted','False','NotAllowedByListeners') if denied else cond(d,'Accepted'),cond(d,'ResolvedRefs','False','RefNotPermitted') if shared else cond(d,'ResolvedRefs')]}]}
  if kind=='BackendTLSPolicy':d['status']={'ancestors':[{'controllerName':'gateway.envoyproxy.io/cnpl-primary-controller','conditions':[cond(d,'Accepted')]}]}
def apply(doc,dry=False):
 s=read();d=copy.deepcopy(doc);m=d['metadata'];k=key(d['kind'],m['name'],m.get('namespace',''));old=s.get(k,{})
 m['uid']=old.get('metadata',{}).get('uid',uuid.uuid4().hex)
 m['generation']=old.get('metadata',{}).get('generation',0)+1
 if not dry:
  s[k]=d;reconcile(s);reconcile(s);write(s)
 return d
def patch(a):
 s=read();ns=a[a.index('-n')+1];d=s[key(a[1],a[2],ns)];ops=json.loads(a[a.index('-p')+1])
 for op in ops:
  parts=op['path'].strip('/').split('/');parent=d
  for part in parts[:-1]:parent=parent[int(part)] if isinstance(parent,list) else parent[part]
  k=int(parts[-1]) if isinstance(parent,list) else parts[-1]
  if op['op']=='test':assert parent[k]==op['value'],'JSON Patch precondition'
  else:parent[k]=op['value']
 d['metadata']['generation']+=1;reconcile(s);reconcile(s);write(s);return d
def delete(a):
 s=read();ns=a[a.index('-n')+1] if '-n' in a else '';kind=aliases.get(a[1].lower(),a[1].lower());s.pop(key(kind,a[2],ns),None)
 if kind=='namespace':s={k:v for k,v in s.items() if k.split('/')[1]!=a[2]}
 reconcile(s);reconcile(s);write(s);return 'offline deleted'
def kubectl(a,payload=None):
 a=a[a.index('--request-timeout=20s')+1:] if '--request-timeout=20s' in a else a
 mode=a[0];ns=a[a.index('-n')+1] if '-n' in a else None
 if mode=='apply':
  source=a[a.index('-f')+1];doc=json.loads(payload or '{}') if source=='-' else yaml.safe_load(pathlib.Path(source).read_text())
  if doc.get('kind') is None:return 'offline wait'
  return json.dumps(apply(doc,'--dry-run=server' in a))
 if mode in ['wait','api-resources']:return 'offline ready'
 if mode=='patch':return json.dumps(patch(a))
 if mode=='delete':return delete(a)
 if mode=='get':
  name=a[2] if len(a)>2 and not a[2].startswith('-') else None;value=get(a[1],name,ns)
  if any(x.startswith('jsonpath=') for x in a):
   fmt=next(x for x in a if x.startswith('jsonpath='))
   if '.data.tls' in fmt:return value['data']['tls.crt']
   if 'range .items' in fmt:
    if a[1]=='crds':return '\n'.join(o['metadata']['name'] for o in get('crds')['items'])
    return '\n'.join(o['metadata']['name']+'\t'+o['metadata']['uid']+'\t'+json.dumps(o['metadata'].get('labels',{})) for o in get(a[1],namespace=ns)['items'])
   return '' if not value else value['metadata']['uid']+'\n'+json.dumps(value['metadata'].get('labels',{}))+'\n'+value['type']
  return json.dumps(value) if value else ''
 raise ValueError('unexpected offline API '+str(a))
def helm(a):
 if 'list' in a:
  ns=a[a.index('-n')+1];return json.dumps([v for k,v in read().items() if k.startswith('helm/'+ns+'/')])
 ns=a[a.index('--namespace')+1];which='eg' if ns=='envoy-gateway-system' else 'compare';release='cnpl-eg' if which=='eg' else 'cnpl-compare'
 if 'uninstall' in a:
  s=read();s={k:v for k,v in s.items() if not (k=='helm/'+ns+'/'+release or v.get('metadata',{}).get('annotations',{}).get('meta.helm.sh/release-name')==release)};write(s);return 'offline uninstalled'
 index=a.index('upgrade');chart=a[index+3];values=a[a.index('--values')+1]
 raw=subprocess.check_output([str(pathlib.Path.home()/'.cnpl/bin/helm'),'template',release,chart,'-n',ns,'--kube-version','1.36.5','--skip-crds','-f',values],text=True)
 for doc in yaml.safe_load_all(raw):
  if not doc or doc['kind']=='Secret':continue
  doc['metadata'].setdefault('annotations',{});doc['metadata']['annotations']=doc['metadata'].get('annotations') or {}
  doc['metadata']['annotations'].update({'meta.helm.sh/release-name':release,'meta.helm.sh/release-namespace':ns})
  apply(doc)
 s=read();s['helm/'+ns+'/'+release]={'name':release,'chart':'gateway-helm-v1.9.2' if which=='eg' else 'traefik-42.0.0','status':'deployed'};write(s);return 'offline deployed'
'''.replace('WORK', repr(str(work)), 1).replace('CONTEXT', repr(context), 1).replace('REPOSITORY', repr(str(ROOT)), 1).replace("WORKERS=['", "IMAGES="+repr({'controller':c.mat.lock()['envoy_gateway']['artifacts'][0]['internal_source']})+"\nWORKERS=['", 1))
put('kubectl', '#!' + str(python) + '\nimport sys\nfrom api import kubectl\nprint(kubectl(sys.argv[1:],sys.stdin.read() if "-f" in sys.argv and sys.argv[sys.argv.index("-f")+1]=="-" else None))\n', True)
put('helm', '#!' + str(python) + '\nimport sys\nfrom api import helm\nprint(helm(sys.argv[1:]))\n', True)
put('crane', '#!' + str(python) + '\nimport sys\nprint(sys.argv[-1].split("@")[1])\n', True)
put('check.py', r'''
import contextlib,hashlib,http.client,importlib.util,json,pathlib,socket,sys,time,uuid
from api import *
spec=importlib.util.spec_from_file_location('real_gateway',str(ROOT/'ops/02-networking/tests/integration/gateway/check.py'))
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
c.__file__=str(W/'check.py');c.K=[str(W/'kubectl'),'--request-timeout=20s'];c.REGISTRY=W/'components.json';c.pki.PRIVATE=W/'leaves'
original_call=c.call
def call(args,payload=None,timeout=40):
 args=[str(x) for x in args]
 if args[0]==str(W/'kubectl'):return kubectl(args[1:],payload)
 if args[0]==str(c.mat.HELM):return helm(args[1:])
 if args[0]=='dig':return '192.168.9.201\n'
 return original_call(args,payload,timeout)
c.call=call
c.get=lambda kind,name=None,namespace=None:get(kind,name,namespace)
c.source=lambda:{'source_sha256':{'offline-simulated-input':'contract'}}
c.protected=lambda:{'offline-protected':{'uid':'same','sha256':'same'}}
c.preflight=lambda records,identity=False:json.loads((records/'context.json').read_text())
c.l2.common.base.preflight=lambda records:json.loads((records/'context.json').read_text())
orig_getaddrinfo=socket.getaddrinfo
socket.getaddrinfo=lambda name,*args,**kwargs:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('192.168.9.201',443))] if str(name).endswith('.svc.internal.egon.top') else orig_getaddrinfo(name,*args,**kwargs)
counter=0
def http(address,path,host=c.probe.DEMO,tls=True,port=None,headers=None,timeout=5,ca=None):
 global counter
 counter+=1;nonce=uuid.uuid4().hex;start=time.monotonic();s=read();gw=s.get(key('gateway','primary','cnpl-gateway'))
 refs=gw['spec']['listeners'][1]['tls']['certificateRefs'][0] if gw else {}
 foreign=refs.get('name')=='foreign-frontend';grant=key('referencegrant','allow-frontend-secret','lab-gateway-backends') in s
 if tls and foreign and not grant:raise OSError('simulated unauthorized TLS listener')
 profile='compare' if address=='192.168.9.203' else ('foreign' if foreign else 'primary')
 cert=json.loads((W/'records/state/tls.json').read_text())[profile]['sha256']
 h=headers or {};hostname=h.get('Host',host);status=200;body=None;response_headers={}
 if not tls:
  status=301 if hostname in [c.probe.DEMO,c.probe.GRPC] else 404
  response_headers['location']='https://'+host+path
 elif hostname not in [c.probe.DEMO,c.probe.GRPC] or path=='/not-routed':status=404
 elif path=='/slow':status=504;time.sleep(.51)
 elif path=='/shared' and key('referencegrant','allow-shared','lab-gateway-backends') not in s:status=500
 else:
  version='v2' if path.startswith('/v2') or (path=='/weight' and (h.get('X-Cnpl-Canary')=='always' or counter%5==0)) else ('secure' if path=='/secure' else ('shared' if path=='/shared' else 'v1'))
  pods=[p for p in s.values() if p.get('kind')=='Pod' and p['metadata'].get('labels',{}).get('version')==version]
  if not pods:status=404
  else:
   pod=pods[0];body={'pod':pod['metadata']['name'],'uid':pod['metadata']['uid'],'version':version,'nonce':nonce,'protocol':'https' if version=='secure' else 'http','tls':'TLS 1.3' if version=='secure' else '', 'path':path.replace('/rewrite','/v1',1),'headers':{'X-Cnpl-Gateway':['envoy']} if path=='/headers' else {}}
   if path=='/headers':response_headers['x-cnpl-controller']='envoy-gateway'
 return {'passed':True,'started_mono':start,'finished_mono':time.monotonic(),'elapsed_ms':(time.monotonic()-start)*1000,'nonce':nonce,'status':status,'headers':response_headers,'body':body,'tls_peer_sha256':cert if tls else None,'address':address,'path':path}
c.probe.http=http
def rpc(client,address,backends,port=443,**kwargs):
 pod=next(p for p in backends if backends[p]['version']=='v1')
 value={'passed':True,'status':'SERVING','authority':c.probe.GRPC,'pod':pod,'uid':backends[pod]['uid'],'version':'v1','protocol':'grpc'}
 c.probe.identity(value,backends,version='v1',protocol='grpc');return value
c.probe.grpc=rpc
def exchange(address,protocol,backends):
 value=rpc(None,address,backends);value.update(protocol=protocol,nonce=uuid.uuid4().hex)
 c.probe.identity(value,backends,nonce=value['nonce'],protocol=protocol);return value
c.probe.exchange=exchange
@contextlib.contextmanager
def forwarded(k,pod,ports,evidence):
 pathlib.Path(evidence).write_text('OFFLINE stubbed Pod forwarding\n');yield {p:p for p in ports}
c.probe.forwarded=forwarded
class Metrics:
 status=200
 def request(self,*args):pass
 def getresponse(self):return self
 def read(self,*args):return b'envoy_listener_manager_lds_update_rejected 0\nenvoy_cluster_manager_cds_update_rejected 0\nenvoy_listener_manager_lds_update_success 1\nenvoy_cluster_manager_cds_update_success 1\n'
 def close(self):pass
c.http_client.HTTPConnection=lambda *args,**kwargs:Metrics()
original_run=c.subprocess.run
def run(args,*a,**kw):
 if len(args)>2 and args[0]==str(W/'kubectl') and 'can-i' in args:
  allowed=args[args.index('can-i')+1]=='create' and 'httproutes.gateway.networking.k8s.io' in args
  return c.subprocess.CompletedProcess(args,0 if allowed else 1,'yes\n' if allowed else 'no\n','')
 return original_run(args,*a,**kw)
c.subprocess.run=run
if SCENARIO=='failure' and 'frontend-allowed' in sys.argv:raise SystemExit('deliberate failure during foreign certificate experiment')
if SCENARIO=='failure' and sys.argv[1]=='case' and 'frontend-denied' not in sys.argv:
 pass
if sys.argv[1]=='case' and 'rbac' in sys.argv and not (W/'checkpoint').exists():
 import shutil
 checkpoint=W/'checkpoint';checkpoint.mkdir()
 shutil.copytree(W/'records',checkpoint/'records')
 shutil.copy2(W/'store.json',checkpoint/'store.json')
 shutil.copy2(W/'components.json',checkpoint/'components.json')
c.main()
'''.replace('SCENARIO', repr(scenario)))
extra = {'gateway_root': str(ROOT), 'gateway_mode': 'all', 'gateway_python': str(python), 'gateway_check': str(work / 'check.py'), 'gateway_kubectl': str(work / 'kubectl'), 'gateway_helm': str(work / 'helm'), 'gateway_crane': str(work / 'crane'), 'gateway_records': str(records), 'gateway_case_retries': 0}
put('extra.json', json.dumps(extra))
prepare = yaml.safe_load((ROOT / 'ops/02-networking/ansible/playbooks/gateway-prepare.yml').read_text())[0]
prepare['vars_files'] = [str(ROOT / 'ops/02-networking/ansible/vars/gateway.yml')]
prepare['tasks'] = [t for t in prepare['tasks'] if t['name'] != '限定模式和规范化证据路径']
driver = [prepare, {'hosts': 'localhost', 'connection': 'local', 'gather_facts': False, 'vars_files': [str(ROOT / 'ops/02-networking/ansible/vars/gateway.yml')], 'tasks': [{'name': 'OFFLINE DNS plan only', 'ansible.builtin.command': {'argv': [str(python), str(work / 'check.py'), 'dns-plan', '--records', str(records), '--attempt', '{{ gateway_attempt }}', '--manifest', str(work / 'zone'), '--output', '{{ gateway_attempt }}/dns-plan.json']}, 'changed_when': False}]}]
put('zone', '$TTL 300\n@\tIN SOA dns. admin. (\n\t2026101702\t; serial\n\t300 )\nexisting IN A 192.168.9.8\n')
for name in ['install', 'routing', 'authorization', 'protocols', 'ingress', 'weights', 'disruption', 'finish']:
    path = ROOT / ('ops/02-networking/ansible/playbooks/gateway-' + name + '.yml')
    if name == 'routing':
        play = yaml.safe_load(path.read_text())[1]
        play['vars_files'] = [str(ROOT / 'ops/02-networking/ansible/vars/gateway.yml')]
        driver.append(play)
    else:
        driver.append({'ansible.builtin.import_playbook': str(path)})
def absolute_paths(value):
    if isinstance(value, dict):
        return {k: absolute_paths(v) for k, v in value.items()}
    if isinstance(value, list):
        return [absolute_paths(v) for v in value]
    if isinstance(value, str) and value.startswith('../../networking/'):
        return str(ROOT / 'ops/02-networking/networking') + '/' + value.removeprefix('../../networking/')
    if isinstance(value, str) and value.startswith('../tasks/'):
        return str(ROOT / 'ops/02-networking/ansible/tasks') + '/' + value.removeprefix('../tasks/')
    return value
put('driver.yml', yaml.safe_dump(absolute_paths(driver), sort_keys=False))
put('inventory.yml', yaml.safe_dump({'all': {'hosts': {'localhost': {'ansible_connection': 'local', 'ansible_python_interpreter': str(python)}}}}))
env = dict(os.environ, ANSIBLE_CONFIG=str(ROOT / 'ops/00-preparation/ansible/ansible.cfg'), PYTHONUNBUFFERED='1')
with (work / 'ansible.txt').open('w') as log:
    result = subprocess.run([str(python.parent / 'ansible-playbook'), str(work / 'driver.yml'), '-i', str(work / 'inventory.yml'), '-e', '@' + str(work / 'extra.json')], stdout=log, stderr=subprocess.STDOUT, env=env)
state = json.loads((work / 'store.json').read_text())
gateway = state.get('gateway/cnpl-gateway/primary')
restored = bool(gateway and gateway['spec']['listeners'][1]['tls']['certificateRefs'][0]['name'] == 'primary-tls' and 'referencegrant/lab-gateway-backends/allow-frontend-secret' not in state)
passed = (result.returncode == 0 if scenario == 'success' else result.returncode != 0) and restored
report = {'scenario': scenario, 'harness_passed': passed, 'ansible_rc': result.returncode, 'certificate_ref_restored': restored, 'work': str(work), 'kubernetes_and_network_are_stubs': True, 'real_ansible_schema_guards_pki_and_observer': True}
put('report.json', json.dumps(report, indent=2))
print(json.dumps(report))
print('\n'.join((work / 'ansible.txt').read_text().splitlines()[-22:]))
sys.exit(0 if passed else 1)
