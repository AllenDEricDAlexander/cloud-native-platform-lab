"""现有十 VM 主集群的数据面对照；管理端只生成计划、只读取证。"""
import copy
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import shlex
import sys
import uuid
import yaml
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'phase02'))
import runtime as r

TOPIC,STAGE='dataplane','02.09'
NS,ADMIN='lab-dataplane-vm','lab-dataplane-vm-admin'
NAMESPACES=[NS,ADMIN]
HELM=str(Path.home()/'.cnpl/bin/helm')
KC=str(Path.home()/'.cnpl-secrets/kubeconfig-lab-primary')
WAIT_SECONDS=420
EXCLUDE='cnpl.io/phase02-l2-exclude'
PROXY_OFF='cnpl.io/phase02-proxy-off'
RESTORE_STEPS=[{'name':name} for name in ['recover-announcements','recover-proxy','recover-cilium','recover-routes','recover-labels','recover-original','recover-firewall']]
BLOCKED={'external_bgp_forwarding':{'status':'BLOCKED','reason':'本批 FRR 是 VM 集群内的软件邻居，验证会话、限定 RIB 和撤回；没有独立上游设备，不把 Pod 内 Service 访问算作外部 BGP 转发验收。'}}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def helm(*args):
    return [HELM,'--kubeconfig',KC]+list(args)


def release():
    releases=json.loads(r.call(helm('list','-n','kube-system','-o','json')))
    row=next((value for value in releases if value['name']=='cilium'),None)
    r.require(row and row['chart']=='cilium-1.20.2','原 Cilium Helm release 或版本不符')
    return row


def controllers():
    return [o for o in r.get('daemonsets,deployments',namespace='kube-system')['items']
            if o['metadata'].get('annotations',{}).get('meta.helm.sh/release-name')=='cilium'
            or o['kind']=='DaemonSet' and o['metadata']['name']=='kube-proxy']


class Session(r.Session):
    def sources(self):
        result=super().sources()
        for file in [r.ROOT/'AGENTS.md',r.PHASE/'ansible/tasks/dataplane-cleanup.yml']:
            result[str(file.relative_to(r.ROOT))]=hashlib.sha256(file.read_bytes()).hexdigest()
        return dict(sorted(result.items()))

    def protected(self):
        values=super().protected()
        managed=controllers()
        uids={o['metadata']['uid'] for o in managed}
        for obj in managed:
            values[self.key(obj)]={'uid':obj['metadata']['uid']}
        cm=r.get('configmap','cilium-config','kube-system')
        values['ConfigMap/kube-system/cilium-config']={'uid':cm['metadata']['uid']}
        replicas=r.get('replicasets',namespace='kube-system')['items']
        uids|={o['metadata']['uid'] for o in replicas if any(v['uid'] in uids for v in o['metadata'].get('ownerReferences',[]))}
        for pod in r.get('pods',namespace='kube-system')['items']:
            if any(v['uid'] in uids for v in pod['metadata'].get('ownerReferences',[])):
                values.pop(self.key(pod),None)
        name='cnpl-dp-'+self.run[-8:]
        for kind in ['deployments','services','pods']:
            for obj in r.get(kind,namespace='envoy-gateway-system')['items']:
                labels=obj['metadata'].get('labels',{})
                if labels.get(r.LABEL)==self.run and (obj['metadata']['name']==name or kind=='pods' and obj['metadata']['name'].startswith(name+'-')):
                    values.pop(self.key(obj),None)
        return values

    def owned(self,obj):
        kind=obj['kind'];meta=obj['metadata']
        if kind in ['CiliumLoadBalancerIPPool','CiliumL2AnnouncementPolicy','CiliumBGPClusterConfig','CiliumBGPPeerConfig','CiliumBGPAdvertisement']:
            r.require(meta['name']==self.context['dp_name'] and meta.get('labels',{}).get(r.LABEL)==self.run,'全局测试对象越界')
            return
        if kind=='CustomResourceDefinition':
            r.require(meta['name'] in self.context['crd_inputs'] and meta.get('labels',{}).get(r.LABEL)==self.run,'CRD 输入越界')
            return
        super().owned(obj)

    def cleanup(self):
        commands=[]
        for kind in ['CiliumBGPAdvertisement','CiliumBGPClusterConfig','CiliumBGPPeerConfig','CiliumL2AnnouncementPolicy','CiliumLoadBalancerIPPool']:
            obj=self.document(kind,self.context['dp_name'])
            if self.receipt(obj).exists():
                commands+=self.delete(obj)
        gateway=self.document('Gateway','edge',NS)
        if self.receipt(gateway).exists():commands+=self.delete(gateway)
        commands+=super().cleanup()
        return commands


def profile(name):
    r.require(name in ['ebpf','native','l2','bgp'],'未知 VM 数据面模式')
    return {'kubeProxyReplacement':True,'k8sServiceHost':'192.168.9.100','k8sServicePort':6443,
            'routingMode':'native' if name=='native' else 'tunnel','tunnelProtocol':'vxlan',
            'autoDirectNodeRoutes':name=='native','ipv4NativeRoutingCIDR':'10.244.0.0/16',
            'devices':['ens33'],'bpf':{'masquerade':True},
            'l2announcements':{'enabled':name=='l2','leaseDuration':'6s','leaseRenewDeadline':'2s','leaseRetryPeriod':'1s'},
            'bgpControlPlane':{'enabled':name=='bgp'}}


def untouched(values):
    value=copy.deepcopy(values)
    for key in profile('ebpf'):
        if key in ['bpf','l2announcements','bgpControlPlane']:
            for child in profile('ebpf')[key]:
                value.get(key,{}).pop(child,None)
            if value.get(key)=={}:value.pop(key,None)
        else:value.pop(key,None)
    return value


def values():
    # 输出只在进程内解析；可能包含 Helm TLS 配置，绝不写公开证据或 stdout。
    return json.loads(r.call(helm('get','values','cilium','-n','kube-system','-o','json')))


def guard(s):
    r.require(r.get('namespace','kube-system')['metadata']['uid']==s.context['cluster_uid'],'VM 主集群 UID 不同')
    r.require(r.call(r.K+['config','view','--minify','-o','jsonpath={.clusters[0].cluster.server}']).strip()=='https://api.k8s.internal.egon.top:6443','VM kubeconfig 指向其他 API')
    current=release()
    r.require(int(current['revision']) in s.context['owned_revisions'],'Cilium Helm revision 被其他操作改变')
    r.require(digest(untouched(values()))==s.context['untouched_values_sha256'],'本批以外的 Helm 值被改变')
    for name,uid in s.context['node_uids'].items():
        r.require(r.get('node',name)['metadata']['uid']==uid,'VM Node UID 改变：'+name)


def remote_facts(ip):
    program="""import json,shutil,subprocess
def run(*args):return subprocess.check_output(args,text=True).strip()
print(json.dumps({'hostname':run('hostname'),'selinux':run('getenforce'),'firewalld':run('systemctl','is-active','firewalld'),
 'links':json.loads(run('ip','-j','link','show','ens33')),'routes':json.loads(run('ip','-j','-4','route','show')),
 'forward':run('sysctl','-n','net.ipv4.ip_forward'),'rp_filter':run('sysctl','-n','net.ipv4.conf.ens33.rp_filter'),
 'rich_rules':sorted(run('firewall-cmd','--zone=public','--list-rich-rules').splitlines()),
 'permanent_rules':sorted(run('firewall-cmd','--permanent','--zone=public','--list-rich-rules').splitlines()),
 'zone':run('firewall-cmd','--get-zone-of-interface=ens33'),'arping':shutil.which('arping')}))
"""
    return json.loads(r.call(r.pol.ssh(ip,shlex.join(['python3','-c',program])),timeout=25))


def prepare(s):
    row=release();r.require(row['status']=='deployed','Cilium release 不是 deployed')
    original=values()
    r.require(original.get('ipam',{}).get('mode')=='cluster-pool','VM 入口需要原 cluster-pool IPAM，不能切换地址分配器')
    r.require(str(original.get('kubeProxyReplacement')).lower()=='false' and original.get('routingMode')=='tunnel','需要原 kube-proxy/VXLAN 基线')
    r.require(all(str(original.get(key,{}).get('enabled',False)).lower()!='true' for key in ['bgpControlPlane','l2announcements']),'原集群已有启用的 BGP/L2 能力，不能覆盖')
    lock=yaml.safe_load((r.ROOT/'ops/versions.lock.yaml').read_text())['components']
    component=lock['dataplane_vm'];chart=lock['cilium']['chart']
    r.require(hashlib.sha256(Path(chart['local_source']).read_bytes()).hexdigest()==chart['sha256'],'Cilium Chart 摘要不符')
    nodes=r.get('nodes')['items'];cidrs={}
    for obj in r.get('ciliumnodes')['items']:
        blocks=obj['spec'].get('ipam',{}).get('podCIDRs') or []
        r.require(len(blocks)==1 and ipaddress.ip_network(blocks[0]).subnet_of(ipaddress.ip_network('10.244.0.0/16')),'CiliumNode PodCIDR 不符')
        cidrs[obj['metadata']['name']]=blocks[0]
    r.require(set(cidrs)==set(r.pol.base.NODES),'需要十 VM 的真实 CiliumNode 地址块')
    for obj in nodes:
        r.require(EXCLUDE not in obj['metadata'].get('labels',{}) and PROXY_OFF not in obj['metadata'].get('labels',{}),'有未恢复的本专题 Node 标签')
    facts={name:remote_facts(ip) for name,ip in r.pol.base.NODES.items()}
    r.require(all(v['hostname']==n and v['selinux']=='Enforcing' and v['firewalld']=='active' and v['forward']=='1' and v['links'][0]['mtu']>=1500 for n,v in facts.items()),'VM 原路由、安全状态或 MTU 不满足')
    arping=facts[r.WORKERS[0]]['arping'];r.require(arping,'VM 缺少原生 arping，不能核对 VIP 冲突')
    for ip in component['vip_addresses']:
        r.call(r.pol.ssh(r.pol.base.NODES[r.WORKERS[0]],shlex.join([arping,'-D','-I','ens33','-c','2','-w','2',ip])),timeout=12)
    ports={p['nodePort'] for svc in json.loads(r.call(r.K+['get','services','-A','-o','json']))['items'] for p in svc['spec'].get('ports',[]) if p.get('nodePort')}
    r.require(not {31080,31090}&ports,'实验 NodePort 已被占用')
    for svc in json.loads(r.call(r.K+['get','services','-A','-o','json']))['items']:
        for ip in (svc.get('status',{}).get('loadBalancer',{}).get('ingress') or []):
            r.require(ip.get('ip') not in component['vip_addresses'],'Cilium 测试 VIP 已被使用')
    for pool in r.get('ipaddresspools',namespace='metallb-system')['items']:
        for address in pool['spec'].get('addresses',[]):
            version,left,right=r.pol.gw.l2.ip_bounds(address)
            r.require(version==4 and not any(left<=int(ipaddress.ip_address(ip))<=right for ip in component['vip_addresses']),'Cilium VIP 与 MetalLB 地址池重叠')
    r.require(not r.get('ciliumloadbalancerippools')['items'],'已有 Cilium IPAM Pool，需要重新核对地址归属')
    for crd,kind in [('ciliuml2announcementpolicies.cilium.io','ciliuml2announcementpolicies'),
                     ('ciliumbgpclusterconfigs.cilium.io','ciliumbgpclusterconfigs'),
                     ('ciliumbgpnodeconfigoverrides.cilium.io','ciliumbgpnodeconfigoverrides')]:
        if r.optional('crd',crd) is not None:
            r.require(not r.get(kind)['items'],'存在其他归属的 '+kind+'，停止')
    snapshots={o['kind']+'/'+o['metadata']['name']:{'uid':o['metadata']['uid'],'spec':o['spec']} for o in controllers()}
    crds=component['schemas']
    crd_inputs={yaml.safe_load(Path(v['path']).read_text())['metadata']['name']:v for v in crds.values()}
    for item in crd_inputs.values():
        r.require(hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item['sha256'],'CRD schema 摘要不符')
    for key in ['resource_fixture']:
        image=lock[key]['platforms']['amd64']['internal_source']
        expected=lock[key]['platforms']['amd64']['manifest_digest']
        r.require(r.call(['/opt/homebrew/bin/crane','digest','--platform','linux/amd64',image]).strip()==expected,'amd64 实验镜像摘要不符')
    frr=component['frr']
    r.require(r.call(['/opt/homebrew/bin/crane','digest','--platform','linux/amd64',frr['internal_source']]).strip()==frr['manifest_digest'],'FRR amd64 镜像未准备')
    s.context.update(execution_backend='vm-primary',dp_name='cnpl-dp-'+s.run[-8:],original_revision=int(row['revision']),
        owned_revisions=[int(row['revision'])],original_values_sha256=digest(original),untouched_values_sha256=digest(untouched(original)),
        original_manifest_sha256=hashlib.sha256(r.call(helm('get','manifest','cilium','-n','kube-system')).encode()).hexdigest(),
        original_cilium_config_sha256=digest(r.get('configmap','cilium-config','kube-system')['data']),
        controllers=snapshots,node_uids={o['metadata']['name']:o['metadata']['uid'] for o in nodes},pod_cidrs=cidrs,
        vm_facts=facts,chart=chart,crd_inputs=crd_inputs,component_crds_retained=[],original_label_values={name:None for name in r.WORKERS},
        firewall_rules={})
    r.save(s.path,s.context)
    (s.records/'state').mkdir(exist_ok=True)
    r.save(s.records/'state/controllers-before.json',snapshots)
    fixture=lock['resource_fixture']['platforms']['amd64']
    eg=r.get('envoyproxy','primary','cnpl-gateway')['spec']['provider']['kubernetes']['envoyDeployment']
    gateway_image=next(c['image'] for c in eg['patch']['value']['spec']['template']['spec']['containers'] if c['name']=='shutdown-manager')
    proxy_image=r.get('daemonset','kube-proxy','kube-system')['spec']['template']['spec']['containers'][0]['image']
    proxy_digest=r.call(['/opt/homebrew/bin/crane','digest','--platform','linux/amd64',proxy_image]).strip()
    r.require(re.fullmatch(r'sha256:[0-9a-f]{64}',proxy_digest),'原 kube-proxy 镜像摘要无效')
    s.render({'image':fixture['internal_source'],'envoy_image':eg['container']['image'],'gateway_image':gateway_image,
        'name':s.context['dp_name'],'frr_image':frr['internal_source'],'frr_ip':'10.244.8.254',
        'kube_proxy_image':proxy_image.split('@')[0]+'@'+proxy_digest,
        'nodes':list(r.pol.base.NODES),'gateway_class':'cnpl-envoy','workers':r.WORKERS,'pod_cidrs':cidrs,
        'vip_addresses':component['vip_addresses']})


def steps(s):
    return yaml.safe_load((r.PHASE/'networking/dataplane/cases.yml').read_text())


def validate(s):
    definitions=[]
    for value in s.context['crd_inputs'].values():
        obj=yaml.safe_load(Path(value['path']).read_text());definitions.append(obj)
        r.call(r.K+['apply','--server-side','--field-manager=cnpl-gateway-crds','--dry-run=server','--validate=strict','-f','-'],json.dumps(obj))
    gateway=[d for d in r.pol.gw.mat.crds() if d['kind']=='CustomResourceDefinition']
    for obj in gateway:
        r.call(r.K+['apply','--server-side','--field-manager=cnpl-gateway-crds','--dry-run=server','--validate=strict','-f','-'],json.dumps(obj))
    custom=[];builtins=0
    for file in s.attempt.glob('*.yaml'):
        for obj in yaml.safe_load_all(file.read_text()):
            if not obj:continue
            if obj['kind'] in ['Gateway','EnvoyProxy','HTTPRoute','CiliumLoadBalancerIPPool','CiliumL2AnnouncementPolicy','CiliumBGPClusterConfig','CiliumBGPPeerConfig','CiliumBGPAdvertisement']:
                custom.append(obj);continue
            clone=copy.deepcopy(obj)
            if obj['kind']!='Namespace':
                clone['metadata']['namespace']='kube-system' if obj['metadata']['namespace']==ADMIN else 'lab-core'
                clone['metadata']['name']='cnpl-preview-'+obj['metadata']['name']
            r.call(r.K+['apply','--dry-run=server','--validate=strict','-f','-'],json.dumps(clone));builtins+=1
    structural=r.pol.gw.mat.validate_custom(custom,definitions+gateway)
    original=values();profiles={}
    for name in ['ebpf','native','l2','bgp']:
        merged=copy.deepcopy(original)
        for key,value in profile(name).items():
            if isinstance(value,dict):merged.setdefault(key,{}).update(value)
            else:merged[key]=value
        raw=r.call(helm('template','cilium',s.context['chart']['local_source'],'-n','kube-system','--kube-version','1.36.5','-f','-'),json.dumps(merged),timeout=90)
        docs=[obj for obj in yaml.safe_load_all(raw) if obj and obj['kind']!='Secret']
        r.save(s.attempt/('rendered-'+name+'.json'),docs)
        profiles[name]={'non_secret_objects':len(docs)}
    return {'passed':True,'backend':'vm-primary','builtin_server_dry_run':builtins,'custom_structure':structural,
        'crd_server_side_previews':len(definitions)+len(gateway),'profiles':profiles,'mac_container_runtime_used':False,'runtime_executed':False}


def patch_spec(s,kind,name,before,wanted):
    current=r.get(kind,name,'kube-system')
    r.require(current['metadata']['uid']==before['uid'],'控制器 UID 改变')
    if current['spec']==wanted:return []
    file=s.attempt/('patch-'+kind+'-'+name+'.json')
    r.save(file,[{'op':'test','path':'/metadata/uid','value':before['uid']},{'op':'test','path':'/spec','value':current['spec']},{'op':'replace','path':'/spec','value':wanted}])
    return [s.command(r.K+['patch',kind,name,'-n','kube-system','--type=json','--patch-file',file,'-o','name'])]


def label(s,node,remove=False):
    obj=r.get('node',node);r.require(obj['metadata']['uid']==s.context['node_uids'][node],'Node UID 改变')
    current=obj['metadata'].get('labels',{});value=current.get(EXCLUDE)
    r.require(value in [None,s.run],'实验标签被其他操作改变')
    if remove and value is None:return []
    patches=[{'op':'test','path':'/metadata/uid','value':obj['metadata']['uid']},{'op':'test','path':'/metadata/labels','value':current}]
    patches.append({'op':'remove','path':'/metadata/labels/'+EXCLUDE.replace('/','~1')} if remove else {'op':'add','path':'/metadata/labels/'+EXCLUDE.replace('/','~1'),'value':s.run})
    file=s.attempt/('node-label-'+node+'.json');r.save(file,patches)
    return [s.command(r.K+['patch','node',node,'--type=json','--patch-file',file,'-o','name'])]


def plan(s,name):
    if name=='recover-firewall':
        r.require(r.get('namespace','kube-system')['metadata']['uid']==s.context['cluster_uid'],'回收规则时集群 UID 改变')
        r.require(all(r.get('node',node)['metadata']['uid']==s.context['node_uids'][node] for node in r.WORKERS),'回收规则时 Node UID 改变')
    else:guard(s)
    if name=='recover-announcements':
        commands=[]
        for kind in ['CiliumBGPAdvertisement','CiliumBGPClusterConfig','CiliumBGPPeerConfig','CiliumL2AnnouncementPolicy','CiliumLoadBalancerIPPool']:
            obj=s.document(kind,s.context['dp_name'])
            if s.receipt(obj).exists():commands+=s.delete(obj)
        return commands
    if name=='crds':
        docs=[]
        for crd,value in s.context['crd_inputs'].items():
            if r.optional('crd',crd) is None:
                obj=yaml.safe_load(Path(value['path']).read_text());obj['metadata'].setdefault('labels',{})[r.LABEL]=s.run;docs.append(obj)
        file=s.attempt/'component-crds.yaml';file.write_text(yaml.safe_dump_all(docs))
        return s.apply(file.name)
    if name in ['ebpf-enable','native-enable','l2-enable','bgp-enable']:
        desired=profile(name.removesuffix('-enable'));file=s.attempt/(name+'.values.yaml');file.write_text(yaml.safe_dump(desired))
        revision=int(release()['revision'])+1;s.context['owned_revisions']=sorted(set(s.context['owned_revisions']+[revision]))
        if name=='native-enable':s.context['native_intent']=True
        r.save(s.path,s.context)
        return [s.command(helm('upgrade','cilium',s.context['chart']['local_source'],'-n','kube-system','--reuse-values','-f',str(file),'--history-max','20','--wait','--timeout','8m'))]
    if name=='proxy-pause':
        before=s.context['controllers']['DaemonSet/kube-proxy'];wanted=copy.deepcopy(before['spec'])
        wanted['template']['spec'].setdefault('nodeSelector',{})[PROXY_OFF]=s.run
        s.context['proxy_pause_intent']=True;r.save(s.path,s.context)
        return patch_spec(s,'DaemonSet','kube-proxy',before,wanted)
    if name=='access':
        port=gateway_ready(s)['node_port'];rules={}
        for node in r.WORKERS:
            target=r.pol.base.NODES[node]
            rule=lambda destination,p:'rule priority="-100" family="ipv4" source address="192.168.9.200/32" destination address="'+destination+'/32" port port="'+str(p)+'" protocol="tcp" accept'
            rules[node]=sorted(set([rule(target,p) for p in [31080,port]]+[rule(ip,8080) for ip in ['192.168.9.211','192.168.9.212','192.168.9.213','192.168.9.214']]))
            before=s.context['vm_facts'][node]
            r.require(before['zone']=='public' and not set(rules[node])&(set(before['rich_rules'])|set(before['permanent_rules'])),'实验访问规则已有外部归属')
        s.context['firewall_rules']=rules;r.save(s.path,s.context)
        return [s.command(r.pol.ssh(r.pol.base.NODES[node],shlex.join(['firewall-cmd','--zone=public','--add-rich-rule='+rule,'--timeout=7200']))) for node,items in rules.items() for rule in items]
    if name=='bgp':
        pod=s.pod('frr',ADMIN)
        file=s.attempt/'bgp.yaml';docs=list(yaml.safe_load_all(file.read_text()))
        for obj in docs:
            if obj and obj['kind']=='CiliumBGPClusterConfig':obj['spec']['bgpInstances'][0]['peers'][0]['peerAddress']=pod['status']['podIP']
        file.write_text(yaml.safe_dump_all(docs))
        return s.apply(file.name)
    if name=='l2-handoff':
        holder=json.loads((s.attempt/'l2.json').read_text())['holder'];s.context['l2_excluded_node']=holder;r.save(s.path,s.context)
        return label(s,holder)
    if name in ['l2-resume','recover-labels']:
        return sum([label(s,node,True) for node in r.WORKERS],[])
    if name in ['l2-withdraw','bgp-withdraw']:
        kind='CiliumL2AnnouncementPolicy' if name=='l2-withdraw' else 'CiliumBGPAdvertisement'
        return s.delete(s.document(kind,s.context['dp_name']))
    if name=='recover-proxy':
        before=s.context['controllers']['DaemonSet/kube-proxy']
        return patch_spec(s,'DaemonSet','kube-proxy',before,before['spec']) if s.context.get('proxy_pause_intent') else []
    if name=='recover-cilium':
        if digest(values())==s.context['original_values_sha256'] and hashlib.sha256(r.call(helm('get','manifest','cilium','-n','kube-system')).encode()).hexdigest()==s.context['original_manifest_sha256']:return []
        revision=int(release()['revision'])+1;s.context['owned_revisions']=sorted(set(s.context['owned_revisions']+[revision]));r.save(s.path,s.context)
        return [s.command(helm('rollback','cilium',str(s.context['original_revision']),'-n','kube-system','--wait','--timeout','8m'))]
    if name=='recover-routes':
        r.require(r.get('configmap','cilium-config','kube-system')['data'].get('routing-mode')=='tunnel','只能在恢复隧道后清理本批 Native 路由')
        commands=[]
        for node,ip in r.pol.base.NODES.items():
            before=direct_routes(s,s.context['vm_facts'][node]['routes'])
            current=direct_routes(s,remote_facts(ip)['routes'])
            for route in current:
                if route in before:continue
                r.require(s.context.get('native_intent'),'未授权的直接路由变更')
                args=['ip','-4','route','del',route['dst'],'via',route['gateway'],'dev',route['dev']]
                if 'metric' in route:args+=['metric',str(route['metric'])]
                commands.append(s.command(r.pol.ssh(ip,shlex.join(args))))
        return commands
    if name=='recover-firewall':
        commands=[]
        for node,rules in s.context.get('firewall_rules',{}).items():
            current=remote_facts(r.pol.base.NODES[node])
            for rule in rules:
                if rule in current['rich_rules']:
                    commands.append(s.command(r.pol.ssh(r.pol.base.NODES[node],shlex.join(['firewall-cmd','--zone=public','--remove-rich-rule='+rule]))))
        return commands
    return []


def ready_system(s,proxy=True):
    nodes=r.get('nodes')['items'];r.require(len(nodes)==10 and all(r.pol.base.ready(n) for n in nodes),'十 VM 尚未全部 Ready')
    for name in ['cilium','cilium-envoy']+(['kube-proxy'] if proxy else []):
        obj=r.get('daemonset',name,'kube-system');status=obj['status']
        r.require(status.get('observedGeneration')==obj['metadata']['generation'] and status.get('numberReady')==10 and status.get('updatedNumberScheduled')==10,'等待 '+name+' 10/10')
    for obj in controllers():
        if obj['kind']=='Deployment':
            r.require(obj['status'].get('observedGeneration')==obj['metadata']['generation'] and obj['status'].get('updatedReplicas',0)==obj['spec']['replicas'] and obj['status'].get('availableReplicas',0)>=obj['spec']['replicas'],'等待控制面 '+obj['metadata']['name'])


def direct_routes(s,routes):
    wanted={cidr:r.pol.base.NODES[node] for node,cidr in s.context['pod_cidrs'].items()}
    return [row for row in routes if row.get('dst') in wanted and row.get('gateway')==wanted[row['dst']] and row.get('dev')=='ens33']


def gateway_ready(s):
    gateway=r.get('gateway','edge',NS)
    r.require(all(any(c['type']==kind and c['status']=='True' and c.get('observedGeneration')==gateway['metadata']['generation'] for c in gateway.get('status',{}).get('conditions',[])) for kind in ['Accepted','Programmed']),'实验 Gateway 本代未就绪')
    edge=r.get('service',s.context['dp_name'],'envoy-gateway-system')
    return {'passed':True,'node_port':next(p['nodePort'] for p in edge['spec']['ports'] if p['port']==80)}


def backend_uids(s):
    return {p['metadata']['uid'] for p in r.get('pods',namespace=NS)['items'] if p['metadata'].get('labels',{}).get('app')=='api' and r.pol.base.ready(p)}


def probe(s,target,external=False,ca=''):
    nonce=uuid.uuid4().hex
    if external:
        raw=r.call(['/usr/bin/curl','--silent','--show-error','--noproxy','*','--connect-timeout','3','--max-time','7','-H','X-Cnpl-Nonce: '+nonce,target],timeout=12)
        body=json.loads(raw)
        with (s.attempt/'requests.jsonl').open('a') as log:log.write(json.dumps({'target':target,'nonce':nonce,'external':True,'body':body})+'\n')
        r.require(body.get('nonce')==nonce and body.get('uid') in backend_uids(s),'外部响应 nonce/UID 不符')
        return {'passed':True,'target':target,'nonce':nonce,'body':body}
    value=json.loads(r.call(r.K+['exec','-i','-n',NS,'client','-c','net','--','/phase-lab','probe'],json.dumps({'target':target,'nonce':nonce,'timeout_ms':5000,'ca':ca}),timeout=20))
    with (s.attempt/'requests.jsonl').open('a') as log:log.write(json.dumps({'external':False,'response':value})+'\n')
    if ca:
        r.require(value.get('status') in [200,401,403] and not value.get('error'),'API Service 可信 TLS 不通')
    else:
        r.require(value.get('status')==200 and not value.get('error'),'内部请求失败')
        body=json.loads(value['body']);r.require(body.get('nonce')==nonce and body.get('uid') in backend_uids(s),'响应 nonce/UID 不符')
    return value


def matrix(s,proxy=False):
    ready_system(s,proxy);r.require(len(backend_uids(s))==2,'两 VM API 后端未就绪')
    service=r.get('service','api',NS);edge=r.get('service',s.context['dp_name'],'envoy-gateway-system')
    gateway=r.get('gateway','edge',NS)
    r.require(all(any(c['type']==kind and c['status']=='True' and c.get('observedGeneration')==gateway['metadata']['generation'] for c in gateway.get('status',{}).get('conditions',[])) for kind in ['Accepted','Programmed']),'实验 Gateway 本代未就绪')
    port=next(p['nodePort'] for p in edge['spec']['ports'] if p['port']==80)
    rows={'dns':probe(s,'http://api.'+NS+'.svc.cluster.local:8080/allowed'),'cluster_ip':probe(s,'http://'+service['spec']['clusterIP']+':8080/allowed'),
        'node_port':probe(s,'http://192.168.9.110:31080/allowed',True),'gateway':probe(s,'http://192.168.9.110:'+str(port)+'/allowed',True),
        'api_service':probe(s,'https://kubernetes.default.svc/readyz',ca='/trust/ca.crt')}
    rows['pod_ips']=[probe(s,'http://'+p['status']['podIP']+':8080/allowed') for p in r.get('pods',namespace=NS)['items'] if p['metadata'].get('labels',{}).get('app')=='api' and r.pol.base.ready(p)]
    primary=r.pol.gw.probe.http('192.168.9.201','/dataplane-vm-check');r.require(primary['status']==404 and primary.get('tls_peer_sha256'),'原 .201 可信 TLS 异常')
    return {'passed':True,'requests':rows,'primary_tls_status':primary['status'],'config':r.get('configmap','cilium-config','kube-system')['data']}


def l2(s):
    service=r.get('service','l2',NS);ingress=service.get('status',{}).get('loadBalancer',{}).get('ingress') or []
    r.require(len(ingress)==1 and ingress[0].get('ip') in ['192.168.9.211','192.168.9.212','192.168.9.213','192.168.9.214'],'L2 VIP 不符')
    ip=ingress[0]['ip'];lease=r.get('lease','cilium-l2announce-'+NS+'-l2','kube-system');holder=lease['spec'].get('holderIdentity')
    r.require(holder in r.WORKERS,'L2 持有者不是实验 Worker')
    row=probe(s,'http://'+ip+':8080/allowed',True);arp=r.call(['/usr/sbin/arp','-n',ip])
    mac=s.context['vm_facts'][holder]['links'][0]['address']
    normalize=lambda v:':'.join(x.zfill(2) for x in v.lower().split(':'))
    found=re.search(r' at ([0-9a-f:]+) ',arp,re.I);r.require(found and normalize(found.group(1))==normalize(mac),'实际 ARP 与 Lease VM MAC 不同')
    return {'passed':True,'vip':ip,'holder':holder,'lease_uid':lease['metadata']['uid'],'arp':arp,'request':row}


def observe(s,name):
    if name=='recover-announcements':
        for kind in ['CiliumBGPAdvertisement','CiliumBGPClusterConfig','CiliumBGPPeerConfig','CiliumL2AnnouncementPolicy','CiliumLoadBalancerIPPool']:
            if s.receipt(s.document(kind,s.context['dp_name'])).exists():
                r.require(r.optional(kind,s.context['dp_name']) is None,'本批宣告配置未回收')
        return {'passed':True}
    if name=='crds':
        crds={n:r.get('crd',n) for n in s.context['crd_inputs']}
        r.require(all(any(c['type']=='Established' and c['status']=='True' for c in obj.get('status',{}).get('conditions',[])) for obj in crds.values()),'CRD 尚未 Established')
        return {'passed':True,'crds_present':{n:obj['metadata']['uid'] for n,obj in crds.items()},'retained_component_schemas':True}
    if name in ['workloads','proxy-cleanup','frr','stream']:
        if name=='workloads':
            s.ready('client',r.WORKERS[0],NS);r.require(len(backend_uids(s))==2,'API 后端未就绪')
        elif name=='proxy-cleanup':
            for i in range(10):
                obj=s.pod('proxy-cleanup-'+str(i),ADMIN)
                r.require(obj['status'].get('phase')=='Succeeded','等待 VM kube-proxy 清理成功')
        else:s.ready(name,ns=ADMIN if name=='frr' else NS)
        return {'passed':True}
    if name=='gateway':return gateway_ready(s)
    if name=='access':
        for node,rules in s.context['firewall_rules'].items():
            current=remote_facts(r.pol.base.NODES[node]);before=s.context['vm_facts'][node]
            r.require(set(current['rich_rules'])==set(before['rich_rules'])|set(rules) and current['permanent_rules']==before['permanent_rules'],'临时访问规则未收敛或永久配置改变')
        return {'passed':True,'runtime_only':True,'rules':s.context['firewall_rules']}
    if name=='baseline':
        value=matrix(s,True);s.context['initial_matrix_completed']=True;r.save(s.path,s.context);return value
    if name in ['ebpf-enable','native-enable','l2-enable','bgp-enable']:
        ready_system(s,name=='ebpf-enable');config=r.get('configmap','cilium-config','kube-system')['data']
        r.require(config.get('kube-proxy-replacement')=='true' and config.get('routing-mode')==('native' if name=='native-enable' else 'tunnel'),'Cilium 模式未收敛')
        return {'passed':True,'helm_revision':release()['revision'],'config':config}
    if name=='proxy-pause':
        owner=s.context['controllers']['DaemonSet/kube-proxy']['uid']
        r.require(not any(any(o['uid']==owner for o in p['metadata'].get('ownerReferences',[])) for p in r.get('pods',namespace='kube-system')['items']),'kube-proxy Pod 尚未停止')
        return {'passed':True,'daemonset_uid_preserved':owner}
    if name in ['ebpf','native']:
        value=matrix(s)
        if name=='native':
            routes={n:remote_facts(ip)['routes'] for n,ip in r.pol.base.NODES.items()}
            for node,table in routes.items():
                for peer,cidr in s.context['pod_cidrs'].items():
                    if peer!=node:r.require(any(row.get('dst')==cidr and row.get('gateway')==r.pol.base.NODES[peer] for row in table),'缺少 Native Routing 回程：'+node+'→'+peer)
            value['routes']=routes
        return value
    if name in ['l2','l2-handoff','l2-resume']:
        value=l2(s)
        if name=='l2-handoff':
            r.require(value['holder']!=s.context['l2_excluded_node'],'L2 Lease 未迁移')
            value['handoff_method']='selector withdrawal; no VM was stopped'
        return value
    if name=='l2-withdraw':
        r.require(r.optional('ciliuml2announcementpolicy',s.context['dp_name']) is None,'L2 策略未撤销')
        return {'passed':True}
    if name in ['bgp','bgp-withdraw']:
        pod=s.pod('frr',ADMIN)
        prefix=r.K+['exec','-n',ADMIN,pod['metadata']['name'],'-c','router','--','vtysh','-c']
        rib=json.loads(r.call(prefix+['show bgp ipv4 unicast json']))
        routes=rib.get('routes') or {}
        r.save(s.attempt/(name+'-rib-last.json'),rib)
        if name=='bgp-withdraw':
            r.require(not routes,'BGP 广告撤回后 RIB 仍有路由')
            return {'passed':True,'routes':rib,'external_forwarding_verified':False}
        summary=json.loads(r.call(prefix+['show bgp summary json']));peers=(summary.get('ipv4Unicast') or {}).get('peers') or {}
        r.save(s.attempt/'bgp-peers-last.json',summary)
        r.require(all(peers.get(r.pol.base.NODES[n],{}).get('state')=='Established' for n in r.WORKERS),'BGP 会话尚未建立')
        wanted={s.context['pod_cidrs'][n] for n in r.WORKERS}
        ingress=r.get('service','bgp',NS).get('status',{}).get('loadBalancer',{}).get('ingress') or []
        r.require(ingress and ingress[0].get('ip') in ['192.168.9.211','192.168.9.212','192.168.9.213','192.168.9.214'],'等待 BGP VIP')
        wanted.add(ingress[0]['ip']+'/32');allowed=wanted|{ip+'/32' for ip in ['192.168.9.211','192.168.9.212','192.168.9.213','192.168.9.214']}
        r.require(wanted<=set(routes) and set(routes)<=allowed,'RIB 缺少允许前缀或越界')
        return {'passed':True,'peers':summary,'rib':rib,'external_forwarding_verified':False}
    if name=='stream-stop':
        raw=r.call(r.K+['logs','-n',NS,'stream']);(s.attempt/'persistent-stream.jsonl').write_text(raw)
        rows=[json.loads(line) for line in raw.splitlines() if line.startswith('{')]
        r.require(sum(not row.get('error') for row in rows)>=5,'持久连接观测不足')
        return {'passed':True,'samples':len(rows),'failures':sum(bool(row.get('error')) for row in rows),'zero_disruption_claimed':False}
    if name=='recover-proxy':
        obj=r.get('daemonset','kube-proxy','kube-system');before=s.context['controllers']['DaemonSet/kube-proxy']
        r.require(obj['metadata']['uid']==before['uid'] and obj['spec']==before['spec'],'kube-proxy 原 UID/spec 未恢复')
        r.require(obj['status'].get('numberReady')==10,'等待 kube-proxy 10/10')
        return {'passed':True}
    if name=='recover-cilium':
        ready_system(s,True);r.require(digest(values())==s.context['original_values_sha256'],'原 Helm 值未恢复')
        r.require(hashlib.sha256(r.call(helm('get','manifest','cilium','-n','kube-system')).encode()).hexdigest()==s.context['original_manifest_sha256'],'原 Helm manifest（含 TLS/RBAC）未恢复')
        r.require(digest(r.get('configmap','cilium-config','kube-system')['data'])==s.context['original_cilium_config_sha256'],'原 Cilium ConfigMap 未恢复')
        for key,before in s.context['controllers'].items():
            kind,controller=key.split('/');current=r.get(kind,controller,'kube-system')
            r.require(current['metadata']['uid']==before['uid'] and current['spec']==before['spec'],'原控制器未恢复：'+key)
        return {'passed':True,'original_revision':s.context['original_revision'],'current_revision':release()['revision']}
    if name=='recover-labels':
        r.require(all(EXCLUDE not in r.get('node',n)['metadata'].get('labels',{}) for n in r.WORKERS),'L2 排除标签未清理')
        return {'passed':True}
    if name=='recover-routes':
        for node,ip in r.pol.base.NODES.items():
            r.require(direct_routes(s,remote_facts(ip)['routes'])==direct_routes(s,s.context['vm_facts'][node]['routes']),'原 VM 的 Node PodCIDR 路由未恢复')
        return {'passed':True}
    if name=='recover-firewall':
        for node in r.WORKERS:
            current=remote_facts(r.pol.base.NODES[node]);before=s.context['vm_facts'][node]
            r.require(current['rich_rules']==before['rich_rules'] and current['permanent_rules']==before['permanent_rules'],'原 VM 防火墙规则未恢复')
        return {'passed':True}
    if name=='recover-original':
        result=matrix(s,True) if s.context.get('initial_matrix_completed') else {'passed':True,'matrix':'initial matrix was not created'}
        stream=s.document('Pod','stream',NS)
        if s.receipt(stream).exists() and r.optional('pod','stream',NS) is not None:
            raw=r.call(r.K+['logs','-n',NS,'stream'])
            (s.attempt/'persistent-stream-after-rollback.jsonl').write_text(raw)
            result['stream_observation_saved_after_rollback']=True
        r.save(s.records/'state/rollback.json',{'run':s.run,**result})
        return result
    raise ValueError('未知 VM 用例：'+name)


def restore(s):
    return []


def final(s):
    guard(s);observe(s,'recover-proxy');observe(s,'recover-cilium');observe(s,'recover-routes');observe(s,'recover-labels');observe(s,'recover-firewall')
    rollback=json.loads((s.records/'state/rollback.json').read_text())
    r.require(rollback['run']==s.run and rollback['passed'],'缺少原模式回退证据')
    def children_absent():
        for kind in ['deployments','services','pods']:
            r.require(not any(obj['metadata'].get('labels',{}).get(r.LABEL)==s.run for obj in r.get(kind,namespace='envoy-gateway-system')['items']),'实验 Gateway 的子资源尚未回收')
        return {'passed':True}
    s.wait('gateway-child-cleanup',children_absent,seconds=120)
    row=r.pol.gw.probe.http('192.168.9.201','/dataplane-vm-final')
    r.require(row['status']==404 and row.get('tls_peer_sha256'),'原主入口可信 TLS 异常')
