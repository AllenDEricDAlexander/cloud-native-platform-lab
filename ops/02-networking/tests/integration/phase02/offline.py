#!/usr/bin/env python3
"""真实 Ansible 的正常/失败/恢复分支模型；从不使用真实 kubectl 或 Docker。"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import yaml
import runtime as r
import summary

MODEL = r'''
import argparse,json,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('action');p.add_argument('--records');p.add_argument('--attempt');p.add_argument('--mode');p.add_argument('--case');p.add_argument('--input');p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
scope=Path(__file__).parent;settings=json.loads((scope/'settings.json').read_text());value={'passed':True}
if a.action=='prepare':
 value={'context':{'stage':settings['stage'],'run':'model'},'steps':settings['steps'],'restore_steps':settings.get('restore_steps',[])}
 (Path(a.records)/'context.json').write_text(json.dumps(value['context']))
elif a.action=='validate' and settings.get('validation_fail'):
 sys.exit('EXPECTED_MODEL_VALIDATION_FAILURE')
elif a.action=='plan':
 command=[sys.executable,'-c','import sys;print("{}");sys.exit(1)' if a.case=='model-rejection' else 'print("{}")']
 value={'commands':[{'argv':command,'allowed_rc':[1] if a.case=='model-rejection' else [0],'key':None}]}
 if a.case=='recover-firewall':
  value={'commands':[{'argv':[sys.executable,'-c','from pathlib import Path;Path('+repr(str(Path(a.records)/'firewall-restored'))+').touch();print("{}")'],'allowed_rc':[0],'key':None}]}
 if a.case==settings.get('command_fail'):
  value={'commands':[{'argv':[sys.executable,'-c','import sys;sys.exit(2)'],'allowed_rc':[0],'key':None},
    {'argv':[sys.executable,'-c','from pathlib import Path;Path('+repr(str(Path(a.records)/'must-not-run'))+').touch()'],'allowed_rc':[0],'key':None}]}
elif a.action=='record':
 data=json.loads(Path(a.input).read_text())
 assert all('phase_command' in v for v in data.get('results',[]))
elif a.action=='observe' and a.case in settings.get('fail_cases',[]):
 sys.exit('EXPECTED_MODEL_OBSERVE_FAILURE')
elif a.action=='cleanup-plan':
 marker=Path(a.records)/'cleaned'
 value={'commands':[{'argv':[sys.executable,'-c','from pathlib import Path;Path('+repr(str(marker))+').touch()'],'allowed_rc':[0],'key':None}]}
elif a.action=='final':
 assert (Path(a.records)/'cleaned').exists();value={'cleanup_passed':True,'run':'model'}
out.write_text(json.dumps(value));print(json.dumps(value))
'''


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--topic',required=True)
    p.add_argument('--records',type=Path,required=True)
    args=p.parse_args()
    records=args.records.resolve()
    require=r.require
    require(records.is_relative_to(r.PHASE/'records'),'模型目录越界')
    cases=yaml.safe_load((r.PHASE/'networking'/args.topic/'cases.yml').read_text())
    restore_file=r.PHASE/'networking'/args.topic/'restore-cases.yml'
    restore_steps=yaml.safe_load(restore_file.read_text()) if restore_file.exists() else []
    cases=cases+[{'name':'model-rejection'}]
    base=records/'offline'/uuid.uuid4().hex[:8]
    base.mkdir(parents=True)
    results={}
    modes=[('normal','all',False),('failure','all',True),('command-failure','all',True),('validation-failure','all',True),('recover','recover',False)]
    if restore_steps:modes += [('rollback-failure','all',True),('double-failure','all',True)]
    for mode_name,mode,failed in modes:
        folder=base/mode_name
        folder.mkdir()
        model=folder/'model.py';model.write_text(MODEL)
        failure_case='l2' if any(v['name']=='l2' for v in cases) else next(v['name'] for v in reversed(cases[:-1]) if v.get('check',True))
        failures=[failure_case] if mode_name in ['failure','double-failure'] else []
        if mode_name in ['rollback-failure','double-failure']:failures.append('recover-cilium')
        command_fail=cases[1]['name'] if mode_name=='command-failure' else None
        (folder/'settings.json').write_text(json.dumps({'steps':cases,'stage':args.topic,'fail_cases':failures,'validation_fail':mode_name=='validation-failure','command_fail':command_fail,'restore_steps':restore_steps}))
        varfile=folder/'vars.json';varfile.write_text(json.dumps({'phase_mode':mode,'phase_records':str(folder),'phase_check':str(model)}))
        log=folder/'ansible.txt'
        env=dict(os.environ,ANSIBLE_CONFIG=str(r.ROOT/'ops/00-preparation/ansible/ansible.cfg'))
        with log.open('w') as stream:
            outcome=subprocess.run([str(Path.home()/'.venvs/cnpl-ansible/bin/ansible-playbook'),
                str(r.PHASE/'ansible/playbooks'/ (args.topic+'.yml')),'-e','@'+str(varfile)],env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=180)
        require(outcome.returncode==(2 if failed else 0),mode_name+' Ansible 返回值异常：'+str(log))
        if mode_name in ['rollback-failure','double-failure','validation-failure']:
            require(not (folder/'state/closed.json').exists(),'回退失败仍发布清理通过')
            require(mode_name=='validation-failure' or (folder/'firewall-restored').exists(),'回退失败未撤销临时入口规则')
        else:
            require(json.loads((folder/'state/closed.json').read_text())['cleanup_passed'],'always 未清理')
            require(not failed or not (folder/'passed.json').exists(),'失败被隐藏成通过')
        require(not (folder/'must-not-run').exists(),'单个命令失败后仍执行了后续命令')
        ending=summary.summarize(log,folder,outcome.returncode,mode)
        if mode_name in ['failure','double-failure']:require(ending['first_failure']['case']==failure_case,'首个失败被回退输出覆盖')
        expected_cleanup='NOT_RUN' if mode_name=='validation-failure' else 'NOT_CONFIRMED' if mode_name in ['rollback-failure','double-failure'] else 'PASS'
        require(ending['cleanup_status']==expected_cleanup,'末尾清理汇总不符')
        r.save(folder/'summary.json',ending)
        results[mode_name]={'passed':True,'exit':outcome.returncode,'cleanup':ending['cleanup_status'],'first_failure':ending['first_failure'],
            'firewall_restored':(folder/'firewall-restored').exists(),'recap':log.read_text().split('PLAY RECAP')[-1].strip(),'log':str(log)}
        print(mode_name+' MODEL PASS',flush=True)
    value={'scope':'Ansible orchestration only','passed':True,'results':results}
    r.save(records/'offline-results.json',value)
    print(json.dumps(value,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
