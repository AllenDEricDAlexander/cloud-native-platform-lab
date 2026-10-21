#!/usr/bin/env python3
"""现有 VM 主集群的 Istio/SPIRE 对照；只读预检，写操作交给 Ansible。"""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import uuid
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'phase02'))
import runtime as r
import cli

mat = r.module('mesh_vm_materials', Path(__file__).with_name('materials.py'))
evidence = r.module('mesh_vm_observe', Path(__file__).with_name('observe.py'))
dp = r.module('mesh_vm_cilium', r.HERE.parent / 'dataplane/vm.py')
TOPIC, STAGE = 'mesh', '02.10'
SIDECAR, AMBIENT, PLAIN, SPIRE = evidence.SIDECAR, evidence.AMBIENT, evidence.PLAIN, evidence.SPIRE
SYSTEM, SPIRE_SYSTEM = 'istio-system', 'spire-system'
NAMESPACES = [SIDECAR, AMBIENT, PLAIN, SPIRE, SYSTEM, SPIRE_SYSTEM]
WAIT_SECONDS = 360
PILOT_PORTS = {8080, 15010, 15012, 15014, 15017}
RESTORE_STEPS = [{'name': name} for name in ['recover-applications', 'recover-components', 'recover-globals', 'recover-cilium', 'recover-socket', 'recover-firewall', 'recover-primary']]
BLOCKED = {'trace_slo_release': {'status': 'BLOCKED', 'reason': '完整 Trace/SLO 和发布联动依赖 Phase04/05；本批只验证基础 mTLS、身份、授权及有界流量策略。'},
           'federation_mesh_integration': {'status': 'BLOCKED', 'reason': 'Istio 和独立 SPIRE 根信任不集成，不宣称联合或 SPIRE 为网格签发身份。'}}
GLOBAL = {'CustomResourceDefinition', 'ClusterRole', 'ClusterRoleBinding', 'MutatingWebhookConfiguration', 'ValidatingWebhookConfiguration', 'ValidatingAdmissionPolicy', 'ValidatingAdmissionPolicyBinding', 'GatewayClass'}
r.RESOURCE.update({'DaemonSet': ('apps/v1', 'daemonsets'), 'Role': ('rbac.authorization.k8s.io/v1', 'roles'),
    'RoleBinding': ('rbac.authorization.k8s.io/v1', 'rolebindings'), 'ClusterRole': ('rbac.authorization.k8s.io/v1', 'clusterroles'),
    'ClusterRoleBinding': ('rbac.authorization.k8s.io/v1', 'clusterrolebindings'),
    'MutatingWebhookConfiguration': ('admissionregistration.k8s.io/v1', 'mutatingwebhookconfigurations'),
    'ValidatingWebhookConfiguration': ('admissionregistration.k8s.io/v1', 'validatingwebhookconfigurations'),
    'ValidatingAdmissionPolicy': ('admissionregistration.k8s.io/v1', 'validatingadmissionpolicies'),
    'ValidatingAdmissionPolicyBinding': ('admissionregistration.k8s.io/v1', 'validatingadmissionpolicybindings'),
    'GatewayClass': ('gateway.networking.k8s.io/v1', 'gatewayclasses'),
    'PeerAuthentication': ('security.istio.io/v1', 'peerauthentications'),
    'AuthorizationPolicy': ('security.istio.io/v1', 'authorizationpolicies'),
    'VirtualService': ('networking.istio.io/v1', 'virtualservices')})


def agent_ids(value):
    rows = (value.get('agents') or []) if isinstance(value, dict) else value
    r.require(isinstance(rows, list), 'SPIRE agent 列表不是数组')
    result = []
    for row in rows:
        r.require(isinstance(row, dict), 'SPIRE agent 条目不是对象')
        identity = row.get('id', row.get('spiffe_id', row.get('spiffeId')))
        if isinstance(identity, dict):
            identity = 'spiffe://' + identity.get('trust_domain', identity.get('trustDomain', '')) + identity.get('path', '')
        r.require(isinstance(identity, str) and identity.startswith('spiffe://internal.egon.top/spire/agent/k8s_psat/cnpl-vm/'), 'SPIRE agent ID 不符合本批 trust domain/attestor')
        result.append(identity)
    r.require(len(result) == len(set(result)), 'SPIRE agent ID 重复')
    return result


def locks():
    return yaml.safe_load((r.ROOT / 'ops/versions.lock.yaml').read_text())['components']


def host_packages():
    registry = locks()['registry_runtime']
    values = []
    for item in registry['artifacts']:
        if item['name'] in ['iptables-libs-1.8.11-16.el10_2.x86_64.rpm', 'iptables-nft-1.8.11-16.el10_2.x86_64.rpm']:
            path = Path(registry['local_source']) / item['name']
            r.require(mat.archive.file_sha(path) == item['sha256'], '原 Rocky iptables RPM 摘要不同：' + item['name'])
            values.append({'path': str(path), 'name': item['name'], 'sha256': item['sha256']})
    r.require(len(values) == 2, '需要锁定的两个原 Rocky iptables RPM')
    return values


def profile():
    return {'cni': {'exclusive': False}, 'socketLB': {'hostNamespaceOnly': True}, 'operator': {'rollOutPods': True}}


def untouched(value):
    result = copy.deepcopy(value)
    for key, fields in profile().items():
        for field in fields:
            result.get(key, {}).pop(field, None)
        if result.get(key) == {}:
            result.pop(key, None)
    return result


def guard(s):
    r.require(r.get('namespace', 'kube-system')['metadata']['uid'] == s.context['cluster_uid'], 'VM 主集群 UID 不同')
    r.require(r.call(r.K + ['config', 'view', '--minify', '-o', 'jsonpath={.clusters[0].cluster.server}']).strip() == 'https://api.k8s.internal.egon.top:6443', '管理 kubeconfig 指向其他 API')
    for node, uid in s.context['node_uids'].items():
        r.require(r.get('node', node)['metadata']['uid'] == uid, 'VM Node UID 改变：' + node)
    r.require(int(dp.release()['revision']) in s.context['owned_revisions'], 'Cilium revision 被外部操作改变，停止覆盖')
    r.require(dp.digest(untouched(dp.values())) == s.context['untouched_values_sha256'], '本批范围以外的 Cilium 值改变')


class Session(r.Session):
    def prepare(self, mode):
        value = super().prepare(mode)
        r.require(not self.context.get('isolation'), '旧本地集群批次不能使用 VM 恢复入口；保留原记录')
        return value

    def sources(self):
        files = super().sources()
        for path in [Path(dp.__file__), r.PHASE / 'ansible/tasks/mesh-cleanup.yml', r.PHASE / 'ansible/tasks/mesh-image.yml', r.PHASE / 'ansible/playbooks/mesh-images.yml']:
            files[str(path.relative_to(r.ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        return dict(sorted(files.items()))

    def protected(self):
        values = super().protected()
        controllers = dp.controllers()
        uids = {obj['metadata']['uid'] for obj in controllers}
        for obj in controllers:
            values[self.key(obj)] = {'uid': obj['metadata']['uid']}
        cm = r.get('configmap', 'cilium-config', 'kube-system')
        values[self.key(cm)] = {'uid': cm['metadata']['uid']}
        for obj in r.get('replicasets', namespace='kube-system')['items']:
            if any(owner['uid'] in uids for owner in obj['metadata'].get('ownerReferences', [])):
                uids.add(obj['metadata']['uid'])
        for obj in r.get('pods', namespace='kube-system')['items']:
            if any(owner['uid'] in uids for owner in obj['metadata'].get('ownerReferences', [])):
                values.pop(self.key(obj), None)
        return values

    def owned(self, obj):
        meta, kind = obj['metadata'], obj['kind']
        r.require(kind in r.RESOURCE and meta.get('labels', {}).get(r.LABEL) == self.run, '对象类型或 run 越界')
        if kind in GLOBAL:
            r.require(self.key(obj) in self.context['global_objects'], '全局对象不在本批已预检清单中')
        else:
            r.require((kind == 'Namespace' and meta['name'] in NAMESPACES) or (kind != 'Namespace' and meta.get('namespace') in NAMESPACES), '对象命名空间越界')

    def apply(self, filename):
        guard(self)
        return super().apply(filename)

    def cleanup(self):
        # 含控制器生成证书的实验空间由专用恢复步骤核对归属后按原 UID 回收。
        return []

    def wait(self, name, check, seconds=90):
        try:
            return super().wait(name, check, seconds)
        except (ValueError, KeyError, OSError, subprocess.TimeoutExpired):
            rows = {}
            for ns in NAMESPACES:
                if r.optional('namespace', ns):
                    try:
                        rows[ns] = {kind: r.get(kind, namespace=ns) for kind in ['pods', 'events']}
                    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
                        rows[ns] = {'collection_error': str(error)}
            r.save(self.attempt / (name + '-diagnostics.json'), rows)
            raise


class Cluster:
    """将保留的只读观察函数绑定到已核验 VM 身份。"""
    def __init__(self, s):
        self.s, self.k = s, r.K
        self.lock = locks()['mesh']
        self.state = {'kubeconfig': dp.KC, 'cluster_uid': s.context['cluster_uid']}

    def get(self, kind, name=None, namespace=None):
        return r.get(kind, name, namespace)

    def node_exec(self, node, args):
        r.require(node in r.WORKERS and r.get('node', node)['metadata']['uid'] == self.s.context['node_uids'][node], 'CRI 观察目标 VM 身份不同')
        return r.pol.ssh(r.pol.base.NODES[node], shlex.join(args))


def worker_facts(node, ca):
    program = '''import hashlib,json,pathlib,shutil,socket,ssl
root=pathlib.Path('/etc/cni/net.d')
context=ssl.create_default_context(cadata=CA)
with context.wrap_socket(socket.create_connection(('127.0.0.1',10250),timeout=5),server_hostname=NODE) as stream:
 tls={'verified':True,'subject_alt_name':stream.getpeercert()['subjectAltName']}
ports=[]
for name in ['/proc/net/tcp','/proc/net/tcp6']:
 for line in pathlib.Path(name).read_text().splitlines()[1:]:
  fields=line.split()
  if fields[3]=='0A':ports.append(int(fields[1].split(':')[1],16))
print(json.dumps({'cni_files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.is_file()},
 'kubelet_tls':tls,'ports':sorted(set(ports)),'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
 'free_memory':int(next(v.split()[1] for v in pathlib.Path('/proc/meminfo').read_text().splitlines() if v.startswith('MemAvailable:')))*1024,
 'disks':{name:{'free':shutil.disk_usage(name).free,'device':pathlib.Path(name).stat().st_dev} for name in ['/var/cache','/var/lib/containerd']}}))
'''
    return json.loads(r.call(r.pol.ssh(r.pol.base.NODES[node], shlex.join(['python3', '-c', 'CA=' + repr(ca) + '\nNODE=' + repr(node) + '\n' + program])), timeout=20))


def documents(path):
    return [obj for obj in yaml.safe_load_all(Path(path).read_text()) if obj]


def generate(s):
    lock = locks()['mesh']
    raw = r.call([lock['tools']['istioctl']['path'], 'manifest', 'generate', '-f', s.attempt / 'istio-operator.yaml', '--manifests', lock['manifests'], '--cluster-specific=false'], timeout=90)
    docs = [obj for obj in yaml.safe_load_all(raw) if obj]
    known = {image['runtime_image'] for image in locks()['mesh_vm']['images'].values()}
    for obj in docs:
        r.require(obj['kind'] != 'Secret', '生成清单含 Secret，不能存入公开记录')
        obj['metadata'].setdefault('labels', {})[r.LABEL] = s.run
        template = obj.get('spec', {}).get('template')
        if template:
            template.setdefault('metadata', {}).setdefault('labels', {})[r.LABEL] = s.run
            images = [c['image'] for c in template['spec'].get('containers', []) + template['spec'].get('initContainers', [])]
            r.require(set(images) <= known, 'Istio 清单含未准备镜像：' + str(set(images) - known))
        for webhook in obj.get('webhooks', []):
            webhook.setdefault('namespaceSelector', {}).setdefault('matchLabels', {})[r.LABEL] = s.run
    docs.append({'apiVersion': 'gateway.networking.k8s.io/v1', 'kind': 'GatewayClass', 'metadata': {'name': 'istio-waypoint', 'labels': {r.LABEL: s.run}}, 'spec': {'controllerName': 'istio.io/mesh-controller'}})
    (s.attempt / 'istio-generated.yaml').write_text(yaml.safe_dump_all(docs, sort_keys=False))
    crds = [o for o in docs if o['kind'] == 'CustomResourceDefinition']
    (s.attempt / 'istio-crds.yaml').write_text(yaml.safe_dump_all(crds, sort_keys=False))
    (s.attempt / 'istio-components.yaml').write_text(yaml.safe_dump_all([o for o in docs if o['kind'] != 'CustomResourceDefinition'], sort_keys=False))
    config = next(o for o in docs if o['kind'] == 'ConfigMap' and 'config' in o.get('data', {}) and 'values' in o.get('data', {}))
    mesh = next(o for o in docs if o['kind'] == 'ConfigMap' and 'mesh' in o.get('data', {}))
    paths = {}
    for name, value in [('inject-config.yaml', config['data']['config']), ('inject-values.json', config['data']['values']), ('mesh-config.yaml', mesh['data']['mesh'])]:
        paths[name] = s.attempt / name
        paths[name].write_text(value)
    example = next(o for o in documents(s.attempt / 'workloads.yaml') if o['kind'] == 'Pod' and o['metadata']['namespace'] == SIDECAR)
    sample = {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': {'name': 'cnpl-preview-sidecar', 'namespace': 'lab-core'},
        'spec': {'selector': {'matchLabels': example['metadata']['labels']}, 'template': {'metadata': {'labels': example['metadata']['labels']}, 'spec': copy.deepcopy(example['spec'])}}}
    sample['spec']['template']['spec']['serviceAccountName'] = 'default'
    file = s.attempt / 'inject-example.yaml'; file.write_text(yaml.safe_dump(sample))
    injected = r.call([lock['tools']['istioctl']['path'], 'kube-inject', '--kubeconfig', dp.KC, '-f', file,
        '--injectConfigFile', paths['inject-config.yaml'], '--meshConfigFile', paths['mesh-config.yaml'], '--valuesFile', paths['inject-values.json']], timeout=45)
    injected_docs = [o for o in yaml.safe_load_all(injected) if o]
    pod = injected_docs[0]['spec']['template']['spec']
    containers = pod['containers'] + pod.get('initContainers', [])
    r.require(all(c['image'] in known for c in containers if c['name'].startswith('istio-')), '注入代理或初始化镜像没有锁定')
    r.require(not any(c['name'] == 'istio-init' for c in containers), 'CNI 模式仍注入 NET_ADMIN 网络初始化')
    (s.attempt / 'injected-example.yaml').write_text(injected)
    return docs


def prepare(s):
    component = locks()
    mat.verify(component['mesh_vm']); mat.verify_charts(component['mesh']); host_packages()
    original = dp.values(); release = dp.release()
    r.require(release['status'] == 'deployed', '原 Cilium release 未 deployed')
    r.require(original.get('ipam', {}).get('mode') == 'cluster-pool' and str(original.get('kubeProxyReplacement')).lower() == 'false' and original.get('routingMode') == 'tunnel', '需要 02.09 已恢复的 kube-proxy/VXLAN 基线')
    r.require(original.get('rollOutCiliumPods') is True, '原 Cilium 必须启用配置变更滚动，防止 ConfigMap 改变而 agent 未更新')
    cm = r.get('configmap', 'cilium-config', 'kube-system')['data']
    r.require(cm.get('enable-bpf-masquerade', 'false') == 'false', 'Ambient 不支持当前启用的 BPF masquerade')
    chart = component['cilium']['chart']
    r.require(mat.archive.file_sha(chart['local_source']) == chart['sha256'], 'Cilium Chart 摘要不同')
    nodes = r.get('nodes')['items']
    r.require(all(n['status']['nodeInfo']['architecture'] == 'amd64' for n in nodes), '本批物料只适用于登记的 amd64 VM')
    ca = r.get('configmap', 'kube-root-ca.crt', 'default')['data']['ca.crt']
    facts = {name: dp.remote_facts(ip) for name, ip in r.pol.base.NODES.items()}
    r.require(all(f['selinux'] == 'Enforcing' and f['firewalld'] == 'active' and f['hostname'] == n for n, f in facts.items()), 'VM 安全状态或 hostname 不符')
    workers = {node: worker_facts(node, ca) for node in r.WORKERS}
    archive_bytes = sum(Path(v['archive']).stat().st_size for v in component['mesh_vm']['images'].values())
    for node, value in workers.items():
        r.require(set(value['cni_files']) == {'05-cilium.conflist'}, '原 CNI 配置不是单一 Cilium，先审阅：' + node)
        r.require(value['free_memory'] >= 2 * 1024**3, 'Worker 空闲内存不足 2Gi：' + node)
        cache, runtime = value['disks']['/var/cache'], value['disks']['/var/lib/containerd']
        if cache['device'] == runtime['device']:
            r.require(cache['free'] >= archive_bytes * 3 + 512 * 1024**2, '镜像缓存与解包所在磁盘空间不足：' + node)
        else:
            r.require(cache['free'] >= archive_bytes + 256 * 1024**2 and runtime['free'] >= archive_bytes * 2 + 256 * 1024**2, '镜像缓存或 containerd 磁盘空间不足：' + node)
        if node == r.WORKERS[0]:
            r.require(not set(value['ports']) & PILOT_PORTS, 'Istiod 主机端口已被占用：' + node)
    main = r.get('service', 'cnpl-primary', 'envoy-gateway-system')
    r.require([o.get('ip') for o in main.get('status', {}).get('loadBalancer', {}).get('ingress') or []] == ['192.168.9.201'], '主 .201 入口漂移')
    controllers = {obj['kind'] + '/' + obj['metadata']['name']: {'uid': obj['metadata']['uid'], 'spec': obj['spec']} for obj in dp.controllers()}
    s.context.update(execution_backend='vm-primary', original_revision=int(release['revision']), owned_revisions=[int(release['revision'])],
        node_uids={n['metadata']['name']: n['metadata']['uid'] for n in nodes}, vm_facts=facts, worker_facts=workers,
        original_values_sha256=dp.digest(original), untouched_values_sha256=dp.digest(untouched(original)),
        original_manifest_sha256=hashlib.sha256(r.call(dp.helm('get', 'manifest', 'cilium', '-n', 'kube-system')).encode()).hexdigest(),
        original_config_sha256=dp.digest(cm), controllers=controllers, primary_uid=main['metadata']['uid'], chart=chart,
        socket_path='/run/cnpl/mesh-' + s.run + '/spire', global_objects={}, firewall_rules={})
    images = component['mesh_vm']['images']
    existing_ns = [o['metadata']['name'] for o in r.get('namespaces')['items']]
    s.render({'workers': r.WORKERS, 'socket_path': s.context['socket_path'], 'excluded_namespaces': sorted(set(existing_ns + [SYSTEM, SPIRE_SYSTEM, PLAIN, SPIRE])),
        'image': component['resource_fixture']['platforms']['amd64']['internal_source'], 'identity_image': images['identity']['runtime_image'],
        'spire_server': images['spire-server']['runtime_image'], 'spire_agent': images['spire-agent']['runtime_image'],
        'proxy_image': images['proxyv2']['runtime_image'], 'pilot_image': images['pilot']['runtime_image'], 'cni_image': images['install-cni']['runtime_image'], 'ztunnel_image': images['ztunnel']['runtime_image'],
        'spire_server_hcl': (r.PHASE / 'networking/mesh/spire-server.conf').read_text(), 'spire_agent_hcl': (r.PHASE / 'networking/mesh/spire-agent.conf').read_text()})
    generated = generate(s)
    all_docs = generated + documents(s.attempt / 'spire-server.yaml') + documents(s.attempt / 'spire-agent.yaml')
    for obj in all_docs:
        if obj['kind'] in GLOBAL:
            r.require(r.optional(obj['kind'], obj['metadata']['name']) is None, '拒绝覆盖已有全局对象：' + s.key(obj))
            s.context['global_objects'][s.key(obj)] = {'apiVersion': obj['apiVersion'], 'kind': obj['kind'], 'metadata': obj['metadata']}
    r.require(not any(o['metadata']['name'].endswith('.istio.io') for o in r.get('crds')['items']), '已有 Istio CRD，不能自动接管或卸载')
    r.save(s.path, s.context)
    return primary(s)


def steps(s):
    return yaml.safe_load((r.PHASE / 'networking/mesh/cases.yml').read_text())


def validate(s):
    definitions = documents(s.attempt / 'istio-crds.yaml')
    models = copy.deepcopy(definitions)
    for model in models:
        for version in model['spec']['versions']:
            properties = version['schema']['openAPIV3Schema'].setdefault('properties', {})
            for key, value in [('apiVersion', {'type': 'string'}), ('kind', {'type': 'string'}), ('metadata', {'type': 'object'})]:
                properties.setdefault(key, value)
    custom, builtins, deferred = [], 0, []
    names = ['image-smoke', 'workloads', 'sidecar-policy', 'ambient-l4', 'waypoint', 'ambient-l7', 'spire-server', 'spire-agent', 'spire-workloads', 'held', 'istio-namespace', 'istio-generated', 'injected-example']
    for name in names:
        for obj in documents(s.attempt / (name + '.yaml')):
            if obj['apiVersion'].startswith(('security.istio.io/', 'networking.istio.io/', 'gateway.networking.k8s.io/')):
                custom.append(obj); continue
            clone = copy.deepcopy(obj)
            if obj['kind'] == 'CustomResourceDefinition':
                r.call(r.K + ['apply', '--server-side', '--field-manager=cnpl-gateway-crds', '--dry-run=server', '--validate=strict', '-f', '-'], json.dumps(clone)); builtins += 1; continue
            if obj['kind'] not in GLOBAL | {'Namespace'}:
                clone['metadata']['namespace'] = 'kube-system' if obj['metadata'].get('namespace') in [SYSTEM, SPIRE_SYSTEM, SPIRE] else 'lab-core'
            clone['metadata']['name'] = 'cnpl-preview-' + obj['metadata']['name']
            pod = clone.get('spec') if clone['kind'] == 'Pod' else clone.get('spec', {}).get('template', {}).get('spec')
            if pod and pod.get('serviceAccountName'):
                deferred.append({'kind': obj['kind'], 'name': obj['metadata']['name'], 'serviceAccountName': pod['serviceAccountName']})
                pod['serviceAccountName'] = 'default'
            r.call(r.K + ['apply', '--dry-run=server', '--validate=strict', '-f', '-'], json.dumps(clone)); builtins += 1
    schemas = models + [o for o in r.pol.gw.mat.crds() if o['kind'] == 'CustomResourceDefinition']
    structural = r.pol.gw.mat.validate_custom(custom, schemas)
    r.call([locks()['mesh']['tools']['istioctl']['path'], 'validate', '-f', s.attempt / 'sidecar-policy.yaml'], timeout=30)
    merged = copy.deepcopy(dp.values())
    for key, value in profile().items(): merged.setdefault(key, {}).update(value)
    raw = r.call(dp.helm('template', 'cilium', s.context['chart']['local_source'], '-n', 'kube-system', '--kube-version', '1.36.5', '-f', '-'), json.dumps(merged), timeout=90)
    rendered = [o for o in yaml.safe_load_all(raw) if o and o['kind'] != 'Secret']
    cm = next(o for o in rendered if o['kind'] == 'ConfigMap' and o['metadata']['name'] == 'cilium-config')['data']
    r.require(cm.get('cni-exclusive') == 'false' and cm.get('bpf-lb-sock-hostns-only') == 'true' and cm.get('enable-bpf-masquerade', 'false') == 'false' and cm.get('kube-proxy-replacement') == 'false', 'Cilium 兼容 profile 错误')
    r.save(s.attempt / 'rendered-cilium.json', rendered)
    return {'passed': True, 'backend': 'vm-primary', 'builtin_server_dry_run': builtins, 'custom_structure': structural,
        'offline_sidecar_injection_checked': True, 'service_account_reference_admission_deferred': deferred,
        'actual_admission': '正式安装相应 Namespace/SA/CRD 后，各对象执行前再次严格服务端预览',
        'mac_container_runtime_used': False, 'runtime_executed': False}


def primary(s):
    guard(s)
    dp.ready_system(s)
    main = r.get('service', 'cnpl-primary', 'envoy-gateway-system')
    r.require(main['metadata']['uid'] == s.context['primary_uid'] and [o.get('ip') for o in main['status']['loadBalancer']['ingress']] == ['192.168.9.201'], '主入口 UID/VIP 改变')
    tls = r.pol.gw.probe.http('192.168.9.201', '/mesh-primary-' + uuid.uuid4().hex)
    r.require(tls['status'] == 404 and tls.get('tls_peer_sha256'), '主入口可信 TLS 异常')
    return {'passed': True, 'nodes_ready': 10, 'cilium_ready': 10, 'kube_proxy_ready': 10, 'main_service_uid': main['metadata']['uid'], 'main_tls': tls}


def compatible(s):
    value = primary(s)
    cm = r.get('configmap', 'cilium-config', 'kube-system')['data']
    r.require(cm.get('cni-exclusive') == 'false' and cm.get('bpf-lb-sock-hostns-only') == 'true' and cm.get('enable-bpf-masquerade', 'false') == 'false', '实际 Cilium/Istio 兼容配置不符')
    return value | {'cni_exclusive': False, 'socket_lb_host_namespace_only': True, 'bpf_masquerade': False}


def loaded(s):
    images = locks()['mesh_vm']['images']
    values = {}
    for node in r.WORKERS:
        values[node] = {}
        for name, image in images.items():
            value = json.loads(r.call(r.pol.ssh(r.pol.base.NODES[node], shlex.join(['crictl', 'inspecti', image['runtime_image']])), timeout=20))
            r.require(value['status']['id'] == image['config_digest'], 'VM CRI 镜像内容不同：' + node + '/' + name)
            values[node][name] = value['status']['id']
    smoke, prerequisites = [], {}
    for index, node in enumerate(r.WORKERS, 1):
        ip = r.pol.base.NODES[node]
        prerequisites[node] = {'packages': r.call(r.pol.ssh(ip, 'rpm -q iptables-nft iptables-libs')).splitlines(),
            'backend': r.call(r.pol.ssh(ip, '/usr/sbin/iptables-save --version')).strip()}
        r.require('nf_tables' in prerequisites[node]['backend'], 'Istio CNI 原生工具未就绪：' + node)
        name = 'image-smoke' + str(index)
        s.ready(name, node, PLAIN)
        pod = s.pod(name, PLAIN)
        payload = {'target': 'http://127.0.0.1:8080/allowed', 'nonce': uuid.uuid4().hex, 'timeout_ms': 4000}
        reply = json.loads(r.call(r.K + ['exec', '-i', '-n', PLAIN, name, '-c', 'net', '--', '/phase-lab', 'probe'], json.dumps(payload), timeout=15))
        r.require(reply.get('status') == 200 and json.loads(reply['body'])['uid'] == pod['metadata']['uid'] and json.loads(reply['body'])['nonce'] == payload['nonce'], 'kubelet 镜像真实启动/UID/nonce 未通过：' + node)
        smoke.append({'node': node, 'pod_uid': pod['metadata']['uid'], 'reply': reply})
    return {'passed': True, 'architecture': 'amd64', 'workers': values, 'host_prerequisites': prerequisites, 'kubelet_image_smoke': smoke}


def generated_istio_config(obj):
    if obj['kind'] != 'ConfigMap':
        return False
    name, data = obj['metadata']['name'], obj.get('data') or {}
    if obj['metadata'].get('namespace') == SYSTEM and name in ['istio-ip-autoallocate', 'istio-leader', 'istio-namespace-controller-election']:
        annotations = obj['metadata'].get('annotations') or {}
        if data or set(annotations) - {'control-plane.alpha.kubernetes.io/leader'}:
            return False
        if annotations:
            leader = json.loads(annotations['control-plane.alpha.kubernetes.io/leader'])
            return leader.get('holderKey') == 'cnpl0210' and str(leader.get('holderIdentity', '')).startswith('istiod-cnpl0210-')
        return True
    if obj['metadata'].get('labels', {}).get('istio.io/config') != 'true':
        return False
    if name == 'istio-ca-root-cert':
        return set(data) == {'root-cert.pem'} and 'BEGIN CERTIFICATE' in data['root-cert.pem']
    if name == 'istio-ca-crl':
        return set(data) == {'ca-crl.pem'} and (data['ca-crl.pem'] == '' or 'BEGIN X509 CRL' in data['ca-crl.pem'])
    return False


def delete_namespace(s, ns):
    current = r.optional('Namespace', ns)
    if not current: return []
    s.owned(current)
    r.require(s.receipt(current).exists(), '实验 Namespace 没有创建意图')
    kinds = ['pods', 'deployments', 'replicasets', 'daemonsets', 'services', 'configmaps', 'serviceaccounts', 'roles', 'rolebindings', 'jobs', 'networkpolicies', 'persistentvolumeclaims', 'poddisruptionbudgets', 'horizontalpodautoscalers']
    if r.optional('crd', 'gateways.gateway.networking.k8s.io'):
        kinds.append('gateways.gateway.networking.k8s.io')
    for crd, resource in [('peerauthentications.security.istio.io', 'peerauthentications.security.istio.io'), ('authorizationpolicies.security.istio.io', 'authorizationpolicies.security.istio.io'), ('virtualservices.networking.istio.io', 'virtualservices.networking.istio.io')]:
        if r.optional('crd', crd): kinds.append(resource)
    objects = [obj for kind in kinds for obj in r.get(kind, namespace=ns)['items']]
    owned = {obj['metadata']['uid'] for obj in objects if obj['metadata'].get('labels', {}).get(r.LABEL) == s.run}
    owned.add(current['metadata']['uid'])
    for _ in range(4):
        owned.update(obj['metadata']['uid'] for obj in objects if any(owner['uid'] in owned for owner in obj['metadata'].get('ownerReferences', [])))
    for obj in objects:
        key = (obj['kind'], obj['metadata']['name'])
        r.require(obj['metadata']['uid'] in owned or key in [('ServiceAccount', 'default'), ('ConfigMap', 'kube-root-ca.crt')] or generated_istio_config(obj), '实验空间含外来对象，停止清理：' + s.key(obj))
    secrets = r.pol.gw.secret_list(ns)
    r.require(not secrets or ns == SYSTEM and all(o['metadata']['name'] == 'istio-ca-secret' for o in secrets), '实验空间出现非预期 Secret')
    return s.delete(current)


def plan(s, name):
    if name.startswith('recover-') and not s.context.get('execution_backend'):
        r.require(not list((s.records / 'state').glob('object-*.json')), '准备上下文不完整但存在创建意图，不能自动推断归属')
        return []
    if name == 'recover-firewall':
        r.require(r.get('namespace', 'kube-system')['metadata']['uid'] == s.context['cluster_uid'], '撤销临时规则时集群 UID 不同')
        r.require(all(r.get('node', n)['metadata']['uid'] == s.context['node_uids'][n] for n in r.WORKERS), '撤销临时规则时 Worker UID 不同')
    else:
        guard(s)
    if name == 'preflight': return []
    if name == 'load':
        file = s.attempt / 'images.json'
        r.save(file, {'mesh_images': list(locks()['mesh_vm']['images'].values()), 'mesh_host_packages': host_packages(), 'mesh_worker_uids': {n: s.context['node_uids'][n] for n in r.WORKERS}})
        return [s.command([Path.home() / '.venvs/cnpl-ansible/bin/ansible-playbook', r.PHASE / 'ansible/playbooks/mesh-images.yml', '-e', '@' + str(file)])] + s.apply('image-smoke.yaml')
    if name == 'access':
        target = r.pol.base.NODES[r.WORKERS[0]]
        rules = ['rule priority="-100" family="ipv4" source address="' + source + '" destination address="' + target + '/32" port port="' + str(port) + '" protocol="tcp" accept'
            for source, port in [(r.pol.base.NODES[n] + '/32', 15017) for n in r.pol.base.NODES if n.startswith('cp')] + [('10.244.0.0/16', 15012)] + [(r.pol.base.NODES[n] + '/32', 15012) for n in r.WORKERS]]
        before = s.context['vm_facts'][r.WORKERS[0]]
        r.require(not set(rules) & set(before['rich_rules'] + before['permanent_rules']), '临时 Istiod 防火墙规则已有外部归属')
        s.context['firewall_rules'] = {r.WORKERS[0]: rules}; r.save(s.path, s.context)
        return [s.command(r.pol.ssh(target, shlex.join(['firewall-cmd', '--zone=public', '--add-rich-rule=' + rule, '--timeout=14400']))) for rule in rules]
    if name == 'cilium':
        s.context['cilium_intent'] = True
        s.context['owned_revisions'].append(int(dp.release()['revision']) + 1); r.save(s.path, s.context)
        file = s.attempt / 'cilium-mesh-values.yaml'; file.write_text(yaml.safe_dump(profile()))
        return [s.command(dp.helm('upgrade', 'cilium', s.context['chart']['local_source'], '-n', 'kube-system', '--reuse-values', '-f', str(file), '--history-max', '20', '--wait', '--timeout', '8m'))]
    if name == 'istio-crds':
        docs = documents(s.attempt / 'istio-crds.yaml')
        return s.apply('istio-namespace.yaml') + s.apply('istio-crds.yaml') + [s.command(r.K + ['wait', '--for=condition=Established', '--timeout=120s', 'crd/' + obj['metadata']['name']]) for obj in docs]
    if name == 'istio': return s.apply('istio-components.yaml')
    if name == 'sidecar-restart':
        obj = next(o for o in documents(s.attempt / 'workloads.yaml') if o['kind'] == 'Pod' and o['metadata']['namespace'] == SIDECAR and o['metadata']['name'] == 'allowed')
        current = s.pod('allowed', SIDECAR)
        s.context['restart_before_uid'] = current['metadata']['uid']; r.save(s.path, s.context)
        file = s.attempt / 'sidecar-restart.yaml'; file.write_text(yaml.safe_dump(obj))
        return s.delete(current) + s.apply(file.name)
    files = {'applications': 'workloads', 'sidecar-policy': 'sidecar-policy', 'ambient-l4': 'ambient-l4', 'waypoint': 'waypoint', 'ambient-l7': 'ambient-l7', 'spire-server': 'spire-server', 'spire-agent': 'spire-agent', 'spire-workloads': 'spire-workloads', 'held': 'held'}
    if name in files:
        commands = sum([s.delete(s.document('Pod', 'image-smoke' + str(i), PLAIN)) for i in [1, 2]], []) if name == 'applications' else []
        return commands + s.apply(files[name] + '.yaml')
    c = Cluster(s)
    if name == 'spire-bundle':
        pem = r.call(evidence.server_exec(c, ['bundle', 'show', '-format', 'pem']))
        r.require('BEGIN CERTIFICATE' in pem and 'PRIVATE KEY' not in pem, 'SPIRE 公共 bundle 异常')
        obj = {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': 'spire-bundle', 'namespace': SPIRE_SYSTEM, 'labels': {r.LABEL: s.run}}, 'data': {'bundle.pem': pem}}
        file = s.attempt / 'spire-bundle.yaml'; file.write_text(yaml.safe_dump(obj))
        return s.apply(file.name)
    if name == 'register':
        ids = agent_ids(json.loads(r.call(evidence.server_exec(c, ['agent', 'list', '-output', 'json']))))
        r.require(len(ids) == 2 and {v.rsplit('/', 1)[-1] for v in ids} == {s.context['node_uids'][n] for n in r.WORKERS}, '需要两个真实 Worker UID 的 PSAT agent')
        entries = [{'id': str(uuid.uuid4()), 'parent': parent, 'role': role} for parent in ids for role in ['server', 'allowed', 'verifier']]
        s.context['spire_entries'] = entries; r.save(s.path, s.context)
        return [s.command(evidence.server_exec(c, ['entry', 'create', '-entryID', e['id'], '-parentID', e['parent'], '-spiffeID', 'spiffe://internal.egon.top/ns/' + SPIRE + '/sa/' + e['role'], '-selector', 'k8s:ns:' + SPIRE, '-selector', 'k8s:sa:' + e['role'], '-x509SVIDTTL', '60'])) for e in entries]
    if name == 'revoke':
        return [s.command(evidence.server_exec(c, ['entry', 'delete', '-entryID', e['id']])) for e in s.context['spire_entries'] if e['role'] == 'allowed']
    if name == 'recover-applications':
        return sum([delete_namespace(s, ns) for ns in [AMBIENT, SIDECAR, SPIRE, PLAIN]], [])
    if name == 'recover-components':
        commands = []
        for obj in s.context['global_objects'].values():
            if obj['kind'] in ['MutatingWebhookConfiguration', 'ValidatingWebhookConfiguration'] and s.receipt(obj).exists(): commands += s.delete(obj)
        return commands + sum([delete_namespace(s, ns) for ns in [SYSTEM, SPIRE_SYSTEM]], [])
    if name == 'recover-globals':
        commands = []
        ordered = sorted(s.context['global_objects'].values(), key=lambda obj: obj['kind'] == 'CustomResourceDefinition')
        for obj in ordered:
            if not s.receipt(obj).exists(): continue
            if obj['kind'] == 'CustomResourceDefinition' and r.optional('crd', obj['metadata']['name']):
                current = r.get('crd', obj['metadata']['name'])
                api = current['spec']['group'] + '/' + next(v['name'] for v in current['spec']['versions'] if v.get('storage'))
                plural = current['spec']['names']['plural']
                instances = json.loads(r.call(r.K + ['get', plural + '.' + current['spec']['group'], '-A', '-o', 'json']))['items']
                r.require(not instances, 'CRD 中出现外来实例，停止卸载：' + api + '/' + plural)
            commands += s.delete(obj)
        return commands
    if name == 'recover-cilium':
        if not s.context.get('cilium_intent') or dp.digest(dp.values()) == s.context['original_values_sha256'] and hashlib.sha256(r.call(dp.helm('get', 'manifest', 'cilium', '-n', 'kube-system')).encode()).hexdigest() == s.context['original_manifest_sha256']: return []
        s.context['owned_revisions'].append(int(dp.release()['revision']) + 1); r.save(s.path, s.context)
        return [s.command(dp.helm('rollback', 'cilium', str(s.context['original_revision']), '-n', 'kube-system', '--wait', '--timeout', '8m'))]
    if name == 'recover-socket':
        root = s.context['socket_path']; r.require(re.fullmatch(r'/run/cnpl/mesh-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}/spire', root), 'socket 路径越界')
        program = 'import pathlib,stat\np=pathlib.Path(' + repr(root) + ')\nassert not p.is_symlink() and not p.parent.is_symlink(), "socket 目录被替换为链接"\nif p.exists():\n for child in p.iterdir():\n  assert child.name=="agent.sock" and stat.S_ISSOCK(child.lstat().st_mode), "socket 目录含外来文件"\n  child.unlink()\n p.rmdir()\n if p.parent.exists():p.parent.rmdir()'
        return [s.command(r.pol.ssh(r.pol.base.NODES[node], shlex.join(['python3', '-c', program]))) for node in r.WORKERS]
    if name == 'recover-firewall':
        commands = []
        for node, rules in s.context['firewall_rules'].items():
            current = dp.remote_facts(r.pol.base.NODES[node])
            for rule in rules:
                if rule in current['rich_rules']: commands.append(s.command(r.pol.ssh(r.pol.base.NODES[node], shlex.join(['firewall-cmd', '--zone=public', '--remove-rich-rule=' + rule]))))
        return commands
    return []


def observe(s, name):
    if name.startswith('recover-') and not s.context.get('execution_backend'):
        return {'passed': True, 'runtime_not_started': True}
    if name in [item['name'] for item in RESTORE_STEPS]:
        if name in ['recover-applications', 'recover-components']:
            spaces = [AMBIENT, SIDECAR, SPIRE, PLAIN] if name == 'recover-applications' else [SYSTEM, SPIRE_SYSTEM]
            r.require(all(r.optional('namespace', ns) is None for ns in spaces), '实验 Namespace 未退出')
        if name == 'recover-globals': r.require(all(r.optional(o['kind'], o['metadata']['name']) is None for o in s.context['global_objects'].values()), '本批全局对象未卸载')
        if name == 'recover-cilium': verify_cilium(s)
        if name == 'recover-primary': return final_checks(s)
        return {'passed': True}
    if name in ['access', 'istio-crds']: return {'passed': True}
    return evidence.observe(s, name, sys.modules[__name__])


def verify_cilium(s):
    primary(s)
    r.require(dp.digest(dp.values()) == s.context['original_values_sha256'], 'Cilium 原值未恢复')
    r.require(hashlib.sha256(r.call(dp.helm('get', 'manifest', 'cilium', '-n', 'kube-system')).encode()).hexdigest() == s.context['original_manifest_sha256'], 'Cilium 原 manifest 未恢复')
    r.require(dp.digest(r.get('configmap', 'cilium-config', 'kube-system')['data']) == s.context['original_config_sha256'], 'Cilium ConfigMap 未恢复')
    for key, before in s.context['controllers'].items():
        kind, name = key.split('/'); current = r.get(kind, name, 'kube-system')
        r.require(current['metadata']['uid'] == before['uid'] and current['spec'] == before['spec'], '原控制器 UID/spec 未恢复：' + key)


def final_checks(s):
    verify_cilium(s)
    ca = r.get('configmap', 'kube-root-ca.crt', 'default')['data']['ca.crt']
    for node in r.WORKERS:
        current = worker_facts(node, ca)
        r.require(current['cni_files'] == s.context['worker_facts'][node]['cni_files'], 'VM CNI 文件未恢复：' + node)
        if node == r.WORKERS[0]:
            r.require(not set(current['ports']) & PILOT_PORTS, 'Istiod 主机端口仍被占用：' + node)
    for node, before in s.context['vm_facts'].items():
        current = dp.remote_facts(r.pol.base.NODES[node])
        for field in ['selinux', 'firewalld', 'rp_filter', 'rich_rules', 'permanent_rules']:
            r.require(current[field] == before[field], '原 VM 字段未恢复：' + node + '/' + field)
        r.require(sorted(current['routes'], key=dp.digest) == sorted(before['routes'], key=dp.digest), '原 VM 路由未恢复：' + node)
    return {'passed': True, 'primary': primary(s), 'cilium_original_content_restored': True, 'worker_cni_files_restored': True, 'vm_security_firewall_routes_restored': True}


def restore(s):
    return []


def final(s):
    if not s.context.get('execution_backend'):
        r.require(r.get('namespace', 'kube-system')['metadata']['uid'] == s.context['cluster_uid'], '准备未完成的恢复集群 UID 不同')
        r.save(s.records / 'postcheck.json', {'passed': True, 'runtime_not_started': True})
        return
    r.require(all(r.optional(o['kind'], o['metadata']['name']) is None for o in s.context['global_objects'].values()), '全局对象仍存在')
    r.save(s.records / 'postcheck.json', final_checks(s))


def post_final(s, closed):
    path = s.records / 'handoff-candidate.json'
    if path.exists() and (s.records / 'passed.json').exists():
        value = json.loads(path.read_text())
        value.update(cleanup_passed=closed['cleanup_passed'], closed_sha256=hashlib.sha256((s.records / 'state/closed.json').read_bytes()).hexdigest(), phase02_complete=False)
        r.save(s.records / 'handoff.json', value)


if __name__ == '__main__':
    cli.run(sys.modules[__name__])
