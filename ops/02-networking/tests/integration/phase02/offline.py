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

MODEL = r'''
import argparse,json,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('action');p.add_argument('--records');p.add_argument('--attempt');p.add_argument('--mode');p.add_argument('--case');p.add_argument('--input');p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
scope=Path(__file__).parent;settings=json.loads((scope/'settings.json').read_text());value={'passed':True}
if a.action=='prepare':
 value={'context':{'stage':settings['stage'],'run':'model'},'steps':settings['steps']}
elif a.action=='plan':
 command=[sys.executable,'-c','import sys;print("{}");sys.exit(1)' if a.case=='model-rejection' else 'print("{}")']
 value={'commands':[{'argv':command,'allowed_rc':[1] if a.case=='model-rejection' else [0],'key':None}]}
 if a.case==settings.get('command_fail'):
  value={'commands':[{'argv':[sys.executable,'-c','import sys;sys.exit(2)'],'allowed_rc':[0],'key':None},
    {'argv':[sys.executable,'-c','from pathlib import Path;Path('+repr(str(Path(a.records)/'must-not-run'))+').touch()'],'allowed_rc':[0],'key':None}]}
elif a.action=='record':
 data=json.loads(Path(a.input).read_text())
 assert all('phase_command' in v for v in data.get('results',[]))
elif a.action=='observe' and a.case==settings.get('fail'):
 sys.exit('EXPECTED_MODEL_OBSERVE_FAILURE')
elif a.action=='cleanup-plan':
 marker=Path(a.records)/'cleaned'
 value={'commands':[{'argv':[sys.executable,'-c','from pathlib import Path;Path('+repr(str(marker))+').touch()'],'allowed_rc':[0],'key':None}]}
elif a.action=='final':
 assert (Path(a.records)/'cleaned').exists();value={'cleanup_passed':True}
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
    cases=cases+[{'name':'model-rejection'}]
    base=records/'offline'/uuid.uuid4().hex[:8]
    base.mkdir(parents=True)
    results={}
    for mode_name,mode,failed in [('normal','all',False),('failure','all',True),('command-failure','all',True),('recover','recover',False)]:
        folder=base/mode_name
        folder.mkdir()
        model=folder/'model.py';model.write_text(MODEL)
        fail=next(v['name'] for v in reversed(cases[:-1]) if v.get('check',True)) if mode_name=='failure' else None
        command_fail=cases[1]['name'] if mode_name=='command-failure' else None
        (folder/'settings.json').write_text(json.dumps({'steps':cases,'stage':args.topic,'fail':fail,'command_fail':command_fail}))
        varfile=folder/'vars.json';varfile.write_text(json.dumps({'phase_mode':mode,'phase_records':str(folder),'phase_check':str(model)}))
        log=folder/'ansible.txt'
        env=dict(os.environ,ANSIBLE_CONFIG=str(r.ROOT/'ops/00-preparation/ansible/ansible.cfg'))
        with log.open('w') as stream:
            outcome=subprocess.run([str(Path.home()/'.venvs/cnpl-ansible/bin/ansible-playbook'),
                str(r.PHASE/'ansible/playbooks'/ (args.topic+'.yml')),'-e','@'+str(varfile)],env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=180)
        require(outcome.returncode==(2 if failed else 0),mode_name+' Ansible 返回值异常：'+str(log))
        require(json.loads((folder/'state/closed.json').read_text())['cleanup_passed'],'always 未清理')
        require(not failed or not (folder/'passed.json').exists(),'失败被隐藏成通过')
        require(not (folder/'must-not-run').exists(),'单个命令失败后仍执行了后续命令')
        results[mode_name]={'passed':True,'exit':outcome.returncode,'cleanup':True,'recap':log.read_text().split('PLAY RECAP')[-1].strip(),'log':str(log)}
    value={'scope':'Ansible orchestration only','passed':True,'results':results}
    r.save(records/'offline-results.json',value)
    print(json.dumps(value,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
