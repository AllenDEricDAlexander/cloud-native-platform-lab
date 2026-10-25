
import argparse,json,os,sys,yaml
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('action');p.add_argument('--records');p.add_argument('--attempt');p.add_argument('--case');p.add_argument('--manifest');p.add_argument('--output',required=True);a=p.parse_args()
out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
if a.action in ['preflight','identity']:
 value={'stage':'02.06','cluster_uid':'offline-cluster','run':'offline-unique-run'}
elif a.action in ['firewall-plan','firewall-cleanup-plan']:
 state=Path(os.environ['CNPL_MODEL_FIREWALL_STATE']);present=set(json.loads(state.read_text())) if state.exists() else set()
 rules=['model-http-rule','model-dns-rule']
 if a.action=='firewall-plan':
  plan=Path(a.records)/'state/l7-firewall.json';plan.parent.mkdir(parents=True,exist_ok=True);plan.write_text(json.dumps({'rules':rules}))
  verb='firewall-add'
 else:
  rules=[r for r in rules if r in present];verb='firewall-remove'
 value={'objects':[{'rule':rule,'argv':[sys.executable,os.environ['CNPL_MODEL_KUBECTL'],verb,rule]} for rule in rules]}
elif a.action in ['firewall-verify','firewall-restored']:
 state=Path(os.environ['CNPL_MODEL_FIREWALL_STATE']);present=set(json.loads(state.read_text())) if state.exists() else set()
 assert present==({'model-http-rule','model-dns-rule'} if a.action=='firewall-verify' else set()),present
 value={'passed':True}
elif a.action=='cleanup-plan':
 rows=[]
 for ns in ['lab-policy','lab-policy-peer','lab-egress']:
  body=out.parent/('delete-'+ns+'.json');body.write_text(json.dumps({'apiVersion':'v1','kind':'DeleteOptions','preconditions':{'uid':'offline-'+ns}}));rows.append({'url':'/api/v1/namespaces/'+ns,'body':str(body),'key':'Namespace//'+ns})
 value={'objects':rows}
elif a.action=='delete-plan':
 rows=[]
 for obj in yaml.safe_load_all(Path(a.manifest).read_text()):
  if not obj:continue
  m=obj['metadata'];key=obj['kind']+'/'+m['namespace']+'/'+m['name']
  body=out.parent/('delete-'+m['name']+'.json');body.write_text(json.dumps({'apiVersion':'v1','kind':'DeleteOptions','preconditions':{'uid':'offline-'+m['name']}}))
  group='networking.k8s.io/v1' if obj['kind']=='NetworkPolicy' else 'cilium.io/v2'
  resource='networkpolicies' if obj['kind']=='NetworkPolicy' else 'ciliumnetworkpolicies'
  rows.append({'url':'/apis/'+group+'/namespaces/'+m['namespace']+'/'+resource+'/'+m['name'],'body':str(body),'key':key})
 value={'objects':rows}
elif a.action=='matrix' and a.case=='cilium' and os.getenv('CNPL_MODEL_FAILURE')=='yes':
 sys.exit('injected Cilium observation failure')
elif a.action=='final':
 value={'cleanup_passed':True,'phase_complete':False}
elif a.action in ['source','protected']:
 value={}
else:
 value={'passed':True,'status':'BLOCKED' if a.action=='blocked' else 'MODEL'}
out.write_text(json.dumps(value));print(json.dumps(value))
