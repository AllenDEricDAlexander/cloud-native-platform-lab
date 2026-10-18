#!/usr/bin/env python3
"""仅供有限离线 Ansible 集成测试的本地 API 替身；从不连接集群。"""
import importlib.util
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import yaml

ROOT=Path(__file__).resolve().parents[1]
DB=Path(os.environ['CNPL_REPLAY_TEST_DB']).resolve()
if not DB.parent.name.startswith('cnpl-replay-test-') or DB.parent.parent != Path(tempfile.gettempdir()).resolve():
    raise SystemExit('test fixture requires isolated temporary directory')


def api(args):
    data=json.loads(DB.read_text()) if DB.exists() else {}
    if os.environ.get('CNPL_REPLAY_TEST_CALLS'):
        with Path(os.environ['CNPL_REPLAY_TEST_CALLS']).open('a') as stream:stream.write(json.dumps(args)+'\n')
    if args[:1]==['-n']:args=args[2:]
    verb=args[0]
    if verb in ['create','apply']:
        value=yaml.safe_load(Path(args[args.index('-f')+1]).read_text());key=value['kind'].lower()+'/'+value['metadata']['name']
        if '--dry-run=client' in args:return 'client schema accepted'
        if verb=='create' and key in data:raise ValueError('AlreadyExists: '+key)
        if value.get('spec',{}).get('replicas',0)<0:raise ValueError('Invalid replicas')
        if verb=='apply' and key in data and value['kind']=='Pod':
            before=copy.deepcopy(data[key]['spec']);after=copy.deepcopy(value['spec'])
            for spec in [before,after]:
                for container in spec.get('containers',[]):container.pop('image',None)
            if before!=after:raise ValueError('Pod spec is immutable')
        if '--dry-run=server' in args:return 'server admission accepted'
        value['metadata']['uid']=data.get(key,{}).get('metadata',{}).get('uid','fixture-'+value['metadata']['name'])
        value['status']={'phase':'Succeeded'};data[key]=value
    elif verb=='get':
        kind=args[1].lower();name=args[2] if len(args)>2 and not args[2].startswith('-') else None
        if '/' in kind:kind,name=kind.split('/',1)
        if 'jsonpath={.status.phase}' in args:return data[kind+'/'+name]['status']['phase']
        if kind=='events':return json.dumps({'items':[]})
        if name:
            value=data.get(kind+'/'+name)
            if value is None:
                if '--ignore-not-found' in args:return ''
                raise ValueError('not found')
            return json.dumps(value)
        selector=args[args.index('-l')+1] if '-l' in args else ''
        items=[o for o in data.values() if all(o['metadata'].get('labels',{}).get(p.split('=')[0])==p.split('=')[1] for p in selector.split(',') if p)]
        return json.dumps({'items':items})
    elif verb=='logs':return 'fixture log'
    elif verb=='patch':
        key=args[1].lower()+'/'+args[2];patch=json.loads(args[args.index('-p')+1]);data[key]['metadata'].update(patch['metadata'])
    elif verb=='delete':data.pop(args[1].lower()+'/'+args[2],None)
    else:raise ValueError('unsupported fixture command: '+str(args))
    DB.write_text(json.dumps(data));return verb+' fixture'


if __name__=='__main__':
    if sys.argv[1] in ['check','cleanup-plan','snapshot','empty','graph','term','owner-pods','endpoints']:
        spec=importlib.util.spec_from_file_location('check',ROOT/'checks/lab-check.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        class FixtureReader(m.Reader):
            def k(self,*parts,admin=False):return api(list(parts))
        m.Reader=FixtureReader
        if sys.argv[1]=='check':sys.argv.pop(1)
        m.main()
    else:print(api(sys.argv[1:]))
