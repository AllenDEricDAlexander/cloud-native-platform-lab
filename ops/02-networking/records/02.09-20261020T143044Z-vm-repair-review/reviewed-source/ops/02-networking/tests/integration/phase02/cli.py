"""固定模板编排：预检→计划→Ansible 命令→证据→always 恢复。"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import runtime as r


def main(driver):
    p = argparse.ArgumentParser()
    p.add_argument('action')
    p.add_argument('--records', type=Path, required=True)
    p.add_argument('--attempt', type=Path, required=True)
    p.add_argument('--mode', choices=['all','validate','recover','cleanup'], required=True)
    p.add_argument('--case')
    p.add_argument('--input', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    s = getattr(driver, 'Session', r.Session)(driver.TOPIC, driver.STAGE, args.records, args.attempt, driver.NAMESPACES)
    s.mode = args.mode
    action = args.action
    if action == 'prepare':
        s.prepare(args.mode)
        if args.mode in ['all','validate']:
            driver.prepare(s)
            s.bind_sources(args.mode)
        value = {'context': s.context, 'steps': driver.steps(s), 'restore_steps': getattr(driver, 'RESTORE_STEPS', [])}
    elif action == 'validate':
        value = driver.validate(s) if hasattr(driver, 'validate') else s.validate()
    elif action == 'plan':
        step = next(step for step in driver.steps(s) + getattr(driver, 'RESTORE_STEPS', []) if step['name'] == args.case)
        value = {'commands': s.apply(step['file']) if step.get('file') else driver.plan(s, args.case)}
    elif action == 'record':
        s.record(json.loads(args.input.read_text()).get('results', []))
        value = {'recorded': True}
    elif action == 'observe':
        value = driver.observe(s,args.case) if args.case in getattr(driver,'FAST_CASES',[]) else s.wait(args.case, lambda: driver.observe(s, args.case), seconds=getattr(driver, 'WAIT_SECONDS', 120))
    elif action == 'cleanup-plan':
        value = {'commands': driver.restore(s) + s.cleanup()}
    elif action == 'accept':
        names = [step['name'] for step in driver.steps(s) if step.get('check', True)]
        value = s.accept(names, getattr(driver, 'BLOCKED', None))
    elif action == 'final':
        if hasattr(driver, 'final'):
            driver.final(s)
        value = s.final()
        if hasattr(driver,'post_final'):
            driver.post_final(s,value)
    else:
        raise ValueError('未知动作')
    r.save(args.output, value)
    print(json.dumps(value, ensure_ascii=False))


def run(driver):
    try:
        main(driver)
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as error:
        sys.exit(str(error))
