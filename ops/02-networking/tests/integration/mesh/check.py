#!/usr/bin/env python3
"""Sidecar/Ambient/waypoint 与独立 SPIRE 的真实身份、策略及交接证据。"""
from datetime import datetime,timezone
import hashlib
import http.client
import json
from pathlib import Path
import re
import sys
import tarfile
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'phase02'))
import runtime as r
import isolated as iso
import cli
import yaml
import select
import subprocess

TOPIC,STAGE='mesh','02.10'
NAMESPACES=[]
WAIT_SECONDS=240
SIDECAR,AMBIENT,PLAIN,SPIRE='lab-mesh-sidecar','lab-mesh-ambient','lab-mesh-plain','lab-spire'
SOCKET='/run/spire/api.sock'


def prepare(s):
    lock=iso.prepare(s,mesh=True);extra=lock['mesh']
    archive=Path(extra['installer']['path'])
    r.require(iso.MATERIALS.file_sha(archive)==extra['installer']['sha256'],'Istio 安装包摘要不同')
    with tarfile.open(archive) as tar:
        prefix='istio-1.31.2/manifests/'
        expected={m.name for m in tar.getmembers() if m.isfile() and m.name.startswith(prefix)}
        actual={str(p.relative_to(archive.parent)) for p in Path(extra['manifests']).rglob('*') if p.is_file()}
        r.require(expected==actual,'Istio Chart 文件集合不同')
        for name in expected:
            r.require(hashlib.sha256(tar.extractfile(name).read()).hexdigest()==iso.MATERIALS.file_sha(archive.parent/name),'Istio Chart 内容不同')
    s.render({'image':lock['images']['resource']['runtime_image'],'identity_image':lock['images']['identity']['runtime_image'],
        'spire_server':lock['images']['spire-server']['runtime_image'],'spire_agent':lock['images']['spire-agent']['runtime_image'],
        'spire_server_hcl':(r.PHASE/'networking/mesh/spire-server.conf').read_text(),
        'spire_agent_hcl':(r.PHASE/'networking/mesh/spire-agent.conf').read_text(),
        'pod_cidr':s.context['isolation']['pod_cidr'],'service_cidr':s.context['isolation']['service_cidr']})
    for topic,key in [('spire-server','server.conf'),('spire-agent','agent.conf')]:
        raw=(r.PHASE/'networking/mesh'/(topic+'.conf')).read_text()
        config=next(d for d in yaml.safe_load_all((s.attempt/(topic+'.yaml')).read_text()) if d and d['kind']=='ConfigMap')
        r.require(config['data'][key]==raw,'YAML 中的 HCL 与已测试的原文件不同')
    generate(s)


def steps(s):
    return yaml.safe_load((r.PHASE/'networking/mesh/cases.yml').read_text())


def generate(s):
    c=iso.Cluster(s);extra=c.lock['mesh'];file=s.attempt/'istio-operator.yaml'
    raw=r.call([extra['tools']['istioctl']['path'],'manifest','generate','-f',file,'--manifests',extra['manifests'],'--cluster-specific=false'],timeout=90)
    docs=[d for d in yaml.safe_load_all(raw) if d]
    r.require(not any(d['kind']=='Secret' and (d.get('data') or d.get('stringData')) for d in docs),'生成清单含秘密，不能写公开记录')
    (s.attempt/'istio-generated.yaml').write_text(raw)
    known=set(v['runtime_image'] for v in c.lock['images'].values())
    images=[p['image'] for d in docs if d['kind'] in ['DaemonSet','Deployment','Job'] for p in d['spec']['template']['spec'].get('containers',[])+d['spec']['template']['spec'].get('initContainers',[])]
    r.require(set(images)<=known,'Istio 清单含未准备镜像：'+str(set(images)-known))
    config=next(d for d in docs if d['kind']=='ConfigMap' and 'config' in d.get('data',{}) and 'values' in d.get('data',{}))
    mesh=next(d for d in docs if d['kind']=='ConfigMap' and 'mesh' in d.get('data',{}))
    inject=s.attempt/'inject-config.yaml';inject.write_text(config['data']['config'])
    values=s.attempt/'inject-values.json';values.write_text(config['data']['values'])
    meshfile=s.attempt/'mesh-config.yaml';meshfile.write_text(mesh['data']['mesh'])
    example=next(d for d in yaml.safe_load_all((s.attempt/'workloads.yaml').read_text()) if d and d['kind']=='Pod' and d['metadata']['namespace']==SIDECAR)
    deployment={'apiVersion':'apps/v1','kind':'Deployment','metadata':example['metadata'],'spec':{'selector':{'matchLabels':example['metadata']['labels']},'template':{'metadata':example['metadata'],'spec':example['spec']}}}
    deployment['metadata']['namespace']='lab-core'
    deployment['spec']['template']['metadata']['namespace']='lab-core'
    deployment['spec']['template']['metadata'].setdefault('annotations',{})['sidecar.istio.io/inject']='true'
    sample=s.attempt/'inject-example.yaml';sample.write_text(yaml.safe_dump(deployment,sort_keys=False))
    injected=r.call([extra['tools']['istioctl']['path'],'kube-inject','--kubeconfig',str(Path.home()/'.cnpl-secrets/kubeconfig-lab-primary'),'-f',sample,
        '--injectConfigFile',inject,'--meshConfigFile',meshfile,'--valuesFile',values],timeout=45)
    pod=next(d for d in yaml.safe_load_all(injected) if d and d.get('kind')=='Deployment')['spec']['template']['spec']
    proxy=next(p for p in pod['containers']+pod.get('initContainers',[]) if p['name']=='istio-proxy')
    r.require(proxy['image'] in known,'实际注入模板的代理镜像未准备')
    r.require(not any(p['name']=='istio-init' for p in pod.get('initContainers',[])),'CNI 模式仍注入 NET_ADMIN init')
    r.save(s.attempt/'istio-render.json',{'objects':len(docs),'images':sorted(set(images)),'offline_sidecar_injection_checked':True,'injected_proxy_image':proxy['image']})
    return docs


def validate(s):
    c=iso.Cluster(s)
    # Cilium 必须允许 CNI 串联并保持 BPF masquerading 关闭。
    values=c.cilium_values('baseline',mesh=True)
    r.require(not values['cni']['exclusive'] and not values['bpf']['masquerade'],'Ambient/Cilium 兼容配置错误')
    docs=list(yaml.safe_load_all((s.attempt/'istio-generated.yaml').read_text()))
    definitions=[d for d in docs if d and d['kind']=='CustomResourceDefinition']
    custom=[];builtins=0;deferred=[]
    for name in ['workloads.yaml','sidecar-policy.yaml','ambient-l4.yaml','waypoint.yaml','ambient-l7.yaml','spire-server.yaml','spire-agent.yaml','spire-workloads.yaml','held.yaml']:
        for obj in yaml.safe_load_all((s.attempt/name).read_text()):
            if not obj:continue
            if obj['apiVersion'].startswith(('security.istio.io/','networking.istio.io/','gateway.networking.k8s.io/')):
                custom.append(obj);continue
            clone=json.loads(json.dumps(obj))
            if clone['kind'] not in ['Namespace','ClusterRole','ClusterRoleBinding']:
                clone['metadata']['namespace']='kube-system'
            clone['metadata']['name']='cnpl-preview-'+clone['metadata']['name']
            podspec=clone.get('spec') if clone['kind']=='Pod' else clone.get('spec',{}).get('template',{}).get('spec')
            if podspec and podspec.get('serviceAccountName'):
                deferred.append({'kind':clone['kind'],'name':obj['metadata']['name'],'serviceAccountName':podspec['serviceAccountName']})
                podspec['serviceAccountName']='default'
            r.call(r.K+['apply','--dry-run=server','--validate=strict','-f','-'],json.dumps(clone));builtins+=1
    for definition in definitions:
        r.call(r.K+['apply','--dry-run=server','--validate=strict','-f','-'],json.dumps(definition))
    # Kubernetes 隐式允许这三个根字段；Istio 生成的 CRD schema 仅显式列 spec/status。
    models=json.loads(json.dumps(definitions))
    for model in models:
        for version in model['spec']['versions']:
            properties=version['schema']['openAPIV3Schema'].setdefault('properties',{})
            for key,value in [('apiVersion',{'type':'string'}),('kind',{'type':'string'}),('metadata',{'type':'object'})]:
                properties.setdefault(key,value)
    checked=r.pol.gw.mat.validate_custom(custom,models+r.pol.gw.mat.crds())
    r.call([c.lock['tools']['istioctl']['path'],'validate','-f',s.attempt/'sidecar-policy.yaml'],timeout=30)
    return {'passed':True,'istio_version':'1.31.2','builtin_server_dry_run':builtins,'istio_crd_server_dry_run':len(definitions),
        'custom_structure':checked,'docker_available':c.state['docker_available'],'runtime_executed':False,
        'service_account_reference_admission_deferred':deferred,
        'actual_custom_admission':'隔离集群安装本批 CRD 后，每份 apply 前严格校验'}


def istio(c,args):
    return [c.lock['tools']['istioctl']['path'],'--kubeconfig',c.state['kubeconfig']]+args


def server_exec(c,args):
    return c.k+['exec','-n','spire-system','spire-server','--','/opt/spire/bin/spire-server']+args+['-socketPath',SOCKET]


def agent_ids(value):
    rows=(value.get('agents') or []) if isinstance(value,dict) else value
    r.require(isinstance(rows,list),'SPIRE agent 列表不是数组')
    result=[]
    for row in rows:
        identity=row.get('id',row.get('spiffe_id',row.get('spiffeId')))
        if isinstance(identity,dict):
            identity='spiffe://'+identity.get('trust_domain',identity.get('trustDomain',''))+identity.get('path','')
        r.require(isinstance(identity,str) and identity.startswith('spiffe://internal.egon.top/spire/agent/k8s_psat/'),'SPIRE agent ID 不符合本批 trust domain/attestor')
        result.append(identity)
    return result


def plan(s,name):
    c=iso.Cluster(s)
    if name=='create':return c.create_plan()
    if name=='load':return c.load_plan()
    if name=='cilium':return c.helm_cilium('baseline',mesh=True)
    if name=='gateway-crds':
        c.guard();file=s.attempt/'gateway-crds.json';r.save(file,{'apiVersion':'v1','kind':'List','items':[d for d in r.pol.gw.mat.crds() if d['kind']=='CustomResourceDefinition']})
        return c.apply([file])
    if name=='istio':
        c.guard();docs=[d for d in yaml.safe_load_all((s.attempt/'istio-generated.yaml').read_text()) if d]
        # CRD 必须先 Established，才能严格校验相应自定义对象。
        crds=[d for d in docs if d['kind']=='CustomResourceDefinition'];other=[d for d in docs if d['kind']!='CustomResourceDefinition']
        root=s.attempt/'istio-crds.json';r.save(root,{'apiVersion':'v1','kind':'List','items':crds})
        body=s.attempt/'istio-components.json';r.save(body,{'apiVersion':'v1','kind':'List','items':other})
        return c.apply([s.attempt/'istio-namespace.yaml',root])+[s.command(c.k+['wait','--for=condition=Established','--timeout=120s','crd/'+d['metadata']['name']]) for d in crds]+c.apply([body])
    files={'applications':'workloads.yaml','sidecar-policy':'sidecar-policy.yaml','ambient-l4':'ambient-l4.yaml',
        'waypoint':'waypoint.yaml','ambient-l7':'ambient-l7.yaml','spire-server':'spire-server.yaml',
        'spire-agent':'spire-agent.yaml','spire-workloads':'spire-workloads.yaml','held':'held.yaml'}
    if name in files:return c.apply([s.attempt/files[name]])
    if name=='spire-bundle':
        c.guard();raw=r.call(server_exec(c,['bundle','show','-format','pem']))
        r.require('BEGIN CERTIFICATE' in raw and 'PRIVATE KEY' not in raw,'SPIRE 公共 bundle 异常')
        file=s.attempt/'spire-bundle.json';r.save(file,{'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'spire-bundle','namespace':'spire-system','labels':{r.LABEL:s.run}},'data':{'bundle.pem':raw}})
        return c.apply([file])
    if name=='register':
        c.guard()
        ids=agent_ids(json.loads(r.call(server_exec(c,['agent','list','-output','json']))))
        r.require(len(ids)==3,'需要本批三个已证明身份的 SPIRE agent')
        entries=[{'id':str(uuid.uuid4()),'parent':parent,'role':role} for parent in ids for role in ['server','allowed','verifier']]
        s.context['spire_entries']=entries;r.save(s.path,s.context)
        return [s.command(server_exec(c,['entry','create','-entryID',e['id'],'-parentID',e['parent'],
            '-spiffeID','spiffe://internal.egon.top/ns/'+SPIRE+'/sa/'+e['role'],
            '-selector','k8s:ns:'+SPIRE,'-selector','k8s:sa:'+e['role'],'-x509SVIDTTL','60'])) for e in entries]
    if name=='revoke':
        c.guard()
        return [s.command(server_exec(c,['entry','delete','-entryID',e['id']])) for e in s.context['spire_entries'] if e['role']=='allowed']
    return []


def app(c,namespace,pod):
    value=c.get('pod',pod,namespace)
    r.require(r.pol.base.ready(value),'工作负载未 Ready：'+namespace+'/'+pod)
    return value


def request(c,namespace,source,target_ns,path='/allowed',method='GET',nonce=None):
    data={'target':'http://server.'+target_ns+'.svc.cluster.local:8080'+path,'nonce':nonce or uuid.uuid4().hex,'method':method,'timeout_ms':4000}
    return json.loads(r.call(c.k+['exec','-i','-n',namespace,source,'-c','net','--','/phase-lab','probe'],json.dumps(data),timeout=15))


def allowed(c,namespace,source,target_ns,path='/allowed'):
    value=request(c,namespace,source,target_ns,path)
    r.require(value.get('status')==200 and not value.get('error'),'已授权请求未成功：'+str(value))
    body=json.loads(value['body']);r.require(body.get('nonce')==value['nonce'] and body.get('uid')==app(c,target_ns,'server')['metadata']['uid'],'请求 nonce/后端 UID 不同')
    return value


def metrics(c,pod,namespace,port,path):
    process=subprocess.Popen(c.k+['port-forward','--address','127.0.0.1','-n',namespace,'pod/'+pod,':'+str(port)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    text='';deadline=time.monotonic()+15
    try:
        while time.monotonic()<deadline:
            if select.select([process.stdout],[],[],.3)[0]:
                line=process.stdout.readline();r.require(line,'port-forward 退出');text+=line
                match=re.search(r'127\.0\.0\.1:(\d+) ->',text)
                if match:break
        else:raise ValueError('port-forward 未就绪')
        conn=http.client.HTTPConnection('127.0.0.1',int(match[1]),timeout=5)
        conn.request('GET',path);response=conn.getresponse();body=response.read(2*1024*1024).decode();conn.close()
        r.require(response.status==200,'指标端点未就绪')
        return body
    finally:
        process.terminate();process.communicate(timeout=8)


def mtls_metrics(c,namespace,ambient=False):
    if ambient:
        server=app(c,namespace,'server');node=server['spec']['nodeName']
        pods=c.get('pods',namespace='istio-system')['items']
        pod=next(p for p in pods if p['metadata'].get('labels',{}).get('app')=='ztunnel' and p['spec']['nodeName']==node and r.pol.base.ready(p))
        raw=metrics(c,pod['metadata']['name'],'istio-system',15020,'/metrics')
    else:
        raw=metrics(c,'server',namespace,15090,'/stats/prometheus')
    lines=[line for line in raw.splitlines() if 'connection_security_policy="mutual_tls"' in line and namespace in line
        and not line.startswith('#') and float(line.rsplit(' ',1)[-1])>0]
    r.require(lines,'缺少本次 Namespace 的实际 mutual_tls 指标')
    return lines


def resources(c,namespace,pod):
    value=app(c,namespace,pod);node=value['spec']['nodeName'];uid=value['metadata']['uid']
    raw=json.loads(r.call(c.node_exec(node,['crictl','stats','-o','json']),timeout=30))
    stats=[v for v in raw.get('stats',[]) if v.get('attributes',{}).get('labels',{}).get('io.kubernetes.pod.uid')==uid]
    r.require(stats,'缺少实际 CRI 容器资源计数')
    return {'pod_uid':uid,'containers':[{'name':v['attributes']['metadata']['name'],'cpu':v.get('cpu'),'memory':v.get('memory')} for v in stats]}


def native(c,pod,mode='call'):
    args=['/identity-lab',mode]
    if mode=='call':args+=['https://server.'+SPIRE+'.svc.cluster.local:8443/','spiffe://internal.egon.top/ns/'+SPIRE+'/sa/server']
    raw=r.call(c.k+['exec','-n',SPIRE,pod,'-c','net','--']+args,timeout=100 if mode=='watch' else 20)
    return json.loads(raw)


def native_allowed(c,pod='verifier'):
    value=native(c,pod);r.require(value.get('status')==200 and not value.get('error'),'SPIFFE mTLS 未成功')
    body=json.loads(value['body']);r.require(body['nonce']==value['nonce'] and body['uid']==app(c,SPIRE,'server')['metadata']['uid']
        and body['peer_id']=='spiffe://internal.egon.top/ns/'+SPIRE+'/sa/'+pod,'实际 mTLS 身份/nonce 不同')
    r.require(value.get('peer_id')=='spiffe://internal.egon.top/ns/'+SPIRE+'/sa/server','服务端 URI 身份不同')
    return value


def observe(s,name):
    c=iso.Cluster(s)
    if name=='create':return c.bind()
    if name=='load':return {'passed':True,'images_preloaded':len(c.lock['images'])-1}
    if name=='cilium':return c.ready()
    if name=='gateway-crds':return {'passed':True,'gateway_crds':len(r.pol.gw.mat.crds())}
    if name=='istio':
        c.ready()
        for kind,item in [('deployment','istiod-cnpl'),('daemonset','istio-cni-node'),('daemonset','ztunnel')]:
            value=c.get(kind,item,'istio-system')['status']
            r.require((value.get('availableReplicas',0)>=1 if kind=='deployment' else value.get('numberReady')==3),item+' 尚未就绪')
        return {'passed':True,'cni_exclusive':False,'bpf_masquerade':False}
    if name=='applications':
        for ns in [SIDECAR,AMBIENT,PLAIN]:
            for pod in ['server','allowed','denied']:
                value=app(c,ns,pod);names={v['name'] for v in value['spec']['containers']+value['spec'].get('initContainers',[])}
                r.require(('istio-proxy' in names)==(ns==SIDECAR),'工作负载重复/遗漏接入 Sidecar')
        return {'passed':True}
    if name=='baseline':
        rows=[allowed(c,PLAIN,'allowed',PLAIN) for _ in range(10)]
        return {'passed':True,'samples':rows,'cri':resources(c,PLAIN,'server')}
    if name=='sidecar-policy':
        good=[allowed(c,SIDECAR,'allowed',SIDECAR) for _ in range(10)]
        denied=request(c,SIDECAR,'denied',SIDECAR);r.require(denied.get('status')==403 and 'rbac' in denied.get('body','').lower(),'未授权身份没有被 RBAC 拒绝')
        plain=request(c,PLAIN,'allowed',SIDECAR);r.require(plain.get('error') and not plain.get('status'),'STRICT mTLS 没有拒绝裸明文')
        allowed(c,SIDECAR,'allowed',SIDECAR)
        return {'passed':True,'samples':good,'denied':denied,'plaintext_rejected':plain,'mtls_metrics':mtls_metrics(c,SIDECAR),'cri':resources(c,SIDECAR,'server'),
            'public_certificate_metadata':r.call(istio(c,['proxy-config','secret','server.'+SIDECAR]))}
    if name=='traffic':
        nonce=uuid.uuid4().hex;failed=request(c,SIDECAR,'allowed',SIDECAR,'/fail',nonce=nonce)
        r.require(failed.get('status')==503,'故障后端应返回503')
        count=request(c,SIDECAR,'allowed',SIDECAR,'/counts?nonce='+nonce);attempts=json.loads(count['body'])['count']
        r.require(attempts==3,'有界重试应为原请求+2次，不应放大')
        slow=request(c,SIDECAR,'allowed',SIDECAR,'/slow')
        r.require(slow.get('status')==504 and slow['elapsed_ms']<1500,'超时预算未生效')
        return {'passed':True,'retry_attempts':attempts,'failure':failed,'timeout':slow,'control':allowed(c,SIDECAR,'allowed',SIDECAR)}
    if name=='ambient-l4':
        good=allowed(c,AMBIENT,'allowed',AMBIENT);denied=request(c,AMBIENT,'denied',AMBIENT)
        r.require(denied.get('error') and not denied.get('status'),'Ambient L4 身份策略没有阻断')
        allowed(c,AMBIENT,'allowed',AMBIENT)
        return {'passed':True,'allowed':good,'identity_denied':denied,'mtls_metrics':mtls_metrics(c,AMBIENT,True),
            'workloads':r.call(istio(c,['ztunnel-config','workloads','-o','json']))}
    if name=='waypoint':
        value=c.get('gateway','waypoint',AMBIENT)
        r.require(any(v['type']=='Programmed' and v['status']=='True' and v.get('observedGeneration')==value['metadata']['generation'] for v in value.get('status',{}).get('conditions',[])),'waypoint 未 Programmed')
        return {'passed':True,'uid':value['metadata']['uid']}
    if name=='ambient-l7':
        good=allowed(c,AMBIENT,'allowed',AMBIENT);bad=request(c,AMBIENT,'allowed',AMBIENT,'/blocked')
        r.require(bad.get('status')==403 and 'rbac' in bad.get('body','').lower(),'waypoint L7 路径策略未生效')
        wrong=request(c,AMBIENT,'allowed',AMBIENT,'/allowed',method='POST');r.require(wrong.get('status')==403,'waypoint 方法策略未生效')
        return {'passed':True,'allowed':good,'path_denied':bad,'method_denied':wrong}
    if name=='spire-server':
        return {'passed':True,'server':app(c,'spire-system','spire-server')['metadata']['uid']}
    if name=='spire-bundle':return {'passed':True,'bundle_sha256':hashlib.sha256(c.get('configmap','spire-bundle','spire-system')['data']['bundle.pem'].encode()).hexdigest()}
    if name=='spire-agent':
        value=c.get('daemonset','spire-agent','spire-system')
        r.require(value['status'].get('numberReady')==3,'SPIRE agent 未全部Ready')
        ids=agent_ids(json.loads(r.call(server_exec(c,['agent','list','-output','json']))));r.require(len(ids)==3,'PSAT节点证明未完成')
        return {'passed':True,'agents':ids}
    if name=='register':
        r.require(len(s.context.get('spire_entries',[]))==9,'注册条目不完整')
        return {'passed':True,'entries':s.context['spire_entries']}
    if name=='spire-workloads':
        for pod in ['server','allowed','denied','verifier']:app(c,SPIRE,pod)
        good=native_allowed(c,'allowed');denied=native(c,'denied')
        r.require(denied.get('class')=='identity_denied','不匹配 selector 的工作负载没有被身份API拒绝')
        return {'passed':True,'allowed':good,'unmatched_selector':denied,'control':native_allowed(c)}
    if name=='rotation':
        row=native(c,'allowed','watch')
        r.require(row.get('rotated') and len({v['serial'] for v in row['samples']})>=2,'SVID 未实际轮换')
        return {'passed':True,'rotation':row,'post_rotation_mtls':native_allowed(c,'allowed')}
    if name=='held':
        pod=app(c,SPIRE,'held');raw=r.call(c.k+['logs','-n',SPIRE,'held']);rows=[json.loads(line) for line in raw.splitlines() if line.startswith('{')]
        r.require(any(v.get('status')==200 for v in rows),'持有旧SVID的对照尚无成功样本')
        return {'passed':True,'pod_uid':pod['metadata']['uid'],'initial_samples':rows}
    if name=='revoke':
        denied=native(c,'allowed');r.require(denied.get('class')=='identity_denied','删除注册后仍能获取新SVID')
        raw=r.call(c.k+['logs','-n',SPIRE,'held']);(s.attempt/'held-svid.jsonl').write_text(raw)
        rows=[json.loads(line) for line in raw.splitlines() if line.startswith('{') and 'identity' in json.loads(line)]
        r.require(rows,'缺少旧SVID样本')
        deadline=datetime.fromisoformat(rows[0]['identity']['not_after'].replace('Z','+00:00'))
        expired=[v for v in rows if datetime.fromisoformat(v['at'].replace('Z','+00:00'))>deadline]
        r.require(expired and all(v.get('error') and not v.get('status') for v in expired),'旧SVID尚未到期或过期后仍可通信')
        return {'passed':True,'new_issuance_denied':denied,'old_certificate_expires_at':deadline.isoformat(),
            'old_certificate_samples':rows,'remaining_authorized_control':native_allowed(c),'scope':'撤销注册停止新签发；已签发证书按TTL到期，不宣称即时吊销全部证书'}
    if name=='handoff':
        value={'passed':True,'primary_cluster_uid':s.context['cluster_uid'],'isolated_cluster_uid':c.state['cluster_uid'],
            'root_trusts_integrated':False,'remaining_prerequisites':['公网入站/ACME','Ceph服务验证','主集群OpenWrt Egress Gateway迁移','共享VM节点压力排序'],
            'trace_slo_release_revisit':['Phase04完整Trace/SLO','Phase05发布联动'],'next_phase':'03'}
        r.save(s.records/'handoff-candidate.json',value);return value
    raise ValueError('未知观察 '+name)


def restore(s):
    return iso.Cluster(s).cleanup_plan() if s.context.get('isolation') else []


def final(s):
    if s.context.get('isolation'):iso.Cluster(s).final()
    row=r.pol.gw.probe.http('192.168.9.201','/mesh-final')
    r.require(row['status']==404 and row.get('tls_peer_sha256'),'主入口可信TLS异常')


def post_final(s,closed):
    path=s.records/'handoff-candidate.json'
    if path.exists() and (s.records/'passed.json').exists():
        value=json.loads(path.read_text());value.update(cleanup_passed=closed['cleanup_passed'],
            closed_sha256=hashlib.sha256((s.records/'state/closed.json').read_bytes()).hexdigest(),
            phase02_complete=False)
        r.save(s.records/'handoff.json',value)


if __name__=='__main__':cli.run(sys.modules[__name__])
