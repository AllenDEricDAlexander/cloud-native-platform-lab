#!/usr/bin/env python3
"""逐专题调用独立入口；只有前一步真实接受且清理成功才继续。"""
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import sys
import uuid
import runtime as r

STEPS=[('02.06','policies'),('02.07','scheduling'),('02.08','resource-governance'),('02.09','dataplane'),('02.10','mesh')]


def main():
    mode,folder=sys.argv[1:]
    records=Path(folder).resolve()
    r.require(mode in ['all','validate'],'整批入口只支持 all/validate；恢复请使用对应专题原目录')
    r.require(mode!='all' or sys.platform!='darwin','当前整批包含尚未交付 VM 版的 02.10；禁止在 Mac 使用旧 kind 后端。请分别运行已交付的 VM 专题。')
    r.require(records.parent==r.PHASE/'records' and records.name.startswith('batch-02.06-10-'),'整批目录越界')
    r.require(not (records/'plan.json').exists(),'整批目录已使用，请换新目录，原证据保留')
    records.mkdir(parents=True,exist_ok=True)
    key=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    plan=[{'stage':stage,'topic':topic,'records':str(r.PHASE/'records'/(stage+'-'+key))} for stage,topic in STEPS]
    r.save(records/'plan.json',{'mode':mode,'steps':plan})
    results=[]
    for step in plan:
        print('\n=== '+step['stage']+' '+step['topic']+' ===',flush=True)
        args=['bash',str(r.PHASE/'scripts'/(step['topic']+'.sh')),mode,step['records']]
        outcome=subprocess.run(args,cwd=r.ROOT)
        row={**step,'exit_code':outcome.returncode};results.append(row)
        if outcome.returncode:
            r.save(records/'result.json',{'completed':False,'results':results,'failed_stage':step['stage']})
            print('整批已停止；先处理该专题原始日志。恢复入口：bash '+str(r.PHASE/'scripts'/(step['topic']+'.sh'))+' recover '+step['records'],file=sys.stderr)
            return outcome.returncode
        if mode=='all':
            directory=Path(step['records'])
            passed=json.loads((directory/'passed.json').read_text());closed=json.loads((directory/'state/closed.json').read_text())
            r.require((passed.get('available_cases_passed') or passed.get('passed')) and closed['cleanup_passed']
                and passed['cluster_uid']==closed['cluster_uid'] and passed['run']==closed['run'],'未接受或未清理，整批停止')
            row['available_cases_passed']=True;row['cleanup_passed']=True
            row['phase_complete']=passed.get('phase_complete',False)
        r.save(records/'result.json',{'completed':False,'results':results})
    r.save(records/'result.json',{'completed':True,'mode':mode,'runtime_executed':mode=='all','phase02_complete':False,'results':results})
    print('\n五个专题已按顺序完成 '+mode+'；完整回执：'+str(records/'result.json'),flush=True)
    return 0


if __name__=='__main__':
    try:
        sys.exit(main())
    except (ValueError,KeyError,OSError) as error:
        sys.exit(str(error))
