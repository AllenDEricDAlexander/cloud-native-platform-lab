#!/usr/bin/env python3
"""01.07–01.10 的只读取证与断言；所有集群变更由 Ansible 执行。"""
import argparse
import base64
import http.client
from datetime import datetime,timezone
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import sys

from cryptography import x509
from cryptography.x509.oid import NameOID

spec=importlib.util.spec_from_file_location('core_reader',Path(__file__).with_name('lab-check.py'))
lab=importlib.util.module_from_spec(spec);spec.loader.exec_module(lab)
require,save=lab.require,lab.save
traffic_spec=importlib.util.spec_from_file_location('core_traffic',Path(__file__).with_name('traffic.py'))
traffic=importlib.util.module_from_spec(traffic_spec);traffic_spec.loader.exec_module(traffic)
PUBLIC_KINDS='pods,services,configmaps,serviceaccounts,resourcequotas,limitranges,networkpolicies,ciliumnetworkpolicies,deployments,replicasets,statefulsets,daemonsets,controllerrevisions,jobs,cronjobs,horizontalpodautoscalers,roles,rolebindings'
NODE_IPS={name+'.k8s.internal.egon.top':'192.168.9.'+str(ip) for name,ip in [('cp01',101),('cp02',102),('cp03',103),('infra01',104),('infra02',105),('storage01',106),('storage02',107),('storage03',108),('worker01',109),('worker02',110)]}


def serving_tls(name,ip):
    require(NODE_IPS.get(name)==ip,'TLS 检查目标不属于原十节点')
    probe="import socket,ssl,sys; c=ssl.create_default_context(cafile='/etc/kubernetes/pki/ca.crt'); s=c.wrap_socket(socket.create_connection(('127.0.0.1',10250),timeout=2),server_hostname=sys.argv[1]); print('KUBELET TLS VERIFIED'); s.close()"
    args=['ssh','-i',str(Path.home()/'.ssh/cnpl_lab_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=3','root@'+ip,shlex.join(['/usr/bin/python3','-c',probe,ip])]
    result=subprocess.run(args,capture_output=True,text=True,timeout=8)
    return result.returncode==0 and result.stdout.strip()=='KUBELET TLS VERIFIED'


class Reader:
    def __init__(self,context):self.context=context;self.api=lab.Reader(context);self.namespace=context['namespace']
    def read(self,kind,name=None,selector=None,namespace=None,missing=False):
        args=['get',kind]+([name] if name else [])+['-n',namespace or self.namespace,'-o','json']
        if selector:args+=['-l',selector]
        if missing:args+=['--ignore-not-found']
        raw=self.api.k(*args,admin=True);return json.loads(raw) if raw else None
    def owned(self,kind):
        return self.read(kind,selector='cnpl.io/core-run='+self.context['run'])['items']
    def raw(self,path):return json.loads(self.api.k('get','--raw='+path,admin=True))


def owned(context,obj):
    require(obj['metadata'].get('labels',{}).get('cnpl.io/core-run')==context['run'],'对象属于其他运行：'+obj['metadata']['name'])


def guard(reader):
    namespace=reader.read('namespace',reader.namespace,missing=True)
    if namespace is None:return {'namespace_absent':True,'objects':[]}
    owned(reader.context,namespace)
    binding=Path(reader.context['records'])/'state/namespace.json'
    require(binding.is_file(),'缺少 Namespace UID 绑定，禁止删除同名空间')
    require(json.loads(binding.read_text())['uid']==namespace['metadata']['uid'],'Namespace 已被替换，禁止接管')
    objects=reader.read(PUBLIC_KINDS)['items']
    for obj in objects:
        if (obj['kind'],obj['metadata']['name']) in [('ServiceAccount','default'),('ConfigMap','kube-root-ca.crt')]:continue
        owned(reader.context,obj)
        require(set(obj['metadata'].get('finalizers',[]))<= {'cnpl.io/core-cleanup','foregroundDeletion','batch.kubernetes.io/job-tracking'},'存在其他控制器 finalizer：'+obj['metadata']['name'])
    # 只输出 Secret 名称、UID 和标签；不保存数据或可能含凭据的 annotation。
    raw=reader.api.k('get','secrets','-n',reader.namespace,'-o','jsonpath-as-json={.items[*].metadata}',admin=True)
    secrets=json.loads(raw or '[]')
    for meta in secrets:owned(reader.context,{'metadata':meta})
    return {'namespace_uid':namespace['metadata']['uid'],'objects':[{'kind':o['kind'],'name':o['metadata']['name'],'uid':o['metadata']['uid'],'finalizers':o['metadata'].get('finalizers',[])} for o in objects],
            'secrets':[{'name':o['name'],'uid':o['uid']} for o in secrets]}


def workload(reader,a):
    parent=reader.read(a.kind,a.name);owned(reader.context,parent)
    owners={parent['metadata']['uid']}
    if a.kind=='deployment':owners={r['metadata']['uid'] for r in reader.owned('replicasets') if lab.owner(r).get('uid')==parent['metadata']['uid']}
    pods=[p for p in reader.owned('pods') if lab.owner(p).get('uid') in owners and not p['metadata'].get('deletionTimestamp')]
    require(parent.get('status',{}).get('observedGeneration',0)>=parent['metadata']['generation'],'控制器尚未观察当前 generation')
    require(len(pods)==a.count,'实际活动 Pod 数量未收敛')
    ready={p['metadata']['name'] for p in pods if lab.condition(p,'Ready','True')}
    if a.not_ready:
        require(set(p['metadata']['name'] for p in pods)-ready==set(a.not_ready.split(',')),'未就绪的序号不符')
    else:require(len(ready)==a.count,'Pod 尚未全部 Ready')
    if a.image:
        for pod in pods:
            image=a.image
            if a.partition is not None and int(pod['metadata']['name'].rsplit('-',1)[1])<a.partition:image=a.old_image
            require(pod['spec']['containers'][0]['image']==image,'Pod 实际镜像不符合更新策略')
    if a.nodes:require({p['spec']['nodeName'] for p in pods}==set(a.nodes.split(',')),'DaemonSet 覆盖节点不符')
    return {'parent':parent,'pods':pods,'ready':sorted(ready)}


class TerminalJobFailure(ValueError):
    """Job 已进入不可能满足预期的终态，等待器应立即停止。"""


def job(reader,a):
    obj=reader.read('job',a.name);owned(reader.context,obj)
    opposite='Failed' if a.condition=='Complete' else 'Complete'
    if lab.condition(obj,opposite,'True'):
        detail=next(c for c in obj['status']['conditions'] if c['type']==opposite and c['status']=='True')
        raise TerminalJobFailure(a.name+' 已进入 '+opposite+'：'+detail.get('reason','')+' '+detail.get('message',''))
    require(lab.condition(obj,a.condition,'True'),'Job 尚未达到 '+a.condition)
    if a.reason:require(any(c['type']==a.condition and c['status']=='True' and c.get('reason')==a.reason for c in obj['status']['conditions']),'Job 结束原因不符')
    pods=[p for p in reader.owned('pods') if lab.owner(p).get('uid')==obj['metadata']['uid']]
    if getattr(a,'retry_exit_code',None) is not None:
        require(obj['spec'].get('completionMode')=='Indexed','重试退出码检查需要 Indexed Job')
        exits={str(index):[] for index in range(obj['spec']['completions'])}
        for pod in pods:
            index=pod['metadata'].get('annotations',{}).get('batch.kubernetes.io/job-completion-index')
            require(index in exits,'Job Pod 缺少有效序号')
            exits[index]+=[c['state']['terminated']['exitCode'] for c in pod['status'].get('containerStatuses',[]) if c['name']=='app' and 'terminated' in c.get('state',{})]
        if not all(a.retry_exit_code in codes and 0 in codes and set(codes)<={0,a.retry_exit_code} for codes in exits.values()):
            raise TerminalJobFailure(a.name+' 序号重试退出码不符：'+json.dumps(exits))
        return {'job':obj,'pods':pods,'exit_codes_by_index':exits}
    return {'job':obj,'pods':pods}


def cron(reader,a):
    parents={c['spec']['concurrencyPolicy']:c for c in reader.owned('cronjobs')}
    require(set(parents)=={'Allow','Forbid','Replace'},'缺少三种 CronJob 并发策略')
    jobs=reader.owned('jobs');groups={policy:[j for j in jobs if lab.owner(j).get('uid')==obj['metadata']['uid']] for policy,obj in parents.items()}
    for obj in parents.values():require(obj['spec']['timeZone']=='Asia/Shanghai','CronJob 时区不符')
    scheduled={}
    for policy,values in groups.items():
        for obj in values:require(obj['metadata'].get('annotations',{}).get('batch.kubernetes.io/cronjob-scheduled-timestamp'),'不是控制器真实调度的 CronJob Job')
        scheduled[policy]=[obj['metadata']['annotations']['batch.kubernetes.io/cronjob-scheduled-timestamp'] for obj in values]
    if a.input:
        first=json.loads(a.input.read_text())
        require(len([j for j in groups['Allow'] if j.get('status',{}).get('active',0)>0])>=2,'尚未观察到 Allow 重叠')
        require(len(groups['Forbid'])==1 and groups['Forbid'][0]['metadata']['uid']==first['initial_uids']['Forbid'],'Forbid 重复启动或原任务丢失')
        require(any(j['metadata']['uid']!=first['initial_uids']['Replace'] for j in groups['Replace']) and all(j['metadata']['uid']!=first['initial_uids']['Replace'] for j in groups['Replace']),'Replace 尚未替换原任务')
        first_scheduled=first['jobs']['Forbid'][0]['metadata']['annotations']['batch.kubernetes.io/cronjob-scheduled-timestamp']
        require(max(scheduled['Allow'])>first_scheduled and max(scheduled['Replace'])==max(scheduled['Allow']),'Allow/Replace 尚未到同一下一次计划时间')
    else:
        require(all(len(v)==1 and v[0].get('status',{}).get('active',0)==1 for v in groups.values()),'等待三种策略各自首次真实调度')
        require(len({v[0] for v in scheduled.values()})==1,'三种策略首次计划时间不是同一分钟')
    return {'cronjobs':parents,'jobs':groups,'initial_uids':{k:v[0]['metadata']['uid'] for k,v in groups.items()}}


def hpa(reader,a):
    obj=reader.read('hpa',a.name);owned(reader.context,obj)
    deployment=reader.read('deployment',obj['spec']['scaleTargetRef']['name'])
    metrics=reader.raw('/apis/metrics.k8s.io/v1beta1/namespaces/'+reader.namespace+'/pods')
    result={'at':datetime.now(timezone.utc).isoformat(),'hpa':obj,'deployment':deployment,'pod_metrics':metrics}
    try:
        pods=[p for p in reader.owned('pods') if p['metadata']['labels'].get('app.kubernetes.io/name')==deployment['metadata']['name'] and not p['metadata'].get('deletionTimestamp')]
        names={p['metadata']['name'] for p in pods};fresh=[m for m in metrics['items'] if m['metadata']['name'] in names and -5<=(datetime.now(timezone.utc)-datetime.fromisoformat(m['timestamp'].replace('Z','+00:00'))).total_seconds()<60]
        require(fresh,'目标应用没有新鲜的实际 Pod 指标')
        if a.condition=='missing':
            require(pods and all(p['spec']['containers'][0]['resources']['requests'].get('cpu') in ['0','0m'] for p in pods),'反例不是明确的零 CPU 请求')
            require(any(c['type']=='ScalingActive' and c['status']=='False' and c.get('reason')=='FailedGetResourceMetric' for c in obj.get('status',{}).get('conditions',[])),'尚未观察 CPU request=0 的不可计算状态')
        else:
            require(lab.condition(obj,'ScalingActive','True'),'HPA 指标尚未可用')
            require(any(m.get('resource',{}).get('name')==obj['spec']['metrics'][0]['resource']['name'] for m in obj.get('status',{}).get('currentMetrics',[])),'HPA 尚未取得当前所选资源的真实指标')
            count=deployment.get('status',{}).get('readyReplicas',0)
            require((count>=2 if a.condition=='up' else count==1),'HPA 实际副本数尚未达到预期')
            require(obj['spec']['minReplicas']==1 and obj['spec']['maxReplicas']==4 and deployment['spec']['replicas']<=4,'HPA 越过受控副本边界')
            require(obj.get('status',{}).get('desiredReplicas')==deployment['spec']['replicas'] and count==deployment['spec']['replicas'],'HPA 与实际就绪副本尚未共同收敛')
        return result
    except ValueError as error:
        result['pending_error']=str(error)
        if a.output:
            save(a.output,result)
            with Path(a.output+'.jsonl').open('a') as stream:stream.write(json.dumps(result)+'\n')
        raise


def app_mode(reader,a):
    pods=[p for p in reader.owned('pods') if p['metadata']['labels'].get('app.kubernetes.io/name')==a.name and lab.condition(p,'Ready','True') and not p['metadata'].get('deletionTimestamp')]
    require(pods,'没有可观察的当前就绪应用 Pod')
    pod=pods[0]
    with traffic.tunnel(pod) as port:result=traffic.get(port,'/identity')
    require(result['code']==200 and result['body']['uid']==pod['metadata']['uid'] and result['body']['load']==a.mode,'应用尚未实际读取新的负载模式')
    return {'pod':pod['metadata']['name'],'uid':pod['metadata']['uid'],'mode':a.mode}


def csr(reader,a):
    if serving_tls(a.name,a.ip):return {'names':[],'already_serving':True}
    rows=reader.read('certificatesigningrequests')['items'];names=[]
    for row in rows:
        spec=row['spec']
        if spec.get('username')!='system:node:'+a.name or spec.get('signerName')!='kubernetes.io/kubelet-serving' or row.get('status',{}).get('certificate'):continue
        require(not any(c['type'] in ['Denied','Failed'] for c in row.get('status',{}).get('conditions',[])),'当前节点服务 CSR 被拒绝')
        request=x509.load_pem_x509_csr(base64.b64decode(spec['request']))
        require(request.is_signature_valid,'CSR 自签名无效')
        require([x.value for x in request.subject.get_attributes_for_oid(NameOID.COMMON_NAME)]==['system:node:'+a.name],'CSR CN 不符')
        require([x.value for x in request.subject.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)]==['system:nodes'],'CSR 组织不符')
        san=request.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        require(all(isinstance(value,(x509.DNSName,x509.IPAddress)) for value in san),'CSR 包含非节点 DNS/IP 的 SAN')
        require(set(san.get_values_for_type(x509.DNSName))<={a.name,a.name.split('.')[0]} and set(str(x) for x in san.get_values_for_type(x509.IPAddress))=={a.ip},'CSR SAN 越过该节点范围')
        require(set(spec.get('usages',[]))<={'digital signature','key encipherment','server auth'} and {'digital signature','server auth'}<=set(spec['usages']),'CSR usages 不符')
        require({'system:nodes','system:authenticated'}<=set(spec.get('groups',[])),'CSR 请求身份组不符')
        created=datetime.fromisoformat(row['metadata']['creationTimestamp'].replace('Z','+00:00'))
        require(-5<=(datetime.now(timezone.utc)-created).total_seconds()<900,'拒绝批准旧 CSR')
        names.append(row['metadata']['name'])
    require(names,'等待本节点新服务 CSR');return {'names':names}


def metrics(reader):
    api=reader.read('apiservice','v1beta1.metrics.k8s.io')
    require(lab.condition(api,'Available','True') and api['spec'].get('insecureSkipTLSVerify',False) is False and api['spec'].get('caBundle'),'指标 API 未通过 TLS/可用性检查')
    nodes=reader.raw('/apis/metrics.k8s.io/v1beta1/nodes')
    require({n['metadata']['name'] for n in nodes['items']}==lab.NODES,'没有取得十节点真实资源指标')
    for item in nodes['items']:
        sampled=datetime.fromisoformat(item['timestamp'].replace('Z','+00:00'))
        require(-5<=(datetime.now(timezone.utc)-sampled).total_seconds()<60,'指标已过期')
    service=reader.read('service',api['spec']['service']['name'],namespace=api['spec']['service']['namespace'])
    selector=','.join(k+'='+v for k,v in service['spec']['selector'].items())
    pods=reader.read('pods',selector=selector,namespace=service['metadata']['namespace'])['items']
    require(pods and all('--kubelet-insecure-tls' not in ' '.join(c.get('command',[])+c.get('args',[])) for p in pods for c in p['spec']['containers']),'指标组件存在不安全 kubelet TLS 参数')
    return {'apiservice':api,'node_metrics':nodes,'metrics_pods':pods}


def snapshot(reader,path):
    path=Path(path)/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ');path.mkdir(parents=True)
    ns=reader.read('namespace',reader.namespace,missing=True)
    if ns is None:save(path/'objects.json',{'namespace_absent':True});return {'snapshot':str(path)}
    owned(reader.context,ns);objects=reader.read(PUBLIC_KINDS)['items'];objects=[o for o in objects if o['metadata'].get('labels',{}).get('cnpl.io/core-run')==reader.context['run']]
    save(path/'objects.json',{'namespace':ns,'items':objects})
    save(path/'events.json',reader.read('events'))
    for pod in objects:
        if pod['kind']!='Pod':continue
        name=pod['metadata']['name']
        try:value=reader.api.k('logs',name,'-n',reader.namespace,'--all-containers=true','--tail=100',admin=True)
        except ValueError as error:value=str(error)
        (path/(name+'.log')).write_text(value+'\n')
    return {'snapshot':str(path),'objects':len(objects)}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['guard','workload','job','cron','hpa','csr','metrics','snapshot','deleted','objects','pool-empty','tls','app-mode','pod'])
    parser.add_argument('--context',type=Path,required=True);parser.add_argument('--output');parser.add_argument('--input',type=Path)
    parser.add_argument('--kind');parser.add_argument('--name');parser.add_argument('--count',type=int,default=1);parser.add_argument('--image');parser.add_argument('--old-image');parser.add_argument('--partition',type=int);parser.add_argument('--not-ready');parser.add_argument('--nodes');parser.add_argument('--condition',default='Complete');parser.add_argument('--reason');parser.add_argument('--ip');parser.add_argument('--mode')
    parser.add_argument('--retry-exit-code',type=int)
    a=parser.parse_args();context=json.loads(a.context.read_text());reader=Reader(context)
    try:
        if a.action=='guard':result=guard(reader)
        elif a.action=='workload':result=workload(reader,a)
        elif a.action=='job':result=job(reader,a)
        elif a.action=='cron':result=cron(reader,a)
        elif a.action=='hpa':result=hpa(reader,a)
        elif a.action=='app-mode':result=app_mode(reader,a)
        elif a.action=='csr':result=csr(reader,a)
        elif a.action=='tls':
            require(serving_tls(a.name,a.ip),'kubelet 服务证书尚未通过集群 CA 与节点 IP SAN 校验');result={'verified':True,'node':a.name}
        elif a.action=='pod':
            obj=reader.read('pod',a.name);owned(context,obj);require(lab.condition(obj,'Ready','True') and not obj['metadata'].get('deletionTimestamp'),'Pod 尚未 Ready');result={'pod':obj}
        elif a.action=='metrics':result=metrics(reader)
        elif a.action=='snapshot':result=snapshot(reader,a.output)
        elif a.action=='deleted':
            obj=reader.read(a.kind,a.name,missing=True);require(obj is None,'对象尚未删除');result={'gone':True}
        elif a.action=='pool-empty':
            items=reader.read('deployments,replicasets,pods',selector='cnpl.io/core-run='+context['run']+',app.kubernetes.io/name='+a.name)['items'];require(not items,'仍有本次父子对象');result={'items':items}
        else:result={'items':reader.owned(a.kind or 'pods')}
        if a.output and a.action!='snapshot':
            save(a.output,result)
            if a.action=='hpa':
                with Path(a.output+'.jsonl').open('a') as stream:stream.write(json.dumps(result)+'\n')
        print(json.dumps(result,ensure_ascii=False))
    except TerminalJobFailure as error:
        print(json.dumps({'ok':False,'terminal_failure':True,'error':str(error)},ensure_ascii=False));return 2
    except (ValueError,KeyError,OSError,lab.subprocess.SubprocessError,http.client.HTTPException) as error:
        print(json.dumps({'ok':False,'error':str(error)},ensure_ascii=False));return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
