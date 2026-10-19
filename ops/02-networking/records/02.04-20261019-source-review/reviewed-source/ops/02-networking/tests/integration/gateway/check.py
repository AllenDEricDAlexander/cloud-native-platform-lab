#!/usr/bin/env python3
"""02.04 的身份、UID、配置准入与验收检查；对象变更由分项 Ansible 剧本执行。"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import http.client as http_client
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import sys
import time
import uuid

import yaml


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


HERE = Path(__file__).resolve().parent
l2 = module('gateway_l2', HERE.parent / 'metallb/check.py')
mat = module('gateway_materials', HERE / 'materials.py')
pki = module('gateway_pki', HERE / 'pki.py')
probe = module('gateway_probe', HERE / 'probe.py')
ROOT, PHASE, K = l2.ROOT, l2.PHASE, l2.K
require, save, call, ready = l2.require, l2.save, l2.call, l2.ready
PERMANENT_NS = ['envoy-gateway-system', 'cnpl-gateway']
TEMP_NS = ['lab-gateway-app', 'lab-gateway-backends', 'lab-gateway-denied', 'ingress-compare']
LABEL, COMPONENT = 'cnpl.io/gateway-run', 'phase02-gateway'
CONTROLLER = 'gateway.envoyproxy.io/cnpl-primary-controller'
REGISTRY = PHASE / 'records/components/gateway-components.json'
CUSTOM = {kind: name for kind, name in [('GatewayClass', 'gatewayclasses.gateway.networking.k8s.io'), ('Gateway', 'gateways.gateway.networking.k8s.io'), ('HTTPRoute', 'httproutes.gateway.networking.k8s.io'), ('GRPCRoute', 'grpcroutes.gateway.networking.k8s.io'), ('TCPRoute', 'tcproutes.gateway.networking.k8s.io'), ('UDPRoute', 'udproutes.gateway.networking.k8s.io'), ('BackendTLSPolicy', 'backendtlspolicies.gateway.networking.k8s.io'), ('ReferenceGrant', 'referencegrants.gateway.networking.k8s.io'), ('EnvoyProxy', 'envoyproxies.gateway.envoyproxy.io')]}
_crd_names = None


def get(kind, name=None, namespace=None):
    require(not any(k.split('.')[0] in ['secret', 'secrets'] for k in kind.lower().split(',')), 'Secret 只能读取白名单元数据或公开证书')
    return json.loads(call(K + ['get', kind] + ([name] if name else []) + (['-n', namespace] if namespace else []) + ['-o', 'json']))


def crd_names():
    global _crd_names
    if _crd_names is None:
        _crd_names = set(call(K + ['get', 'crds', '-o', 'jsonpath={range .items[*]}{.metadata.name}{"\n"}{end}']).splitlines())
    return _crd_names


def secret_meta(name, namespace):
    raw = call(K + ['get', 'secret', name, '-n', namespace, '--ignore-not-found', '-o', 'jsonpath={.metadata.uid}{"\n"}{.metadata.labels}{"\n"}{.type}']).strip()
    if not raw:
        return None
    lines = raw.splitlines()
    return {'kind': 'Secret', 'metadata': {'name': name, 'namespace': namespace, 'uid': lines[0], 'labels': json.loads(lines[1]) if len(lines) > 1 and lines[1] else {}}, 'type': lines[-1]}


def optional(kind, name, namespace=None):
    if kind.lower() == 'secret':
        return secret_meta(name, namespace)
    if kind in CUSTOM and CUSTOM[kind] not in crd_names():
        return None
    raw = call(K + ['get', kind, name, '--ignore-not-found', '-o', 'json'] + (['-n', namespace] if namespace else [])).strip()
    return json.loads(raw) if raw else None


def registry(context):
    if not REGISTRY.exists():
        return {'cluster_uid': context['cluster_uid'], 'objects': {}}
    value = json.loads(REGISTRY.read_text())
    require(value['cluster_uid'] == context['cluster_uid'], 'Gateway 组件登记属于其他集群')
    return value


def key(obj):
    m = obj['metadata']
    return obj['kind'] + '/' + m.get('namespace', '') + '/' + m['name']


def persistent(obj):
    kind, m = obj['kind'], obj['metadata']
    return (kind == 'Namespace' and m['name'] in PERMANENT_NS or m.get('namespace') in PERMANENT_NS or kind in ['GatewayClass', 'CustomResourceDefinition', 'ValidatingAdmissionPolicy', 'ValidatingAdmissionPolicyBinding'])


def prior(uid):
    pointer = json.loads((PHASE / 'records/completed/02.03.json').read_text())
    require(pointer['passed'] and pointer['cleanup_passed'] and pointer['cluster_uid'] == uid and pointer['next_step'] == '02.04', '需要完整同集群02.03交接')
    directory = Path(pointer['records']).resolve()
    require(directory.is_relative_to(PHASE / 'records'), '前序记录路径越界')
    for path, sha, flag in [('passed_receipt', 'passed_receipt_sha256', 'passed'), ('cleanup_receipt', 'cleanup_receipt_sha256', 'cleanup_passed')]:
        raw = (directory / pointer[path]).read_bytes()
        result = json.loads(raw)
        require(hashlib.sha256(raw).hexdigest() == pointer[sha] and result[flag] and result['run'] == pointer['run'] and result['cluster_uid'] == uid, '前序原始回执不一致')
    return pointer


def source():
    files = list(HERE.glob('*.py')) + [HERE / 'requirements.txt']
    files += list((PHASE / 'ansible/playbooks').glob('gateway*.yml')) + list((PHASE / 'ansible/tasks').glob('gateway*.yml'))
    files += list((PHASE / 'networking/gateway').glob('*.j2')) + list((PHASE / 'networking/ingress').glob('*.j2'))
    files += [PHASE / p for p in ['scripts/gateway.sh', 'ansible/vars/gateway.yml', 'examples/gateway/README.md', 'examples/gateway/main.go', 'examples/gateway/main_test.go', 'examples/gateway/go.mod', 'examples/gateway/go.sum', 'records/completed/02.03.json', 'records/components/metallb-primary.json']]
    files += [Path(l2.__file__), Path(l2.common.__file__), Path(l2.common.base.__file__)]
    files += [ROOT / p for p in ['ops/versions.lock.yaml', 'ops/inventory/vips.yaml', 'ops/inventory/networks.yaml', 'ops/inventory/hosts.yaml', 'ops/00-preparation/pki/public/cnpl-lab-root-ca.crt', 'ops/00-preparation/pki/public/cnpl-lab-issuing-ca.crt', 'ops/00-preparation/ansible/ansible.cfg', 'ops/00-preparation/ansible/inventories/lab/hosts.yml', 'ops/00-preparation/ansible/inventories/lab/group_vars/all.yml', 'ops/00-preparation/ansible/inventories/lab/group_vars/k8s_nodes.yml', 'ops/00-preparation/ansible/roles/dns_server/defaults/main.yml', 'ops/00-preparation/ansible/roles/dns_server/templates/forward.zone.j2']]
    require(all(p.is_file() for p in files), '缺少完整剧本、文档或受检输入')
    return {'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))}}


def protected():
    values = l2.protected()
    return {name: value for name, value in values.items() if name.split('/')[1] not in PERMANENT_NS + TEMP_NS}


def preflight(records, identity=False):
    path = Path(records) / 'context.json'
    if identity:
        context = json.loads(path.read_text())
        require(get('namespace', 'kube-system')['metadata']['uid'] == context['cluster_uid'] and call(K + ['config', 'view', '--minify', '-o', 'jsonpath={.clusters[0].cluster.server}']).strip() == 'https://api.k8s.internal.egon.top:6443', '恢复目标集群不同')
        return context
    context = l2.common.base.preflight(records)
    require(context.get('stage', '02.04') == '02.04', '记录目录属于其他步骤')
    context['stage'] = '02.04'
    context['previous'] = prior(context['cluster_uid'])
    context['component'] = l2.common.component_ready(context)
    require(l2.primary(context) == context['previous']['retained_primary'], '持久主池/宣告与02.03交接不同')
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect(('192.168.9.100', 6443))
        ip = sock.getsockname()[0]
    management = yaml.safe_load((ROOT / 'ops/00-preparation/ansible/inventories/lab/group_vars/all.yml').read_text())['lab_mgmt_sources']
    require(ip in management and context.get('mac_ip', ip) == ip, '管理Mac来源改变')
    context['mac_ip'] = ip
    known = registry(context)['objects']
    for name in PERMANENT_NS + TEMP_NS:
        obj = optional('Namespace', name)
        if obj:
            labels = obj['metadata'].get('labels', {})
            require(labels.get('cnpl.io/component') == COMPONENT and labels.get('cnpl.io/cluster-uid') == context['cluster_uid'], '已有Namespace不是本项目组件：' + name)
            if name in TEMP_NS:
                require(labels.get(LABEL) == context['run'], '实验Namespace属于其他运行，先对原记录recover')
            saved = known.get(key(obj)) or local_receipt(records, obj)
            require(saved and saved['uid'] == obj['metadata']['uid'], '已有Namespace缺少原始UID绑定')
    definitions = mat.crds()
    context['cluster_resources'] = {d['kind'] + '/' + d['metadata']['name']: l2.digest(d['spec']) for d in definitions}
    for name in [d['metadata']['name'] for d in definitions if d['kind'] == 'CustomResourceDefinition']:
        if name in crd_names():
            obj = get('crd', name)
            require(obj['metadata'].get('labels', {}).get('cnpl.io/cluster-uid') == context['cluster_uid'] and known.get(key(obj), {}).get('uid') == obj['metadata']['uid'], '已有Gateway CRD不是本项目登记，不能接管')
    for allocation in l2.allocations():
        namespace, name = allocation['namespace'], allocation['name']
        require((namespace, name, allocation['ip']) in [('envoy-gateway-system', 'cnpl-primary', '192.168.9.201'), ('ingress-compare', 'cnpl-ingress-compare', '192.168.9.203')], '主池已有其他业务，不能做网关故障/对照实验')
        obj = get('service', name, namespace)
        require(obj['metadata'].get('labels', {}).get('cnpl.io/cluster-uid') == context['cluster_uid'], 'VIP不是本组件')
    if CUSTOM['HTTPRoute'] in crd_names():
        for kind in ['httproutes', 'grpcroutes', 'tcproutes', 'udproutes']:
            for route in json.loads(call(K + ['get', kind, '-A', '-o', 'json']))['items']:
                if any(p.get('name') == 'primary' and p.get('namespace', route['metadata']['namespace']) == 'cnpl-gateway' for p in route['spec'].get('parentRefs', [])):
                    require(route['metadata']['namespace'] in ['cnpl-gateway', 'lab-gateway-app', 'lab-gateway-denied'], '已有其他业务绑定主Gateway，不能执行实验')
    context['active_ips'] = [a['ip'] for a in l2.allocations()]
    auth = pki.authority()
    context['issuing_ca_sha256'] = pki.fingerprint(auth['certificate'])
    save(path, context)
    return context


def local_receipt(records, obj):
    path = Path(records) / 'state' / ('object-' + key(obj).replace('/', '-') + '.json')
    return json.loads(path.read_text()) if path.exists() else None


def object_plan(records, context, doc):
    kind, m = doc['kind'], doc['metadata']
    namespace = m.get('namespace')
    allowed = ['Namespace', 'CustomResourceDefinition', 'ValidatingAdmissionPolicy', 'ValidatingAdmissionPolicyBinding', 'GatewayClass', 'Gateway', 'EnvoyProxy', 'HTTPRoute', 'GRPCRoute', 'TCPRoute', 'UDPRoute', 'BackendTLSPolicy', 'ReferenceGrant', 'Deployment', 'Service', 'ConfigMap', 'Role', 'RoleBinding', 'ServiceAccount', 'Ingress', 'Secret']
    require(kind in allowed, '对象类型超出02.04范围')
    if kind == 'Namespace':
        require(m['name'] in PERMANENT_NS + TEMP_NS and not namespace, 'Namespace范围越界')
    elif kind in ['GatewayClass', 'CustomResourceDefinition', 'ValidatingAdmissionPolicy', 'ValidatingAdmissionPolicyBinding']:
        if kind == 'GatewayClass':
            require(m['name'] == 'cnpl-envoy', 'GatewayClass范围越界')
        else:
            require(context['cluster_resources'].get(kind + '/' + m['name']) == l2.digest(doc['spec']), '集群资源不是锁定CRD包的一部分')
    else:
        require(namespace in PERMANENT_NS + TEMP_NS, '资源Namespace范围越界')
    labels = m.get('labels', {})
    permanent = persistent(doc)
    if permanent:
        require(labels.get('cnpl.io/component') == COMPONENT and labels.get('cnpl.io/cluster-uid') == context['cluster_uid'], '持久资源身份标签不同')
    else:
        require(labels.get(LABEL) == context['run'], '临时资源运行标签不同')
    obj = optional(kind, m['name'], namespace)
    if obj:
        current_labels = obj['metadata'].get('labels', {})
        require(current_labels.get('cnpl.io/cluster-uid') == context['cluster_uid'] if permanent else current_labels.get(LABEL) == context['run'], '拒绝接管外来对象')
        saved = registry(context)['objects'].get(key(obj)) if permanent else local_receipt(records, obj)
        require(saved and saved['uid'] == obj['metadata']['uid'], '对象UID改变或缺少原始绑定')
    return {'exists': bool(obj), 'persistent': permanent}


def record_object(records, context, obj):
    require(obj['kind'] != 'Secret' or not ({'data', 'stringData'} & obj.keys()), 'Secret证据禁止包含data或stringData')
    value = {'uid': obj['metadata']['uid'], 'kind': obj['kind'], 'name': obj['metadata']['name'], 'namespace': obj['metadata'].get('namespace', ''), 'run': context['run'], 'cluster_uid': context['cluster_uid'], 'spec_sha256': l2.digest(obj.get('spec'))}
    save(Path(records) / 'state' / ('object-' + key(obj).replace('/', '-') + '.json'), value)
    if persistent(obj):
        record = registry(context)
        record['objects'][key(obj)] = value
        save(REGISTRY, record)
    return value


def condition(obj, conditions, kind, status, reason=None):
    return any(c.get('type') == kind and c.get('status') == status and c.get('observedGeneration') == obj['metadata']['generation'] and (not reason or c.get('reason') == reason) for c in (conditions or []))


def route_condition(kind, name, status='True', reason=None, namespace='lab-gateway-app', condition_type='ResolvedRefs'):
    obj = get(kind, name, namespace)
    parents = [p for p in obj.get('status', {}).get('parents') or [] if p.get('controllerName') == CONTROLLER and p.get('parentRef', {}).get('name') == 'primary' and p['parentRef'].get('namespace', namespace) == 'cnpl-gateway']
    require(len(parents) == 1 and condition(obj, parents[0].get('conditions'), condition_type, status, reason), kind + '/' + name + ' 尚未获得本代 ' + condition_type + '=' + status)
    if condition_type == 'ResolvedRefs' and status == 'True':
        require(condition(obj, parents[0].get('conditions'), 'Accepted', 'True'), kind + '/' + name + ' 尚未获得本代 Accepted=True')
    return obj


def listener_condition(status, reason=None):
    obj = get('Gateway', 'primary', 'cnpl-gateway')
    listeners = [l for l in obj.get('status', {}).get('listeners') or [] if l['name'] == 'https']
    require(len(listeners) == 1 and condition(obj, listeners[0].get('conditions'), 'ResolvedRefs', status, reason), 'HTTPS listener引用状态尚未收敛')
    return obj


def backend_pods(context):
    result = {}
    for namespace in ['lab-gateway-app', 'lab-gateway-backends']:
        sets = get('replicasets', namespace=namespace)['items']
        deployments = get('deployments', namespace=namespace)['items']
        ownership = {s['metadata']['uid']: d for d in deployments for s in sets if any(o.get('uid') == d['metadata']['uid'] for o in s['metadata'].get('ownerReferences', []))}
        for pod in get('pods', namespace=namespace)['items']:
            if pod['metadata'].get('deletionTimestamp'):
                continue
            owner = next((ownership[o.get('uid')] for o in pod['metadata'].get('ownerReferences', []) if o.get('uid') in ownership), None)
            require(owner and pod['metadata'].get('labels', {}).get(LABEL) == context['run'], '发现外来后端Pod')
            require(pod['spec']['containers'][0]['image'] == mat.lock()['gateway_fixture']['internal_source'] and not pod['spec'].get('hostNetwork') and pod['spec'].get('automountServiceAccountToken') is False, '后端镜像或隔离模式不同')
            if ready(pod):
                result[pod['metadata']['name']] = {'uid': pod['metadata']['uid'], 'version': pod['metadata']['labels']['version'], 'node': pod['spec']['nodeName']}
    expected = {'v1': 2, 'v2': 2, 'shared': 1, 'secure': 1}
    require(all(sum(p['version'] == name for p in result.values()) == count for name, count in expected.items()) and len(result) == 6, '等待6个测试后端Ready')
    require(all(p['node'] in l2.WORKERS for p in result.values()), '后端调度到未允许VM')
    return result


def data_plane(context, laboratory=True):
    gateway = get('Gateway', 'primary', 'cnpl-gateway')
    klass = get('GatewayClass', 'cnpl-envoy')
    require(condition(klass, klass.get('status', {}).get('conditions'), 'Accepted', 'True'), 'GatewayClass尚未接受')
    for name in ['Accepted', 'Programmed']:
        require(condition(gateway, gateway.get('status', {}).get('conditions'), name, 'True'), 'Gateway本代尚未' + name)
    service = get('service', 'cnpl-primary', 'envoy-gateway-system')
    require(service['metadata'].get('labels', {}).get('cnpl.io/cluster-uid') == context['cluster_uid'], '主入口不是本集群登记的资源')
    require([i.get('ip') for i in (service.get('status', {}).get('loadBalancer', {}).get('ingress') or [])] == ['192.168.9.201'], '主入口尚未取得预留.201')
    require(service['spec'].get('allocateLoadBalancerNodePorts') is False and service['spec']['loadBalancerSourceRanges'] == [context['mac_ip'] + '/32'], '主入口来源或NodePort策略不同')
    expected = {(80, 'TCP'), (443, 'TCP')} | ({(9000, 'TCP'), (9001, 'UDP')} if laboratory else set())
    ports = service['spec'].get('ports') or []
    require({(p['port'], p.get('protocol', 'TCP')) for p in ports} == expected and all(not p.get('nodePort') for p in ports), '主入口端口尚未收敛到本阶段配置')
    dep = get('deployment', 'cnpl-primary', 'envoy-gateway-system')
    require(dep['metadata'].get('labels', {}).get('cnpl.io/cluster-uid') == context['cluster_uid'], '数据面Deployment身份不同')
    status = dep.get('status') or {}
    require(dep['spec']['replicas'] == status.get('readyReplicas') == 2 and status.get('observedGeneration') == dep['metadata']['generation'], '数据面尚未双副本Ready')
    require(dep['spec'].get('strategy') == {'type': 'RollingUpdate', 'rollingUpdate': {'maxSurge': 0, 'maxUnavailable': 1}}, '两VM硬反亲和需要无额外副本且最多一个不可用的滚动策略')
    sets = get('replicasets', namespace='envoy-gateway-system')['items']
    uids = {s['metadata']['uid'] for s in sets if any(o.get('uid') == dep['metadata']['uid'] for o in s['metadata'].get('ownerReferences', []))}
    pods = [p for p in get('pods', namespace='envoy-gateway-system')['items'] if not p['metadata'].get('deletionTimestamp') and any(o.get('uid') in uids for o in p['metadata'].get('ownerReferences', []))]
    require(len(pods) == 2 and all(ready(p) for p in pods) and {p['spec']['nodeName'] for p in pods} == set(l2.WORKERS), '数据面未跨两个worker VM就绪')
    require(all(p['spec'].get('terminationGracePeriodSeconds') == 45 for p in pods), '数据面没有使用实验约定的有界终止时间')
    allowed = {a['internal_source'] for a in mat.lock()['envoy_gateway']['artifacts']}
    require(all(c['image'] in allowed for p in pods for c in p['spec'].get('containers', []) + p['spec'].get('initContainers', [])), '数据面出现未锁定的镜像')
    return {'passed': True, 'gateway_uid': gateway['metadata']['uid'], 'service_uid': service['metadata']['uid'], 'deployment_uid': dep['metadata']['uid'], 'vip': '192.168.9.201', 'data_pods': [{'name': p['metadata']['name'], 'uid': p['metadata']['uid'], 'node': p['spec']['nodeName']} for p in pods]}


def dns_plan(before):
    text = Path(before).read_text()
    defaults = yaml.safe_load((ROOT / 'ops/00-preparation/ansible/roles/dns_server/defaults/main.yml').read_text())
    desired = int(defaults['dns_zone_serial'])
    begin, end = '; BEGIN CNPL GATEWAY A RECORDS', '; END CNPL GATEWAY A RECORDS'
    records = yaml.safe_load((ROOT / 'ops/inventory/vips.yaml').read_text())['gateway_dns_records']
    require({r['fqdn'] for r in records} == {'demo.svc.internal.egon.top', 'grpc-demo.svc.internal.egon.top'} and all(r['ip'] == '192.168.9.201' for r in records), 'DNS台账越过主Gateway身份')
    block = begin + '\n' + ''.join(r['fqdn'].removesuffix('.internal.egon.top') + '\t30 IN A\t' + r['ip'] + '\n' for r in sorted(records, key=lambda r: r['fqdn'])) + end + '\n'
    pattern = re.compile(re.escape(begin) + r'\n.*?' + re.escape(end) + r'\n?', re.S)
    existing = pattern.findall(text)
    require(len(existing) <= 1 and (not existing or existing[0].rstrip() == block.rstrip()), '已有Gateway DNS块内容不符，拒绝覆盖')
    other = pattern.sub('', text)
    for record in records:
        short = record['fqdn'].removesuffix('.internal.egon.top')
        require(not re.search(r'(?m)^' + re.escape(short) + r'(?:\.|\s)', other), '已有非本块DNS记录，拒绝接管 ' + short)
    match = re.search(r'(?m)^(\s*)(\d+)(\s*;\s*serial[^\n]*)$', text)
    require(match, '权威区域缺少可识别SOA serial')
    serial = int(match[2])
    if not existing:
        require(serial < desired, 'DNS serial已超过受检版本，先核对并更新源台账，不能降低serial')
        candidate = text[:match.start(2)] + str(desired) + text[match.end(2):]
        candidate = candidate.rstrip() + '\n' + block
    else:
        candidate = text
    return {'before_sha256': hashlib.sha256(text.encode()).hexdigest(), 'after_sha256': hashlib.sha256(candidate.encode()).hexdigest(), 'serial_before': serial, 'serial_after': desired if not existing else serial, 'changed': candidate != text, 'zone': 'internal.egon.top', 'records': records, 'candidate': candidate}


def tls_records(records):
    return json.loads((Path(records) / 'state/tls.json').read_text())


def secret_plan(records, context, path):
    require(Path(path).resolve().is_relative_to(pki.PRIVATE.resolve()), 'Secret清单只能位于私有目录')
    doc = json.loads(Path(path).read_text())
    require(doc['kind'] == 'Secret' and doc['type'] == 'kubernetes.io/tls' and set(doc['data']) == {'tls.crt', 'tls.key'}, 'Secret类型/字段不符')
    pairs = {('cnpl-gateway', 'primary-tls'): 'primary', ('lab-gateway-backends', 'foreign-frontend'): 'foreign', ('lab-gateway-backends', 'backend-tls'): 'backend', ('lab-gateway-app', 'compare-tls'): 'compare'}
    profile = pairs.get((doc['metadata']['namespace'], doc['metadata']['name']))
    require(profile, 'Secret范围越界')
    leaf = pki.x509.load_pem_x509_certificate(base64.b64decode(doc['data']['tls.crt']))
    require(pki.fingerprint(leaf) == tls_records(records)[profile]['sha256'], 'Secret公开证书与签发回执不同')
    key_material = pki.serialization.load_pem_private_key(base64.b64decode(doc['data']['tls.key']), password=None)
    public = lambda value: value.public_bytes(pki.serialization.Encoding.DER, pki.serialization.PublicFormat.SubjectPublicKeyInfo)
    require(public(key_material.public_key()) == public(leaf.public_key()), 'Secret叶证书与私钥不匹配')
    value = object_plan(records, context, doc)
    value['profile'] = profile
    return value


def record_secret(records, context, name, namespace, profile):
    obj = secret_meta(name, namespace)
    require(obj, 'Secret应用后不存在')
    raw = call(K + ['get', 'secret', name, '-n', namespace, '-o', 'jsonpath={.data.tls\\.crt}'])
    cert = pki.x509.load_pem_x509_certificate(base64.b64decode(raw))
    public_sha = pki.fingerprint(cert)
    require(public_sha == tls_records(records)[profile]['sha256'], '实际Secret公开证书不匹配')
    value = record_object(records, context, obj)
    value.update(certificate_sha256=public_sha, profile=profile)
    save(Path(records) / 'state' / ('object-' + key(obj).replace('/', '-') + '.json'), value)
    if persistent(obj):
        saved = registry(context)
        saved['objects'][key(obj)] = value
        save(REGISTRY, saved)
    return value


def frontend_plan(records, context, restore=False):
    obj = get('Gateway', 'primary', 'cnpl-gateway')
    binding = registry(context)['objects'].get(key(obj))
    require(binding and binding['uid'] == obj['metadata']['uid'], '主Gateway原始UID不同')
    listeners = obj['spec']['listeners']
    require(len(listeners) >= 2 and listeners[1]['name'] == 'https', '监听器顺序不同，不能生成精确补丁')
    refs = listeners[1]['tls']['certificateRefs']
    original = [{'group': '', 'kind': 'Secret', 'name': 'primary-tls'}]
    foreign = [{'group': '', 'kind': 'Secret', 'name': 'foreign-frontend', 'namespace': 'lab-gateway-backends'}]
    state = Path(records) / 'state/frontend-original.json'
    if not state.exists():
        require(refs == original, '首次保存前主证书引用已经改变')
        save(state, {'gateway_uid': obj['metadata']['uid'], 'refs': original})
    saved = json.loads(state.read_text())
    require(saved['gateway_uid'] == obj['metadata']['uid'] and saved['refs'] == original and refs in [original, foreign], '证书维护字段或UID被其他操作改变')
    target = original if restore else foreign
    return {'patch': [] if refs == target else [{'op': 'test', 'path': '/metadata/uid', 'value': obj['metadata']['uid']}, {'op': 'test', 'path': '/spec/listeners/1/name', 'value': 'https'}, {'op': 'test', 'path': '/spec/listeners/1/tls/certificateRefs', 'value': refs}, {'op': 'replace', 'path': '/spec/listeners/1/tls/certificateRefs', 'value': target}]}


def delete_plan(records, context, kind, name, namespace):
    allowed = {('ReferenceGrant', 'allow-shared', 'lab-gateway-backends'), ('ReferenceGrant', 'allow-frontend-secret', 'lab-gateway-backends'), ('ReferenceGrant', 'allow-secure', 'lab-gateway-backends'), ('Ingress', 'compare', 'lab-gateway-app')}
    require((kind, name, namespace) in allowed, '删除范围越界')
    obj = optional(kind, name, namespace)
    if obj:
        bound = local_receipt(records, obj)
        require(obj['metadata'].get('labels', {}).get(LABEL) == context['run'] and bound and bound['uid'] == obj['metadata']['uid'], '删除对象UID/运行归属不同')
    return {'exists': bool(obj)}


def helm_render(values, which):
    component = 'envoy_gateway' if which == 'eg' else 'ingress_compare'
    release, namespace = ('cnpl-eg', 'envoy-gateway-system') if which == 'eg' else ('cnpl-compare', 'ingress-compare')
    raw = mat.call([mat.HELM, 'template', release, mat.checked_chart(component), '-n', namespace, '--kube-version', '1.36.5', '--skip-crds', '-f', values])
    docs = [d for d in yaml.safe_load_all(raw) if d]
    require(all(d['kind'] not in ['Gateway', 'GatewayClass', 'CustomResourceDefinition'] for d in docs), 'Controller Chart意外包含其他Gateway/CRD')
    allowed_images = {a['internal_source'] for a in mat.lock()[component]['artifacts']}
    images = []
    for doc in docs:
        if doc['kind'] in ['Deployment', 'Job', 'DaemonSet']:
            containers = doc['spec']['template']['spec'].get('containers', []) + doc['spec']['template']['spec'].get('initContainers', [])
            for c in containers:
                images.append(c['image'])
                require(any(c['image'].split('@')[-1] == image.split('@')[-1] and c['image'].split('@')[0].split(':')[0] == image.split('@')[0] for image in allowed_images), 'Chart包含未锁定镜像')
    require(images, 'Chart没有工作负载')
    return release, namespace, docs, images


def helm_guard(context, values, which):
    release, namespace, docs, images = helm_render(values, which)
    ns = optional('Namespace', namespace)
    if ns:
        saved = registry(context)['objects'].get(key(ns)) if which == 'eg' else local_receipt(values.parent.parent.parent, ns)
        require(saved and saved['uid'] == ns['metadata']['uid'] and ns['metadata'].get('labels', {}).get('cnpl.io/cluster-uid') == context['cluster_uid'], 'release 所在 Namespace UID 或集群归属改变')
        require(which != 'compare' or ns['metadata'].get('labels', {}).get(LABEL) == context['run'], '临时 release Namespace 属于其他批次')
    releases = json.loads(call([str(mat.HELM), '--kubeconfig', str(Path.home() / '.cnpl-secrets/kubeconfig-lab-primary'), 'list', '-n', namespace, '--deployed', '--failed', '--pending', '--uninstalling', '--uninstalled', '--superseded', '-o', 'json']))
    require(all(r['name'] == release and r['chart'] == ('gateway-helm-v1.9.2' if which == 'eg' else 'traefik-42.0.0') for r in releases), 'Namespace有其他release或版本不同')
    for doc in docs:
        m = doc['metadata']
        if doc['kind'] == 'Secret':
            continue
        obj = optional(doc['kind'], m['name'], m.get('namespace'))
        if obj:
            annotations = obj['metadata'].get('annotations', {})
            require(annotations.get('meta.helm.sh/release-name') == release and annotations.get('meta.helm.sh/release-namespace') == namespace, 'Chart同名对象不是本release，拒绝接管')
    return {'passed': True, 'exists': bool(releases), 'release': release, 'namespace': namespace, 'images': images}


def controller_ready(context):
    dep = get('deployment', 'envoy-gateway', 'envoy-gateway-system')
    require((dep.get('status') or {}).get('readyReplicas') == dep['spec']['replicas'] == 1, 'Envoy Gateway控制面尚未Ready')
    expected = mat.lock()['envoy_gateway']['artifacts'][0]['internal_source']
    require(dep['spec']['template']['spec']['containers'][0]['image'] == expected, '控制面镜像不同')
    return {'passed': True, 'uid': dep['metadata']['uid'], 'replicas': 1, 'image': expected}


def validate_all(context, attempt):
    definitions = mat.crds()
    injected = []
    for definition in definitions:
        item = json.loads(json.dumps(definition))
        item['metadata'].setdefault('labels', {}).update({'cnpl.io/component': COMPONENT, 'cnpl.io/cluster-uid': context['cluster_uid']})
        injected.append(item)
        call(K + ['apply', '--server-side', '--field-manager=cnpl-gateway-crds', '--dry-run=server', '--validate=strict', '-f', '-'], json.dumps(item))
    (attempt / 'crds.yaml').write_text(yaml.safe_dump_all(injected, sort_keys=False))
    (attempt / 'crds-only.yaml').write_text(yaml.safe_dump_all([d for d in injected if d['kind'] == 'CustomResourceDefinition'], sort_keys=False))
    files = list(attempt.glob('*.yaml'))
    all_docs = [d for path in files if path.name not in ['crds.yaml', 'crds-only.yaml', 'controller-values.yaml', 'compare-values.yaml'] for d in yaml.safe_load_all(path.read_text()) if d]
    require({'GatewayClass', 'Gateway', 'EnvoyProxy', 'HTTPRoute', 'GRPCRoute', 'TCPRoute', 'UDPRoute', 'BackendTLSPolicy', 'ReferenceGrant', 'Ingress', 'Role', 'RoleBinding', 'ServiceAccount'} <= {d['kind'] for d in all_docs}, '整组缺少必需资源类型')
    structural = mat.validate_custom(all_docs, definitions)
    custom_kinds = {d['spec']['names']['kind'] for d in definitions if d['kind'] == 'CustomResourceDefinition'}
    builtin_count = 0
    for doc in all_docs:
        if doc['kind'] in custom_kinds:
            continue
        preview = json.loads(json.dumps(doc))
        if preview['kind'] != 'Namespace' and preview['metadata'].get('namespace'):
            preview['metadata']['namespace'] = 'lab-core'
        call(K + ['apply', '--dry-run=server', '--validate=strict', '-f', '-'], json.dumps(preview))
        builtin_count += 1
    charts = {}
    for which, filename in [('eg', 'controller-values.yaml'), ('compare', 'compare-values.yaml')]:
        release, namespace, docs, images = helm_render(attempt / filename, which)
        public = [d for d in docs if d['kind'] != 'Secret']
        (attempt / ('rendered-' + which + '.yaml')).write_text(yaml.safe_dump_all(public, sort_keys=False))
        for doc in public:
            preview = json.loads(json.dumps(doc))
            if preview['metadata'].get('namespace'):
                preview['metadata']['namespace'] = 'lab-core'
            call(K + ['apply', '--dry-run=server', '--validate=strict', '-f', '-'], json.dumps(preview))
        charts[which] = {'release': release, 'namespace': namespace, 'documents': len(public), 'images': images}
    return {'passed': True, 'stage': '02.04.01', 'gateway_api': '1.6.1', 'channel': 'Standard', 'envoy_gateway': '1.9.2', 'kubernetes': '1.36.5', 'standard_v1_protocols': ['HTTPRoute', 'GRPCRoute', 'TCPRoute', 'UDPRoute', 'BackendTLSPolicy', 'ReferenceGrant'], 'crd_documents': len(definitions), 'custom_structure': structural, 'builtin_server_dry_run': builtin_count, 'charts': charts, 'secrets': 'actual signing/crypto validation occurs at all/run entry before cluster changes; templates validated with isolated test CA'}


def checked_http(records, backends, path, version, address='192.168.9.201', profile='primary', **kwargs):
    row = probe.http(address, path, **kwargs)
    probe.identity(row, backends, version=version, nonce=row['nonce'])
    require(row['tls_peer_sha256'] == tls_records(records)[profile]['sha256'], '实际TLS证书不是登记身份')
    return row


def http_case(records, context):
    backends = backend_pods(context)
    route_condition('HTTPRoute', 'web')
    route_condition('HTTPRoute', 'secure')
    policy = get('BackendTLSPolicy', 'secure', 'lab-gateway-backends')
    require(any(a.get('controllerName') == CONTROLLER and condition(policy, a.get('conditions'), 'Accepted', 'True') for a in policy.get('status', {}).get('ancestors') or []), 'BackendTLSPolicy尚未被接受')
    rows = [checked_http(records, backends, path, version) for path, version in [('/v1', 'v1'), ('/v2/test', 'v2'), ('/rewrite/test', 'v1'), ('/headers', 'v1'), ('/secure', 'secure')]]
    require(rows[2]['body']['path'] == '/v1/test', 'URL重写未生效')
    require(rows[3]['body']['headers'].get('X-Cnpl-Gateway') == ['envoy'] and rows[3]['headers'].get('x-cnpl-controller') == 'envoy-gateway', '请求或响应Header修改未生效')
    require(rows[-1]['body'].get('protocol') == 'https' and rows[-1]['body'].get('tls') in ['TLS 1.2', 'TLS 1.3'], '网关到后端未实际使用TLS')
    redirect = probe.http('192.168.9.201', '/v1', tls=False)
    require(redirect['status'] == 301 and redirect['headers'].get('location') in ['https://' + probe.DEMO + '/v1', 'https://' + probe.DEMO + ':443/v1'], 'HTTP到HTTPS重定向不同')
    slow = probe.http('192.168.9.201', '/slow')
    require(slow['status'] == 504 and 500 <= slow['elapsed_ms'] < 4500, '后端超时未按规则返回504')
    missing = probe.http('192.168.9.201', '/not-routed')
    wrong = probe.http('192.168.9.201', '/v1', headers={'Host': 'unknown.svc.internal.egon.top'})
    require(missing['status'] == wrong['status'] == 404, '未知Path/Host意外进入后端')
    return {'passed': True, 'requests': rows, 'redirect': redirect, 'timeout': slow, 'unmatched': [missing, wrong], 'tls_model': 'client-to-gateway TLS termination plus separately verified gateway-to-backend TLS'}


def rbac_case():
    account = 'system:serviceaccount:lab-gateway-app:route-editor'
    cases = [('create', 'httproutes.gateway.networking.k8s.io', 'lab-gateway-app', True), ('create', 'referencegrants.gateway.networking.k8s.io', 'lab-gateway-backends', False), ('get', 'secrets', 'lab-gateway-backends', False), ('patch', 'gateways.gateway.networking.k8s.io', 'cnpl-gateway', False), ('patch', 'namespaces', None, False)]
    result = []
    for verb, resource, namespace, allowed in cases:
        args = K + ['auth', 'can-i', verb, resource, '--as', account] + (['-n', namespace] if namespace else [])
        reply = subprocess.run(args, capture_output=True, text=True, timeout=30)
        require(reply.returncode == (0 if allowed else 1) and reply.stdout.strip() == ('yes' if allowed else 'no'), '业务角色权限不符合授权边界')
        result.append({'verb': verb, 'resource': resource, 'namespace': namespace, 'allowed': allowed})
    route_condition('HTTPRoute', 'untrusted', 'False', 'NotAllowedByListeners', 'lab-gateway-denied', 'Accepted')
    rejected = probe.http('192.168.9.201', '/v1', host='forbidden.svc.internal.egon.top', tls=False)
    require(rejected['status'] == 404, '未授权Namespace的Route意外生效')
    return {'passed': True, 'service_account': account, 'authorization': result, 'untrusted_route': rejected}


def shared_case(records, context, allowed):
    route_condition('HTTPRoute', 'shared', 'True' if allowed else 'False', None if allowed else 'RefNotPermitted')
    row = probe.http('192.168.9.201', '/shared')
    if allowed:
        probe.identity(row, backend_pods(context), version='shared', nonce=row['nonce'])
    else:
        require(row['status'] in [500, 503] and (not isinstance(row.get('body'), dict) or not (row['body'].get('pod') or row['body'].get('uid'))), '未授权跨空间后端仍可访问')
    return {'passed': True, 'reference_granted': allowed, 'request': row}


def frontend_case(records, context, profile, denied=False):
    listener_condition('False' if denied else 'True', 'RefNotPermitted' if denied else None)
    try:
        row = probe.http('192.168.9.201', '/v1', timeout=2)
    except (OSError, http_client.HTTPException):
        if not denied:
            raise
        return {'passed': True, 'reference_granted': False, 'tls_connected': False}
    if denied:
        require(row['tls_peer_sha256'] == tls_records(records)['primary']['sha256'], '未授权外国Secret证书被实际使用')
    else:
        probe.identity(row, backend_pods(context), version='v1', nonce=row['nonce'])
        require(row['tls_peer_sha256'] == tls_records(records)[profile]['sha256'], '授权证书切换未在真实TLS生效')
    return {'passed': True, 'reference_granted': not denied, 'profile': profile, 'request': row}


def protocol_case(context):
    backends = backend_pods(context)
    for kind, name in [('GRPCRoute', 'health'), ('TCPRoute', 'tcp'), ('UDPRoute', 'udp')]:
        route_condition(kind, name)
    client = Path(mat.lock()['gateway_fixture']['client']['path'])
    require(hashlib.sha256(client.read_bytes()).hexdigest() == mat.lock()['gateway_fixture']['client']['sha256'], '本机gRPC客户端摘要不同')
    rpc = [probe.grpc(client, '192.168.9.201', backends) for _ in range(3)]
    transport = [probe.exchange('192.168.9.201', protocol, backends) for protocol in ['tcp', 'udp'] for _ in range(3)]
    return {'passed': True, 'grpc_method': 'grpc.health.v1.Health/Check', 'grpc': rpc, 'transports': transport, 'scope': 'dedicated protocol fixtures; database and broker discovery semantics are not inferred from port reachability'}


def ingress_case(records, context):
    backends = backend_pods(context)
    ingress = get('ingress', 'compare', 'lab-gateway-app')
    require(ingress['spec']['ingressClassName'] == 'cnpl-compare', 'IngressClass不同')
    service = get('service', 'cnpl-ingress-compare', 'ingress-compare')
    require([a.get('ip') for a in (service.get('status', {}).get('loadBalancer', {}).get('ingress') or [])] == ['192.168.9.203'], 'Ingress尚未取得独立入口.203')
    require(service['spec'].get('allocateLoadBalancerNodePorts') is False and service['spec']['loadBalancerSourceRanges'] == [context['mac_ip'] + '/32'], 'Ingress来源或NodePort策略不同')
    klass = get('ingressclass', 'cnpl-compare')
    require(klass['metadata'].get('annotations', {}).get('ingressclass.kubernetes.io/is-default-class') != 'true', '对照IngressClass不能成为默认类')
    rows = [checked_http(records, backends, path, version, address='192.168.9.203', profile='compare') for path, version in [('/v1', 'v1'), ('/v2/test', 'v2')]]
    wrong = probe.http('192.168.9.203', '/v1', headers={'Host': 'unknown.svc.internal.egon.top'})
    require(wrong['status'] == 404, 'Ingress未知Host仍进入应用')
    redirect = probe.http('192.168.9.203', '/v1', tls=False)
    require(redirect['status'] in [301, 308] and redirect['headers'].get('location') in ['https://' + probe.DEMO + '/v1', 'https://' + probe.DEMO + ':443/v1'], 'Ingress HTTP/HTTPS重定向不同')
    return {'passed': True, 'implementation': 'Traefik3.7.14', 'vip': '192.168.9.203', 'requests': rows, 'unknown_host': wrong, 'redirect': redirect, 'comparison': 'same backend Host/Path/TLS; standard Ingress does not define the Gateway API weight/header interface'}


def weight_case(records, context, attempt):
    route_condition('HTTPRoute', 'weighted')
    backends = backend_pods(context)
    counts = {'v1': 0, 'v2': 0}
    with (attempt / 'weighted-requests.jsonl').open('w') as output:
        for _ in range(200):
            row = probe.http('192.168.9.201', '/weight')
            body = probe.identity(row, backends, nonce=row['nonce'])
            require(body['version'] in counts and row['tls_peer_sha256'] == tls_records(records)['primary']['sha256'], '权重请求进入未知后端或TLS身份不同')
            counts[body['version']] += 1
            output.write(json.dumps(row) + '\n')
    require(20 <= counts['v2'] <= 70 and counts['v1'] > 0, '200个独立连接未呈现80/20规则的合理分布')
    headers = [checked_http(records, backends, '/weight', 'v2', headers={'X-Cnpl-Canary': 'always'}) for _ in range(10)]
    return {'passed': True, 'configured_weights': {'v1': 80, 'v2': 20}, 'observed': counts, 'requests': 200, 'accepted_v2_range': [20, 70], 'forced_header_requests': len(headers), 'header_samples': headers, 'argo_rollouts_adapter': 'not installed or assumed; these are validated manual route controls'}


def dns_check(attempt):
    plan = json.loads((attempt / 'dns-plan.json').read_text())
    answers = {}
    for record in plan['records']:
        value = call(['dig', '@192.168.9.11', '+short', '+time=3', '+tries=1', record['fqdn'], 'A']).splitlines()
        require(value == ['192.168.9.201'], '权威DNS没有正确主入口A记录')
        answers[record['fqdn']] = value
    deadline = time.monotonic() + 330
    while True:
        try:
            resolved = {name: sorted({x[4][0] for x in socket.getaddrinfo(name, 443, socket.AF_INET, socket.SOCK_STREAM)}) for name in answers}
            if all(values == ['192.168.9.201'] for values in resolved.values()):
                return {'passed': True, 'authoritative': answers, 'system_resolver': resolved, 'retained_for_main_gateway': True}
        except socket.gaierror:
            pass
        require(time.monotonic() < deadline, 'Mac内部域解析未恢复；已等待既有负缓存TTL')
        time.sleep(3)


def disrupt_plan(context):
    state = data_plane(context)
    pod = sorted(state['data_pods'], key=lambda p: p['name'])[0]
    return {'pod': pod, 'before': state, 'at_mono': time.monotonic()}


def disrupt_state(context, attempt):
    plan = json.loads((attempt / 'disrupt-plan.json').read_text())
    state = data_plane(context)
    require(state['gateway_uid'] == plan['before']['gateway_uid'] and state['service_uid'] == plan['before']['service_uid'] and state['deployment_uid'] == plan['before']['deployment_uid'], '网关/Service/Deployment被重建')
    require(plan['pod']['uid'] not in {p['uid'] for p in state['data_pods']}, '被删除的Pod仍在数据面')
    retained = {p['uid'] for p in plan['before']['data_pods']} - {plan['pod']['uid']}
    require(retained <= {p['uid'] for p in state['data_pods']}, '另一数据面Pod也被替换，不能归为单Pod故障实验')
    return dict(state, observed_mono=time.monotonic())


def cold_proxy(context, attempt):
    state = disrupt_state(context, attempt)
    old = json.loads((attempt / 'disrupt-plan.json').read_text())['before']['data_pods']
    new = next(p for p in state['data_pods'] if p['uid'] not in {x['uid'] for x in old})
    service = get('service', 'cnpl-primary', 'envoy-gateway-system')
    target = next(p['targetPort'] for p in service['spec']['ports'] if p['port'] == 443)
    if isinstance(target, str):
        pod = get('pod', new['name'], 'envoy-gateway-system')
        target = next(p['containerPort'] for c in pod['spec']['containers'] for p in c.get('ports', []) if p['name'] == target)
    backends = backend_pods(context)
    client = Path(mat.lock()['gateway_fixture']['client']['path'])
    with probe.forwarded(K, new['name'], [target, 19001], attempt / 'cold-proxy-forward.txt') as ports:
        row = probe.http('127.0.0.1', '/v1', port=ports[target])
        probe.identity(row, backends, version='v1', nonce=row['nonce'])
        require(row['tls_peer_sha256'] == tls_records(attempt.parent.parent)['primary']['sha256'], '新Pod没有提供登记的主证书')
        rpc = probe.grpc(client, '127.0.0.1', backends, port=ports[target])
        connection = http_client.HTTPConnection('127.0.0.1', ports[19001], timeout=3)
        try:
            connection.request('GET', '/stats/prometheus')
            response = connection.getresponse()
            metrics = response.read(2 * 1024 * 1024).decode()
            require(response.status == 200, '冷启动Pod指标不可读')
        finally:
            connection.close()
        (attempt / 'cold-proxy-metrics.txt').write_text(metrics)
        stats = probe.xds_metrics(metrics)
    return {'passed': True, 'new_pod': new, 'http': row, 'grpc': rpc, 'xds': stats}


def observer_alive(attempt):
    path = attempt / 'observer-pid.json'
    if not path.exists():
        return False
    result = subprocess.run(['/bin/ps', '-ww', '-p', str(json.loads(path.read_text())['pid']), '-o', 'command='], capture_output=True, text=True, timeout=5)
    if result.returncode != 0:
        return False
    try:
        argv = shlex.split(result.stdout.strip())
        index = argv.index('observe')
        return index > 0 and Path(argv[index - 1]).resolve() == Path(__file__).resolve() and Path(argv[argv.index('--attempt') + 1]).resolve() == attempt.resolve()
    except (ValueError, IndexError):
        return False


def stop_observers(records):
    for attempt in (Path(records) / 'attempts').glob('*'):
        if (attempt / 'disrupt-plan.json').exists():
            (attempt / 'observer.stop').touch()
    deadline = time.monotonic() + 25
    while True:
        live = [a for a in (Path(records) / 'attempts').glob('*') if observer_alive(a)]
        if not live:
            return {'stopped': True}
        for attempt in live:
            (attempt / 'observer.stop').touch()
        require(time.monotonic() < deadline, '本批观测进程尚未停止')
        time.sleep(1)


def complete_rows(path):
    text = Path(path).read_text()
    return [json.loads(line) for line in text[:text.rfind('\n') + 1].splitlines() if line]


def disruption_result(context, attempt):
    before = json.loads((attempt / 'disrupt-plan.json').read_text())
    after = json.loads((attempt / 'replacement.json').read_text())
    summary = json.loads((attempt / 'observer-summary.json').read_text())
    rows = complete_rows(attempt / 'traffic.jsonl')
    require(summary['stopped'] and len(rows) == summary['samples'], '观测没有完整结束')
    successes = [r for r in rows if r['passed'] and r['started_mono'] >= after['observed_mono']]
    require(len(successes) >= 10 and before['pod']['uid'] not in {p['uid'] for p in after['data_pods']}, '缺少Pod替换后实际成功请求')
    cold = json.loads((attempt / 'cold-proxy.json').read_text())
    require(cold['passed'], '冷启动Pod未验证实际HTTP/gRPC和xDS')
    return {'passed': True, 'deleted_pod': before['pod'], 'replacement': after, 'requests': len(rows), 'failed_samples': sum(not r['passed'] for r in rows), 'successful_requests_after_replacement': len(successes), 'cold_proxy': cold}


def secret_list(namespace):
    raw = call(K + ['get', 'secrets', '-n', namespace, '-o', 'jsonpath={range .items[*]}{.metadata.name}{"\t"}{.metadata.uid}{"\t"}{.metadata.labels}{"\n"}{end}'])
    result = []
    for line in raw.splitlines():
        name, uid, labels = line.split('\t')
        result.append({'kind': 'Secret', 'metadata': {'name': name, 'namespace': namespace, 'uid': uid, 'labels': json.loads(labels) if labels else {}}})
    return result


def cleanup_plan(records, context, namespace):
    require(namespace in TEMP_NS, '清理Namespace范围越界')
    ns = optional('Namespace', namespace)
    if not ns:
        return {'exists': False}
    bound = local_receipt(records, ns)
    require(ns['metadata'].get('labels', {}).get(LABEL) == context['run'] and bound and bound['uid'] == ns['metadata']['uid'], 'Namespace UID/运行归属不同')
    types = ['pods', 'deployments', 'replicasets', 'daemonsets', 'statefulsets', 'services', 'configmaps', 'serviceaccounts', 'roles', 'rolebindings', 'jobs', 'cronjobs', 'persistentvolumeclaims', 'networkpolicies', 'ciliumnetworkpolicies', 'ingresses', 'horizontalpodautoscalers', 'resourcequotas', 'limitranges']
    types += [kind.lower() for kind, crd in CUSTOM.items() if crd in crd_names() and kind not in ['GatewayClass', 'EnvoyProxy', 'Gateway']]
    objects = get(','.join(types), namespace=namespace)['items'] + secret_list(namespace)
    for obj in objects:
        if (obj['kind'], obj['metadata']['name']) in [('ConfigMap', 'kube-root-ca.crt'), ('ServiceAccount', 'default')]:
            continue
        require(obj['metadata'].get('labels', {}).get(LABEL) == context['run'], '空间存在外来资源，不能清理：' + obj['kind'] + '/' + obj['metadata']['name'])
    services = {s['metadata']['uid'] for s in objects if s['kind'] == 'Service'}
    for obj in get('endpointslices', namespace=namespace)['items']:
        require(any(o.get('uid') in services for o in obj['metadata'].get('ownerReferences', [])), '有外来EndpointSlice，拒绝清理')
    return {'exists': True, 'uid': ns['metadata']['uid']}


def accept(records, context, attempt):
    names = ['compatibility', 'main-ready', 'dns', 'http', 'rbac', 'shared-denied', 'shared-allowed', 'shared-revoked', 'frontend-denied', 'frontend-allowed', 'frontend-restored', 'protocols', 'ingress', 'weights', 'disruption']
    results = {name: json.loads((attempt / (name + '.json')).read_text()) for name in names}
    require(all(value['passed'] for value in results.values()), '完整02.04存在缺项或未通过项')
    require(protected() == json.loads((Path(records) / 'state/protected.json').read_text()), '原有集群工作负载/关键配置改变')
    require(source() == json.loads((Path(records) / 'state/source.json').read_text()), '执行期间源码或输入改变')
    data = data_plane(context)
    require(json.loads((attempt / 'frontend-restored.json').read_text())['request']['tls_peer_sha256'] == tls_records(records)['primary']['sha256'], '主证书未恢复')
    return {'passed': True, 'cleanup_passed': False, 'stage': '02.04', 'run': context['run'], 'cluster_uid': context['cluster_uid'], 'steps': ['02.04.' + str(i).zfill(2) for i in range(1, 8)], 'attempt': str(attempt), 'results': results, 'retained_main': data, 'source': source()}


def main_exists(context):
    obj = optional('Gateway', 'primary', 'cnpl-gateway')
    if obj:
        bound = registry(context)['objects'].get(key(obj))
        require(bound and bound['uid'] == obj['metadata']['uid'] and obj['metadata'].get('labels', {}).get('cnpl.io/cluster-uid') == context['cluster_uid'], '主Gateway UID或集群归属改变')
    return {'exists': bool(obj)}


def final(records, context, attempt):
    stop_observers(records)
    require(all(optional('Namespace', ns) is None for ns in TEMP_NS), '临时实验Namespace尚未清空')
    require(optional('ingressclass', 'cnpl-compare') is None, '临时IngressClass尚未撤销')
    baseline = Path(records) / 'state/protected.json'
    require(baseline.exists() or not list((Path(records) / 'state').glob('object-*.json')), '发生对象变更却缺少原保护基线')
    require(not baseline.exists() or protected() == json.loads(baseline.read_text()), '原有工作负载/关键配置改变')
    require(l2.common.base.preflight(records)['cluster_uid'] == context['cluster_uid'], '清理后集群身份不同')
    exists = main_exists(context)['exists']
    formal = (Path(records) / 'passed.json').exists()
    main, pending = None, None
    if exists:
        try:
            main = data_plane(context, laboratory=False)
            row = probe.http('192.168.9.201', '/v1')
            require(row['status'] == 404 and row['tls_peer_sha256'] == tls_records(records)['primary']['sha256'], '实验路由尚未撤销或主TLS身份改变')
            for name in [probe.DEMO, probe.GRPC]:
                require(call(['dig', '@192.168.9.11', '+short', '+time=3', '+tries=1', name, 'A']).splitlines() == ['192.168.9.201'], '主入口持久DNS记录不符')
            main['tls_peer_sha256'] = row['tls_peer_sha256']
            for kind in ['deployment', 'service']:
                obj = get(kind, 'cnpl-primary', 'envoy-gateway-system')
                saved = registry(context)['objects'].get(key(obj))
                require(saved and saved['uid'] == obj['metadata']['uid'], '持久数据面 UID 改变')
                record_object(records, context, obj)
            record = registry(context)
            record.update(passed=formal, primary=main, dns_names=[probe.DEMO, probe.GRPC], tls_certificate_sha256=row['tls_peer_sha256'], manual_tls_replacement_planned_for_phase_02_05=True)
            save(REGISTRY, record)
        except (ValueError, OSError, KeyError, http_client.HTTPException) as error:
            if formal:
                raise
            main, pending = None, str(error)
    require(not formal or main, '正式验收后主入口缺失')
    return {'cleanup_passed': True, 'stage': '02.04', 'run': context['run'], 'cluster_uid': context['cluster_uid'], 'temporary_namespaces_absent': True, 'comparison_removed': True, 'observers_stopped': True, 'main_gateway': main, 'main_status': 'ready' if main else ('incomplete_retained' if exists else 'not_created'), 'pending_main_reason': pending, 'retained_dns_names': [probe.DEMO, probe.GRPC] if main else [], 'existing_workloads_unchanged': True if baseline.exists() else 'no_mutation_started', 'formal_acceptance_passed': formal}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['preflight', 'identity', 'source', 'protected', 'validate', 'build', 'object-plan', 'record', 'secret-plan', 'record-secret', 'helm-guard', 'controller-ready', 'fixtures', 'main-ready', 'main-exists', 'case', 'frontend-plan', 'frontend-restore-plan', 'delete-plan', 'dns-plan', 'dns-check', 'disrupt-plan', 'disrupt-state', 'disrupt-delete-plan', 'observe', 'observe-ready', 'post-disruption-samples', 'stop-observers', 'disrupt-analyse', 'cleanup-plan', 'accept', 'final'])
    p.add_argument('--records', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--attempt', type=Path)
    p.add_argument('--manifest', type=Path)
    p.add_argument('--which', default='eg', choices=['eg', 'compare'])
    p.add_argument('--values', type=Path)
    p.add_argument('--kind', default='ReferenceGrant')
    p.add_argument('--name')
    p.add_argument('--namespace')
    p.add_argument('--profile')
    p.add_argument('--case')
    a = p.parse_args()
    records, attempt = a.records.resolve(), a.attempt
    if attempt:
        require(attempt.resolve().is_relative_to(records / 'attempts'), 'attempt路径越界')
    if a.mode in ['preflight', 'identity']:
        value = preflight(records, a.mode == 'identity')
    elif a.mode == 'source':
        value = source()
    elif a.mode == 'protected':
        value = protected()
    elif a.mode == 'build':
        value = mat.build(a.output)
        expected = mat.lock()['gateway_fixture']
        require(value['source_sha256'] == expected['source_sha256'] and value['manifest_digest'] == expected['manifest_digest'] and value['binaries']['darwin-arm64']['sha256'] == expected['client']['sha256'], '诊断源码/镜像/客户端与锁定物料不同')
    else:
        context = json.loads((records / 'context.json').read_text())
        if a.mode == 'validate':
            value = validate_all(context, attempt)
        elif a.mode == 'object-plan':
            value = object_plan(records, context, json.loads(a.manifest.read_text()))
        elif a.mode == 'record':
            value = record_object(records, context, json.loads(a.manifest.read_text()))
        elif a.mode == 'secret-plan':
            value = secret_plan(records, context, a.manifest)
        elif a.mode == 'record-secret':
            value = record_secret(records, context, a.name, a.namespace, a.profile)
        elif a.mode == 'helm-guard':
            value = helm_guard(context, a.values, a.which)
        elif a.mode == 'controller-ready':
            value = controller_ready(context)
            record_object(records, context, get('deployment', 'envoy-gateway', 'envoy-gateway-system'))
        elif a.mode == 'fixtures':
            value = {'passed': True, 'backends': backend_pods(context)}
        elif a.mode == 'main-ready':
            value = data_plane(context)
            for kind in ['deployment', 'service']:
                record_object(records, context, get(kind, 'cnpl-primary', 'envoy-gateway-system'))
        elif a.mode == 'main-exists':
            value = main_exists(context)
        elif a.mode in ['frontend-plan', 'frontend-restore-plan']:
            value = frontend_plan(records, context, a.mode == 'frontend-restore-plan')
        elif a.mode == 'delete-plan':
            value = delete_plan(records, context, a.kind, a.name, a.namespace)
        elif a.mode == 'dns-plan':
            value = dns_plan(a.manifest)
            (attempt / 'gateway-forward.zone').write_text(value.pop('candidate'))
        elif a.mode == 'dns-check':
            value = dns_check(attempt)
        elif a.mode == 'disrupt-plan':
            value = disrupt_plan(context)
        elif a.mode == 'disrupt-delete-plan':
            value = json.loads((attempt / 'disrupt-plan.json').read_text())
            pod = get('pod', value['pod']['name'], 'envoy-gateway-system')
            require(pod['metadata']['uid'] == value['pod']['uid'], '待删除Pod UID已改变')
        elif a.mode == 'disrupt-state':
            value = disrupt_state(context, attempt)
        elif a.mode == 'observe':
            value = probe.observe(attempt, backend_pods(context), tls_records(records)['primary']['sha256'])
        elif a.mode == 'observe-ready':
            require((attempt / 'observer.ready').exists(), '等待实际HTTPS观测预热')
            value = {'passed': True}
        elif a.mode == 'post-disruption-samples':
            after = json.loads((attempt / 'replacement.json').read_text())
            require(sum(r['passed'] and r['started_mono'] >= after['observed_mono'] for r in complete_rows(attempt / 'traffic.jsonl')) >= 10, '等待Pod替换后至少10个成功请求')
            value = {'passed': True}
        elif a.mode == 'disrupt-analyse':
            value = disruption_result(context, attempt)
        elif a.mode == 'stop-observers':
            value = stop_observers(records)
        elif a.mode == 'cleanup-plan':
            value = cleanup_plan(records, context, a.namespace)
        elif a.mode == 'accept':
            value = accept(records, context, attempt)
        elif a.mode == 'final':
            value = final(records, context, attempt)
        else:
            cases = {'http': lambda: http_case(records, context), 'rbac': rbac_case, 'shared-denied': lambda: shared_case(records, context, False), 'shared-allowed': lambda: shared_case(records, context, True), 'shared-revoked': lambda: shared_case(records, context, False), 'frontend-denied': lambda: frontend_case(records, context, 'primary', True), 'frontend-allowed': lambda: frontend_case(records, context, 'foreign'), 'frontend-restored': lambda: frontend_case(records, context, 'primary'), 'protocols': lambda: protocol_case(context), 'ingress': lambda: ingress_case(records, context), 'weights': lambda: weight_case(records, context, attempt), 'cold-proxy': lambda: cold_proxy(context, attempt)}
            require(a.case in cases, '未知验收用例')
            value = cases[a.case]()
    save(a.output, value)
    print(json.dumps(value, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, http_client.HTTPException, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
