#!/usr/bin/env python3
"""运行真实 Ansible 编排；只将命令路径替换为本地模型，绝不接触集群。

覆盖正常整组、Cilium 对照失败、即时规则只添加一部分后的 always 清理、显式 recover。
模型不证明 Cilium 的数据面行为；真实数据面验收仍由操作者的 all 完成。
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import textwrap

ROOT = Path(__file__).resolve().parents[5]
PHASE = ROOT / 'ops/02-networking'
PYTHON = Path.home() / '.venvs/cnpl-ansible/bin/python'

CHECK = r'''
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
'''

KUBECTL = r'''
import json,os,sys
from pathlib import Path
args=sys.argv[1:]
with open(os.environ['CNPL_MODEL_CALLS'],'a') as f:f.write(json.dumps(args)+'\n')
if 'apply' in args:
 path=args[args.index('-f')+1];obj=json.loads(Path(path).read_text());obj['metadata']['uid']='offline-'+obj['metadata']['name'];print(json.dumps(obj))
elif 'delete' in args:
 body=json.loads(Path(args[args.index('-f')+1]).read_text());assert body['preconditions']['uid'].startswith('offline-');print('{}')
elif 'wait' in args:print('deleted')
elif args[0] in ['firewall-add','firewall-remove']:
 state=Path(os.environ['CNPL_MODEL_FIREWALL_STATE']);present=set(json.loads(state.read_text())) if state.exists() else set()
 if args[0]=='firewall-add':
  if os.getenv('CNPL_MODEL_FIREWALL_FAILURE')=='yes' and args[1]=='model-dns-rule':sys.exit('injected partial firewall failure')
  present.add(args[1])
 else:present.discard(args[1])
 state.write_text(json.dumps(sorted(present)));print('success')
else:raise SystemExit('unexpected mocked kubectl command')
'''


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--records', type=Path, required=True)
    args = p.parse_args()
    records = args.records.resolve()
    if not records.is_relative_to(PHASE / 'records') or not records.name.startswith('02.06-'):
        raise ValueError('离线记录目录越界')
    model = records / 'offline'
    model.mkdir(parents=True, exist_ok=True)
    checker, kubectl = model / 'check-model.py', model / 'kubectl-model.py'
    checker.write_text(textwrap.dedent(CHECK))
    kubectl.write_text(textwrap.dedent(KUBECTL))
    results = {}
    for name, mode, failure in [('success', 'all', False), ('failure', 'all', True),
                                ('partial-firewall', 'all', True), ('recover', 'recover', False)]:
        folder = model / ('model-' + name)
        folder.mkdir(exist_ok=True)
        calls, log = folder / 'calls.jsonl', folder / 'ansible.txt'
        calls.write_text('')
        firewall_state = folder / 'host-firewall-model.json'
        firewall_state.write_text(json.dumps(['model-http-rule', 'model-dns-rule'] if mode == 'recover' else []))
        variables = {'pol_mode': mode, 'pol_records': str(folder), 'pol_check': str(checker),
            'pol_materials': str(checker), 'pol_k': [str(PYTHON), str(kubectl)]}
        varfile = folder / 'vars.json'
        varfile.write_text(json.dumps(variables))
        env = dict(os.environ, ANSIBLE_CONFIG=str(ROOT / 'ops/00-preparation/ansible/ansible.cfg'),
            CNPL_MODEL_CALLS=str(calls), CNPL_MODEL_FAILURE='yes' if name == 'failure' else 'no',
            CNPL_MODEL_FIREWALL_FAILURE='yes' if name == 'partial-firewall' else 'no',
            CNPL_MODEL_FIREWALL_STATE=str(firewall_state), CNPL_MODEL_KUBECTL=str(kubectl))
        with log.open('w') as output:
            run = subprocess.run([str(Path.home() / '.venvs/cnpl-ansible/bin/ansible-playbook'),
                str(PHASE / 'ansible/playbooks/policies.yml'), '-e', '@' + str(varfile)], env=env,
                stdout=output, stderr=subprocess.STDOUT, timeout=180)
        text = log.read_text()
        commands = [json.loads(line) for line in calls.read_text().splitlines()]
        closed = json.loads((folder / 'state/closed.json').read_text())
        deletes = [v for v in commands if 'delete' in v and '--raw' in v and v[v.index('--raw') + 1].startswith('/api/v1/namespaces/')]
        assert closed['cleanup_passed'] and len(deletes) == 3, name + ': missing cleanup'
        assert (run.returncode != 0 if failure else run.returncode == 0), name + ': unexpected exit'
        assert not any('CiliumEgressGatewayPolicy' in json.dumps(v) for v in commands), 'reference applied'
        assert json.loads(firewall_state.read_text()) == [], name + ': leaked temporary firewall rules'
        removed = [v[1] for v in commands if v[0] == 'firewall-remove']
        assert set(removed) == ({'model-http-rule'} if name == 'partial-firewall' else {'model-http-rule', 'model-dns-rule'}), name + ': wrong firewall removal scope'
        if failure:
            assert ('injected partial firewall failure' if name == 'partial-firewall' else 'injected Cilium observation failure') in text
            assert not (folder / 'passed.json').exists()
        if name == 'success':
            assert (folder / 'passed.json').exists()
            assert all((next((folder / 'attempts').iterdir()) / (case + '.json')).exists()
                for case in ['denied', 'standard', 'cilium', 'egress', 'proxy-unreachable', 'proxy-restored', 'egress-gateway'])
            policy_deletes = [v for v in commands if 'delete' in v and '--raw' in v and v[v.index('--raw') + 1].startswith('/apis/')]
            policy_waits = [v for v in commands if 'wait' in v and '-n' in v]
            assert len(policy_deletes) == len(policy_waits) == 8, 'missing standard/fault policy delete and wait'
        results[name] = {'passed': True, 'ansible_exit': run.returncode, 'namespace_uid_deletes': len(deletes),
            'cleanup_passed': closed['cleanup_passed'], 'firewall_rules_removed': len(removed),
            'recap': text.split('PLAY RECAP')[-1].strip()}
    (model / 'results.json').write_text(json.dumps({'scope': 'Ansible orchestration model only', 'results': results}, indent=2) + '\n')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
