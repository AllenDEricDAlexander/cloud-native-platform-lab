#!/usr/bin/env python3
"""02.02 整组只读前检、配置核验和网络请求；对象和防火墙变更由 Ansible 执行。"""
import argparse
from datetime import datetime, timezone
import errno
import hashlib
import importlib.util
import ipaddress
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import yaml

spec = importlib.util.spec_from_file_location('network_base', Path(__file__).resolve().parents[1] / 'network-baseline/check.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
ROOT, K = base.ROOT, base.K
require, save, call, get, ready = base.require, base.save, base.call, base.get, base.ready
PHASE = ROOT / 'ops/02-networking'
NS, META_NS, RELEASE, POOL, VIP = 'lab-services', 'metallb-system', 'cnpl-metallb', 'cnpl-services-test', '192.168.9.202'
LABEL = 'cnpl.io/services-run'
WORKERS = {'worker01.k8s.internal.egon.top': '192.168.9.109', 'worker02.k8s.internal.egon.top': '192.168.9.110'}
CLIENTS = ['client-worker01', 'client-worker02']


def lock():
    return yaml.safe_load((ROOT / 'ops/versions.lock.yaml').read_text())['components']


def absent_or_owned(kind, name, namespace, run):
    raw = call(K + ['get', kind, name, '--ignore-not-found', '-o', 'json'] + (['-n', namespace] if namespace else [])).strip()
    if not raw:
        return None
    obj = json.loads(raw)
    require(obj['metadata'].get('labels', {}).get(LABEL) == run, kind + '/' + name + ' 属于其他运行')
    return obj


def previous(uid):
    pointer = json.loads((PHASE / 'records/completed/02.02.01.json').read_text())
    require(pointer['passed'] and pointer['cleanup_passed'] and pointer['cluster_uid'] == uid, '02.02.01 未完成同集群验收和清理')
    folder = Path(pointer['records']).resolve()
    require(folder.is_relative_to(PHASE / 'records'), '前序记录路径越界')
    for path_key, hash_key, flag in [('passed_receipt', 'passed_receipt_sha256', 'passed'), ('cleanup_receipt', 'cleanup_receipt_sha256', 'cleanup_passed')]:
        data = (folder / pointer[path_key]).read_bytes()
        receipt = json.loads(data)
        require(hashlib.sha256(data).hexdigest() == pointer[hash_key] and receipt[flag] and receipt['run'] == pointer['run'] and receipt['cluster_uid'] == uid, '前序原始回执不一致')
    return pointer


def protected():
    # get 默认不跨 Namespace；显式使用 -A，避免漏掉控制台和系统工作负载。
    items = json.loads(call(K + ['get', 'deployments,daemonsets,services', '-A', '-o', 'json']))['items']
    result = {}
    for obj in items:
        ns = obj['metadata']['namespace']
        if ns in [NS, META_NS]:
            continue
        key = obj['kind'] + '/' + ns + '/' + obj['metadata']['name']
        result[key] = {'uid': obj['metadata']['uid'], 'sha256': hashlib.sha256(json.dumps(obj['spec'], sort_keys=True).encode()).hexdigest()}
    for name in ['coredns', 'cilium-config', 'kube-proxy']:
        obj = get('configmap', name, 'kube-system')
        result['ConfigMap/kube-system/' + name] = {'uid': obj['metadata']['uid'], 'sha256': hashlib.sha256(json.dumps(obj['data'], sort_keys=True).encode()).hexdigest()}
    return result


def component(uid):
    raw = call(K + ['get', 'namespace', META_NS, '--ignore-not-found', '-o', 'json']).strip()
    crds = [d for d in get('crds')['items'] if d['spec']['group'] == 'metallb.io']
    if not raw:
        require(not crds, '已有未登记的 MetalLB CRD，不能自动接管')
        return {'install': True, 'namespace_exists': False}
    ns = json.loads(raw)
    require(ns['metadata'].get('labels', {}).get('cnpl.io/component') == 'metallb' and ns['metadata']['labels'].get('cnpl.io/cluster-uid') == uid, '已有 MetalLB Namespace 不是本项目同集群组件')
    releases = json.loads(call([Path.home() / '.cnpl/bin/helm', '--kubeconfig', Path.home() / '.cnpl-secrets/kubeconfig-lab-primary', 'list', '-n', META_NS, '--deployed', '--failed', '--pending', '--uninstalling', '--uninstalled', '--superseded', '-o', 'json']))
    require(all(r['name'] == RELEASE and r['chart'] == 'metallb-' + lock()['metallb']['version'] for r in releases), '已有 MetalLB release 版本或归属不同')
    for crd in crds:
        require(crd['metadata'].get('annotations', {}).get('meta.helm.sh/release-name') == RELEASE, '已有 CRD 不属于本项目 release')
    if not releases:
        return {'install': True, 'namespace_exists': True, 'namespace_uid': ns['metadata']['uid']}
    require(releases[0]['status'] == 'deployed', 'MetalLB release 处于未完成状态；先执行 recover 检查现场')
    return {'install': False, 'namespace_exists': True, 'namespace_uid': ns['metadata']['uid']}


def preflight(records, identity=False):
    if identity:
        context = json.loads((records / 'context.json').read_text())
        require(get('namespace', 'kube-system')['metadata']['uid'] == context['cluster_uid'], '清理目标集群 UID 不同')
        require(call(K + ['config', 'view', '--minify', '-o', 'jsonpath={.clusters[0].cluster.server}']).strip() == 'https://api.k8s.internal.egon.top:6443', 'kubeconfig 目标不同')
    else:
        context = base.preflight(records)
        prior = previous(context['cluster_uid'])
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as source:
            source.connect(('192.168.9.100', 6443))
            mac_ip = source.getsockname()[0]
        allowed = yaml.safe_load((ROOT / 'ops/00-preparation/ansible/inventories/lab/group_vars/all.yml').read_text())['lab_mgmt_sources']
        require(mac_ip in allowed and mac_ip == context.get('mac_ip', mac_ip), '管理 Mac 源地址与受控来源不同')
        require(shutil.which('arp'), '管理端缺少 arp 查询命令')
        context.update(mac_ip=mac_ip, previous=prior, metallb=component(context['cluster_uid']))
        corefile = get('configmap', 'coredns', 'kube-system')['data']['Corefile']
        require('prometheus :9153' in corefile and re.search(r'\bcache\s+\d+', corefile), 'DNS 缓存实验需要已有 cache/prometheus 插件')
        proxy = yaml.safe_load(get('configmap', 'kube-proxy', 'kube-system')['data']['config.conf'])
        require(proxy.get('mode') != 'ipvs' or proxy.get('ipvs', {}).get('strictARP'), 'IPVS 模式需要 strictARP，当前不满足')
        services = json.loads(call(K + ['get', 'services', '-A', '-o', 'json']))['items']
        holders = [s for s in services if any(i.get('ip') == VIP for i in (s.get('status', {}).get('loadBalancer', {}).get('ingress') or []))]
        require(all(s['metadata']['namespace'] == NS and s['metadata'].get('labels', {}).get(LABEL) == context['run'] for s in holders), '测试 VIP 已被别的 Service 占用')
        context['vip_owned'] = bool(holders)
        require(not get('ciliuml2announcementpolicies')['items'] and not get('ciliumloadbalancerippools')['items'], '当前存在 Cilium L2/LB 配置，先核对控制器与地址范围，避免双重宣告')
        context['corefile_sha256'] = hashlib.sha256(corefile.encode()).hexdigest()
    require(context.get('stage', '02.02') == '02.02', '记录目录属于其他步骤')
    context['stage'] = '02.02'
    ns = absent_or_owned('namespace', NS, None, context['run'])
    saved = records / 'state/namespace.json'
    if ns and saved.exists():
        require(json.loads(saved.read_text())['uid'] == ns['metadata']['uid'], '测试 Namespace UID 改变')
    save(records / 'context.json', context)
    return context


def sources():
    files = [PHASE / 'scripts/services.sh', PHASE / 'examples/services/README.md', ROOT / 'ops/versions.lock.yaml', PHASE / 'records/completed/02.02.01.json', Path(base.__file__), ROOT / 'ops/00-preparation/pki/public/cnpl-lab-root-ca.crt']
    files += list((PHASE / 'ansible/playbooks').glob('services*.yml')) + list((PHASE / 'ansible/tasks').glob('services*.yml')) + [PHASE / 'ansible/vars/services.yml']
    files += list((PHASE / 'networking/metallb').glob('*')) + [p for p in (PHASE / 'networking/services').glob('*.j2') if p.name != 'clusterip.yaml.j2']
    files += list(Path(__file__).parent.glob('*.py')) + [PHASE / 'examples/network-baseline' / name for name in ['main.go', 'main_test.go', 'go.mod']]
    files += [ROOT / 'ops/00-preparation/ansible' / p for p in ['ansible.cfg', 'inventories/lab/hosts.yml', 'inventories/lab/group_vars/all.yml', 'inventories/lab/group_vars/k8s_nodes.yml']]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files)) if p.is_file()}


def hosts(records, context, attempt):
    macs = {}
    for name, ip in WORKERS.items():
        text = (attempt / ('host-' + name.split('.')[0] + '.txt')).read_text()
        addresses = [json.loads(line) for line in text.splitlines() if line.strip().startswith('[{')]
        require(len(addresses) == 1 and len(addresses[0]) == 1, 'VM 接口只读取证缺失或不唯一')
        interface = addresses[0][0]
        require(interface['ifname'] == 'ens33' and any(a.get('local') == ip for a in interface['addr_info']), 'VM 接口地址与原十节点不同')
        require(re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', interface['address']), 'VM MAC 无效')
        macs[name] = interface['address']
    require(len(set(macs.values())) == 2, '两个 VM 的 MAC 重复')
    context['worker_macs'] = macs
    save(records / 'context.json', context)
    return context


def build(output):
    image = base.build(output)
    expected = lock()['services_diagnostics']
    require(image['source_sha256'] == expected['source_sha256'] and image['image'].split('@')[1] == expected['manifest_digest'], '本地诊断源码/镜像与准备物料不同')
    image['local_image'] = image['image']
    image['image'] = expected['internal_source']
    return image


def validate_controller(output):
    entry = lock()['metallb']
    chart = Path(entry['chart']['local_source'])
    require(hashlib.sha256(chart.read_bytes()).hexdigest() == entry['chart']['sha256'], 'MetalLB Chart 摘要不同')
    raw = call([Path.home() / '.cnpl/bin/helm', 'template', RELEASE, chart, '-n', META_NS, '--kube-version', '1.36.5', '-f', PHASE / 'networking/metallb/values.yaml'])
    docs = [d for d in yaml.safe_load_all(raw) if d and d['kind'] != 'Secret']
    workloads = [d for d in docs if d['kind'] in ['Deployment', 'DaemonSet']]
    images = [c['image'] for d in workloads for c in d['spec']['template']['spec']['containers']]
    expected = [a['internal_source'] for a in entry['artifacts']]
    require(len(workloads) == len(images) == 2 and all(any(i.split('@')[1] == e.split('@')[1] and i.split('@')[0].rsplit(':', 1)[0] == e.split('@')[0] for e in expected) for i in images), 'MetalLB 渲染包含额外镜像或未锁定内容')
    speaker = next(d for d in workloads if d['kind'] == 'DaemonSet')
    require(speaker['spec']['template']['spec']['hostNetwork'] and speaker['spec']['template']['spec']['nodeSelector'].get('node-role.kubernetes.io/worker') == '', 'speaker 范围不同')
    require(speaker['spec']['template']['spec']['containers'][0]['securityContext']['capabilities']['add'] == ['NET_RAW'], 'speaker 能力不符合已审阅配置')
    output.with_suffix('.yaml').write_text(yaml.safe_dump_all(docs, sort_keys=False))
    deferred = []
    for doc in docs:
        if doc['apiVersion'].startswith('metallb.io/'):
            deferred.append(doc['kind'])
            continue
        preview = json.loads(json.dumps(doc))
        if preview['metadata'].get('namespace'):
            preview['metadata']['namespace'] = 'kube-system'
        call(K + ['apply', '--dry-run=server', '--validate=strict', '-f', '-'], json.dumps(preview))
    return {'passed': True, 'images': images, 'documents': len(docs), 'custom_resources_admitted_after_crd_install': deferred, 'secret_manifests_saved': False}


def validate_manifest(path):
    docs = [d for d in yaml.safe_load_all(path.read_text()) if d]
    count = 0
    for doc in docs:
        if doc['apiVersion'].startswith('metallb.io/'):
            require(doc['kind'] in ['IPAddressPool', 'L2Advertisement'] and doc['metadata']['namespace'] == META_NS, '自定义资源范围不同')
            if doc['kind'] == 'IPAddressPool':
                require(doc['spec']['addresses'] == [VIP + '/32'] and doc['spec']['autoAssign'] is False, '测试池必须仅使用台账内 .202，且禁止自动分配')
            else:
                require(doc['spec']['ipAddressPools'] == [POOL] and doc['spec']['interfaces'] == ['ens33'], 'L2 宣告范围不同')
            continue
        preview = json.loads(json.dumps(doc))
        if preview['kind'] != 'Namespace':
            preview['metadata']['namespace'] = 'lab-core'
        call(K + ['apply', '--dry-run=server', '--validate=strict', '-f', '-'], json.dumps(preview))
        count += 1
    return {'passed': True, 'builtin_documents': count, 'metallb_cr_local_checks': len(docs) - count, 'persisted': False}


def fixtures(context):
    ns = get('namespace', NS)
    require(ns['metadata'].get('labels', {}).get(LABEL) == context['run'], '实验空间归属不符')
    dep = get('deploy', 'echo', NS)
    require(dep['metadata'].get('labels', {}).get(LABEL) == context['run'], 'echo Deployment 归属不同')
    sets = get('replicasets', namespace=NS)['items']
    rs_uids = {s['metadata']['uid'] for s in sets if any(o.get('uid') == dep['metadata']['uid'] for o in s['metadata'].get('ownerReferences', []))}
    all_pods = get('pods', namespace=NS)['items']
    echoes = [p for p in all_pods if any(o.get('uid') in rs_uids for o in p['metadata'].get('ownerReferences', [])) and not p['metadata'].get('deletionTimestamp')]
    clients = [p for p in all_pods if p['metadata']['name'] in CLIENTS and not p['metadata'].get('deletionTimestamp')]
    good = len(echoes) == len(clients) == 2 and all(ready(p) for p in echoes + clients)
    for pod in echoes + clients:
        require(pod['metadata'].get('labels', {}).get(LABEL) == context['run'] and not pod['spec'].get('hostNetwork'), 'Pod 归属或网络模式不同')
    if good:
        good = all(p['spec']['nodeName'] == 'worker02.k8s.internal.egon.top' for p in echoes) and {p['spec']['nodeName'] for p in clients} == set(WORKERS)
    return {'ok': good, 'echoes': echoes, 'clients': clients, 'backends': {p['metadata']['name']: p['metadata']['uid'] for p in echoes}}


def endpoints(service, pods):
    slices = get('endpointslices', namespace=NS)['items']
    slices = [s for s in slices if s['metadata'].get('labels', {}).get('kubernetes.io/service-name') == service['metadata']['name']]
    found = {}
    for s in slices:
        require(any(o.get('uid') == service['metadata']['uid'] for o in s['metadata'].get('ownerReferences', [])), 'Slice owner UID 不符')
        items, ports = s.get('endpoints') or [], s.get('ports') or []
        if s.get('addressType') != 'IPv4' or items and not any(p.get('name') == 'http' and p.get('port') == 8080 and p.get('protocol') == 'TCP' for p in ports):
            return False
        for item in items:
            for address in item.get('addresses') or []:
                if (item.get('conditions') or {}).get('ready') is True:
                    key = ((item.get('targetRef') or {}).get('uid'), address)
                    require(key not in found, 'Slice 中存在重复的就绪端点')
                    found[key] = True
    return set(found) == {(p['metadata']['uid'], p['status']['podIP']) for p in pods}


def wait_fixtures(context, output):
    deadline = time.monotonic() + 150
    sequence = 0
    while True:
        state = fixtures(context)
        sequence += 1
        save(output.with_name(output.stem + '-poll-' + str(sequence) + '.json'), state)
        if state['ok'] and endpoints(get('service', 'echo', NS), state['echoes']):
            return state
        require(time.monotonic() < deadline, '诊断 Pod/EndpointSlice 尚未就绪，查看轮询快照和 Pod 事件')
        time.sleep(2)


def net(probes, attempt, label, client=CLIENTS[0], negative=False):
    p = subprocess.run(K[:-1] + ['--request-timeout=0', '-n', NS, 'exec', '-i', client, '-c', 'net', '--', '/net-lab', 'matrix'], input=json.dumps(probes), capture_output=True, text=True, timeout=90)
    path = attempt / (label + '-' + uuid.uuid4().hex[:8] + '.jsonl')
    path.write_text(p.stdout)
    rows = [json.loads(line) for line in p.stdout.splitlines()]
    require(len(rows) == sum(q['count'] for q in probes), '探测输出数量不同：' + p.stderr[-1000:])
    if negative:
        require(p.returncode != 0, '预期失败请求意外成功')
    else:
        require(p.returncode == 0 and all(r['passed'] for r in rows), 'Pod 探测失败，查看 ' + path.name)
    return rows


def query(name, protocol, target, expected='', count=1, ca=''):
    return base.probe(name, protocol, target, expected, count=count, timeout=3000, ca=ca)


def verify_echo(body, backends):
    require(isinstance(body, dict) and isinstance(body.get('pod'), str) and body['pod'] in backends and backends[body['pod']] == body.get('uid'), 'HTTP 后端名称/UID 不在当前端点集合')


def mac_request(url, attempt, label, backends, fail=False):
    row = {'at': datetime.now(timezone.utc).isoformat(), 'url': url, 'expected_failure': fail}
    path = attempt / (label + '-' + uuid.uuid4().hex[:8] + '.json')
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(urllib.request.Request(url, headers={'Connection': 'close'}), timeout=3) as response:
            row.update(status=response.status, response=json.load(response))
        require(not fail, '无本地端点的 Local NodePort 意外成功')
        require(row['status'] == 200, 'Mac HTTP 状态不同')
        verify_echo(row['response'], backends)
    except (urllib.error.URLError, OSError) as error:
        if isinstance(error, urllib.error.HTTPError):
            error.close()
        cause = error.reason if isinstance(error, urllib.error.URLError) else error
        row['error'] = type(cause).__name__
        row['detail'] = str(error)
        expected = isinstance(cause, (TimeoutError, ConnectionError)) or isinstance(cause, OSError) and cause.errno in [errno.ETIMEDOUT, errno.ECONNREFUSED, errno.EHOSTUNREACH, errno.ENETUNREACH]
        require(fail and expected, 'Mac 请求失败：' + str(error))
    finally:
        save(path, row)
    return row


def nodeport(context, attempt, affinity=False):
    state = fixtures(context)
    require(state['ok'], 'NodePort 测试前后端未就绪')
    cluster, local = [get('service', name, NS) for name in ['nodeport-cluster', 'nodeport-local']]
    require(cluster['spec']['externalTrafficPolicy'] == 'Cluster' and local['spec']['externalTrafficPolicy'] == 'Local', '流量策略不同')
    require(endpoints(cluster, state['echoes']) and endpoints(local, state['echoes']), 'NodePort 端点尚未收敛')
    ports = [s['spec']['ports'][0]['nodePort'] for s in [cluster, local]]
    if affinity:
        require(cluster['spec']['sessionAffinity'] == 'ClientIP', '未启用 ClientIP affinity')
        rows = [mac_request('http://192.168.9.109:' + str(ports[0]) + '/', attempt, 'affinity', state['backends']) for _ in range(10)]
        require(len({r['response']['uid'] for r in rows}) == 1, '同一客户端的新连接未保持相同后端')
        return {'passed': True, 'requests': 10, 'backend_uid': rows[0]['response']['uid']}
    c = mac_request('http://192.168.9.109:' + str(ports[0]) + '/', attempt, 'cluster-remote', state['backends'])
    l = mac_request('http://192.168.9.110:' + str(ports[1]) + '/', attempt, 'local-backend', state['backends'])
    denied = mac_request('http://192.168.9.109:' + str(ports[1]) + '/', attempt, 'local-without-endpoint', state['backends'], fail=True)
    require(l['response']['peer'].rsplit(':', 1)[0] == context['mac_ip'], 'Local 未保留 Mac 源地址')
    cluster_source = c['response']['peer'].rsplit(':', 1)[0]
    require(cluster_source != context['mac_ip'] and ipaddress.ip_address(cluster_source).is_private, 'Cluster 非本地转发的 SNAT 与基准不同')
    return {'passed': True, 'ports': ports, 'cluster_source': cluster_source, 'local_source': context['mac_ip'], 'no_local_endpoint': denied['error']}


def lb(context, attempt, name):
    service = get('service', name, NS)
    ips = [e.get('ip') for e in service.get('status', {}).get('loadBalancer', {}).get('ingress', [])]
    require(ips == [VIP] and service['spec'].get('allocateLoadBalancerNodePorts') is False, 'LoadBalancer 未取得指定 VIP 或错误分配 NodePort')
    require(service['spec']['loadBalancerSourceRanges'] == [context['mac_ip'] + '/32'], 'VIP 来源范围不同')
    state = fixtures(context)
    require(state['ok'] and endpoints(service, state['echoes']), 'LoadBalancer 端点未收敛')
    row = mac_request('http://' + VIP + ':8080/', attempt, name, state['backends'])
    arp = call([shutil.which('arp'), '-n', VIP])
    match = re.search(r'[0-9a-f]{1,2}(?::[0-9a-f]{1,2}){5}', arp, re.I)
    require(match, '未取得实际 ARP 邻居记录')
    mac = ':'.join(part.zfill(2) for part in match[0].lower().split(':'))
    holder = [node for node, value in context['worker_macs'].items() if value == mac]
    require(len(holder) == 1, 'VIP 实际 ARP 持有者不是受控的两个 worker VM')
    return {'passed': True, 'vip': VIP, 'service_uid': service['metadata']['uid'], 'response': row['response'], 'arp': arp, 'entry_vm': holder[0], 'entry_mac': mac}


def manual(context):
    state = fixtures(context)
    require(state['ok'], '手工端点需要已就绪后端')
    pod = sorted(state['echoes'], key=lambda p: p['metadata']['name'])[0]
    service = get('service', 'manual', NS)
    require(not service['spec'].get('selector'), '手工 Service 不应有 selector')
    return {'service_uid': service['metadata']['uid'], 'pod': pod['metadata']['name'], 'pod_uid': pod['metadata']['uid'], 'pod_ip': pod['status']['podIP']}


def discovery(context, attempt):
    state = fixtures(context)
    require(state['ok'], '服务发现后端未就绪')
    headless, service = get('service', 'headless', NS), get('service', 'manual', NS)
    require(headless['spec']['clusterIP'] == 'None' and headless['spec'].get('selector'), 'Headless 不是带 selector 的无 ClusterIP 服务')
    expected = {p['status']['podIP'] for p in state['echoes']}
    rows = net([query('headless', p, 'headless.' + NS + '.svc.cluster.local') for p in ['dns-udp', 'dns-tcp']], attempt, 'headless-dns')
    require(all(set(r['addresses']) == expected for r in rows), 'Headless DNS 与就绪 Pod IP 不一致')
    plan = manual(context)
    slice_obj = get('endpointslice', 'manual', NS)
    require(slice_obj['metadata']['labels']['kubernetes.io/service-name'] == 'manual' and any(o['uid'] == service['metadata']['uid'] for o in slice_obj['metadata']['ownerReferences']), '手工 Slice 的 Service 归属不同')
    manual_backends = {plan['pod']: plan['pod_uid']}
    requests = net([query('manual', 'http', 'http://manual:8080/', count=5)], attempt, 'manual-http')
    for row in requests:
        verify_echo(row['echo'], manual_backends)
    return {'passed': True, 'headless_addresses': sorted(expected), 'manual_service_ip': service['spec']['clusterIP'], 'manual_endpoint': plan}


def aliases(context, attempt):
    state = fixtures(context)
    require(state['ok'], 'ExternalName 后端未就绪')
    echo_alias, registry_alias = 'echo-alias.' + NS + '.svc.cluster.local', 'registry-alias.' + NS + '.svc.cluster.local'
    dns = net([query('cname-echo', 'dns-cname', echo_alias, 'echo.' + NS + '.svc.cluster.local.'), query('cname-registry', 'dns-cname', registry_alias, 'harbor.k8s.internal.egon.top.'), query('registry-address', 'dns-udp', registry_alias, '192.168.9.12')], attempt, 'externalname-dns')
    request = net([query('alias-host', 'http', 'http://' + echo_alias + ':8080/')], attempt, 'externalname-host')[0]
    verify_echo(request['echo'], state['backends'])
    require(request['echo']['host'] == echo_alias + ':8080', 'ExternalName 意外改写 HTTP Host')
    positive = net([query('registry-ca', 'http', 'https://harbor.k8s.internal.egon.top/v2/', ca='/ca/ca.crt')], attempt, 'tls-positive')[0]
    negative = net([query('alias-sni', 'http', 'https://' + registry_alias + '/v2/', ca='/ca/ca.crt')], attempt, 'tls-hostname-negative', negative=True)[0]
    require(negative.get('status') == 0 and 'x509:' in negative.get('error', '') and registry_alias in negative['error'] and ('not ' + registry_alias in negative['error'] or 'not valid for' in negative['error']), 'HTTPS 失败不是已验证的 SNI/证书主机名不匹配')
    return {'passed': True, 'dns': dns, 'http_host': request['echo']['host'], 'trusted_registry_status': positive['status'], 'alias_tls_error': negative['error']}


def tools(argv, attempt, label, failure=False):
    started = time.monotonic()
    p = subprocess.run(K[:-1] + ['--request-timeout=0', '-n', NS, 'exec', CLIENTS[0], '-c', 'tools', '--'] + argv, capture_output=True, text=True, timeout=20)
    save(attempt / (label + '-' + uuid.uuid4().hex[:8] + '.json'), {'argv': argv, 'rc': p.returncode, 'elapsed_ms_including_exec': round((time.monotonic() - started) * 1000, 3), 'stdout': p.stdout, 'stderr': p.stderr})
    if not failure:
        require(p.returncode == 0, label + ' 失败：' + p.stderr[-800:])
    return p


def cache_hits(text, kind):
    value = 0.0
    for line in text.splitlines():
        if line.startswith('coredns_cache_hits_total{') and 'type="' + kind + '"' in line:
            value += float(line.rsplit(' ', 1)[1])
    return value


def dns_before(context, attempt):
    state = fixtures(context)
    require(state['ok'], 'DNS 实验前 Pod 未就绪')
    rows = net([query('cluster-service', p, 'echo.' + NS + '.svc.cluster.local', get('service', 'echo', NS)['spec']['clusterIP']) for p in ['dns-udp', 'dns-tcp']] + [query('internal', 'dns-udp', 'harbor.k8s.internal.egon.top', '192.168.9.12'), query('external', 'dns-tcp', 'kubernetes.io.')], attempt, 'dns-scopes')
    info = json.loads(call(K + ['-n', NS, 'exec', CLIENTS[0], '-c', 'net', '--', '/net-lab', 'info']))
    require(NS + '.svc.cluster.local' in info['resolv_conf'] and '192.168.20.10' in info['resolv_conf'], 'Pod 搜索域或 DNS 服务地址不同')
    coredns = [p for p in get('pods', namespace='kube-system')['items'] if p['metadata'].get('labels', {}).get('k8s-app') == 'kube-dns' and ready(p)]
    require(len(coredns) == 2, 'CoreDNS 不是两个就绪实例')
    server = coredns[0]['status']['podIP']
    def metrics():
        return tools(['wget', '-q', '-T', '5', '-O', '-', 'http://' + server + ':9153/metrics'], attempt, 'cache-metrics').stdout
    before = metrics()
    for _ in range(3):
        tools(['nslookup', '-type=A', 'kubernetes.io.', server], attempt, 'cache-positive')
    negative_name = 'absent-' + uuid.uuid4().hex[:12] + '.invalid.'
    for _ in range(3):
        response = tools(['nslookup', '-type=A', negative_name, server], attempt, 'cache-negative', failure=True)
        require('NXDOMAIN' in response.stdout + response.stderr, '负缓存请求没有明确 NXDOMAIN')
    after = metrics()
    positive_delta, negative_delta = cache_hits(after, 'success') - cache_hits(before, 'success'), cache_hits(after, 'denial') - cache_hits(before, 'denial')
    require(positive_delta >= 1 and negative_delta >= 1, '指定 CoreDNS 实例的正/负缓存命中计数没有增加')
    late = 'late.' + NS + '.svc.cluster.local'
    deadline = time.monotonic() + 45
    while True:
        response = tools(['nslookup', '-type=A', late, server], attempt, 'late-before', failure=True)
        if 'NXDOMAIN' in response.stdout + response.stderr:
            break
        require(time.monotonic() < deadline, '待创建 Service 的旧名称尚未变为 NXDOMAIN')
        time.sleep(2)
    corefile = get('configmap', 'coredns', 'kube-system')['data']['Corefile']
    return {'passed': True, 'server': server, 'server_pod_uid': coredns[0]['metadata']['uid'], 'positive_cache_hit_delta': positive_delta, 'negative_cache_hit_delta': negative_delta, 'negative_name': negative_name, 'late_name': late, 'late_query_at': datetime.now(timezone.utc).isoformat(), 'cluster_local_cache_disabled': 'disable success cluster.local' in corefile and 'disable denial cluster.local' in corefile, 'scope_queries': rows, 'resolv_conf': info['resolv_conf']}


def dns_after(context, attempt):
    before = json.loads((attempt / 'dns-before.json').read_text())
    service = get('service', 'late', NS)
    ip = service['spec']['clusterIP']
    deadline = time.monotonic() + 60
    tries = 0
    while True:
        tries += 1
        response = tools(['nslookup', '-type=A', before['late_name'], before['server']], attempt, 'late-after', failure=True)
        if response.returncode == 0 and re.search(r'(?<![\d.])' + re.escape(ip) + r'(?![\d.])', response.stdout):
            break
        require(time.monotonic() < deadline, 'Service 创建后指定 CoreDNS 未恢复正确解析')
        time.sleep(2)
    state = fixtures(context)
    row = net([query('late-recovered', 'http', 'http://late:8080/')], attempt, 'dns-recovered-http')[0]
    verify_echo(row['echo'], state['backends'])
    return {'passed': True, 'late_service_ip': ip, 'same_coredns_server': before['server'], 'polls': tries, 'recovered_at': datetime.now(timezone.utc).isoformat(), 'backend': row['echo']}


def cleanup_plan(records, context):
    raw = call(K + ['get', 'namespace', NS, '--ignore-not-found', '-o', 'json']).strip()
    if not raw:
        return {'namespace_exists': False}
    ns = absent_or_owned('namespace', NS, None, context['run'])
    binding = records / 'state/namespace.json'
    require(binding.exists() and json.loads(binding.read_text())['uid'] == ns['metadata']['uid'], '清理 Namespace UID 不符')
    objects = get('pods,deploy,rs,ds,sts,svc,cm,secret,sa,networkpolicy,ciliumnetworkpolicy,pvc,job,cronjob,role,rolebinding,resourcequota,limitrange,ingress,hpa', namespace=NS)['items']
    for obj in objects:
        if (obj['kind'], obj['metadata']['name']) in [('ConfigMap', 'kube-root-ca.crt'), ('ServiceAccount', 'default')]:
            continue
        require(obj['metadata'].get('labels', {}).get(LABEL) == context['run'], '空间存在外来资源，不能清理：' + obj['kind'] + '/' + obj['metadata']['name'])
    return {'namespace_exists': True, 'namespace_uid': ns['metadata']['uid']}


def component_ready(context):
    namespace = get('namespace', META_NS)
    require(namespace['metadata']['labels'].get('cnpl.io/cluster-uid') == context['cluster_uid'], 'MetalLB Namespace 绑定不同')
    deployment, daemon = get('deployment', RELEASE + '-controller', META_NS), get('daemonset', RELEASE + '-speaker', META_NS)
    require(deployment['status'].get('readyReplicas') == 1 and daemon['status'].get('numberReady') == daemon['status'].get('desiredNumberScheduled') == 2, 'MetalLB 控制器或两个 speaker 未就绪')
    expected = {a['name']: a['internal_source'] for a in lock()['metallb']['artifacts']}
    for resource, name in [(deployment, 'controller'), (daemon, 'speaker')]:
        actual = resource['spec']['template']['spec']['containers'][0]['image']
        require(actual.split('@')[1] == expected[name].split('@')[1] and actual.split('@')[0].rsplit(':', 1)[0] == expected[name].split('@')[0], 'MetalLB 实际镜像不同')
    return {'passed': True, 'cluster_uid': context['cluster_uid'], 'namespace_uid': namespace['metadata']['uid'], 'release': RELEASE, 'version': lock()['metallb']['version'], 'controller_uid': deployment['metadata']['uid'], 'speaker_uid': daemon['metadata']['uid'], 'speaker_ready': 2, 'retained_for_phase_02_03': True}


def firewall_restore(records, context, host):
    require(host in ['worker01', 'worker02'], '防火墙恢复主机越界')
    rules = {}
    for path in sorted((records / 'state').glob('firewall-nodeport-' + host + '-*.json')):
        original = json.loads(path.read_text())
        require(original['host'] == host and original['purpose'] == 'nodeport' and original['cluster_uid'] == context['cluster_uid'] and original['run'] == context['run'], '防火墙回执归属不符')
        require(len(original['rules']) == len(original['runtime']) == len(original['permanent']), '防火墙原始回执不完整')
        for rule, runtime, permanent in zip(original['rules'], original['runtime'], original['permanent']):
            match = re.fullmatch(r'rule family="ipv4" source address="' + re.escape(context['mac_ip']) + r'/32" port port="(\d+)" protocol="tcp" accept', rule)
            require(match and 30000 <= int(match[1]) <= 32767 and runtime in [0, 1] and permanent in [0, 1], '防火墙恢复规则超出动态 NodePort 范围')
            value = {'rule': rule, 'runtime': runtime == 0, 'permanent': permanent == 0}
            require(rule not in rules or rules[rule] == value, '同一规则存在互相冲突的原始状态')
            rules[rule] = value
    return {'host': host, 'rules': list(rules.values())}


def control(mode, records, context, attempt, kind, name, namespace):
    if mode == 'nodeport-plan':
        services = [get('service', n, NS) for n in ['nodeport-cluster', 'nodeport-local']]
        for s in services:
            require(s['metadata']['labels'].get(LABEL) == context['run'], 'NodePort Service 归属不同')
        ports = [s['spec']['ports'][0]['nodePort'] for s in services]
        require(len(set(ports)) == 2 and all(30000 <= p <= 32767 for p in ports), 'NodePort 分配无效')
        return {'ports': ports, 'rules': [f'rule family="ipv4" source address="{context["mac_ip"]}/32" port port="{p}" protocol="tcp" accept' for p in ports]}
    if mode == 'delete-plan':
        require(kind in ['service', 'ipaddresspool', 'l2advertisement'] and namespace in [NS, META_NS], '删除范围越界')
        if kind in ['ipaddresspool', 'l2advertisement'] and not any(c['metadata']['name'] == kind + 's.metallb.io' for c in get('crds')['items']):
            return {'exists': False, 'crd_absent': True}
        obj = absent_or_owned(kind, name, namespace, context['run'])
        if obj:
            receipt = records / 'state' / ('object-' + kind + '-' + namespace + '-' + name + '.json')
            require(receipt.exists() and json.loads(receipt.read_text())['uid'] == obj['metadata']['uid'], '删除对象 UID 与创建回执不同')
        return {'exists': bool(obj)}
    if mode == 'component-ready':
        return component_ready(context)
    if mode == 'firewall-restore':
        return firewall_restore(records, context, name)
    if mode == 'accept':
        require(attempt.resolve().is_relative_to(records.resolve() / 'attempts'), '验收路径越界')
        results = {n: json.loads((attempt / (n + '.json')).read_text()) for n in ['nodeport', 'affinity', 'loadbalancer', 'loadbalancer-reuse', 'discovery', 'aliases', 'dns-before', 'dns-after']}
        require(all(v['passed'] for v in results.values()), '存在未通过的专题')
        require(results['loadbalancer']['service_uid'] != results['loadbalancer-reuse']['service_uid'] and results['loadbalancer']['vip'] == results['loadbalancer-reuse']['vip'] == VIP, 'VIP 未在不同 Service UID 间成功释放/再分配')
        require(protected() == json.loads((records / 'state/protected.json').read_text()), '已有控制台、系统工作负载或配置发生变化')
        source = json.loads((records / 'state/source.json').read_text())
        require(source['source_sha256'] == sources(), '运行期间源码发生变化')
        return {'stage': '02.02', 'run': context['run'], 'cluster_uid': context['cluster_uid'], 'passed': True, 'cleanup_passed': False, 'attempt': str(attempt), 'referenced_02_02_01': context['previous'], 'steps': ['02.02.01', '02.02.02', '02.02.03', '02.02.04', '02.02.05', '02.02.06'], 'results': results, 'existing_workloads_unchanged': True, 'source': source}
    if mode == 'final':
        require(not call(K + ['get', 'namespace', NS, '--ignore-not-found', '-o', 'name']).strip(), '实验 Namespace 尚未回收')
        crds = {c['metadata']['name'] for c in get('crds')['items']}
        for resource in ['ipaddresspool', 'l2advertisement']:
            if resource + 's.metallb.io' in crds:
                require(not call(K + ['get', resource, POOL, '-n', META_NS, '--ignore-not-found', '-o', 'name']).strip(), '临时地址池或宣告尚未回收')
        baseline = records / 'state/protected.json'
        require(baseline.exists() or not list((records / 'state').glob('object-*.json')), '发生过对象变更却缺少原始保护基线')
        unchanged = baseline.exists() and protected() == json.loads(baseline.read_text())
        require(not baseline.exists() or unchanged, '清理后原有资源或配置改变')
        for host in ['worker01', 'worker02']:
            original = firewall_restore(records, context, host)
            receipt = json.loads((records / 'state' / ('firewall-restored-' + host + '.json')).read_text())
            require(receipt['run'] == context['run'] and receipt['restored'] and receipt['rules'] == original['rules'], 'NodePort 防火墙恢复回执不符')
        health = base.preflight(records)
        require(health['cluster_uid'] == context['cluster_uid'], '清理后集群身份变化')
        ns = call(K + ['get', 'namespace', META_NS, '--ignore-not-found', '-o', 'name']).strip()
        meta = {'installed': False}
        if ns:
            try:
                meta = component_ready(context)
            except (ValueError, KeyError) as error:
                require(not (records / 'passed.json').exists(), '正式通过后 MetalLB 不健康：' + str(error))
                meta = {'passed': False, 'retained_for_inspection': True, 'error': str(error)}
        return {'cleanup_passed': True, 'run': context['run'], 'cluster_uid': context['cluster_uid'], 'stage': '02.02', 'temporary_namespace_absent': True, 'temporary_pool_absent': True, 'existing_workloads_unchanged': unchanged if baseline.exists() else 'no_mutation_started', 'metallb': meta}
    raise ValueError('未实现的控制动作 ' + mode)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['preflight', 'identity', 'source', 'hosts', 'build', 'controller', 'validate', 'protected', 'fixtures', 'nodeport', 'affinity', 'loadbalancer', 'manual', 'discovery', 'aliases', 'dns-before', 'dns-after', 'cleanup-plan', 'component-ready', 'accept', 'final', 'nodeport-plan', 'delete-plan', 'firewall-restore'])
    p.add_argument('--records', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--attempt', type=Path)
    p.add_argument('--manifest', type=Path)
    p.add_argument('--name', default='loadbalancer')
    p.add_argument('--kind', default='service')
    p.add_argument('--namespace', default=NS)
    a = p.parse_args()
    if a.mode in ['preflight', 'identity']:
        value = preflight(a.records, a.mode == 'identity')
    elif a.mode == 'source':
        value = {'source_sha256': sources()}
    elif a.mode == 'build':
        value = build(a.output)
    elif a.mode == 'controller':
        value = validate_controller(a.output)
    elif a.mode == 'validate':
        value = validate_manifest(a.manifest)
    elif a.mode == 'protected':
        value = protected()
    else:
        context = json.loads((a.records / 'context.json').read_text())
        if a.mode == 'hosts':
            value = hosts(a.records, context, a.attempt)
        elif a.mode == 'fixtures':
            value = wait_fixtures(context, a.output)
        elif a.mode in ['nodeport', 'affinity']:
            value = nodeport(context, a.attempt, a.mode == 'affinity')
        elif a.mode == 'loadbalancer':
            value = lb(context, a.attempt, a.name)
        elif a.mode == 'manual':
            value = manual(context)
        elif a.mode == 'discovery':
            value = discovery(context, a.attempt)
        elif a.mode == 'aliases':
            value = aliases(context, a.attempt)
        elif a.mode == 'dns-before':
            value = dns_before(context, a.attempt)
        elif a.mode == 'dns-after':
            value = dns_after(context, a.attempt)
        elif a.mode == 'cleanup-plan':
            value = cleanup_plan(a.records, context)
        else:
            value = control(a.mode, a.records, context, a.attempt, a.kind, a.name, a.namespace)
    save(a.output, value)
    print(json.dumps({'ok': value['ok'], 'backends': value['backends']} if a.mode == 'fixtures' else value, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
