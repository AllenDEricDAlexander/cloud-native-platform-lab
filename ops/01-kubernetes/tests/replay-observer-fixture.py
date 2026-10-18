#!/usr/bin/env python3
"""有限离线观测夹具：只写临时测试文件，不访问网络或运行应用。"""
import argparse
import json
from pathlib import Path
import time

p=argparse.ArgumentParser();p.add_argument('action');p.add_argument('--output',required=True);p.add_argument('--ready',required=True)
p.add_argument('--stop',required=True);p.add_argument('--timeline',required=True);p.add_argument('--seconds',type=int,required=True)
p.add_argument('--finish-immediately',action='store_true');a,_=p.parse_known_args()
require_root=Path(a.output).resolve().parent
if not require_root.name.startswith('cnpl-observer-test-'):raise SystemExit('isolated fixture directory required')
Path(a.ready).write_text(json.dumps({'ready':True,'expires_at':time.time()+a.seconds}))
end=time.monotonic()+min(a.seconds,30)
while not a.finish_immediately and time.monotonic()<end and not Path(a.stop).exists():time.sleep(.05)
result={'rows':[{'ok':True} for _ in range(6)],'stopped_by_ansible':Path(a.stop).exists(),'received_seconds':a.seconds}
Path(a.output).write_text(json.dumps(result));Path(a.timeline).write_text(json.dumps(result)+'\n');print(json.dumps({'finished':True}))
