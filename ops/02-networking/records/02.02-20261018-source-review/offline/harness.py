import json, os, pathlib, subprocess, sys, tempfile
import yaml
root=pathlib.Path('/Users/mario/SelfProject/cloud-native-platform-lab')
work=pathlib.Path(tempfile.mkdtemp(prefix='cnpl-services-offline-'))
python=pathlib.Path.home()/'.venvs/cnpl-ansible/bin/python'

def put(name, value, executable=False):
    path=work/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(value)
    if executable:path.chmod(0o700)
    return str(path)

put('store.json','{}')
put('stub.py',f'''#!{python}
import json,os,pathlib,sys,uuid
import yaml
W=pathlib.Path({str(work)!r}); file=W/'store.json'; state=json.loads(file.read_text()); a=sys.argv[1:]; binary=pathlib.Path(sys.argv[0]).name
if binary=='helm': print('offline Helm contract only');sys.exit(0)
if binary=='firewall-cmd':
    key='fw/'+os.environ['MOCK_HOST']+('/p/' if '--permanent' in a else '/r/')+next(x.split('=',1)[1] for x in a if x.startswith('--query-rich-rule='))
    sys.exit(0 if state.get(key,False) else 1)
if '--request-timeout=20s' in a:a=a[a.index('--request-timeout=20s')+1:]
mode=a[0]
if mode=='wait': print('offline established');sys.exit(0)
if mode=='apply':
    obj=json.loads(sys.stdin.read()); m=obj['metadata']; key=obj['kind'].lower()+'/'+m.get('namespace','')+'/'+m['name']; obj['metadata']['uid']=state.get(key,{{}}).get('metadata',{{}}).get('uid',str(uuid.uuid4()))
    if '--dry-run=server' not in a:state[key]=obj
    file.write_text(json.dumps(state));print(json.dumps(obj));sys.exit(0)
if mode=='patch': print('offline patch');sys.exit(0)
ns=a[a.index('-n')+1] if '-n' in a else '';key=a[1]+'/'+ns+'/'+a[2]
if mode=='get':print(json.dumps(state[key]) if key in state else '');sys.exit(0)
if mode=='delete':
    if a[1]=='namespace':
        for item in list(state):
            if item==key or item.split('/')[1:2]==[a[2]]:state.pop(item)
    else:state.pop(key,None)
    file.write_text(json.dumps(state));print('offline deleted');sys.exit(0)
raise SystemExit('unexpected command '+str(a))
''',True)
for name in ['kubectl','helm','firewall-cmd']:(work/name).symlink_to(work/'stub.py')
for name in ['worker01','worker02']:
    put('python-'+name, '#!/bin/sh\nMOCK_HOST='+name+' exec '+str(python)+' "$@"\n',True)
put('inventory.yml',yaml.safe_dump({'all':{'hosts':{'localhost':{'ansible_connection':'local','ansible_python_interpreter':str(python)},**{h:{'ansible_connection':'local','ansible_python_interpreter':str(work/('python-'+h))} for h in ['worker01','worker02']}}}}))
put('collections/ansible_collections/ansible/posix/plugins/modules/firewalld.py',f'''
from ansible.module_utils.basic import AnsibleModule
import json,os,pathlib
m=AnsibleModule(argument_spec={{'zone':{{'type':'str'}},'rich_rule':{{'type':'str'}},'state':{{'type':'str'}},'permanent':{{'type':'bool'}},'immediate':{{'type':'bool'}}}})
p=pathlib.Path({str(work/'store.json')!r}); state=json.loads(p.read_text()); arg=m.params
for suffix in (['p'] if arg['permanent'] else [])+(['r'] if arg['immediate'] else []):state['fw/'+os.environ['MOCK_HOST']+'/'+suffix+'/'+arg['rich_rule']]=arg['state']=='enabled'
p.write_text(json.dumps(state));m.exit_json(changed=True)
''')
put('check.py',f'''#!{python}
import argparse,importlib.util,json,pathlib,sys
p=argparse.ArgumentParser();p.add_argument('mode')
for key in ['records','output','attempt','kind','name','namespace']:p.add_argument('--'+key)
a=p.parse_args();records=pathlib.Path(a.records);context=json.loads((records/'context.json').read_text());value={{'passed':True,'offline_contract_only':True}}
if a.mode=='nodeport-plan':value={{'rules':['rule family="ipv4" source address="192.168.9.200/32" port port="'+str(port)+'" protocol="tcp" accept' for port in [31111,31112]]}}
elif a.mode=='firewall-restore':
    s=importlib.util.spec_from_file_location('check',{str(root/'ops/02-networking/tests/integration/services/check.py')!r});c=importlib.util.module_from_spec(s);s.loader.exec_module(c);value=c.firewall_restore(records,context,a.name)
elif a.mode=='delete-plan':value={{'exists':True}}
elif a.mode=='cleanup-plan':value={{'namespace_exists':True}}
elif a.mode=='manual':value={{'service_uid':'11111111-1111-1111-1111-111111111111','pod':'p','pod_uid':'22222222-2222-2222-2222-222222222222','pod_ip':'10.244.9.4'}}
elif a.mode=='loadbalancer':value.update(vip='192.168.9.202',service_uid=a.name)
path=pathlib.Path(a.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value));print(json.dumps(value))
''',True)
records=work/'records';attempt=records/'attempts/offline';attempt.mkdir(parents=True);(records/'state').mkdir()
context={'run':'offline-rehearsal','cluster_uid':'offline-cluster','mac_ip':'192.168.9.200','metallb':{'install':True}}
(records/'context.json').write_text(json.dumps(context))
variables={'services_mode':'all','services_root':str(root),'services_records':str(records),'services_attempt':str(attempt),'services_run':context['run'],'services_context':context,'services_python':str(python),'services_check':str(work/'check.py'),'services_kubectl':str(work/'kubectl'),'services_helm':str(work/'helm'),'services_progress':str(work/'components'),'services_image':{'image':'offline.invalid/diag@sha256:'+'a'*64},'services_manual':{'pod':'preview','pod_ip':'10.244.9.2','pod_uid':'22222222-2222-2222-2222-222222222222','service_uid':'11111111-1111-1111-1111-111111111111'}}
(work/'components').mkdir()
put('extra.json',json.dumps(variables))
playbooks=root/'ops/02-networking/ansible/playbooks';tasks=root/'ops/02-networking/ansible/tasks'
bootstrap=[{'name':'OFFLINE ONLY - render and seed isolated state','hosts':'localhost','connection':'local','gather_facts':False,'vars_files':[str(root/'ops/02-networking/ansible/vars/services.yml')],'tasks':[{'name':'render all templates','ansible.builtin.template':{'src':str(root/'ops/02-networking/networking')+'/{{ item }}.j2','dest':'{{ services_attempt }}/{{ item | basename }}'},'loop':['services/suite-fixtures.yaml','services/nodeport.yaml','services/loadbalancer.yaml','services/discovery.yaml','services/manual-endpoints.yaml','services/late-service.yaml','metallb/test-pool.yaml','metallb/namespace.yaml']},{'name':'seed base objects','ansible.builtin.include_tasks':str(tasks/'services-apply.yml'),'vars':{'services_manifest':'{{ services_attempt }}/suite-fixtures.yaml'}}]}]
for name in ['nodeport','loadbalancer','discovery','externalname','dns','finish']:bootstrap.append({'ansible.builtin.import_playbook':str(playbooks/('services-'+name+'.yml'))})
put('rehearsal.yml',yaml.safe_dump(bootstrap,sort_keys=False))
env=dict(os.environ,PATH=str(work)+':'+os.environ['PATH'],ANSIBLE_CONFIG=str(root/'ops/00-preparation/ansible/ansible.cfg'),ANSIBLE_COLLECTIONS_PATH=str(work/'collections'))
with (work/'ansible.log').open('w') as log: result=subprocess.run([str(python.parent/'ansible-playbook'),str(work/'rehearsal.yml'),'-i',str(work/'inventory.yml'),'-e','@'+str(work/'extra.json')],env=env,stdout=log,stderr=subprocess.STDOUT)
print(json.dumps({'rc':result.returncode,'work':str(work),'evidence':'offline command/module stubs; no cluster or VM mutations'},ensure_ascii=False))
print('\n'.join((work/'ansible.log').read_text().splitlines()[-32:]))
sys.exit(result.returncode)
