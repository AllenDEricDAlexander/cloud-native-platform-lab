#!/usr/bin/env python3
"""资源治理、真实 cgroup 结果、限定低优先级抢占与按标签 drain。"""
import json
from pathlib import Path
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'phase02'))
import runtime as r
import cli
import yaml
materials=r.module('resource_materials',Path(__file__).with_name('materials.py'))

TOPIC,STAGE='resource-governance','02.08'
NAMESPACES=['lab-resource-app','lab-resource-build','lab-resource-test','lab-qos','lab-availability']
NS,APP=NAMESPACES[3],NAMESPACES[4]
WAIT_SECONDS=210
FAST_CASES=['quota-reject','limitrange-reject']
MARKER='cnpl.io/resource-maintenance'
BLOCKED={'whole_vm_pressure':{'status':'BLOCKED','reason':'现有十 VM 承载主线；不耗尽整 VM。实际执行 Pod OOM 与空卷限额驱逐，未验证节点压力下的 QoS 驱逐次序。'}}


def cpu_request(pod):
    spec=pod['spec']
    r.require(not spec.get('resources'),'现有 Pod 使用 PodLevelResources，需要更新请求核算后再抢占')
    request=lambda c:r.quantity(c.get('resources',{}).get('requests',{}).get('cpu','0'))
    running=sum(request(c) for c in spec.get('containers',[]))
    sidecars,peak=0.,0.
    for c in spec.get('initContainers',[]):
        if c.get('restartPolicy')=='Always':
            sidecars+=request(c);peak=max(peak,sidecars)
        else:
            peak=max(peak,sidecars+request(c))
    return max(running+sidecars,peak)+r.quantity(spec.get('overhead',{}).get('cpu','0'))


def prepare(s):
    nodes=[r.get('node',n) for n in r.WORKERS]
    original=nodes[1]
    r.require(MARKER not in original['metadata'].get('labels',{}),'有未恢复的节点维护标记')
    pods=json.loads(r.call(r.K+['get','pods','-A','--field-selector','spec.nodeName='+r.WORKERS[1],'-o','json']))['items']
    active=[p for p in pods if p['status'].get('phase') not in ['Succeeded','Failed']]
    r.require(all(p['spec'].get('priority',0)>-99999 for p in active),'目标 VM 有可能被测试优先级抢占的现有 Pod，停止')
    free=int(round((r.quantity(original['status']['allocatable']['cpu'])-sum(cpu_request(p) for p in active))*1000))
    r.require(free>=1000,'worker02 可分配 CPU 请求余量不足 1000m，停止')
    facts={}
    remote="python3 -c 'import json,shutil;v={p.split(\":\")[0]:int(p.split()[1])*1024 for p in open(\"/proc/meminfo\") if p.startswith(\"MemAvailable:\")};v[\"disk_free\"]=shutil.disk_usage(\"/var/lib/kubelet\").free;v[\"containerd_free\"]=shutil.disk_usage(\"/var/lib/containerd\").free;print(json.dumps(v))'"
    for vm in ['192.168.9.109','192.168.9.110']:
        raw=r.call(r.pol.ssh(vm,remote),timeout=20);value=json.loads(raw)
        r.require(value['MemAvailable']>=2*1024**3 and value['disk_free']>=10*1024**3,'VM 安全余量不足：'+vm)
        facts[vm]=value
    s.context.update(reserve_cpu=str(free-200)+'m',priority_low='cnpl-0208-low-'+s.run[-8:],
        priority_high='cnpl-0208-high-'+s.run[-8:],maintenance_node={'uid':original['metadata']['uid'],'unschedulable':original['spec'].get('unschedulable')},vm_margin=facts)
    r.save(s.path,s.context)
    lock=yaml.safe_load((r.ROOT/'ops/versions.lock.yaml').read_text())['components']['resource_fixture']['platforms']['amd64']
    materials.verify(s.attempt/'materials')
    s.render({'image':lock['internal_source'],**{k:s.context[k] for k in ['reserve_cpu','priority_low','priority_high']}})


def steps(s):
    return yaml.safe_load((r.PHASE/'networking/resource-governance/cases.yml').read_text())


def validate(s):
    documents=[obj for file in s.attempt.glob('*.yaml') for obj in yaml.safe_load_all(file.read_text()) if obj]
    classes={obj['metadata']['name']:obj for obj in documents if obj['kind']=='PriorityClass'}
    deferred=[]
    for obj in documents:
        clone=json.loads(json.dumps(obj))
        if clone['kind'] not in ['Namespace','PriorityClass']:
            clone['metadata']['namespace']='lab-core'
            clone['metadata']['name']='cnpl-preview-'+clone['metadata']['name']
        if clone['kind']=='Pod' and clone['spec'].get('priorityClassName'):
            name=clone['spec']['priorityClassName'];r.require(name in classes,'未声明的 PriorityClass 引用')
            r.require(classes[name]['value'] in [-100000,-99999] and not classes[name].get('globalDefault'),'测试优先级边界错误')
            deferred.append({'pod':obj['metadata']['name'],'priorityClassName':name})
            del clone['spec']['priorityClassName']
        r.call(r.K+['apply','--dry-run=server','--validate=strict','-f','-'],json.dumps(clone))
    return {'passed':True,'server_dry_run_objects':len(documents),'priority_reference_structure_checked':deferred,
        'priority_reference_admission':'实际创建本批 PriorityClass 后，原 Pod 在真实 Namespace apply 前再次严格预览','persisted':False}


def controlled_pods(s):
    deployment=r.get('deployment','pdb-demo',APP)
    path=s.receipt(s.document('Deployment','pdb-demo',APP))
    r.require(path.exists() and json.loads(path.read_text())['uid']==deployment['metadata']['uid'],'PDB Deployment UID 不同')
    sets={p['metadata']['uid']:p for p in r.get('replicasets',namespace=APP)['items']
          if any(o.get('uid')==deployment['metadata']['uid'] for o in p['metadata'].get('ownerReferences',[]))}
    result=[]
    for pod in r.get('pods',namespace=APP)['items']:
        if pod['metadata'].get('labels',{}).get('app')!='pdb-demo':
            continue
        r.require(pod['metadata'].get('labels',{}).get(r.LABEL)==s.run and any(o.get('uid') in sets for o in pod['metadata'].get('ownerReferences',[])),'选中的 Pod 不是本批控制器后代')
        result.append(pod)
    return result


def maintenance(s,cordon):
    node=r.get('node',r.WORKERS[1]);original=s.context['maintenance_node']
    r.require(node['metadata']['uid']==original['uid'],'维护 Node UID 不同')
    marker=node['metadata'].get('labels',{}).get(MARKER)
    current=node['spec'].get('unschedulable')
    if not cordon and marker is None:
        r.require(current==original['unschedulable'],'Node 已被其他操作封锁，拒绝解锁')
        return []
    r.require(marker in [None,s.run],'Node 维护标记属于其他操作')
    patches=[{'op':'test','path':'/metadata/uid','value':original['uid']},
             {'op':'test','path':'/metadata/resourceVersion','value':node['metadata']['resourceVersion']}]
    path='/metadata/labels/'+MARKER.replace('/','~1')
    if cordon:
        r.require(current==original['unschedulable'] or marker==s.run,'Node 已被外部封锁')
        if marker==s.run and current is True:return []
        patches += [{'op':'add','path':path,'value':s.run},{'op':'add','path':'/spec/unschedulable','value':True}]
    else:
        r.require(marker==s.run and current is True,'维护字段被外部改变')
        patches += [{'op':'remove','path':path}]
        patches += [{'op':'remove','path':'/spec/unschedulable'}] if original['unschedulable'] is None else [{'op':'add','path':'/spec/unschedulable','value':original['unschedulable']}]
    file=s.attempt/('maintenance-'+str(cordon)+'.json');r.save(file,patches)
    return [s.command(r.K+['patch','node',r.WORKERS[1],'--type=json','--patch-file',file,'-o','json'])]


def plan(s,name):
    if name in ['quota-reject','limitrange-reject']:
        return [s.command(r.K+['apply','--dry-run=server','--validate=strict','-f',s.attempt/(name+'.yaml')],allowed_rc=[1])]
    if name in ['drain-blocked','drain-allowed']:
        pods=controlled_pods(s)
        selected=[p for p in pods if p['spec'].get('nodeName')==r.WORKERS[1] and not p['metadata'].get('deletionTimestamp')]
        r.require(len(selected)==1,'维护目标应恰有一个本批 PDB Pod')
        r.save(s.attempt/(name+'-selected.json'),{'uid':selected[0]['metadata']['uid'],'name':selected[0]['metadata']['name']})
        return maintenance(s,True)+[s.command(r.K+['drain',r.WORKERS[1],'--pod-selector='+r.LABEL+'='+s.run+',app=pdb-demo','--ignore-daemonsets','--grace-period=10','--timeout='+('8s' if name=='drain-blocked' else '60s')],allowed_rc=[1] if name=='drain-blocked' else [0])]
    if name=='uncordon':
        return maintenance(s,False)
    if name=='direct-delete':
        pods=[p for p in controlled_pods(s) if r.pol.base.ready(p)]
        r.require(len(pods)==2,'直接删除对照前必须两个副本 Ready')
        pod=pods[0];r.save(s.receipt(pod),{'key':s.key(pod),'uid':pod['metadata']['uid'],'run':s.run})
        r.save(s.attempt/'direct-delete-selected.json',{'uid':pod['metadata']['uid'],'name':pod['metadata']['name']})
        return s.delete(pod)
    return []


def healthy_nodes():
    for node in r.WORKERS:
        value=r.get('node',node)
        r.require(r.pol.base.ready(value) and all(c['status']=='False' for c in value['status']['conditions'] if c['type'].endswith('Pressure')),'VM Ready/压力状态异常：'+node)


def pdb_state(allowed):
    value=r.get('pdb','availability',APP)
    status=value.get('status',{})
    r.require(status.get('observedGeneration')==value['metadata']['generation'] and status.get('disruptionsAllowed')==allowed,'等待 PDB 预算收敛')
    return {'uid':value['metadata']['uid'],'status':status}


def service_probe(s):
    nonce=uuid.uuid4().hex
    probe={'target':'http://pdb-demo.'+APP+'.svc.cluster.local:8080/allowed','nonce':nonce,'timeout_ms':5000}
    raw=r.call(r.K+['exec','-i','-n',NS,'guaranteed','--','/phase-lab','probe'],json.dumps(probe))
    value=json.loads(raw);r.require(value.get('status')==200 and not value.get('error'),'维护中服务不可达')
    body=json.loads(value['body']);r.require(body.get('nonce')==nonce and any(p['metadata']['uid']==body.get('uid') for p in controlled_pods(s)),'维护响应不是本批服务')
    return value


def observe(s,name):
    healthy_nodes()
    if name=='budgets':
        return {'passed':True,'quotas':{ns:r.get('resourcequota','budget',ns)['spec'] for ns in NAMESPACES[:3]}}
    if name=='defaulted':
        row=s.ready('defaulted',ns=NAMESPACES[0]);pod=s.pod('defaulted',NAMESPACES[0])
        resource=pod['spec']['containers'][0]['resources']
        r.require(resource['requests']['cpu']=='100m' and resource['limits']['cpu']=='200m','LimitRange 默认值没有注入')
        return {'passed':True,'pod':row,'resources':resource}
    if name in ['quota-reject','limitrange-reject']:
        results=json.loads((s.attempt/('commands-'+name+'.json')).read_text())['results']
        text=' '.join(v.get('stderr','')+' '+v.get('stdout','') for v in results).lower()
        if name=='quota-reject':r.require('exceeded quota' in text and 'budget' in text,'失败并非配额拒绝')
        else:r.require('maximum cpu usage' in text or 'limitrange' in text,'失败并非 LimitRange 拒绝')
        return {'passed':True,'expected_admission_rejection':text}
    if name=='qos':
        values={}
        for pod,klass in [('guaranteed','Guaranteed'),('burstable','Burstable'),('besteffort','BestEffort')]:
            s.ready(pod,ns=NS);value=s.pod(pod,NS)
            r.require(value['status'].get('qosClass')==klass,'QoS 类不符：'+pod);values[pod]=klass
        return {'passed':True,'actual_qos':values}
    if name=='cpu':
        pod=s.pod('cpu',NS);r.require(pod['status'].get('phase')=='Succeeded','CPU 负载尚未成功退出')
        value=json.loads(r.call(r.K+['logs','-n',NS,'cpu']))
        r.require(value['after'].get('nr_throttled',0)>value['before'].get('nr_throttled',0)
                  and value['after'].get('throttled_usec',0)>value['before'].get('throttled_usec',0),'没有真实 cgroup CPU 限流增量')
        return {'passed':True,**value}
    if name=='memory':
        pod=s.pod('memory',NS);statuses=pod.get('status',{}).get('containerStatuses') or []
        terminated=(statuses[0].get('state',{}).get('terminated') or {}) if statuses else {}
        r.require(terminated.get('reason')=='OOMKilled' and terminated.get('exitCode')==137,'等待 Pod 内存上限触发的 OOMKilled')
        return {'passed':True,'qos':pod['status'].get('qosClass'),'terminated':terminated,'node_pressure':False}
    if name=='disk':
        pod=s.pod('disk',NS);status=pod.get('status',{})
        message=status.get('message','')
        r.require(status.get('reason')=='Evicted' and any(x in message.lower() for x in ['emptydir','ephemeral-storage']),'等待空卷/临时存储限额驱逐')
        return {'passed':True,'status':status,'node_disk_pressure':False}
    if name=='reserve':
        return s.ready('reserve',r.WORKERS[1],NS)
    if name=='preemptor':
        high=s.ready('preemptor',r.WORKERS[1],NS)
        r.require(r.optional('Pod','reserve',NS) is None,'低优先级本批预留 Pod 尚未被抢占')
        events=r.get('events',namespace=NS)['items']
        old=json.loads(s.receipt(s.document('Pod','reserve',NS)).read_text())['uid']
        evidence=[e for e in events if e.get('involvedObject',{}).get('uid')==old and ('preempt' in e.get('reason','').lower() or 'preempt' in e.get('message','').lower())]
        r.require(evidence,'缺少本次低优先级 Pod 的抢占事件')
        return {'passed':True,'preemptor':high,'victim_uid':old,'events':evidence}
    if name in ['pdb','pdb-one','pdb-two']:
        wanted=1 if name=='pdb-one' else 0
        pods=[p for p in controlled_pods(s) if r.pol.base.ready(p)]
        r.require(len(pods)==2 and len({p['spec']['nodeName'] for p in pods})==2,'PDB 应有两个不同 VM 的就绪副本')
        return {'passed':True,'pdb':pdb_state(wanted),'service':service_probe(s)}
    if name=='drain-blocked':
        results=json.loads((s.attempt/'commands-drain-blocked.json').read_text())['results']
        text=' '.join(v.get('stderr','')+' '+v.get('stdout','') for v in results).lower()
        r.require('disruption budget' in text or 'disruptionbudget' in text,'drain 并非被 PDB 阻止')
        return {'passed':True,'pdb':pdb_state(0),'service':service_probe(s),'drain_scope':'本批 app=pdb-demo 标签'}
    if name=='drain-allowed':
        old=json.loads((s.attempt/'drain-allowed-selected.json').read_text())
        r.require(not any(p['metadata']['uid']==old['uid'] for p in controlled_pods(s)),'原维护 Pod 未删除')
        return {'passed':True,'removed_uid':old['uid'],'service':service_probe(s)}
    if name=='uncordon':
        r.require(not r.get('node',r.WORKERS[1])['spec'].get('unschedulable'),'VM 未恢复调度')
        return observe(s,'pdb-one')
    if name=='direct-delete':
        old=json.loads((s.attempt/'direct-delete-selected.json').read_text())
        r.require(not any(p['metadata']['uid']==old['uid'] for p in controlled_pods(s)),'原 Pod 未删除')
        value=observe(s,'pdb')
        return {'passed':True,'direct_delete_bypassed_pdb':True,'deleted_uid':old['uid'],'restored':value}
    raise ValueError('未定义观察：'+name)


def restore(s):
    return maintenance(s,False) if s.context.get('maintenance_node') else []


def final(s):
    healthy_nodes()
    if s.context.get('maintenance_node'):
        node=r.get('node',r.WORKERS[1])
        r.require(node['metadata']['uid']==s.context['maintenance_node']['uid'] and not node['spec'].get('unschedulable') and MARKER not in node['metadata'].get('labels',{}),'维护字段未恢复')
    row=r.pol.gw.probe.http('192.168.9.201','/resource-final')
    r.require(row['status']==404 and row.get('tls_peer_sha256'),'主入口可信 TLS 异常')


if __name__=='__main__':
    cli.run(sys.modules[__name__])
