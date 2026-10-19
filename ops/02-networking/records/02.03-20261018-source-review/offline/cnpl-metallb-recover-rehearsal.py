from pathlib import Path
import copy,json,os,subprocess,tempfile
import yaml
root=Path('/Users/mario/SelfProject/cloud-native-platform-lab');python=Path.home()/'.venvs/cnpl-ansible/bin/python'
work=sorted(Path(tempfile.gettempdir()).glob('cnpl-metallb-failure-*'),key=lambda p:p.stat().st_mtime)[-1]
records=work/'records';context=json.loads((records/'context.json').read_text());context['primary_preexisting']={'IPAddressPool':False,'L2Advertisement':False};(records/'context.json').write_text(json.dumps(context));original=context['speaker_original']
plan=json.loads((records/'state/fault-plan.json').read_text())
result=subprocess.run([str(work/'kubectl'),'--request-timeout=20s','patch','daemonset','cnpl-metallb-speaker','-n','metallb-system','--type=json','-p',json.dumps(plan['patch'])],capture_output=True,text=True);assert result.returncode==0,result.stderr
orphan_attempt=records/'attempts/orphan';orphan_attempt.mkdir(exist_ok=True)
env=dict(os.environ,PATH=str(work)+':'+os.environ['PATH'],ANSIBLE_CONFIG=str(root/'ops/00-preparation/ansible/ansible.cfg'))
orphan_log=(work/'orphan.txt').open('w');orphan=subprocess.Popen([str(python),str(work/'check.py'),'observe','--records',str(records),'--attempt',str(orphan_attempt),'--output',str(orphan_attempt/'observer.json')],stdout=orphan_log,stderr=subprocess.STDOUT,env=env)
reports=[]
for scenario in ['recover','partial']:
 if scenario=='partial':
  state=json.loads((work/'store.json').read_text());state.pop('l2advertisement/metallb-system/cnpl-primary');(work/'store.json').write_text(json.dumps(state));(work/'components/primary.json').unlink()
 attempt=records/('attempts/'+scenario);attempt.mkdir(exist_ok=True)
 extra=json.loads((work/'extra.json').read_text());extra.update(metallb_mode='recover',metallb_context=context,metallb_attempt=str(attempt));(work/('extra-'+scenario+'.json')).write_text(json.dumps(extra))
 (work/('driver-'+scenario+'.yml')).write_text(yaml.safe_dump([{'ansible.builtin.import_playbook':str(root/'ops/02-networking/ansible/playbooks/metallb-finish.yml')}]))
 with (work/(scenario+'.txt')).open('w') as f:outcome=subprocess.run([str(python.parent/'ansible-playbook'),str(work/('driver-'+scenario+'.yml')),'-i',str(work/'inventory.yml'),'-e','@'+str(work/('extra-'+scenario+'.json'))],stdout=f,stderr=subprocess.STDOUT,env=env)
 state=json.loads((work/'store.json').read_text());daemon=state['daemonset/metallb-system/cnpl-metallb-speaker'];restored=daemon['spec']==original['spec'] and daemon['status']['numberReady']==2
 if scenario=='recover':orphan.wait(timeout=10);orphan_log.close()
 stopped=json.loads((orphan_attempt/'monitor-summary.json').read_text())['stopped_by_controller'];primary_present='ipaddresspool/metallb-system/cnpl-primary' in state
 passed=outcome.returncode==0 and restored and stopped and primary_present==(scenario=='recover')
 report={'scenario':scenario,'harness_passed':passed,'ansible_rc':outcome.returncode,'speaker_spec_restored':restored,'orphan_observer_stopped':stopped,'primary_pool_retained':primary_present,'work':str(work),'network_and_kubernetes_are_stubs':True}
 (work/(scenario+'-report.json')).write_text(json.dumps(report,indent=2));reports.append(report)
 print(json.dumps(report));print('\n'.join((work/(scenario+'.txt')).read_text().splitlines()[-10:]))
 if not passed:raise SystemExit(1)
