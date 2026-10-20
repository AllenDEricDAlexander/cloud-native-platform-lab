"""仅操作本批 Docker 网络/kind；从不更改默认 kubeconfig 或主集群 Cilium。"""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
import yaml
import runtime as r

MATERIALS=r.module('isolation_materials',r.HERE.parent/'dataplane/materials.py')
HELM=str(Path.home()/'.cnpl/bin/helm')
KUBECTL=str(Path.home()/'.cnpl/bin/kubectl')


def require_runtime_host():
    r.require(sys.platform!='darwin','禁止在 Mac 运行 Docker/kind 实验；请使用 VM 执行入口。旧批次仅允许清理恢复。')


def locks(topic):
    components=yaml.safe_load((r.ROOT/'ops/versions.lock.yaml').read_text())['components']
    base=components['isolated_network']
    if topic=='mesh':
        extra=components['mesh']
        return {**base,'images':{k:v for k,v in base['images'].items() if k in ['kind-node','cilium','operator','cilium-envoy','resource']}|extra['images'],
                'tools':base['tools']|extra['tools'],'mesh':extra}
    return base


def prepare(s,mesh=False):
    if s.mode=='all':require_runtime_host()
    lock=locks(s.topic)
    MATERIALS.verify(lock)
    context,available,data='disabled-on-mac',False,{}
    if sys.platform!='darwin':
        context=r.call(['docker','context','show']).strip()
        endpoint=json.loads(r.call(['docker','context','inspect',context,'--format','{{json .Endpoints.docker.Host}}']))
        r.require(endpoint.startswith('unix://'),'本入口要求本机 Docker Unix socket')
        info=subprocess.run(['docker','--context',context,'info','--format','{{json .}}'],capture_output=True,text=True,timeout=15)
        available=info.returncode==0
        data=json.loads(info.stdout) if available else {}
    if s.mode=='all':
        r.require(available,'Docker 当前未运行；请先启动 Docker Desktop，再运行本专题 all。不会自动启动 Docker。')
        r.require(data.get('OSType')=='linux' and data.get('Architecture') in ['aarch64','arm64'],'物料锁仅覆盖本机 linux/arm64 Docker')
        r.require(data.get('NCPU',0)>=4 and data.get('MemTotal',0)>=6*1024**3,'Docker 至少需要4 CPU/6Gi内存，建议8Gi')
        r.require(str(data.get('CgroupVersion'))=='2','Cilium kube-proxy replacement 需要本批 cgroup v2')
    name='cnpl-'+('mesh' if mesh else 'dp')+'-'+s.run[-8:]
    subnet='172.30.'+('91' if mesh else '90')+'.0/24'
    private=Path.home()/'.cnpl-secrets/phase02-isolated'/s.run
    value={'name':name,'network':name+'-net','docker_context':context,'docker_id':data.get('ID'),
        'docker_available':available,'subnet':subnet,'pod_cidr':'10.247.0.0/16' if mesh else '10.246.0.0/16',
        'service_cidr':'10.99.0.0/16' if mesh else '10.98.0.0/16','kubeconfig':str(private/'kind.config'),'nodes':{}}
    if s.mode=='all':
        existing=r.call(['docker','--context',context,'network','ls','-q']).splitlines()
        for identity in existing:
            network=json.loads(r.call(['docker','--context',context,'network','inspect',identity]))[0]
            for block in network.get('IPAM',{}).get('Config') or []:
                if block.get('Subnet') and ':' not in block['Subnet']:
                    r.require(not ipaddress.ip_network(subnet).overlaps(ipaddress.ip_network(block['Subnet'])),'隔离网段与现有 Docker 网络重叠')
        names=r.call(['env','DOCKER_CONTEXT='+context,'KIND_EXPERIMENTAL_PROVIDER=docker',lock['tools']['kind']['path'],'get','clusters']).splitlines()
        r.require(name not in names,'拒绝复用同名 kind 集群')
        private.mkdir(parents=True,exist_ok=True,mode=0o700)
    s.context['isolation']=value
    r.save(s.path,s.context)
    return lock


class Cluster:
    def __init__(self,s):
        self.s=s
        self.state=s.context['isolation']
        self.lock=locks(s.topic)
        self.docker=['docker','--context',self.state['docker_context']]
        self.k=[KUBECTL,'--kubeconfig',self.state['kubeconfig'],'--request-timeout=20s']

    def save(self):
        self.s.context['isolation']=self.state;r.save(self.s.path,self.s.context)

    def check_engine(self):
        info=json.loads(r.call(self.docker+['info','--format','{{json .}}']))
        r.require(info.get('ID')==self.state['docker_id'],'Docker daemon 身份不同')
        return info

    def kind(self,arguments):
        return ['env','-u','DOCKER_HOST','-u','DOCKER_DEFAULT_PLATFORM','DOCKER_CONTEXT='+self.state['docker_context'],
            'KIND_EXPERIMENTAL_PROVIDER=docker','KIND_EXPERIMENTAL_DOCKER_NETWORK='+self.state['network'],
            self.lock['tools']['kind']['path']]+arguments

    def inspect_node(self,name):
        self.check_engine()
        value=json.loads(r.call(self.docker+['inspect',name]))[0]
        r.require(value['Config']['Labels'].get('io.x-k8s.kind.cluster')==self.state['name']
            and value['HostConfig']['NetworkMode']==self.state['network']
            and value['HostConfig'].get('PidMode')!='host','容器不属于本批隔离 kind')
        saved=self.state['nodes'].get(name)
        r.require(not saved or saved['id']==value['Id'],'kind 容器 ID 改变')
        return value

    def node_exec(self,name,args):
        self.inspect_node(name)
        return self.docker+['exec',name]+[str(a) for a in args]

    def image_load(self,name):
        value=self.lock['images'][name]
        result=subprocess.run(self.docker+['image','inspect',value['runtime_image'],'--format','{{json .Id}}'],capture_output=True,text=True,timeout=15)
        if result.returncode==0:
            r.require(json.loads(result.stdout)==value['config_digest'],'本地同名镜像内容不同，拒绝覆盖')
            return []
        return [self.s.command(self.docker+['load','--input',value['archive']])]

    def create_plan(self):
        require_runtime_host()
        self.check_engine()
        self.state['creation_intent']=True;self.save()
        commands=self.image_load('kind-node')+self.image_load('resource')
        commands += [self.s.command(self.docker+['network','create','--driver','bridge','--subnet',self.state['subnet'],
            '--label',r.LABEL+'='+self.s.run,self.state['network']])]
        commands += [self.s.command(self.kind(['create','cluster','--name',self.state['name'],'--image',self.lock['images']['kind-node']['runtime_image'],
            '--config',str(self.s.attempt/'kind.yaml'),'--kubeconfig',self.state['kubeconfig'],'--wait','0s','--retain']))]
        return commands

    def bind(self):
        self.check_engine()
        names=r.call(self.kind(['get','nodes','--name',self.state['name']])).splitlines()
        r.require(len(names)==3,'必须是本批三个 kind 节点')
        for name in names:
            value=self.inspect_node(name)
            r.require(value['HostConfig'].get('CgroupnsMode')=='private','kind 节点需要 private cgroup namespace')
            network=value['NetworkSettings']['Networks'][self.state['network']]
            self.state['nodes'][name]={'id':value['Id'],'ip':network['IPAddress'],'mac':network['MacAddress'],
                'role':value['Config']['Labels']['io.x-k8s.kind.role']}
        os.chmod(self.state['kubeconfig'],0o600)
        server=r.call(self.k+['config','view','--minify','-o','jsonpath={.clusters[0].cluster.server}'])
        r.require(server.startswith('https://127.0.0.1:'),'kind API 必须仅绑定本机 loopback')
        uid=json.loads(r.call(self.k+['get','namespace','kube-system','-o','json']))['metadata']['uid']
        r.require(uid!=self.s.context['cluster_uid'],'隔离 kubeconfig 指向主集群，拒绝继续')
        r.require(not self.state.get('cluster_uid') or self.state['cluster_uid']==uid,'kind UID 改变')
        self.state['cluster_uid']=uid;self.save()
        return {'passed':True,'isolated_uid':uid,'api':server,'nodes':self.state['nodes']}

    def guard(self):
        self.check_engine()
        r.require(self.state.get('cluster_uid'),'kind 身份尚未绑定')
        server=r.call(self.k+['config','view','--minify','-o','jsonpath={.clusters[0].cluster.server}'])
        r.require(server.startswith('https://127.0.0.1:'),'隔离 API 地址改变')
        current=json.loads(r.call(self.k+['get','namespace','kube-system','-o','json']))['metadata']['uid']
        r.require(current==self.state['cluster_uid'] and current!=self.s.context['cluster_uid'],'隔离 API UID 不同')

    def get(self,kind,name=None,namespace=None):
        r.require(not any(k.split('.')[0] in ['secret','secrets'] for k in kind.lower().split(',')),'不能读取完整 Secret')
        return json.loads(r.call(self.k+['get',kind]+([name] if name else [])+(['-n',namespace] if namespace else [])+['-o','json']))

    def apply(self,files):
        self.guard();commands=[]
        for file in files:
            documents=[d for d in yaml.safe_load_all(Path(file).read_text()) if d]
            objects=[item for doc in documents for item in (doc['items'] if doc['kind']=='List' else [doc])]
            for obj in objects:
                m=obj['metadata']
                path=self.s.attempt/('isolated-'+obj['kind']+'-'+m.get('namespace','cluster')+'-'+m['name']+'.json')
                r.save(path,obj)
                # Namespace/SA/CRD 的创建必须先落地，之后的依赖对象才能做真实准入。
                apply=['apply']+(['--server-side','--field-manager=cnpl-gateway-crds'] if obj['kind']=='CustomResourceDefinition' else [])
                commands += [self.s.command(self.k+apply+['--dry-run=server','--validate=strict','-f',path]),
                             self.s.command(self.k+apply+['--validate=strict','-f',path])]
        return commands

    def delete(self,kind,name,ns=None):
        self.guard()
        obj=self.get(kind,name,ns)
        r.require((kind=='DaemonSet' and name=='kube-proxy' and ns=='kube-system')
            or obj['metadata'].get('labels',{}).get(r.LABEL)==self.s.run,'拒绝删除非本批对象')
        api=obj['apiVersion'];plural=kind
        mappings={'Service':'services','CiliumL2AnnouncementPolicy':'ciliuml2announcementpolicies','CiliumBGPAdvertisement':'ciliumbgpadvertisements','DaemonSet':'daemonsets'}
        plural=mappings.get(kind,kind.lower())
        url=('/api/' if api=='v1' else '/apis/')+api+'/'
        url+=('namespaces/'+ns+'/' if ns else '')+plural+'/'+name
        file=self.s.attempt/('delete-'+kind+'-'+name+'.json')
        r.save(file,{'apiVersion':'v1','kind':'DeleteOptions','preconditions':{'uid':obj['metadata']['uid']},'propagationPolicy':'Foreground'})
        return [self.s.command(self.k+['delete','--raw',url,'-f',file]),
                self.s.command(self.k+['wait','--for=delete',kind+'/'+name,'--timeout=120s']+(['-n',ns] if ns else []))]

    def load_plan(self):
        self.guard()
        return [self.s.command(self.kind(['load','image-archive',value['archive'],'--name',self.state['name']]))
                for name,value in self.lock['images'].items() if name not in ['kind-node','frr']]

    def control(self):
        return next(name for name,v in self.state['nodes'].items() if v['role']=='control-plane')

    def workers(self):
        return [name for name,v in self.state['nodes'].items() if v['role']=='worker']

    def cilium_values(self,profile,mesh=False):
        image=self.lock['images']
        repo_tag=lambda value:value['runtime_image'].rsplit(':',1)
        agent=repo_tag(image['cilium']);operator=repo_tag(image['operator']);envoy=repo_tag(image['cilium-envoy'])
        native=profile=='native';kpr=profile in ['ebpf','native','l2','bgp']
        control=next((value for value in self.state['nodes'].values() if value['role']=='control-plane'),None)
        api=control['ip'] if control else str(ipaddress.ip_network(self.state['subnet']).network_address+2)
        return {'image':{'repository':agent[0],'tag':agent[1],'useDigest':False,'pullPolicy':'Never'},
            'operator':{'replicas':1,'image':{'override':image['operator']['runtime_image'],'repository':operator[0].removesuffix('-generic'),'tag':operator[1],'useDigest':False,'pullPolicy':'Never'},'rollOutPods':True},
            'envoy':{'image':{'repository':envoy[0],'tag':envoy[1],'useDigest':False,'pullPolicy':'Never'}},
            'ipam':{'mode':'kubernetes'},'kubeProxyReplacement':kpr,'routingMode':'native' if native else 'tunnel',
            'tunnelProtocol':'vxlan','autoDirectNodeRoutes':native,'ipv4NativeRoutingCIDR':self.state['pod_cidr'],
            'bpf':{'masquerade':kpr},'k8sServiceHost':api,
            'k8sServicePort':6443,'devices':['eth0'],'rollOutCiliumPods':True,'hubble':{'enabled':False},
            'cni':{'exclusive':not mesh},'l2announcements':{'enabled':profile=='l2','leaseDuration':'6s','leaseRenewDeadline':'2s','leaseRetryPeriod':'1s'},
            'bgpControlPlane':{'enabled':profile=='bgp'},'k8sClientRateLimit':{'qps':30,'burst':60}}

    def helm_cilium(self,profile,mesh=False):
        self.guard();values=self.cilium_values(profile,mesh);file=self.s.attempt/('cilium-'+profile+'.values.yaml')
        file.write_text(yaml.safe_dump(values,sort_keys=False))
        return [self.s.command([HELM,'--kubeconfig',self.state['kubeconfig'],'upgrade','--install','cilium',
            self.lock['cilium_chart']['local_source'],'-n','kube-system','--reset-values','-f',file,'--wait','--timeout','6m'])]

    def ready(self,expected_nodes=3):
        nodes=self.get('nodes')['items']
        r.require(len(nodes)==3 and sum(r.pol.base.ready(n) for n in nodes)==expected_nodes,'kind Node Ready 数不符')
        for kind,name in [('daemonset','cilium'),('deployment','coredns')]:
            value=self.get(kind,name,'kube-system');status=value['status']
            if kind=='daemonset':r.require(status.get('numberReady')==expected_nodes,'Cilium 尚未就绪')
            else:r.require(status.get('availableReplicas',0)>=1,'CoreDNS 未就绪')
        return {'passed':True,'nodes_ready':expected_nodes,'cilium':self.get('cm','cilium-config','kube-system')['data']}

    def probe(self,target,namespace=None,pod=None,ca='',nonce=None):
        request={'target':target,'nonce':nonce or __import__('uuid').uuid4().hex,'timeout_ms':5000,'ca':ca}
        if pod:
            args=self.k+['exec','-i','-n',namespace,pod,'-c','net','--','/phase-lab','probe']
        else:
            args=self.docker+['run','--rm','-i','--platform','linux/arm64','--network',self.state['network'],
                '--label',r.LABEL+'='+self.s.run,'-e','CNPL_ARP_PROBE=true',self.lock['images']['resource']['runtime_image'],'probe']
        return json.loads(r.call(args,json.dumps(request),timeout=25))

    def cleanup_plan(self):
        if not self.state.get('creation_intent'):return []
        self.check_engine();commands=[]
        for name in self.state.get('nodes',{}):
            result=subprocess.run(self.docker+['inspect',name],capture_output=True,text=True,timeout=15)
            if result.returncode:
                continue
            value=self.inspect_node(name)
            if value['State'].get('Paused'):commands.append(self.s.command(self.docker+['unpause',name]))
        # 只回收本批额外的探针/路由器；kind 自己按本批独有名称回收节点及匿名卷。
        ids=r.call(self.docker+['ps','-aq','--filter','label='+r.LABEL+'='+self.s.run]).splitlines()
        for identity in ids:
            value=json.loads(r.call(self.docker+['inspect',identity]))[0]
            r.require(value['Config']['Labels'].get(r.LABEL)==self.s.run,'容器归属不同')
            commands.append(self.s.command(self.docker+['rm','-f',identity]))
        commands.append(self.s.command(self.kind(['delete','cluster','--name',self.state['name'],'--kubeconfig',self.state['kubeconfig']])))
        result=subprocess.run(self.docker+['network','inspect',self.state['network']],capture_output=True,text=True,timeout=15)
        if result.returncode==0:
            network=json.loads(result.stdout)[0];r.require(network.get('Labels',{}).get(r.LABEL)==self.s.run,'网络归属不同')
            commands.append(self.s.command(self.docker+['network','rm',self.state['network']]))
        return commands

    def final(self):
        if self.state.get('creation_intent'):
            self.check_engine()
            remaining=r.call(self.docker+['ps','-aq','--filter','label=io.x-k8s.kind.cluster='+self.state['name']]).strip()
            r.require(not remaining,'kind 节点仍残留')
            remaining=r.call(self.docker+['network','ls','-q','--filter','label='+r.LABEL+'='+self.s.run]).strip()
            r.require(not remaining,'本批 Docker 网络仍残留')
