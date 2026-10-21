"""02.10 只读观察；所有集群与主机变更由主驱动返回给 Ansible。"""
from datetime import datetime
import hashlib
import http.client
import json
import re
import select
import subprocess
import time
import uuid
import runtime as r

SIDECAR, AMBIENT, PLAIN, SPIRE = 'lab-mesh-sidecar','lab-mesh-ambient','lab-mesh-plain','lab-spire'
SOCKET = '/run/spire/api.sock'


def istio(c,args):
    return [c.lock['tools']['istioctl']['path'],'--kubeconfig',c.state['kubeconfig']]+args


def server_exec(c,args):
    return c.k+['exec','-n','spire-system','spire-server','--','/opt/spire/bin/spire-server']+args+['-socketPath',SOCKET]


def app(c,namespace,pod):
    value=c.get('pod',pod,namespace)
    r.require(value['metadata'].get('labels',{}).get(r.LABEL)==c.s.run,'工作负载 run 不同')
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
        process.terminate()
        try:process.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill();process.communicate(timeout=4)


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


def observe(s,name,driver):
    c=driver.Cluster(s)
    if name=='preflight':return driver.primary(s)
    if name=='load':return driver.loaded(s)
    if name=='cilium':return driver.compatible(s)
    if name=='istio':
        driver.compatible(s)
        for kind,item in [('deployment','istiod-cnpl0210'),('daemonset','istio-cni-node'),('daemonset','ztunnel')]:
            obj=c.get(kind,item,'istio-system');value=obj['status']
            r.require(value.get('observedGeneration')==obj['metadata']['generation'],item+' 尚未观察本次配置')
            r.require((value.get('availableReplicas',0)>=1 if kind=='deployment' else value.get('numberReady')==2),item+' 尚未就绪')
        return {'passed':True,'cni_exclusive':False,'bpf_masquerade':False}
    if name=='applications':
        for ns in [SIDECAR,AMBIENT,PLAIN]:
            for pod in ['server','allowed','denied']:
                value=app(c,ns,pod);names={v['name'] for v in value['spec']['containers']+value['spec'].get('initContainers',[])}
                r.require(('istio-proxy' in names)==(ns==SIDECAR),'工作负载重复/遗漏接入 Sidecar')
                r.require(value['spec']['nodeName']==r.WORKERS[0 if pod=='server' else 1],'工作负载不在计划 VM')
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
    if name=='sidecar-restart':
        pod=app(c,SIDECAR,'allowed')
        r.require(pod['metadata']['uid']!=s.context['restart_before_uid'],'Sidecar 客户端没有完成退出和重建')
        names={v['name'] for v in pod['spec']['containers']+pod['spec'].get('initContainers',[])}
        r.require('istio-proxy' in names,'重建后未重新注入代理')
        return {'passed':True,'old_uid':s.context['restart_before_uid'],'new_uid':pod['metadata']['uid'],
            'authorized_after_restart':allowed(c,SIDECAR,'allowed',SIDECAR),'unmeshed_control':allowed(c,PLAIN,'allowed',PLAIN)}
    if name=='ambient-l4':
        rows=[allowed(c,AMBIENT,'allowed',AMBIENT) for _ in range(10)];good=rows[-1];denied=request(c,AMBIENT,'denied',AMBIENT)
        r.require(denied.get('error') and not denied.get('status'),'Ambient L4 身份策略没有阻断')
        allowed(c,AMBIENT,'allowed',AMBIENT)
        return {'passed':True,'allowed':good,'samples':rows,'cri':resources(c,AMBIENT,'server'),'identity_denied':denied,'mtls_metrics':mtls_metrics(c,AMBIENT,True),
            'workloads':r.call(istio(c,['ztunnel-config','workloads','-o','json']))}
    if name=='waypoint':
        value=c.get('gateway','waypoint',AMBIENT)
        r.require(any(v['type']=='Programmed' and v['status']=='True' and v.get('observedGeneration')==value['metadata']['generation'] for v in value.get('status',{}).get('conditions',[])),'waypoint 未 Programmed')
        deployment=c.get('deployment','waypoint',AMBIENT)
        r.require(any(o['uid']==value['metadata']['uid'] for o in deployment['metadata'].get('ownerReferences',[])),'waypoint Deployment 不属于本 Gateway')
        r.require(deployment['spec']['template']['spec']['nodeSelector'].get('kubernetes.io/hostname')==r.WORKERS[1] and deployment['status'].get('availableReplicas')==1,'waypoint 未在计划 Worker 就绪')
        return {'passed':True,'uid':value['metadata']['uid']}
    if name=='ambient-l7':
        rows=[allowed(c,AMBIENT,'allowed',AMBIENT) for _ in range(10)];good=rows[-1];bad=request(c,AMBIENT,'allowed',AMBIENT,'/blocked')
        r.require(bad.get('status')==403 and 'rbac' in bad.get('body','').lower(),'waypoint L7 路径策略未生效')
        wrong=request(c,AMBIENT,'allowed',AMBIENT,'/allowed',method='POST');r.require(wrong.get('status')==403,'waypoint 方法策略未生效')
        return {'passed':True,'allowed':good,'samples':rows,'path_denied':bad,'method_denied':wrong}
    if name=='measurements':
        values={}
        for case in ['baseline','sidecar-policy','ambient-l4','ambient-l7']:
            row=json.loads((s.attempt/(case+'.json')).read_text())
            samples=sorted(v['elapsed_ms'] for v in row['samples'])
            r.require(len(samples)==10,'延迟样本缺失：'+case)
            values[case]={'samples':len(samples),'p50_ms':samples[4],'p95_ms':samples[9],'cri':row.get('cri')}
        r.save(s.records/'measurements.json',values)
        return {'passed':True,'comparison':values,'unmeshed_control':allowed(c,PLAIN,'allowed',PLAIN),
            'scope':'十次串行真实请求与实际 CRI 累计计数；不外推吞吐、CPU 利用率或容量结论'}
    if name=='spire-server':
        return {'passed':True,'server':app(c,'spire-system','spire-server')['metadata']['uid']}
    if name=='spire-bundle':return {'passed':True,'bundle_sha256':hashlib.sha256(c.get('configmap','spire-bundle','spire-system')['data']['bundle.pem'].encode()).hexdigest()}
    if name=='spire-agent':
        value=c.get('daemonset','spire-agent','spire-system')
        r.require(value['status'].get('numberReady')==2,'SPIRE agent 未全部Ready')
        ids=driver.agent_ids(json.loads(r.call(server_exec(c,['agent','list','-output','json']))));r.require(len(ids)==2,'PSAT节点证明未完成')
        return {'passed':True,'agents':ids}
    if name=='register':
        r.require(len(s.context.get('spire_entries',[]))==6,'注册条目不完整')
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
        value={'passed':True,'primary_cluster_uid':s.context['cluster_uid'],'execution_backend':'vm-primary',
            'root_trusts_integrated':False,'remaining_prerequisites':['公网入站/ACME','Ceph服务验证','主集群OpenWrt Egress Gateway迁移','共享VM节点压力排序'],
            'trace_slo_release_revisit':['Phase04完整Trace/SLO','Phase05发布联动'],'next_phase':'03'}
        r.save(s.records/'handoff-candidate.json',value);return value
    raise ValueError('未知观察 '+name)
