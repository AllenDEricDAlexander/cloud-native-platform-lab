#!/usr/bin/env python3
"""02.09：隔离 kind 内比较 kube-proxy/eBPF、VXLAN/Native、L2 与 BGP。"""
import ipaddress
import json
from pathlib import Path
import re
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'phase02'))
import runtime as r
import isolated as iso
import cli
import yaml

TOPIC,STAGE='dataplane','02.09'
NAMESPACES=[]
WAIT_SECONDS=240
NS='lab-dataplane'


def prepare(s):
    lock=iso.prepare(s)
    s.render({'image':lock['images']['resource']['runtime_image'],'gateway_image':lock['images']['gateway']['runtime_image'],
        'envoy_image':lock['images']['envoy']['runtime_image'],'name':s.context['isolation']['name'],
        'subnet':s.context['isolation']['subnet'],'pod_cidr':s.context['isolation']['pod_cidr'],
        'service_cidr':s.context['isolation']['service_cidr'],'frr_ip':'172.30.90.250'})


def steps(s):
    return yaml.safe_load((r.PHASE/'networking/dataplane/cases.yml').read_text())


def config_file(s,name,value):
    file=s.attempt/name;file.write_text(yaml.safe_dump(value,sort_keys=False));return file


def gateway_values(s,c):
    return {'crds':{'enabled':False},'global':{'images':{
        'envoyGateway':{'image':c.lock['images']['gateway']['runtime_image'],'pullPolicy':'Never'},
        'envoyProxy':{'image':c.lock['images']['envoy']['runtime_image'],'pullPolicy':'Never'}}},
        'deployment':{'replicas':1,'envoyGateway':{'resources':{'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'cpu':'1','memory':'512Mi'}}}},
        'config':{'envoyGateway':{'gateway':{'controllerName':'gateway.envoyproxy.io/cnpl-isolated'},
            'provider':{'type':'Kubernetes','kubernetes':{'shutdownManager':{'image':c.lock['images']['gateway']['runtime_image']}}}}},
        'topologyInjector':{'enabled':False},'kubernetesClusterDomain':'cluster.local'}


def validate(s):
    c=iso.Cluster(s);lock=c.lock;images=set(v['runtime_image'] for v in lock['images'].values())
    kind=yaml.safe_load((s.attempt/'kind.yaml').read_text())
    r.require(kind['apiVersion']=='kind.x-k8s.io/v1alpha4' and kind['kind']=='Cluster'
        and kind['networking']['apiServerAddress']=='127.0.0.1'
        and kind['networking']['disableDefaultCNI'] is True
        and [n['role'] for n in kind['nodes']]==['control-plane','worker','worker'],'kind 配置越界')
    summaries={}
    for profile in ['baseline','ebpf','native','l2','bgp']:
        file=config_file(s,'preview-'+profile+'.values.yaml',c.cilium_values(profile))
        raw=r.call([iso.HELM,'template','cilium',lock['cilium_chart']['local_source'],'-n','kube-system','--kube-version','1.36.4','-f',file],timeout=60)
        docs=[obj for obj in yaml.safe_load_all(raw) if obj]
        found=[]
        for obj in docs:
            if obj['kind'] in ['DaemonSet','Deployment','Job']:
                containers=obj['spec']['template']['spec'].get('containers',[])+obj['spec']['template']['spec'].get('initContainers',[])
                found += [p['image'] for p in containers]
        r.require(set(found)<=images,'Chart 出现未准备镜像：'+str(set(found)-images))
        summaries[profile]={'objects':len(docs),'images':sorted(set(found))}
    schemas=[]
    for value in lock['schemas'].values():
        path=Path(value['path']);r.require(iso.MATERIALS.file_sha(path)==value['sha256'],'CRD 摘要不符')
        schemas.append(yaml.safe_load(path.read_text()))
        r.call(r.K+['apply','--dry-run=server','--validate=strict','-f',path])
    custom=[]
    builtins=0
    for name in ['workloads.yaml','gateway.yaml','l2.yaml','bgp.yaml']:
        for obj in yaml.safe_load_all((s.attempt/name).read_text()):
            if not obj:continue
            if obj['apiVersion'].split('/')[0] in ['cilium.io','gateway.networking.k8s.io','gateway.envoyproxy.io']:
                custom.append(obj);continue
            clone=json.loads(json.dumps(obj))
            if obj['kind']!='Namespace':clone['metadata']['namespace']='lab-core';clone['metadata']['name']='cnpl-preview-'+clone['metadata']['name']
            r.call(r.K+['apply','--dry-run=server','--validate=strict','-f','-'],json.dumps(clone));builtins+=1
    definitions=schemas+r.pol.gw.mat.crds()
    checked=r.pol.gw.mat.validate_custom(custom,definitions)
    file=config_file(s,'gateway.values.yaml',gateway_values(s,c))
    r.call([iso.HELM,'template','envoy',lock['gateway_chart']['local_source'],'-n','envoy-gateway-system','--kube-version','1.36.4','-f',file],timeout=60)
    return {'passed':True,'profiles':summaries,'builtin_server_dry_run':builtins,'custom_structure':checked,
        'docker_available':c.state['docker_available'],'runtime_executed':False,
        'custom_admission':'安装本批 CRD 后在隔离集群再次严格预览','primary_cilium_modified':False}


def save_kube_proxy(s,c):
    c.guard();obj=c.get('daemonset','kube-proxy','kube-system')
    public={k:v for k,v in obj.items() if k not in ['status']}
    for field in ['uid','resourceVersion','creationTimestamp','generation','managedFields']:
        public['metadata'].pop(field,None)
    r.save(s.records/'state/kube-proxy-before.json',public)
    return obj


def frr_plan(s,c):
    c.guard()
    directory=s.attempt/'frr';directory.mkdir()
    # 入口 umask=077；FRR 降权后仍需遍历挂载的公开配置目录。
    directory.chmod(0o755)
    lines=['frr defaults traditional','hostname cnpl-frr','service integrated-vtysh-config',
        'ip prefix-list LAB seq 10 permit '+c.state['pod_cidr']+' ge 24 le 24',
        'ip prefix-list LAB seq 20 permit 172.30.90.224/28 ge 32 le 32',
        'route-map ONLY-LAB permit 10',' match ip address prefix-list LAB',
        'router bgp 65009',' bgp router-id 172.30.90.250',' no bgp ebgp-requires-policy',' no bgp default ipv4-unicast']
    for node in c.workers():lines.append(' neighbor '+c.state['nodes'][node]['ip']+' remote-as 65010')
    lines.append(' address-family ipv4 unicast')
    for node in c.workers():
        ip=c.state['nodes'][node]['ip'];lines += ['  neighbor '+ip+' activate','  neighbor '+ip+' route-map ONLY-LAB in']
    lines += [' exit-address-family','exit']
    (directory/'frr.conf').write_text('\n'.join(lines)+'\n')
    (directory/'daemons').write_text('zebra=yes\nbgpd=yes\nvtysh_enable=yes\nzebra_options=" -A 127.0.0.1 -s 90000000"\nbgpd_options=" -A 127.0.0.1"\n')
    for file in directory.iterdir():file.chmod(0o644)
    name=c.state['name']+'-frr';c.state['frr_name']=name;c.save()
    binary=yaml.safe_load((r.ROOT/'ops/versions.lock.yaml').read_text())['components']['resource_fixture']['platforms']['arm64']['oci_layout']
    binary=str(Path(binary).parent/'phase-lab')
    return c.image_load('frr')+[s.command(c.docker+['run','-d','--name',name,'--label',r.LABEL+'='+s.run,
        '--platform','linux/arm64','--network',c.state['network'],'--ip','172.30.90.250','--cap-add','NET_ADMIN','--cap-add','NET_RAW','--cap-add','SYS_ADMIN',
        '-v',str(directory)+':/etc/frr',c.lock['images']['frr']['runtime_image']]),
        s.command(c.docker+['cp',binary,name+':/tmp/phase-lab'])]


def plan(s,name):
    c=iso.Cluster(s)
    if name=='create':return c.create_plan()
    if name=='load':return c.load_plan()
    if name=='baseline-install':return c.helm_cilium('baseline')
    if name=='applications':return c.apply([s.attempt/'workloads.yaml'])
    if name=='gateway-install':
        c.guard();defs=[v for v in r.pol.gw.mat.crds() if v['kind']=='CustomResourceDefinition']
        file=s.attempt/'gateway-crds.json';r.save(file,{'apiVersion':'v1','kind':'List','items':defs})
        values=config_file(s,'gateway.values.yaml',gateway_values(s,c))
        return c.apply([file])+[s.command([iso.HELM,'--kubeconfig',c.state['kubeconfig'],'upgrade','--install','envoy',
            c.lock['gateway_chart']['local_source'],'-n','envoy-gateway-system','--create-namespace','-f',values,'--wait','--timeout','5m'])]
    if name=='gateway':return c.apply([s.attempt/'gateway.yaml'])
    if name=='stream':
        c.guard();control=c.state['nodes'][c.control()]['ip'];monitor=c.state['name']+'-monitor'
        c.state['monitor_name']=monitor;c.save()
        return [s.command(c.docker+['run','-d','--name',monitor,'--label',r.LABEL+'='+s.run,'--network',c.state['network'],
            c.lock['images']['resource']['runtime_image'],'stream',control+':30090','1200'])]
    if name=='remove-kube-proxy':
        obj=save_kube_proxy(s,c);commands=c.delete('DaemonSet','kube-proxy','kube-system')
        for node in c.state['nodes']:
            commands.append(s.command(c.node_exec(node,['sh','-ec','iptables-save | sed "/KUBE-/d" | iptables-restore'])))
        return commands
    if name in ['ebpf','native','l2-install','bgp-install']:
        return c.helm_cilium({'l2-install':'l2','bgp-install':'bgp'}.get(name,name))
    if name=='l2':return c.apply([s.attempt/'l2.yaml'])
    if name=='l2-failure':
        lease=c.get('lease','cilium-l2announce-'+NS+'-l2','kube-system')
        holder=lease['spec']['holderIdentity'];r.require(holder in c.workers(),'L2 持有者不是本批 worker')
        c.inspect_node(holder);c.state['paused_node']=holder;c.save()
        return [s.command(c.docker+['pause',holder])]
    if name=='l2-resume':
        node=c.state['paused_node'];c.inspect_node(node)
        return [s.command(c.docker+['unpause',node])]
    if name=='l2-withdraw':return c.delete('CiliumL2AnnouncementPolicy','comparison')
    if name=='frr':return frr_plan(s,c)
    if name=='bgp':return c.apply([s.attempt/'bgp.yaml'])
    if name=='bgp-withdraw':return c.delete('CiliumBGPAdvertisement','comparison')
    if name=='restore-baseline':
        c.guard()
        file=s.records/'state/kube-proxy-before.json'
        return c.apply([file])+c.helm_cilium('baseline')
    if name=='stream-stop':
        return [s.command(c.docker+['stop','--time','5',c.state['monitor_name']])]
    return []


def backend_uids(c):
    pods=c.get('pods',namespace=NS)['items']
    values=[p for p in pods if p['metadata'].get('labels',{}).get('app')=='api' and r.pol.base.ready(p)]
    r.require(values,'没有就绪后端')
    return {p['metadata']['uid'] for p in values}


def response(c,target,external=False):
    row=c.probe(target,namespace=NS,pod=None if external else 'client')
    r.require(row.get('status')==200 and not row.get('error'),'实际请求失败：'+str(row))
    value=json.loads(row['body'])
    r.require(value.get('nonce')==row['nonce'] and value.get('uid') in backend_uids(c),'nonce/后端 UID 不同')
    return row


def matrix(c):
    c.ready();uids=backend_uids(c);r.require(len(uids)==2,'需要两个后端 Ready')
    service=c.get('service','api',NS);ip=service['spec']['clusterIP'];control=c.state['nodes'][c.control()]['ip']
    gateway=c.get('service','comparison-edge','envoy-gateway-system')
    programmed=c.get('gateway','edge',NS)
    r.require(all(any(v['type']==kind and v['status']=='True' and v.get('observedGeneration')==programmed['metadata']['generation']
        for v in programmed.get('status',{}).get('conditions',[])) for kind in ['Accepted','Programmed']),'Gateway 本代未就绪')
    port=next(p['nodePort'] for p in gateway['spec']['ports'] if p['port']==80)
    results={'dns_service':response(c,'http://api.'+NS+'.svc.cluster.local:8080/allowed'),
        'cluster_ip':response(c,'http://'+ip+':8080/allowed'),
        'node_port':response(c,'http://'+control+':30080/allowed',True),
        'gateway':response(c,'http://'+control+':'+str(port)+'/allowed',True)}
    results['pod_ips']=[response(c,'http://'+p['status']['podIP']+':8080/allowed')
        for p in c.get('pods',namespace=NS)['items'] if p['metadata'].get('labels',{}).get('app')=='api' and r.pol.base.ready(p)]
    api=c.probe('https://kubernetes.default.svc/readyz',namespace=NS,pod='client',ca='/trust/ca.crt')
    r.require(api.get('status') in [200,401,403] and not api.get('error'),'API Service 的可信 TLS 失败')
    results['api_service']=api
    return {'passed':True,'requests':results,'cilium_config':c.get('cm','cilium-config','kube-system')['data']}


def l2(c):
    service=c.get('service','l2',NS);ingress=service.get('status',{}).get('loadBalancer',{}).get('ingress') or []
    r.require(len(ingress)==1,'等待独立 L2 VIP')
    ip=ingress[0]['ip'];r.require(ipaddress.ip_address(ip) in ipaddress.ip_network('172.30.90.224/28'),'VIP 超出本批池')
    lease=c.get('lease','cilium-l2announce-'+NS+'-l2','kube-system');holder=lease['spec'].get('holderIdentity')
    r.require(holder in c.workers(),'缺少本批 L2 宣告者')
    row=response(c,'http://'+ip+':8080/allowed',True)
    arp=[line.split() for line in row.get('arp','').splitlines()[1:] if line.split() and line.split()[0]==ip]
    r.require(arp and arp[0][3].lower()==c.state['nodes'][holder]['mac'].lower(),'实际 ARP MAC 与 Lease 持有者不同')
    return {'passed':True,'vip':ip,'holder':holder,'lease_uid':lease['metadata']['uid'],'arp':arp,'request':row}


def bgp_rib(c):
    name=c.state['frr_name']
    return json.loads(r.call(c.docker+['exec',name,'vtysh','-c','show bgp ipv4 unicast json'],timeout=20))


def observe(s,name):
    c=iso.Cluster(s)
    if name=='create':return c.bind()
    if name=='load':
        c.guard()
        return {'passed':True,'images_preloaded':len(c.lock['images'])-2}
    if name in ['baseline-install','gateway-install','l2-install','bgp-install']:
        return c.ready()
    if name=='applications':
        c.ready();r.require(len(backend_uids(c))==2 and r.pol.base.ready(c.get('pod','client',NS)),'应用尚未就绪')
        return {'passed':True}
    if name in ['gateway','ebpf','native','restore-baseline']:
        value=matrix(c)
        config=value['cilium_config']
        expected=name not in ['gateway','restore-baseline']
        r.require(config['kube-proxy-replacement']==str(expected).lower(),'kube-proxy replacement 模式不符')
        r.require(config['routing-mode']==('native' if name=='native' else 'tunnel'),'路由模式不符')
        if name=='native':
            targets={n['metadata']['name']:n['spec']['podCIDR'] for n in c.get('nodes')['items']}
            routes={}
            for node in c.state['nodes']:
                table=json.loads(r.call(c.node_exec(node,['ip','-j','route','show'])))
                for peer,cidr in targets.items():
                    if peer!=node:
                        r.require(any(v.get('dst')==cidr and v.get('gateway')==c.state['nodes'][peer]['ip'] for v in table),'Native Routing 缺少 PodCIDR 的直连回程路由')
                routes[node]=table
            value['native_routes']=routes
        return value
    if name=='stream':
        raw=r.call(c.docker+['logs',c.state['monitor_name']]);rows=[json.loads(v) for v in raw.splitlines() if v.startswith('{')]
        r.require(any(not v.get('error') for v in rows),'持久连接观测尚无成功样本')
        return {'passed':True,'initial_samples':rows}
    if name=='remove-kube-proxy':
        raw=r.call(c.k+['get','daemonset','kube-proxy','-n','kube-system','--ignore-not-found','-o','name'])
        r.require(not raw.strip(),'kube-proxy DS 没有移除')
        return {'passed':True,'original_rules_cleaned_in_owned_kind_nodes_only':True}
    if name=='l2':return l2(c)
    if name=='l2-failure':
        old=c.state['paused_node'];node=c.get('node',old)
        r.require(not r.pol.base.ready(node),'等待暂停的 kind 节点 NotReady')
        value=l2(c);r.require(value['holder']!=old,'L2 Lease 未迁移')
        endpoints=c.get('endpointslices',namespace=NS)['items']
        r.require(not any(e.get('nodeName')==old and e.get('conditions',{}).get('ready') is True for sl in endpoints if sl['metadata'].get('labels',{}).get('kubernetes.io/service-name')=='l2' for e in (sl.get('endpoints') or [])),'失效节点仍在就绪 EndpointSlice')
        value['paused_node']=old;return value
    if name=='l2-resume':
        c.ready();return l2(c)
    if name=='l2-withdraw':
        raw=r.call(c.k+['get','ciliuml2announcementpolicy','comparison','--ignore-not-found','-o','name'])
        r.require(not raw.strip(),'L2 策略没有撤销')
        return {'passed':True,'declaration_removed':True}
    if name=='frr':
        out=r.call(c.docker+['exec',c.state['frr_name'],'vtysh','-c','show version'],timeout=20)
        r.require('FRRouting' in out,'FRR 未运行')
        return {'passed':True,'software_router_only':True,'version':out}
    if name=='bgp':
        summary=json.loads(r.call(c.docker+['exec',c.state['frr_name'],'vtysh','-c','show bgp summary json']))
        peers=(summary.get('ipv4Unicast') or {}).get('peers') or {}
        r.require(all(peers.get(c.state['nodes'][n]['ip'],{}).get('state')=='Established' for n in c.workers()),'BGP 邻居尚未 Established')
        rib=bgp_rib(c);routes=rib.get('routes') or {}
        nodes=c.get('nodes')['items'];wanted={n['spec']['podCIDR'] for n in nodes if n['metadata']['name'] in c.workers()}
        service=c.get('service','bgp',NS);ingress=service.get('status',{}).get('loadBalancer',{}).get('ingress') or []
        r.require(ingress,'BGP Service 没有 VIP');vip=ingress[0]['ip'];wanted.add(vip+'/32')
        r.require(wanted<=set(routes),'FRR RIB 缺少允许的 Pod/VIP 路由')
        allowed=lambda prefix:ipaddress.ip_network(prefix).subnet_of(ipaddress.ip_network(c.state['pod_cidr'])) or ipaddress.ip_network(prefix).subnet_of(ipaddress.ip_network('172.30.90.224/28'))
        r.require(all(allowed(prefix) for prefix in routes),'FRR 学到授权之外的前缀')
        nonce=uuid.uuid4().hex;request={'target':'http://'+vip+':8080/allowed','nonce':nonce,'timeout_ms':5000}
        row=json.loads(r.call(c.docker+['exec','-i',c.state['frr_name'],'/tmp/phase-lab','probe'],json.dumps(request)))
        body=json.loads(row.get('body','{}'))
        r.require(row.get('status')==200 and body.get('nonce')==nonce and body.get('uid') in backend_uids(c),'FRR 路由路径实际请求失败')
        return {'passed':True,'peers':summary,'routes':rib,'request':row,'vip':vip}
    if name=='bgp-withdraw':
        routes=bgp_rib(c).get('routes') or {}
        r.require(not routes,'删除广告后路由未撤回')
        response(c,'http://'+c.state['nodes'][c.control()]['ip']+':30080/allowed',True)
        vip=json.loads((s.attempt/'bgp.json').read_text())['vip']
        row=json.loads(r.call(c.docker+['exec','-i',c.state['frr_name'],'/tmp/phase-lab','probe'],
            json.dumps({'target':'http://'+vip+':8080/allowed','nonce':uuid.uuid4().hex,'timeout_ms':2000})))
        r.require(row.get('error') and not row.get('status'),'BGP 撤回后 VIP 仍可经无 L2 的 FRR 路径访问')
        return {'passed':True,'routes_after_withdraw':routes,'nodeport_control_healthy':True,'withdrawn_vip_request':row}
    if name=='stream-stop':
        raw=r.call(c.docker+['logs',c.state['monitor_name']]);(s.attempt/'persistent-stream.jsonl').write_text(raw)
        rows=[json.loads(v) for v in raw.splitlines() if v.startswith('{')]
        good=[v for v in rows if not v.get('error')]
        r.require(len(good)>=5 and rows[-1].get('seq',0)>=5,'连接观测不足')
        return {'passed':True,'samples':len(rows),'successes':len(good),'failures':len(rows)-len(good),
            'scope':'记录实际连接中断/重连，不承诺零丢包','last_samples':rows[-5:]}
    raise ValueError('未定义观察 '+name)


def restore(s):
    return iso.Cluster(s).cleanup_plan() if s.context.get('isolation') else []


def final(s):
    if s.context.get('isolation'):iso.Cluster(s).final()
    row=r.pol.gw.probe.http('192.168.9.201','/dataplane-final')
    r.require(row['status']==404 and row.get('tls_peer_sha256'),'主入口可信 TLS 异常')


if __name__=='__main__':cli.run(sys.modules[__name__])
