#!/usr/bin/env python3
"""只读检查/取证。Kubernetes 写操作不属于本程序，全部由 Ansible 执行。"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys


KINDS = 'deployments,replicasets,replicationcontrollers,pods,services,configmaps,networkpolicies,resourcequotas,limitranges'
WORKERS = {'worker01.k8s.internal.egon.top', 'worker02.k8s.internal.egon.top'}
NODES = {n + '.k8s.internal.egon.top' for n in ['cp01','cp02','cp03','infra01','infra02','storage01','storage02','storage03','worker01','worker02']}
FINALIZER = 'cnpl.io/replay-observe-stop'


def require(value, reason):
    if not value: raise ValueError(reason)


def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n'); temporary.replace(path)


def call(argv, timeout=25):
    result = subprocess.run([str(x) for x in argv], capture_output=True, text=True, timeout=timeout)
    if result.returncode: raise ValueError(Path(str(argv[0])).name + ': ' + result.stderr[-1500:])
    return result.stdout.strip()


class Reader:
    def __init__(self, context):
        self.context = context; self.namespace = 'lab-core'
        self.binary = Path.home()/'.cnpl/bin/kubectl'

    def k(self, *parts, admin=False):
        # 不接收任意命令。没有 stdin payload、kubectl exec 或 --raw 写入口。
        require(parts and parts[0] in ['get','logs','version','config','auth'], '只读检查器拒绝 Kubernetes 写操作')
        require(parts[0]!='config' or parts[1:2]==('view',), '只允许读取 kubeconfig')
        require(parts[0]!='auth' or parts[1:2]==('can-i',), '只允许权限查询')
        config = Path.home()/('.cnpl-secrets/kubeconfig-lab-primary' if admin else '.cnpl-secrets/access/lab-primary/mac.conf')
        args = [self.binary, '--kubeconfig', config, '--request-timeout=15s']
        if not admin: args += ['--context', 'lab-primary-lab-ops']
        return call(args + list(parts))

    def get(self, kind, name): return json.loads(self.k('get', kind, name, '-n', self.namespace, '-o', 'json'))

    def items(self, kind=KINDS, topic='*', case='*'):
        selector = 'cnpl.io/replay-run=' + self.context['run']
        if topic != '*': selector += ',cnpl.io/replay-topic=' + topic
        if case != '*': selector += ',cnpl.io/replay-case=' + case
        return json.loads(self.k('get', kind, '-n', self.namespace, '-l', selector, '-o', 'json'))['items']


def condition(obj, key, value): return any(c['type']==key and c['status']==value for c in obj.get('status',{}).get('conditions',[]))
def state(obj): return next((c for c in obj.get('status',{}).get('containerStatuses',[]) if c['name']=='app'), {})
def owner(obj): return next((o for o in obj['metadata'].get('ownerReferences',[]) if o.get('controller')), {})
def cpu(value): return int(value[:-1]) if value.endswith('m') else int(float(value)*1000)


def cluster(reader):
    for admin in [False,True]:
        server = reader.k('config','view','--minify','-o','jsonpath={.clusters[0].cluster.server}',admin=admin)
        require(server=='https://api.k8s.internal.egon.top:6443','kubeconfig 目标不是本实验集群')
    nodes = json.loads(reader.k('get','nodes','-o','json'))['items']
    require({n['metadata']['name'] for n in nodes}==NODES and len(nodes)==10,'需要原十节点')
    for n in nodes:
        require(condition(n,'Ready','True'),'节点未 Ready：'+n['metadata']['name'])
        require(all(condition(n,c,'False') for c in ['MemoryPressure','DiskPressure','PIDPressure']),'节点已有压力')
        if n['metadata']['name'] in WORKERS:
            require(not n['spec'].get('unschedulable') and not n['spec'].get('taints'),'worker 已处于维护状态')
            require(n['status']['allocatable']['cpu']=='7','8 核 Pending 反例需要重新设计')
    version = json.loads(reader.k('version','-o','json'))['serverVersion']['gitVersion'];require(version=='v1.36.5','版本漂移')
    ns = reader.get('namespace','lab-core');labels=ns['metadata']['labels']
    require(labels.get('pod-security.kubernetes.io/enforce')=='restricted' and labels.get('pod-security.kubernetes.io/enforce-version')=='v1.36','命名空间安全策略漂移')
    system = json.loads(reader.k('get','pods','-n','kube-system','-o','json'))['items']
    require(all(p['status'].get('phase')=='Succeeded' or condition(p,'Ready','True') for p in system if not p['metadata'].get('deletionTimestamp')),'系统 Pod 尚未恢复健康')
    return {'cluster_uid':reader.get('namespace','kube-system')['metadata']['uid'],'version':version,'nodes_ready':10}


def cleanup_plan(reader, topic, case):
    objects = reader.items(topic=topic,case=case)
    for obj in objects:
        require(obj['metadata']['labels'].get('cnpl.io/replay-run')==reader.context['run'],'对象归属不符')
        allowed={FINALIZER}
        if obj['metadata'].get('deletionTimestamp'):allowed.add('foregroundDeletion')
        require(set(obj['metadata'].get('finalizers',[]))<=allowed,'存在外来 finalizer：'+obj['metadata']['name'])
    order={'Deployment':0,'ReplicationController':1,'ReplicaSet':2,'Pod':3,'Service':4,'ConfigMap':5,'NetworkPolicy':6,'ResourceQuota':7,'LimitRange':8}
    return {'objects':sorted(objects,key=lambda x:order[x['kind']])}


def empty(reader, topic, case):
    objects=reader.items(topic=topic,case=case);require(not objects,'仍有本批资源')
    services=set()
    records=reader.context.get('records')
    if records:
        for path in Path(records).glob('attempts/*/observations/*-cleanup-plan-*.json'):
            for obj in json.loads(path.read_text())['objects']:
                labels=obj['metadata'].get('labels',{})
                if obj['kind']=='Service' and labels.get('cnpl.io/replay-run')==reader.context['run'] and (topic=='*' or labels.get('cnpl.io/replay-topic')==topic) and (case=='*' or labels.get('cnpl.io/replay-case')==case):
                    services.add(obj['metadata']['uid'])
    slices=json.loads(reader.k('get','endpointslices','-n','lab-core','-o','json'))['items']
    remaining=[s for s in slices if any(o.get('uid') in services for o in s['metadata'].get('ownerReferences',[]))]
    require(not remaining,'本批 Service 的 EndpointSlice 尚未回收')
    return {'items':objects,'endpointslices':remaining}


def graph(reader, name, count, image=None):
    dep = reader.get('deployment',name);require(dep['metadata']['labels'].get('cnpl.io/replay-run')==reader.context['run'],'Deployment 属于其他批次')
    sets=[r for r in reader.items('replicasets') if owner(r).get('uid')==dep['metadata']['uid']];uids={r['metadata']['uid'] for r in sets}
    pods=[p for p in reader.items('pods') if owner(p).get('uid') in uids];active=[p for p in pods if not p['metadata'].get('deletionTimestamp')]
    status=dep.get('status',{});ok=(status.get('observedGeneration',0)>=dep['metadata']['generation'] and dep['spec']['replicas']==count and all(status.get(k,0)==count for k in ['replicas','updatedReplicas','readyReplicas','availableReplicas']) and len(active)==count and all(condition(p,'Ready','True') for p in active))
    if image:ok=ok and all(p['spec']['containers'][0]['image']==image for p in active)
    return {'ok':ok,'deployment':dep,'replicasets':sets,'pods':pods,'active':active,
            'desired_rs_replicas':sum(r['spec']['replicas'] for r in sets),'total_pod_objects':len(pods),
            'declared_cpu_m':sum(cpu(c['resources']['requests']['cpu']) for p in pods for c in p['spec']['containers'])}


def termination(document):
    pod=document['pod'];terminated=state(pod).get('state',{}).get('terminated',{})
    require(pod['metadata'].get('deletionTimestamp') and terminated.get('exitCode')==0 and terminated.get('reason')=='Completed','未取得正常删除后的 Completed/0')
    raw=terminated.get('message','');require(raw,'没有终止回执')
    if raw.startswith('cnpl-termination-v1'):
        require('signal=TERM' in raw and 'pod_uid='+pod['metadata']['uid'] in raw and 'child_reaped=true' in raw,'BusyBox TERM 回执不完整')
        return {'pod_uid':pod['metadata']['uid'],'receipt':raw}
    receipt=json.loads(raw);require(receipt.get('uid')==pod['metadata']['uid'] and receipt.get('signal')=='TERM' and receipt.get('drained') is True,'TERM/UID/排空回执不符')
    term=datetime.fromisoformat(receipt['term_at'].replace('Z','+00:00'))
    if document.get('hook_seconds'):
        pre=datetime.fromisoformat(receipt['prestop_at'].replace('Z','+00:00'));require((term-pre).total_seconds()>=float(document['hook_seconds'])-.2,'没有证明 PreStop 占用宽限期')
    for response in document.get('responses',[]):
        require(response.get('uid')==pod['metadata']['uid'] and response.get('result')=='completed','请求归属或完成状态不符')
        require(datetime.fromisoformat(response['completed_at'].replace('Z','+00:00'))>term,'请求未在 TERM 后完成，未证明排空')
    if document.get('job'):
        job=document['job'];require(job['effects']==1 and job['id'] in (receipt.get('completed') or []),'终止前消息未提交')
        require(datetime.fromisoformat(job['committed_at'].replace('Z','+00:00'))>term,'消息在 TERM 前就结束，未证明排空')
    return {'pod_uid':pod['metadata']['uid'],'receipt':receipt}


def snapshot(reader,topic,case,output):
    folder=Path(output)/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ');folder.mkdir(parents=True)
    objects=reader.items(topic=topic,case=case);save(folder/'objects.json',{'items':objects})
    for obj in objects:
        if obj['kind']!='Pod':continue
        uid=obj['metadata']['uid'];name=obj['metadata']['name']
        save(folder/(name+'.events.json'),json.loads(reader.k('get','events','-n','lab-core','--field-selector=involvedObject.uid='+uid,'-o','json')))
        if obj['metadata'].get('deletionTimestamp'):continue
        # emptyDir 会随 Pod 消失；删除前尽量保全应用的只读状态，失败也如实记录。
        if condition(obj,'Ready','True') and any(c.get('image','').startswith('cnpl.local/phase01/') for c in obj['spec']['containers']):
            import importlib.util
            spec=importlib.util.spec_from_file_location('traffic_snapshot',Path(__file__).with_name('traffic.py'))
            traffic=importlib.util.module_from_spec(spec);spec.loader.exec_module(traffic)
            broker=any('broker' in c.get('command',[]) for c in obj['spec']['containers'])
            try:
                with traffic.tunnel(obj,9090 if broker else 8080) as port:
                    for endpoint in (['/status'] if broker else ['/metrics','/local']):
                        save(folder/(name+endpoint.replace('/','-')+'.json'),traffic.get(port,endpoint))
            except (OSError,ValueError,subprocess.SubprocessError) as exc:
                save(folder/(name+'.inspection-error.json'),{'error':str(exc)})
        for previous in [False,True]:
            if previous and state(obj).get('restartCount',0)==0:continue
            try:text=reader.k('logs',name,'-n','lab-core','--tail=100',*(['--previous'] if previous else []))
            except ValueError as exc:text=str(exc)
            (folder/(name+('.previous' if previous else '')+'.txt')).write_text(text+'\n')
    return {'snapshot':str(folder),'objects':len(objects)}


def audit(root, output):
    root=Path(root);base=root/'ops/01-kubernetes';paths=[]
    for relative in ['ansible','checks','tools','scripts','core-resources','operations']:
        paths += [p for p in (base/relative).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ['.pyc']]
    sums={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    legacy=base/'records/2026-10-18-ansible-replay/legacy/original-records-sha256.json'
    for name,sha in json.loads(legacy.read_text()).items():require(hashlib.sha256((root/name).read_bytes()).hexdigest()==sha,'原始记录变化：'+name)
    result={'source_sha256':sums,'original_records_unchanged':True,'source_commit':call(['git','-C',root,'rev-parse','HEAD'])}
    if output:save(output,result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['preflight','snapshot','cleanup-plan','empty','graph','term','audit','pods','owner-pods','endpoints'])
    p.add_argument('--context',type=Path);p.add_argument('--root');p.add_argument('--output');p.add_argument('--input',type=Path)
    p.add_argument('--topic',default='*');p.add_argument('--case',default='*');p.add_argument('--name');p.add_argument('--count',type=int,default=2);p.add_argument('--image');p.add_argument('--kind');p.add_argument('--exclude')
    a=p.parse_args();ctx=json.loads(a.context.read_text()) if a.context and a.context.exists() else {};r=Reader(ctx)
    try:
        if a.action=='audit':result=audit(a.root,a.output)
        elif a.action=='preflight':result=cluster(r)
        elif a.action=='cleanup-plan':result=cleanup_plan(r,a.topic,a.case)
        elif a.action=='snapshot':result=snapshot(r,a.topic,a.case,a.output)
        elif a.action=='empty':result=empty(r,a.topic,a.case)
        elif a.action=='graph':
            result=graph(r,a.name,a.count,a.image)
            if a.output:
                with Path(a.output).open('a') as stream:stream.write(json.dumps(result)+'\n')
            require(result['ok'],'Deployment/RS/Pod 尚未共同收敛')
        elif a.action=='term':result=termination(json.loads(a.input.read_text()))
        elif a.action=='endpoints':
            service=r.get('service',a.name);require(service['metadata']['labels'].get('cnpl.io/replay-run')==ctx['run'],'Service 归属不符')
            items=json.loads(r.k('get','endpointslices','-n','lab-core','-l','kubernetes.io/service-name='+a.name,'-o','json'))['items']
            current=[item for item in items if any(o.get('uid')==service['metadata']['uid'] for o in item['metadata'].get('ownerReferences',[]))]
            result={'items':current,'endpoints':[ep for item in current for ep in item.get('endpoints',[])]}
        elif a.action=='owner-pods':
            parent=r.get(a.kind,a.name);require(parent['metadata']['labels'].get('cnpl.io/replay-run')==ctx['run'],'父对象归属不符')
            pods=[p for p in r.items('pods') if owner(p).get('uid')==parent['metadata']['uid'] and not p['metadata'].get('deletionTimestamp')]
            require(len(pods)==a.count and all(condition(p,'Ready','True') for p in pods) and a.exclude not in {p['metadata']['uid'] for p in pods},'子 Pod 数量/就绪/替换 UID 尚未收敛')
            result={'parent':parent,'items':pods}
        else:result={'items':r.items('pods',a.topic,a.case)}
        if a.output and a.action not in ['graph','audit','snapshot']:save(a.output,result)
        print(json.dumps(result,ensure_ascii=False))
    except (ValueError,KeyError,OSError,subprocess.SubprocessError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False));raise SystemExit(1)


if __name__=='__main__':main()
