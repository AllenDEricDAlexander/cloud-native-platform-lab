
import argparse,json,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('action');p.add_argument('--records');p.add_argument('--attempt');p.add_argument('--mode');p.add_argument('--case');p.add_argument('--input');p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
scope=Path(__file__).parent;settings=json.loads((scope/'settings.json').read_text());value={'passed':True}
if a.action=='prepare':
 value={'context':{'stage':settings['stage'],'run':'model'},'steps':settings['steps'],'restore_steps':settings.get('restore_steps',[])}
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
elif a.action=='observe' and a.case==settings.get('fail'):
 sys.exit('EXPECTED_MODEL_OBSERVE_FAILURE')
elif a.action=='cleanup-plan':
 marker=Path(a.records)/'cleaned'
 value={'commands':[{'argv':[sys.executable,'-c','from pathlib import Path;Path('+repr(str(marker))+').touch()'],'allowed_rc':[0],'key':None}]}
elif a.action=='final':
 assert (Path(a.records)/'cleaned').exists();value={'cleanup_passed':True}
out.write_text(json.dumps(value));print(json.dumps(value))
