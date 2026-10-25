
import json,os,sys
from pathlib import Path
args=sys.argv[1:]
with open(os.environ['CNPL_MODEL_CALLS'],'a') as f:f.write(json.dumps(args)+'\n')
if 'apply' in args:
 path=args[args.index('-f')+1];obj=json.loads(Path(path).read_text());obj['metadata']['uid']='offline-'+obj['metadata']['name'];print(json.dumps(obj))
elif 'delete' in args:
 body=json.loads(Path(args[args.index('-f')+1]).read_text());assert body['preconditions']['uid'].startswith('offline-');print('{}')
elif 'wait' in args:print('deleted')
else:raise SystemExit('unexpected mocked kubectl command')
