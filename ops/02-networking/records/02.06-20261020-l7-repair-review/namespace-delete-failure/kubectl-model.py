
import json,os,sys
from pathlib import Path
args=sys.argv[1:]
with open(os.environ['CNPL_MODEL_CALLS'],'a') as f:f.write(json.dumps(args)+'\n')
if 'apply' in args:
 path=args[args.index('-f')+1];obj=json.loads(Path(path).read_text());obj['metadata']['uid']='offline-'+obj['metadata']['name'];print(json.dumps(obj))
elif 'delete' in args:
 if args[args.index('--raw')+1].endswith('/lab-policy'):sys.exit('injected namespace delete failure')
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
