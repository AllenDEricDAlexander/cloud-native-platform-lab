#!/usr/bin/env python3
"""02.03 只读检查、精确变更计划与有界流量观测；集群变更由 Ansible 执行。"""
import argparse
from datetime import datetime, timezone
import errno
import hashlib
import http.client
import importlib.util
import ipaddress
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

spec = importlib.util.spec_from_file_location('services_checks', Path(__file__).resolve().parents[1] / 'services/check.py')
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)
spec = importlib.util.spec_from_file_location('l2_monitor', Path(__file__).with_name('monitor.py'))
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)
ROOT, PHASE, K = common.ROOT, common.PHASE, common.K
require, save, call, get, ready = common.require, common.save, common.call, common.get, common.ready
NS, META, POOL, SPEAKER = 'lab-metallb', 'metallb-system', 'cnpl-primary', 'cnpl-metallb-speaker'
LABEL, COMPONENT, VIP = 'cnpl.io/metallb-run', 'metallb-primary', '192.168.9.202'
WORKERS = common.WORKERS
PRIMARY_RECORD = PHASE / 'records/components/metallb-primary.json'


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def prior(uid):
    pointer = json.loads((PHASE / 'records/completed/02.02.json').read_text())
    require(pointer['passed'] and pointer['cleanup_passed'] and pointer['cluster_uid'] == uid and pointer['next_step'] == '02.03', '需要同集群完整 02.02 验收和清理交接')
    folder = Path(pointer['records']).resolve()
    require(folder.is_relative_to(PHASE / 'records'), '前序记录路径越界')
    for path, sha, flag in [('passed_receipt', 'passed_receipt_sha256', 'passed'), ('cleanup_receipt', 'cleanup_receipt_sha256', 'cleanup_passed')]:
        raw = (folder / pointer[path]).read_bytes()
        value = json.loads(raw)
        require(hashlib.sha256(raw).hexdigest() == pointer[sha] and value[flag] and value['run'] == pointer['run'] and value['cluster_uid'] == uid, '前序原始回执不一致')
    return pointer


def protected():
    result = {}
    objects = json.loads(call(K + ['get', 'deployments,daemonsets,services', '-A', '-o', 'json']))['items']
    for obj in objects:
        ns = obj['metadata']['namespace']
        if ns != NS:
            result[obj['kind'] + '/' + ns + '/' + obj['metadata']['name']] = {'uid': obj['metadata']['uid'], 'spec_sha256': digest(obj['spec'])}
    for name in ['coredns', 'cilium-config', 'kube-proxy']:
        obj = get('configmap', name, 'kube-system')
        result['ConfigMap/kube-system/' + name] = {'uid': obj['metadata']['uid'], 'data_sha256': digest(obj['data'])}
    return result


def source():
    files = list((PHASE / 'ansible/playbooks').glob('metallb*.yml')) + list((PHASE / 'ansible/tasks').glob('metallb*.yml'))
    files += list(Path(__file__).parent.glob('*.py')) + list((PHASE / 'networking/metallb').glob('*'))
    files += [PHASE / p for p in ['scripts/metallb.sh', 'ansible/vars/metallb.yml', 'examples/metallb/README.md', 'records/completed/02.02.json', 'records/components/metallb.json', 'examples/network-baseline/main.go', 'examples/network-baseline/go.mod']]
    files += [Path(common.__file__), Path(common.base.__file__), ROOT / 'ops/versions.lock.yaml', ROOT / 'ops/inventory/vips.yaml', ROOT / 'ops/inventory/networks.yaml']
    files += [ROOT / 'ops/00-preparation/ansible' / p for p in ['ansible.cfg', 'inventories/lab/hosts.yml', 'inventories/lab/group_vars/all.yml', 'inventories/lab/group_vars/k8s_nodes.yml']]
    require(all(p.is_file() for p in files), '缺少整组剧本、文档或物料输入')
    return {'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))}}


def ip_bounds(value):
    if '-' in value:
        left, right = [ipaddress.ip_address(p) for p in value.split('-', 1)]
        require(left.version == right.version and int(left) <= int(right), '地址区间无效')
        return left.version, int(left), int(right)
    network = ipaddress.ip_network(value, strict=False)
    return network.version, int(network.network_address), int(network.broadcast_address)


def pool_spec(kind):
    if kind == 'IPAddressPool':
        return {'addresses': ['192.168.9.201-192.168.9.210'], 'autoAssign': False, 'avoidBuggyIPs': False, 'serviceAllocation': {'serviceSelectors': [{'matchLabels': {'cnpl.io/vip-policy': 'primary'}}]}}
    return {'ipAddressPools': [POOL], 'interfaces': ['ens33'], 'nodeSelectors': [{'matchLabels': {'kubernetes.io/hostname': node}} for node in WORKERS]}


def pool_owned(obj, context):
    labels = obj['metadata'].get('labels', {})
    require(labels.get('cnpl.io/component') == COMPONENT and labels.get('cnpl.io/cluster-uid') == context['cluster_uid'], '主池或宣告不是本集群组件')
    require(obj['spec'] == pool_spec(obj['kind']), '主池或宣告的地址/选择器/自动分配策略不同')


def preflight(records, identity=False):
    if identity:
        context = json.loads((records / 'context.json').read_text())
        require(get('namespace', 'kube-system')['metadata']['uid'] == context['cluster_uid'], '恢复目标集群 UID 不同')
        require(call(K + ['config', 'view', '--minify', '-o', 'jsonpath={.clusters[0].cluster.server}']).strip() == 'https://api.k8s.internal.egon.top:6443', '恢复目标 API 不同')
        return context
    context = common.base.preflight(records)
    require(context.get('stage', '02.03') == '02.03', '批次属于其他步骤')
    context['stage'] = '02.03'
    context['previous'] = prior(context['cluster_uid'])
    require(not common.component(context['cluster_uid'])['install'], '02.02 保留的 MetalLB 不存在')
    component = common.component_ready(context)
    expected = context['previous']['retained_metallb']
    require(all(component[k] == expected[k] for k in ['namespace_uid', 'controller_uid', 'speaker_uid', 'version']), 'MetalLB 身份或版本与交接不同')
    context['component'] = component
    daemon = get('daemonset', SPEAKER, META)
    require('kubernetes.io/hostname' not in daemon['spec']['template']['spec']['nodeSelector'] and daemon['spec']['updateStrategy']['type'] == 'RollingUpdate', 'speaker 已处于维护状态，先对原批次 recover')
    context['speaker_original'] = {'uid': daemon['metadata']['uid'], 'spec': daemon['spec']}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect(('192.168.9.100', 6443))
        mac_ip = sock.getsockname()[0]
    allowed = yaml.safe_load((ROOT / 'ops/00-preparation/ansible/inventories/lab/group_vars/all.yml').read_text())['lab_mgmt_sources']
    require(mac_ip in allowed and context.get('mac_ip', mac_ip) == mac_ip, '管理 Mac 来源改变')
    context['mac_ip'] = mac_ip
    require(common.shutil.which('arp'), '管理 Mac 缺少 arp 命令')
    require(not get('ciliuml2announcementpolicies')['items'] and not get('ciliumloadbalancerippools')['items'], '存在 Cilium L2/LB 配置，不能双重宣告')
    proxy = yaml.safe_load(get('configmap', 'kube-proxy', 'kube-system')['data']['config.conf'])
    require(proxy.get('mode') != 'ipvs' or proxy.get('ipvs', {}).get('strictARP'), 'IPVS 模式需要 strictARP')
    inventory = yaml.safe_load((ROOT / 'ops/inventory/vips.yaml').read_text())
    require(inventory['primary']['addresses'] == pool_spec('IPAddressPool')['addresses'] and inventory['primary']['auto_assign'] is False and inventory['reservations'][0]['ip'] == '192.168.9.201' and not inventory['reservations'][0]['dns_records'], 'VIP 台账与主池/网关预留不一致')
    network = yaml.safe_load((ROOT / 'ops/inventory/networks.yaml').read_text())
    planned = next(p for p in network['business_vip_pools'] if p['name'] == 'primary')
    require(planned['start'] + '-' + planned['end'] == inventory['primary']['addresses'][0] and planned['owner'] == 'metallb' and network['primary_cluster']['api_vip'] == '192.168.9.100', 'VIP 台账与网络主池/API 规划不同')
    dhcp = network['lan']['dhcp_range_user_confirmed']
    require(int(ipaddress.ip_address(dhcp['end'])) < int(ipaddress.ip_address(planned['start'])) or int(ipaddress.ip_address(dhcp['start'])) > int(ipaddress.ip_address(planned['end'])), '用户已确认 DHCP 范围与主池重叠')
    existing = json.loads(PRIMARY_RECORD.read_text()) if PRIMARY_RECORD.exists() else None
    found_primary = {}
    for kind in ['IPAddressPool', 'L2Advertisement']:
        obj = optional(kind.lower(), POOL, META)
        found_primary[kind] = bool(obj)
        if obj:
            pool_owned(obj, context)
            path = records / 'state' / ('object-' + kind.lower() + '-' + META + '-' + POOL + '.json')
            receipt = existing['objects'][kind] if existing else json.loads(path.read_text()) if path.exists() else None
            require(receipt and receipt['uid'] == obj['metadata']['uid'], '已存在主池/宣告缺少原始 UID 绑定')
    context.setdefault('primary_preexisting', found_primary)
    for obj in get('ipaddresspools', namespace=META)['items']:
        if obj['metadata']['name'] == POOL:
            continue
        for value in obj['spec']['addresses']:
            version, low, high = ip_bounds(value)
            require(version != 4 or high < int(ipaddress.ip_address('192.168.9.201')) or low > int(ipaddress.ip_address('192.168.9.210')), '其他 MetalLB 池与主池重叠')
    require(all(o['metadata']['name'] == POOL for o in get('l2advertisements', namespace=META)['items']), '存在未核对的 L2Advertisement，可能合并扩大宣告范围')
    allocated = allocations()
    require(all(s['namespace'] == NS and s['run'] == context['run'] and s['ip'] == VIP for s in allocated), '主池内已有其他业务，不能执行 speaker 故障实验')
    context['active_ips'] = [s['ip'] for s in allocated]
    namespace = optional('namespace', NS)
    if namespace:
        require(namespace['metadata'].get('labels', {}).get(LABEL) == context['run'], '实验空间属于其他批次')
        receipt = records / 'state/object-namespace--lab-metallb.json'
        require(receipt.exists() and json.loads(receipt.read_text())['uid'] == namespace['metadata']['uid'], '实验 Namespace UID 改变')
    save(records / 'context.json', context)
    return context


def optional(kind, name, namespace=None):
    raw = call(K + ['get', kind, name, '--ignore-not-found', '-o', 'json'] + (['-n', namespace] if namespace else [])).strip()
    return json.loads(raw) if raw else None


def allocations():
    result = []
    for service in json.loads(call(K + ['get', 'services', '-A', '-o', 'json']))['items']:
        for item in service.get('status', {}).get('loadBalancer', {}).get('ingress') or []:
            ip = item.get('ip')
            if ip and ipaddress.ip_address(ip).version == 4 and ipaddress.ip_address('192.168.9.201') <= ipaddress.ip_address(ip) <= ipaddress.ip_address('192.168.9.210'):
                m = service['metadata']
                result.append({'ip': ip, 'name': m['name'], 'namespace': m['namespace'], 'uid': m['uid'], 'run': m.get('labels', {}).get(LABEL)})
    return result


def object_plan(records, context, document):
    kind, meta = document['kind'], document['metadata']
    namespace = meta.get('namespace', '')
    persistent = kind in ['IPAddressPool', 'L2Advertisement']
    require(kind in ['Namespace', 'DaemonSet', 'Service', 'IPAddressPool', 'L2Advertisement'], '对象类型越界')
    if persistent:
        require(namespace == META and meta['name'] == POOL, '主池资源范围越界')
        pool_owned(document, context)
    else:
        require((kind == 'Namespace' and meta['name'] == NS and not namespace) or (kind != 'Namespace' and namespace == NS), '应用资源空间越界')
        require(meta.get('labels', {}).get(LABEL) == context['run'], '对象运行标签不符')
    path = records / 'state' / ('object-' + kind.lower() + '-' + namespace + '-' + meta['name'] + '.json')
    obj = optional(kind.lower(), meta['name'], namespace or None)
    if obj:
        if persistent:
            pool_owned(obj, context)
            saved = json.loads(PRIMARY_RECORD.read_text())['objects'].get(kind) if PRIMARY_RECORD.exists() else json.loads(path.read_text()) if path.exists() else None
        else:
            require(obj['metadata'].get('labels', {}).get(LABEL) == context['run'], '拒绝接管外来对象')
            saved = json.loads(path.read_text()) if path.exists() else None
        require(saved and saved['uid'] == obj['metadata']['uid'], '同名对象缺少原始 UID 或已被重建')
    return {'receipt': str(path), 'exists': bool(obj), 'persistent': persistent}


def record_object(records, context, document):
    kind, meta = document['kind'], document['metadata']
    path = records / 'state' / ('object-' + kind.lower() + '-' + meta.get('namespace', '') + '-' + meta['name'] + '.json')
    value = {'run': context['run'], 'cluster_uid': context['cluster_uid'], 'kind': kind, 'name': meta['name'], 'namespace': meta.get('namespace', ''), 'uid': meta['uid'], 'spec_sha256': digest(document.get('spec')), 'recorded_at': now()}
    save(path, value)
    return value


def validate(path):
    docs = [d for d in yaml.safe_load_all(path.read_text()) if d]
    for doc in docs:
        preview = json.loads(json.dumps(doc))
        if doc['kind'] in ['IPAddressPool', 'L2Advertisement']:
            require(doc['spec'] == pool_spec(doc['kind']), '渲染主池不符合台账策略')
        elif doc['kind'] != 'Namespace':
            preview['metadata']['namespace'] = 'lab-core'
        call(K + ['apply', '--dry-run=server', '--validate=strict', '-f', '-'], json.dumps(preview))
    return {'passed': True, 'strict_server_dry_run_documents': len(docs), 'persisted': False}


def primary(context):
    objects = {}
    for kind in ['IPAddressPool', 'L2Advertisement']:
        obj = get(kind.lower(), POOL, META)
        pool_owned(obj, context)
        objects[kind] = {'uid': obj['metadata']['uid'], 'spec_sha256': digest(obj['spec'])}
    return {'passed': True, 'stage': '02.03.01', 'cluster_uid': context['cluster_uid'], 'controller': 'cnpl-metallb', 'namespace_uid': context['component']['namespace_uid'], 'objects': objects, 'addresses': pool_spec('IPAddressPool')['addresses'], 'auto_assign': False, 'retained_for_02_04': True}


def partial_plan(records, context):
    require(not allocations(), '仍有实际 VIP 分配，不能处理未完成主池')
    objects = {kind: optional(kind.lower(), POOL, META) for kind in ['IPAddressPool', 'L2Advertisement']}
    for kind, obj in objects.items():
        if not obj:
            continue
        pool_owned(obj, context)
        path = records / 'state' / ('object-' + kind.lower() + '-' + META + '-' + POOL + '.json')
        saved = json.loads(PRIMARY_RECORD.read_text())['objects'].get(kind) if PRIMARY_RECORD.exists() else json.loads(path.read_text()) if path.exists() else None
        require(saved and saved['uid'] == obj['metadata']['uid'], '主池清理/保留缺少原始 UID 绑定')
    if all(objects.values()):
        save(PRIMARY_RECORD, primary(context))
        return {'delete': [], 'retained_complete': True}
    pending = []
    for kind, obj in objects.items():
        if obj:
            require(not context['primary_preexisting'][kind], '原有主池部分丢失，不能自动删除其余原始组件')
            pending.append({'kind': kind.lower(), 'name': POOL, 'uid': obj['metadata']['uid']})
    return {'delete': pending, 'retained_complete': False}


def fixtures(context):
    daemon = get('daemonset', 'echo', NS)
    require(daemon['metadata'].get('labels', {}).get(LABEL) == context['run'], 'echo 不属于本批')
    pods = [p for p in get('pods', namespace=NS)['items'] if not p['metadata'].get('deletionTimestamp') and any(o.get('uid') == daemon['metadata']['uid'] for o in p['metadata'].get('ownerReferences', []))]
    ok = len(pods) == 2 and all(ready(p) for p in pods) and {p['spec'].get('nodeName') for p in pods} == set(WORKERS)
    for pod in pods:
        require(pod['metadata'].get('labels', {}).get(LABEL) == context['run'] and not pod['spec'].get('hostNetwork') and pod['spec'].get('automountServiceAccountToken') is False, '后端归属或隔离方式不符')
        require(pod['spec']['containers'][0]['image'] == common.lock()['services_diagnostics']['internal_source'], '后端镜像不同')
    return {'ok': ok, 'pods': pods, 'backends': {p['metadata']['name']: p['metadata']['uid'] for p in pods}}


def endpoint_match(service, pods):
    found = set()
    for obj in get('endpointslices', namespace=NS)['items']:
        if obj['metadata'].get('labels', {}).get('kubernetes.io/service-name') != service['metadata']['name']:
            continue
        require(any(o.get('uid') == service['metadata']['uid'] for o in obj['metadata'].get('ownerReferences', [])), 'EndpointSlice Service UID 不符')
        endpoints, ports = obj.get('endpoints') or [], obj.get('ports') or []
        if obj.get('addressType') != 'IPv4' or endpoints and not any(p.get('name') == 'http' and p.get('port') == 8080 for p in ports):
            return False
        for item in endpoints:
            if (item.get('conditions') or {}).get('ready') is True:
                for ip in item.get('addresses') or []:
                    found.add(((item.get('targetRef') or {}).get('uid'), ip))
    return found == {(p['metadata']['uid'], p['status']['podIP']) for p in pods}


def speaker_pods(context):
    return [p for p in get('pods', namespace=META)['items'] if any(o.get('uid') == context['component']['speaker_uid'] for o in p['metadata'].get('ownerReferences', []))]


def l2_status(name):
    return [s for s in get('servicel2statuses', namespace=META)['items'] if s.get('status', {}).get('serviceName') == name and s['status'].get('serviceNamespace') == NS]


def route(records, context, attempt, name):
    service = get('service', name, NS)
    require(service['metadata'].get('labels', {}).get(LABEL) == context['run'], '测试 Service 归属不同')
    binding = records / 'state' / ('object-service-' + NS + '-' + name + '.json')
    require(binding.exists() and json.loads(binding.read_text())['uid'] == service['metadata']['uid'], 'Service UID 与应用回执不同')
    require([e.get('ip') for e in (service.get('status', {}).get('loadBalancer', {}).get('ingress') or [])] == [VIP], '未分配指定 VIP')
    require(service['spec'].get('allocateLoadBalancerNodePorts') is False and service['spec'].get('loadBalancerSourceRanges') == [context['mac_ip'] + '/32'], '入口端口或来源范围不符')
    state = fixtures(context)
    require(state['ok'] and endpoint_match(service, state['pods']), '后端或 EndpointSlice 尚未收敛')
    connection = http.client.HTTPConnection(VIP, 8080, timeout=2)
    try:
        row = monitor.request(connection, state['backends'], 'new')
    finally:
        connection.close()
    neighbor = monitor.arp(VIP, context['worker_macs'])
    save(attempt / ('request-' + name + '-' + uuid.uuid4().hex[:8] + '.json'), {'http': row, 'arp': neighbor})
    require(row['passed'] and neighbor['vm'] in WORKERS, 'Mac VIP 请求或已知 VM ARP 入口未通过')
    statuses = l2_status(name)
    active_nodes = {p['spec']['nodeName'] for p in speaker_pods(context) if not p['metadata'].get('deletionTimestamp') and ready(p)}
    active_status = [s for s in statuses if s['status'].get('node') in active_nodes]
    require(len(active_status) == 1 and active_status[0]['status']['node'] == neighbor['vm'] and {'name': 'ens33'} in active_status[0]['status'].get('interfaces', []), 'L2 状态与实际 ARP VM/接口尚未一致')
    return {'passed': True, 'vip': VIP, 'service_uid': service['metadata']['uid'], 'service_name': name, 'entry_vm': neighbor['vm'], 'entry_mac': neighbor['mac'], 'observed_at': now(), 'response': row['response'], 'l2_status': statuses}


def fault_plan(records, context, before):
    original = json.loads((records / 'state/speaker-original.json').read_text())
    daemon = get('daemonset', SPEAKER, META)
    require(daemon['metadata']['uid'] == original['uid'] == context['component']['speaker_uid'] and daemon['spec'] == original['spec'], '故障前 speaker UID/spec 不同')
    excluded = before['entry_vm']
    require(excluded in WORKERS, '宣告 VM 不在允许集合')
    remaining = next(n for n in WORKERS if n != excluded)
    pods = speaker_pods(context)
    require(len(pods) == 2 and all(ready(p) and not p['metadata'].get('deletionTimestamp') for p in pods), '故障前需要两个稳定就绪 speaker')
    selector = dict(original['spec']['template']['spec']['nodeSelector'], **{'kubernetes.io/hostname': remaining})
    operations = maintenance_patch(original, remaining)
    return {'patch': operations, 'excluded_vm': excluded, 'remaining_vm': remaining, 'selector': selector, 'pod_uids': {p['spec']['nodeName']: p['metadata']['uid'] for p in pods}}


def maintenance_patch(original, remaining):
    require(remaining in WORKERS, '维护选择器只能使用两个 worker VM')
    selector = dict(original['spec']['template']['spec']['nodeSelector'], **{'kubernetes.io/hostname': remaining})
    operations = [{'op': 'test', 'path': '/metadata/uid', 'value': original['uid']}]
    for path, old, new in [('/spec/updateStrategy', original['spec']['updateStrategy'], {'type': 'OnDelete'}), ('/spec/template/spec/nodeSelector', original['spec']['template']['spec']['nodeSelector'], selector)]:
        operations += [{'op': 'test', 'path': path, 'value': old}, {'op': 'replace', 'path': path, 'value': new}]
    return operations


def restore_plan(records, context):
    path = records / 'state/speaker-original.json'
    if not path.exists():
        return {'patch': [], 'mutation_not_started': True}
    original = json.loads(path.read_text())
    daemon = get('daemonset', SPEAKER, META)
    require(daemon['metadata']['uid'] == original['uid'] == context['component']['speaker_uid'], '恢复对象 speaker UID 已改变')
    selector = daemon['spec']['template']['spec']['nodeSelector']
    strategy = daemon['spec']['updateStrategy']
    old_selector, old_strategy = original['spec']['template']['spec']['nodeSelector'], original['spec']['updateStrategy']
    if selector == old_selector and strategy == old_strategy:
        return {'patch': [], 'already_restored': True}
    plan = json.loads((records / 'state/fault-plan.json').read_text())
    require(selector == plan['selector'] and strategy == {'type': 'OnDelete'}, 'speaker 维护字段被其他操作改变，拒绝覆盖')
    return {'patch': [{'op': 'test', 'path': '/metadata/uid', 'value': original['uid']}, {'op': 'test', 'path': '/spec/template/spec/nodeSelector', 'value': selector}, {'op': 'test', 'path': '/spec/updateStrategy', 'value': strategy}, {'op': 'replace', 'path': '/spec/template/spec/nodeSelector', 'value': old_selector}, {'op': 'replace', 'path': '/spec/updateStrategy', 'value': old_strategy}]}


def speaker_ready(records, context):
    path = records / 'state/speaker-original.json'
    if path.exists():
        original = json.loads(path.read_text())
        daemon = get('daemonset', SPEAKER, META)
        require(daemon['metadata']['uid'] == original['uid'] and daemon['spec'] == original['spec'], 'speaker 原始配置尚未恢复')
    return common.component_ready(context)


def fault_state(records, context, attempt):
    plan = json.loads((attempt / 'fault-plan.json').read_text())
    daemon = get('daemonset', SPEAKER, META)
    pods = speaker_pods(context)
    require(daemon['spec']['template']['spec']['nodeSelector'] == plan['selector'] and daemon['spec']['updateStrategy'] == {'type': 'OnDelete'}, '未进入本批 speaker 维护状态')
    require(daemon['status'].get('desiredNumberScheduled') == daemon['status'].get('numberReady') == 1, '维护状态尚未收敛为一个 speaker')
    require(len(pods) == 1 and ready(pods[0]) and pods[0]['metadata']['uid'] == plan['pod_uids'][plan['remaining_vm']], '原宣告 speaker 尚未停止或幸存实例被重建')
    value = route(records, context, attempt, 'vip-primary')
    require(value['entry_vm'] == plan['remaining_vm'], '数据面入口未切换到幸存 VM')
    value.update(stopped_vm=plan['excluded_vm'], surviving_speaker_uid=pods[0]['metadata']['uid'])
    return value


def delete_plan(records, context, name):
    require(name in ['no-explicit-allocation', 'vip-primary', 'vip-reuse'], '删除范围越界')
    obj = optional('service', name, NS)
    if obj:
        path = records / 'state' / ('object-service-' + NS + '-' + name + '.json')
        require(obj['metadata'].get('labels', {}).get(LABEL) == context['run'] and path.exists() and json.loads(path.read_text())['uid'] == obj['metadata']['uid'], '删除对象归属或 UID 不同')
    return {'exists': bool(obj)}


def withdrawn(records, context, attempt, name):
    require(not optional('service', name, NS) and not l2_status(name), '旧 Service 或宣告状态尚未撤销')
    require(not allocations(), '主池仍有实际分配，不能回收再分配')
    connection = http.client.HTTPConnection(VIP, 8080, timeout=1)
    try:
        row = monitor.request(connection, {}, 'new')
    finally:
        connection.close()
    save(attempt / ('withdraw-http-' + uuid.uuid4().hex[:8] + '.json'), row)
    require(not row['passed'] and (row.get('error_type') in ['TimeoutError', 'ConnectionRefusedError', 'ConnectionResetError', 'ConnectionAbortedError', 'RemoteDisconnected'] or row.get('errno') in [errno.ETIMEDOUT, errno.ECONNREFUSED, errno.EHOSTUNREACH, errno.ENETUNREACH]), '撤销后不是明确的网络拒绝/超时')
    return {'passed': True, 'withdrawn_service': name, 'vip': VIP, 'active_allocations': [], 'dns_references': [], 'new_connection_error': row['error_type'], 'observed_at': now()}


def pending(context, attempt):
    deadline, samples = time.monotonic() + 8, []
    while True:
        obj = get('service', 'no-explicit-allocation', NS)
        require(obj['metadata'].get('labels', {}).get(LABEL) == context['run'] and not obj['metadata'].get('annotations', {}).get('metallb.io/address-pool'), '负向用例不是无显式申请的本批 Service')
        require(not (obj.get('status', {}).get('loadBalancer', {}).get('ingress') or []) and all(not p.get('nodePort') for p in obj['spec']['ports']), '禁止自动分配的主池意外分配 VIP/NodePort')
        samples.append({'at': now(), 'uid': obj['metadata']['uid'], 'status': obj.get('status', {})})
        if time.monotonic() >= deadline:
            return {'passed': True, 'expected_pending': True, 'samples': samples}
        time.sleep(1)


def arp_check(document, expected):
    macs = sorted({monitor.mac_address(m) for m in re.findall(r'\[(?:[0-9a-f]{1,2}:){5}[0-9a-f]{1,2}\]', document['stdout'], re.I)})
    require(document['rc'] == 0 and macs == [expected], '广播 ARP 没有得到唯一预期 VM 的应答')
    return {'passed': True, 'unique_reply_macs': macs, 'probe': document}


def cleanup_plan(records, context):
    namespace = optional('namespace', NS)
    if not namespace:
        return {'exists': False}
    path = records / 'state/object-namespace--lab-metallb.json'
    require(namespace['metadata'].get('labels', {}).get(LABEL) == context['run'] and path.exists() and json.loads(path.read_text())['uid'] == namespace['metadata']['uid'], '清理 Namespace UID/归属不符')
    objects = get('pods,ds,deploy,sts,rs,svc,cm,secret,sa,job,cronjob,pvc,role,rolebinding,networkpolicy,ciliumnetworkpolicy,ingress,hpa,resourcequota,limitrange', namespace=NS)['items']
    for obj in objects:
        if (obj['kind'], obj['metadata']['name']) in [('ConfigMap', 'kube-root-ca.crt'), ('ServiceAccount', 'default')]:
            continue
        require(obj['metadata'].get('labels', {}).get(LABEL) == context['run'], '发现外来资源，拒绝清理 ' + obj['kind'] + '/' + obj['metadata']['name'])
    return {'exists': True, 'uid': namespace['metadata']['uid']}


def process_alive(attempt):
    path = attempt / 'monitor-pid.json'
    if not path.exists():
        return False
    pid = json.loads(path.read_text())['pid']
    result = subprocess.run(['/bin/ps', '-ww', '-p', str(pid), '-o', 'command='], capture_output=True, text=True, timeout=5)
    if result.returncode != 0:
        return False
    try:
        argv = shlex.split(result.stdout.strip())
        index = argv.index('observe')
        target = argv[argv.index('--attempt') + 1]
        return index > 0 and Path(argv[index - 1]).resolve() == Path(__file__).resolve() and Path(target).resolve() == attempt.resolve()
    except (ValueError, IndexError):
        return False


def stop_all(records):
    attempts = list((records / 'attempts').glob('*'))
    for attempt in attempts:
        if process_alive(attempt):
            (attempt / 'monitor.stop').touch()
    deadline = time.monotonic() + 25
    while any(process_alive(a) for a in attempts):
        require(time.monotonic() < deadline, '有界观测进程尚未停止，原证据已保留')
        time.sleep(1)
    return {'stopped': True}


def accept(records, context, attempt):
    names = ['primary', 'pending', 'baseline', 'during', 'restored', 'arp-baseline', 'arp-during', 'arp-restored', 'failover', 'withdraw-primary', 'withdraw-arp-primary', 'reuse', 'arp-reuse', 'withdraw-reuse', 'withdraw-arp-reuse']
    results = {name: json.loads((attempt / (name + '.json')).read_text()) for name in names}
    require(all(v['passed'] for v in results.values()), '完整 02.03 存在未通过项')
    require(results['baseline']['service_uid'] != results['reuse']['service_uid'] and results['baseline']['vip'] == results['reuse']['vip'] == VIP, '没有验证不同 UID 间的地址回收再分配')
    require(protected() == json.loads((records / 'state/protected.json').read_text()), '原有资源或 MetalLB speaker 配置未恢复')
    require(source() == json.loads((records / 'state/source.json').read_text()), '执行期间源码改变')
    speaker_ready(records, context)
    ledger = {'stage': '02.03.03', 'run': context['run'], 'cluster_uid': context['cluster_uid'], 'pool': POOL, 'owner': 'lab-platform', 'reserved_gateway': {'ip': '192.168.9.201', 'state': 'reserved', 'dns_records': []}, 'test_vip': VIP, 'events': [{'operation': operation, 'service_uid': results[key]['service_uid'], 'service': results[key]['service_name'], 'ip': VIP, 'observed_at': results[key]['observed_at'], 'dns_records': []} for key, operation in [('baseline', 'allocated'), ('reuse', 'reallocated')]], 'withdrawals': [results['withdraw-primary'], results['withdraw-reuse']], 'active_allocations': allocations(), 'passed': True}
    require(not ledger['active_allocations'], '地址台账仍有失去归属的分配')
    save(records / 'vip-ledger.json', ledger)
    return {'stage': '02.03', 'run': context['run'], 'cluster_uid': context['cluster_uid'], 'passed': True, 'cleanup_passed': False, 'steps': ['02.03.01', '02.03.02', '02.03.03'], 'attempt': str(attempt), 'results': results, 'existing_workloads_unchanged': True, 'source': source()}


def final(records, context):
    require(not optional('namespace', NS) and not allocations(), '实验空间或 VIP 分配尚未清空')
    stop_all(records)
    speaker = speaker_ready(records, context)
    baseline = records / 'state/protected.json'
    require(baseline.exists() or not list((records / 'state').glob('object-*.json')), '发生变更却缺少原始保护基线')
    require(not baseline.exists() or protected() == json.loads(baseline.read_text()), '清理后原控制台、关键配置或组件 spec 改变')
    require(common.base.preflight(records)['cluster_uid'] == context['cluster_uid'], '清理后集群身份不同')
    present = optional('ipaddresspool', POOL, META)
    retained = primary(context) if present else None
    require(not (records / 'passed.json').exists() or retained is not None, '正式通过后持久主池缺失')
    return {'cleanup_passed': True, 'stage': '02.03', 'run': context['run'], 'cluster_uid': context['cluster_uid'], 'temporary_namespace_absent': True, 'active_allocations': [], 'speaker': speaker, 'primary_pool_retained': retained, 'existing_workloads_unchanged': True, 'observers_stopped': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['preflight', 'identity', 'source', 'protected', 'validate', 'controller', 'build', 'hosts', 'maintenance-preview', 'object-plan', 'record-object', 'primary', 'partial-plan', 'fixtures', 'route', 'fault-plan', 'fault-state', 'restore-plan', 'speaker-ready', 'mark', 'observe', 'monitor-ready', 'fault-samples', 'analyse', 'pending', 'delete-plan', 'withdrawn', 'arp-check', 'withdraw-arp', 'cleanup-plan', 'stop-all', 'accept', 'final'])
    parser.add_argument('--records', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--attempt', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--document')
    parser.add_argument('--name', default='vip-primary')
    parser.add_argument('--case', default='baseline')
    args = parser.parse_args()
    records, attempt = args.records.resolve(), args.attempt
    if attempt:
        require(attempt.resolve().is_relative_to(records / 'attempts'), 'attempt 路径越界')
    if args.mode in ['preflight', 'identity']:
        value = preflight(records, args.mode == 'identity')
    elif args.mode == 'source':
        value = source()
    elif args.mode == 'protected':
        value = protected()
    elif args.mode == 'validate':
        value = validate(args.manifest)
    elif args.mode == 'controller':
        value = common.validate_controller(args.output)
    elif args.mode == 'build':
        value = common.build(args.output)
    else:
        context = json.loads((records / 'context.json').read_text())
        if args.mode == 'hosts':
            value = common.hosts(records, context, attempt)
        elif args.mode == 'maintenance-preview':
            value = {'patch': maintenance_patch(context['speaker_original'], args.name)}
        elif args.mode in ['object-plan', 'record-object']:
            value = (object_plan if args.mode == 'object-plan' else record_object)(records, context, json.loads(args.document))
        elif args.mode == 'primary':
            value = primary(context)
        elif args.mode == 'partial-plan':
            value = partial_plan(records, context)
        elif args.mode == 'fixtures':
            value = fixtures(context)
            require(value['ok'], '等待两个 VM 上的后端 Pod 就绪')
        elif args.mode == 'route':
            value = route(records, context, attempt, args.name)
        elif args.mode == 'fault-plan':
            value = fault_plan(records, context, json.loads((attempt / 'baseline.json').read_text()))
        elif args.mode == 'fault-state':
            value = fault_state(records, context, attempt)
        elif args.mode == 'restore-plan':
            value = restore_plan(records, context)
        elif args.mode == 'speaker-ready':
            value = speaker_ready(records, context)
        elif args.mode == 'mark':
            value = {'mono': time.monotonic(), 'at': now()}
        elif args.mode == 'observe':
            monitor.atomic_json(attempt / 'monitor-pid.json', {'pid': os.getpid()})
            state = fixtures(context)
            require(state['ok'], '启动观测前后端未就绪')
            value = monitor.observe(attempt, VIP, context['worker_macs'], state['backends'])
        elif args.mode == 'monitor-ready':
            value = json.loads((attempt / 'monitor.ready.json').read_text())
            require(value['ready'], '原有连接尚未预热')
        elif args.mode == 'fault-samples':
            text = (attempt / 'traffic.jsonl').read_text()
            rows = [json.loads(line) for line in text[:text.rfind('\n') + 1].splitlines() if line]
            plan = json.loads((attempt / 'fault-plan.json').read_text())
            marker = json.loads((attempt / 'fault-start.json').read_text())
            require(sum(r['kind'] == 'new' and r['passed'] and r['started_mono'] >= marker['mono'] and r['arp']['vm'] == plan['remaining_vm'] for r in rows) >= 3, '等待迁移后至少三个成功新连接样本')
            value = {'passed': True}
        elif args.mode == 'analyse':
            value = monitor.analyse(attempt, json.loads((attempt / 'baseline.json').read_text()), json.loads((attempt / 'during.json').read_text()))
        elif args.mode == 'pending':
            value = pending(context, attempt)
        elif args.mode == 'delete-plan':
            value = delete_plan(records, context, args.name)
        elif args.mode == 'withdrawn':
            value = withdrawn(records, context, attempt, args.name)
        elif args.mode == 'arp-check':
            value = arp_check(json.loads(args.document), json.loads((attempt / (args.case + '.json')).read_text())['entry_mac'])
        elif args.mode == 'withdraw-arp':
            result = json.loads(args.document)
            require(result['rc'] == 0, 'VIP 仍在响应 ARP 重复探测')
            value = {'passed': True, 'no_arp_reply': True, 'probe': result}
        elif args.mode == 'cleanup-plan':
            value = cleanup_plan(records, context)
        elif args.mode == 'stop-all':
            value = stop_all(records)
        elif args.mode == 'accept':
            value = accept(records, context, attempt)
        else:
            value = final(records, context)
    save(args.output, value)
    print(json.dumps({'ok': value['ok'], 'backends': value['backends']} if args.mode == 'fixtures' else value, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
