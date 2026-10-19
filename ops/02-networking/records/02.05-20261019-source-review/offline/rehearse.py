"""OFFLINE ONLY: real Ansible, PKI and local Python/Go TLS; Kubernetes, timers and gateway are stubs."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import yaml

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / 'ops/02-networking/tests/integration/certificates'))
import check as c
from test_check import Authority

scenario = sys.argv[1] if len(sys.argv) > 1 else 'success'
work = Path(tempfile.mkdtemp(prefix='cnpl-tls-' + scenario + '-')).resolve()
python = Path.home() / '.venvs/cnpl-ansible/bin/python'
records = work / 'records'
records.mkdir()


def put(name, text, executable=False):
    path = work / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if executable:
        path.chmod(0o700)
    return str(path)


ca = Authority()
ca.setUp()
c.pki.PRIVATE = work / 'private'
context = {'cluster_uid': 'offline-cluster', 'run': 'offline-contract', 'mac_ip': '192.168.9.200', 'stage': '02.05'}
c.pki.prepare(records, context, b'unit-root')
public_root = c.pki.PUBLIC
# Only public retained resources are read; no cluster Secret body is fetched.
state = {}
objects, main = c.main_objects({'cluster_uid': '4d3e52d7-e203-4daf-aced-9c3a666fcf5b', 'mac_ip': '192.168.9.200'})
initial = list(objects.values()) + c.get('replicasets', namespace='envoy-gateway-system')['items'] + c.get('pods', namespace='envoy-gateway-system')['items']
for obj in initial:
    if obj['kind'] == 'Pod' and not obj['metadata']['name'].startswith('cnpl-primary-'):
        continue
    text = json.dumps(obj).replace('4d3e52d7-e203-4daf-aced-9c3a666fcf5b', context['cluster_uid'])
    obj = json.loads(text)
    state[obj['kind'].lower() + '/' + obj['metadata'].get('namespace', '') + '/' + obj['metadata']['name']] = obj
for kind, obj in objects.items():
    item = state[obj['kind'].lower() + '/' + obj['metadata'].get('namespace', '') + '/' + obj['metadata']['name']]
    context.setdefault('main_original', {})[kind] = {'uid': item['metadata']['uid'], 'spec_sha256': c.gw.l2.digest(item['spec'])}
context['gateway_original_refs'] = state['gateway/cnpl-gateway/primary']['spec']['listeners'][1]['tls']['certificateRefs']
context['data_pod_uids'] = sorted(p['uid'] for p in main['data_pods'])
state['_timer'] = {'count': 0}
put('store.json', json.dumps(state))
put('records/context.json', json.dumps(context))
put('api.py', r'''
import copy,json,pathlib,subprocess,uuid,yaml,datetime,base64
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec
W=pathlib.Path(WORK);ROOT=pathlib.Path(REPOSITORY)
def read():return json.loads((W/'store.json').read_text())
def write(s):
 p=W/'store.tmp';p.write_text(json.dumps(s));p.replace(W/'store.json')
def key(kind,name,ns=''):return kind.lower()+'/'+ns+'/'+name
aliases={'crds':'customresourcedefinition','crd':'customresourcedefinition','pods':'pod','deployments':'deployment','replicasets':'replicaset','services':'service','secrets':'secret','namespaces':'namespace','certificates':'certificate','certificaterequests':'certificaterequest','issuers':'issuer','configmaps':'configmap','serviceaccounts':'serviceaccount','roles':'role','rolebindings':'rolebinding','httproutes':'httproute','backendtlspolicies':'backendtlspolicy','endpointslices':'endpointslice'}
def condition(obj,name):return {'type':name,'status':'True','observedGeneration':obj['metadata']['generation']}
def issue(s,doc):
 m=doc['metadata'];spec=doc['spec'];duration=168 if spec['duration'].startswith('168') else 1
 ca=json.loads((W/'records/state/materials.json').read_text())['issuer']
 issuer=x509.load_pem_x509_certificate(pathlib.Path(ca['certificate']).read_bytes())
 issuer_key=serialization.load_pem_private_key(pathlib.Path(ca['private_key']).read_bytes(),None)
 keypair=ec.generate_private_key(ec.SECP256R1());now=datetime.datetime.now(datetime.timezone.utc)
 cert=(x509.CertificateBuilder().subject_name(x509.Name([])).issuer_name(issuer.subject).public_key(keypair.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now).not_valid_after(now+datetime.timedelta(hours=duration)).add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in spec['dnsNames']]),False).sign(issuer_key,hashes.SHA384()))
 old=s.get('secret/cnpl-gateway/primary-managed-tls',{});uid=old.get('metadata',{}).get('uid',uuid.uuid4().hex)
 secret={'apiVersion':'v1','kind':'Secret','metadata':{'name':'primary-managed-tls','namespace':'cnpl-gateway','uid':uid,'labels':spec['secretTemplate']['labels'],'ownerReferences':[{'kind':'Certificate','uid':m['uid']}]},'type':'kubernetes.io/tls','data':{'tls.crt':base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)+issuer.public_bytes(serialization.Encoding.PEM)).decode()}}
 s['secret/cnpl-gateway/primary-managed-tls']=secret
 revision=doc.get('status',{}).get('revision',0)+1
 doc['status']={'conditions':[condition(doc,'Ready')],'revision':revision,'renewalTime':(now+datetime.timedelta(seconds=.2) if duration==1 else now+datetime.timedelta(days=5)).isoformat()}
 csr=x509.CertificateSigningRequestBuilder().subject_name(x509.Name([])).add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in spec['dnsNames']]),False).sign(keypair,hashes.SHA256())
 s['certificaterequest/cnpl-gateway/primary-'+str(revision)]={'apiVersion':'cert-manager.io/v1','kind':'CertificateRequest','metadata':{'name':'primary-'+str(revision),'namespace':'cnpl-gateway','uid':uuid.uuid4().hex,'ownerReferences':[{'uid':m['uid']}]},'spec':{'issuerRef':spec['issuerRef'],'request':base64.b64encode(csr.public_bytes(serialization.Encoding.PEM)).decode(),'duration':spec['duration'],'usages':spec['usages']}}
 doc['_issued_duration']=duration
def reconcile(s):
 for d in list(s.values()):
  if not isinstance(d,dict):continue
  kind=d.get('kind');m=d.get('metadata',{})
  if kind=='Deployment':
   d['status']={'readyReplicas':d['spec']['replicas'],'availableReplicas':d['spec']['replicas'],'observedGeneration':m['generation']}
   if m.get('namespace')=='lab-tls':
    rsuid=m['uid']+'-'+str(m['generation']);label=d['spec']['template']['metadata']['labels']
    for k,v in list(s.items()):
     if k.startswith(('pod/lab-tls/','replicaset/lab-tls/')):s.pop(k)
    s['replicaset/lab-tls/backend']={'kind':'ReplicaSet','metadata':{'name':'backend','namespace':'lab-tls','uid':rsuid,'labels':label,'ownerReferences':[{'uid':m['uid']}]}}
    s['pod/lab-tls/backend']={'kind':'Pod','metadata':{'name':'backend','namespace':'lab-tls','uid':rsuid+'-pod','labels':label,'ownerReferences':[{'uid':rsuid}]},'spec':dict(d['spec']['template']['spec'],nodeName='worker01.k8s.internal.egon.top'),'status':{'conditions':[{'type':'Ready','status':'True'}]}}
  if kind=='Issuer':d['status']={'conditions':[condition(d,'Ready')]}
  if kind=='Certificate':
   requested=168 if d['spec']['duration'].startswith('168') else 1
   timer=any((p/'certificate-initial.json').exists() for p in (W/'records/attempts').glob('*'))
   if d.get('_issued_duration')!=requested or (requested==1 and d.get('status',{}).get('revision')==1 and timer):issue(s,d)
  if kind=='ValidatingAdmissionPolicy':d['status']={'observedGeneration':m['generation'],'typeChecking':{}}
  if kind=='HTTPRoute':d['status']={'parents':[{'controllerName':'gateway.envoyproxy.io/cnpl-primary-controller','parentRef':d['spec']['parentRefs'][0],'conditions':[condition(d,'Accepted'),condition(d,'ResolvedRefs')]}]}
  if kind=='BackendTLSPolicy':d['status']={'ancestors':[{'controllerName':'gateway.envoyproxy.io/cnpl-primary-controller','conditions':[condition(d,'Accepted')]}]}
def get(kind,name=None,namespace=None):
 s=read();reconcile(s);write(s);kinds=[aliases.get(k.lower(),k.lower()) for k in kind.split(',')]
 if name:return s.get(key(kinds[0],name,namespace or ''))
 return {'items':[v for k,v in s.items() if '/' in k and k.split('/')[0] in kinds and (not namespace or k.split('/')[1]==namespace)]}
def apply(d,dry=False):
 s=read();m=d['metadata'];k=key(d['kind'],m['name'],m.get('namespace',''));old=s.get(k,{})
 m['uid']=old.get('metadata',{}).get('uid',uuid.uuid4().hex);m['generation']=1 if not old else old['metadata']['generation']+(old.get('spec')!=d.get('spec'))
 if not dry:
  if d['kind']=='Certificate' and old:
   d.update({n:v for n,v in old.items() if n.startswith('_') or n=='status'})
  s[k]=d;reconcile(s);write(s)
 return d
def cli(a,payload=None):
 a=a[a.index('--request-timeout=20s')+1:] if '--request-timeout=20s' in a else a
 mode=a[0];ns=a[a.index('-n')+1] if '-n' in a else None
 if mode=='auth':
  resource=a[a.index('can-i')+2];verb=a[a.index('can-i')+1]
  allowed=verb=='patch' and resource=='certificates.cert-manager.io/primary-auto'
  return (0 if allowed else 1,'yes\n' if allowed else 'no\n','')
 if mode=='apply':
  path=a[a.index('-f')+1];d=json.loads(payload) if path=='-' else json.loads(pathlib.Path(path).read_text())
  spec=d.get('spec',{});kind=d['kind']
  denied=(kind in ['CertificateRequest','CertificateSigningRequest'] or kind=='ClusterIssuer' or kind=='Certificate' and (spec.get('isCA') or any(x not in ['demo.svc.internal.egon.top','grpc-demo.svc.internal.egon.top'] for x in spec.get('dnsNames',[])) or 'client auth' in spec.get('usages',[])) or kind=='HTTPRoute' and any(h not in ['demo.svc.internal.egon.top','grpc-demo.svc.internal.egon.top'] for h in spec.get('hostnames',[])))
  if denied:return (1,'','CNPL_TLS_BOUNDARY: offline policy denial')
  obj=apply(d,'--dry-run=server' in a)
  return (0, d['kind']+'/'+d['metadata']['name'] if '-o' in a and a[a.index('-o')+1]=='name' else json.dumps(obj),'')
 if mode=='get':
  name=a[2] if len(a)>2 and not a[2].startswith('-') else None;value=get(a[1],name,ns)
  if any(x.startswith('jsonpath=') for x in a):
   fmt=next(x for x in a if x.startswith('jsonpath='))
   if '.data.tls' in fmt:return (0,value['data']['tls.crt'],'')
   if '.metadata.ownerReferences' in fmt:return (0,json.dumps(value['metadata'].get('ownerReferences',[])),'')
   if 'range .items' in fmt:
    if a[1]=='crds':return (0,'\n'.join(d['metadata']['name'] for d in get('crds')['items']),'')
    return (0,'\n'.join(d['metadata']['name']+'\t'+d['metadata']['uid']+'\t'+json.dumps(d['metadata'].get('labels',{})) for d in get(a[1],namespace=ns)['items']),'')
   return (0,'' if not value else value['metadata']['uid']+'\n'+json.dumps(value['metadata'].get('labels',{}))+'\n'+value['type'],'')
  return (0,json.dumps(value) if value else '','')
 if mode=='patch':
  s=read();d=s[key(a[1],a[2],ns)]
  for op in json.loads(a[a.index('-p')+1]):
   parts=op['path'].strip('/').split('/');parent=d
   for part in parts[:-1]:parent=parent[int(part)] if isinstance(parent,list) else parent[part]
   k=int(parts[-1]) if isinstance(parent,list) else parts[-1]
   if op['op']=='test':assert parent[k]==op['value']
   else:parent[k]=op['value']
  d['metadata']['generation']+=1;d['status']['conditions']=[condition(d,n) for n in ['Accepted','Programmed']];write(s);return (0,json.dumps(d),'')
 if mode=='delete':
  s=read();s={k:v for k,v in s.items() if not k.startswith(('namespace//'+a[2],)) and not ('/' in k and k.split('/')[1]==a[2])};write(s);return (0,'offline namespace deleted','')
 if mode=='wait':return (0,'offline ready','')
 raise ValueError('unhandled API '+str(a))
def helm(a):
 if 'list' in a:return json.dumps([{'name':'cnpl-cert-manager','chart':'cert-manager-v1.21.2','status':'deployed'}] if read().get('_helm') else [])
 index=a.index('upgrade');chart=a[index+3];values=a[a.index('--values')+1]
 raw=subprocess.check_output([str(pathlib.Path.home()/'.cnpl/bin/helm'),'template','cnpl-cert-manager',chart,'-n','cert-manager','--skip-crds','--kube-version','1.36.5','-f',values],text=True)
 for d in yaml.safe_load_all(raw):
  if not d:continue
  d['metadata']['annotations']=d['metadata'].get('annotations') or {}
  d['metadata']['annotations'].update({'meta.helm.sh/release-name':'cnpl-cert-manager','meta.helm.sh/release-namespace':'cert-manager'});apply(d)
 s=read();s['_helm']=True;write(s);return 'offline installed'
'''.replace('WORK', repr(str(work)), 1).replace('REPOSITORY', repr(str(ROOT)), 1))
put('kubectl', '#!' + str(python) + '\nimport sys\nfrom api import cli\nrc,out,err=cli(sys.argv[1:],sys.stdin.read() if "-f" in sys.argv and sys.argv[sys.argv.index("-f")+1]=="-" else None);print(out);print(err,file=sys.stderr);sys.exit(rc)\n', True)
put('helm', '#!' + str(python) + '\nimport sys\nfrom api import helm\nprint(helm(sys.argv[1:]))\n', True)
put('crane', '#!' + str(python) + '\nimport sys\nprint(sys.argv[-1].split("@")[1])\n', True)
put('check.py', r'''
import contextlib,datetime,hashlib,http.server,importlib.util,json,pathlib,ssl,subprocess,sys,threading,time,uuid
from api import *
spec=importlib.util.spec_from_file_location('real_tls',str(ROOT/'ops/02-networking/tests/integration/certificates/check.py'));c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
c.K=[str(W/'kubectl'),'--request-timeout=20s'];c.gw.K=c.K;c.REGISTRY=W/'components.json';c.pki.PRIVATE=W/'private';c.pki.PUBLIC=pathlib.Path(PUBLIC_ROOT)
original_call=c.call
def call(args,payload=None,timeout=40):
 args=[str(x) for x in args]
 if args[0]==str(W/'kubectl'):
  rc,out,err=cli(args[1:],payload);c.require(rc==0,err);return out
 if args[0]==str(c.mat.HELM):return helm(args[1:])
 return original_call(args,payload,timeout)
c.call=call;c.gw.call=call
c.preflight=lambda records,identity=False:json.loads((records/'context.json').read_text())
c.source=lambda:{'source_sha256':{'offline':'contract'}}
c.protected=lambda:{'unchanged':'protected'}
original_http=c.gw.probe.http
def probe_http(address,path,*args,**kwargs):
 if address=='127.0.0.1':return original_http(address,path,*args,**dict(kwargs,ca=c.pki.PUBLIC))
 s=read();cert=s.get('secret/cnpl-gateway/primary-managed-tls');refs=s['gateway/cnpl-gateway/primary']['spec']['listeners'][1]['tls']['certificateRefs']
 fp=c.public_certificate('primary-managed-tls','cnpl-gateway')['sha256'] if refs[0]['name']=='primary-managed-tls' else 'manual-before'
 pod=s.get('pod/lab-tls/backend');profile=pod['metadata']['labels']['version'] if pod else None;nonce=uuid.uuid4().hex;body=None
 status=404
 if pod and path.startswith('/tls-probe'):
  status=200 if profile=='valid' else 503
  if status==200:body={'uid':pod['metadata']['uid'],'pod':'backend','version':profile,'nonce':nonce,'protocol':'https'}
  else:s['_timer']['count']+=1;write(s)
 return {'status':status,'body':body,'nonce':nonce,'tls_peer_sha256':fp}
c.gw.probe.http=probe_http
@contextlib.contextmanager
def forward(k,pod,ports,evidence,namespace='envoy-gateway-system'):
 profile=read().get('pod/lab-tls/backend',{}).get('metadata',{}).get('labels',{}).get('version')
 class Handler(http.server.BaseHTTPRequestHandler):
  def log_message(self,*a):pass
  def do_GET(self):
   self.send_response(200);self.end_headers()
   if namespace=='lab-tls':
    p=read()['pod/lab-tls/backend'];data=json.dumps({'nonce':self.headers.get('X-Cnpl-Nonce'),'uid':p['metadata']['uid'],'pod':'backend','version':profile,'protocol':'https'}).encode()
   else:data=('envoy_cluster_ssl_fail_verify_error '+str(read()['_timer']['count'])+'\n').encode()
   self.wfile.write(data)
 server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
 if namespace=='lab-tls':
  item=c.materials(W/'records')['profiles'][profile];ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(item['fullchain'],item['private_key']);server.socket=ctx.wrap_socket(server.socket,server_side=True)
 worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
 try:yield {ports[0]:server.server_port}
 finally:server.shutdown();worker.join(5);server.server_close();pathlib.Path(evidence).write_text('OFFLINE short-lived local TLS/metrics server only\n')
c.gw.probe.forwarded=forward
if sys.argv[1]=='main-tls' and not (W/'checkpoint').exists():
 import shutil
 checkpoint=W/'checkpoint';checkpoint.mkdir()
 shutil.copytree(W/'records',checkpoint/'records')
 shutil.copy2(W/'store.json',checkpoint/'store.json')
 shutil.copy2(W/'components.json',checkpoint/'components.json')
if SCENARIO=='failure' and sys.argv[1]=='rotation':raise SystemExit('deliberate offline failure after managed certificate switch')
c.main()
'''.replace('PUBLIC_ROOT', repr(str(public_root))).replace('SCENARIO', repr(scenario)))
extra = {'tls_root': str(ROOT), 'tls_mode': 'all', 'tls_records': str(records), 'tls_python': str(python), 'tls_check': str(work / 'check.py'), 'tls_kubectl': str(work / 'kubectl'), 'tls_helm': str(work / 'helm'), 'tls_wait_retries': 0}
put('extra.json', json.dumps(extra))
prepare = yaml.safe_load((ROOT / 'ops/02-networking/ansible/playbooks/certificates-prepare.yml').read_text())[0]
prepare['vars_files'] = [str(ROOT / 'ops/02-networking/ansible/vars/certificates.yml')]
prepare['tasks'] = [t for t in prepare['tasks'] if t['name'] != '限定批次模式和记录路径']
for task in prepare['tasks']:
    if task['name'] == '核对五个 cert-manager 镜像和既有后端镜像摘要':
        task['ansible.builtin.command']['argv'][0] = str(work / 'crane')
driver = [prepare] + [{'ansible.builtin.import_playbook': str(ROOT / ('ops/02-networking/ansible/playbooks/certificates-' + n + '.yml'))} for n in ['install', 'rotation', 'faults', 'public', 'finish']]


def absolute(value):
    if isinstance(value, list):
        return [absolute(v) for v in value]
    if isinstance(value, dict):
        return {k: absolute(v) for k, v in value.items()}
    if isinstance(value, str) and value.startswith('../../networking/'):
        return str(ROOT / 'ops/02-networking/networking') + '/' + value.removeprefix('../../networking/')
    return value


put('driver.yml', yaml.safe_dump(absolute(driver), sort_keys=False))
put('inventory.yml', yaml.safe_dump({'all': {'hosts': {'localhost': {'ansible_connection': 'local', 'ansible_python_interpreter': str(python)}}}}))
env = dict(os.environ, ANSIBLE_CONFIG=str(ROOT / 'ops/00-preparation/ansible/ansible.cfg'))
with (work / 'ansible.txt').open('w') as log:
    result = subprocess.run([str(python.parent / 'ansible-playbook'), str(work / 'driver.yml'), '-i', str(work / 'inventory.yml'), '-e', '@' + str(work / 'extra.json')], stdout=log, stderr=subprocess.STDOUT, env=env)
state = json.loads((work / 'store.json').read_text())
gateway = state['gateway/cnpl-gateway/primary']
expected_ref = 'primary-managed-tls' if scenario == 'success' else context['gateway_original_refs'][0]['name']
cert = state.get('certificate/cnpl-gateway/primary-auto', {})
passed = (result.returncode == 0 if scenario == 'success' else result.returncode != 0) and gateway['spec']['listeners'][1]['tls']['certificateRefs'][0]['name'] == expected_ref and cert.get('spec', {}).get('duration') == '168h'
report = {'scenario': scenario, 'harness_passed': passed, 'ansible_rc': result.returncode, 'gateway_certificate_ref': gateway['spec']['listeners'][1]['tls']['certificateRefs'][0]['name'], 'stable_duration': cert.get('spec', {}).get('duration'), 'work': str(work), 'kubernetes_gateway_and_clock_are_stubs': True, 'python_and_go_negative_tls_handshakes_are_real_local': True}
put('report.json', json.dumps(report, indent=2))
print(json.dumps(report))
print('\n'.join((work / 'ansible.txt').read_text().splitlines()[-24:]))
sys.exit(0 if passed else 1)
