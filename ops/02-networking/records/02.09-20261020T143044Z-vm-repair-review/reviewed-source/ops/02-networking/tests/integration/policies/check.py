#!/usr/bin/env python3
"""02.06 只读前检、UID 边界、探测及证据判定；资源写入/删除由 Ansible 执行。"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import select
import shlex
import socket
import subprocess
import sys
import time
import uuid
from urllib.parse import urlparse
import yaml


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


HERE = Path(__file__).resolve().parent
gw = module('policy_gateway', HERE.parent / 'gateway/check.py')
ROOT, PHASE, K = gw.ROOT, gw.PHASE, gw.K
base = gw.l2.common.base
require, call, save, get = gw.require, gw.call, gw.save, gw.get
NS = ['lab-policy', 'lab-policy-peer', 'lab-egress']
LABEL = 'cnpl.io/policy-run'
KINDS = {'Namespace': 'namespaces', 'Pod': 'pods', 'Service': 'services', 'ConfigMap': 'configmaps',
         'NetworkPolicy': 'networkpolicies', 'CiliumNetworkPolicy': 'ciliumnetworkpolicies'}
PODS = [
    ('client', NS[0], 'worker01'), ('api', NS[0], 'worker02'),
    ('dependency', NS[0], 'worker01'), ('fqdn', NS[0], 'worker01'),
    ('ingress', NS[1], 'worker01'), ('monitor', NS[1], 'worker02'),
    ('outsider', NS[1], 'worker02'), ('egress', NS[2], 'worker01')]
CA = '/trust/root.crt'
PROXY = 'http://192.168.9.10:7890'
EXTERNAL = 'https://www.google.com/generate_204'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def source():
    files = list(HERE.glob('*.py'))
    for directory, pattern in [('ansible/playbooks', 'policies*.yml'), ('ansible/tasks', 'policies*.yml'),
                               ('networking/policies', '*'), ('examples/policies', '*')]:
        files += [p for p in (PHASE / directory).glob(pattern) if p.is_file()]
    files += [PHASE / p for p in ['scripts/policies.sh', 'ansible/vars/policies.yml', 'records/completed/02.05.json']]
    files += [Path(gw.__file__), Path(gw.mat.__file__), Path(gw.probe.__file__),
              Path(gw.l2.__file__), Path(gw.l2.common.__file__), Path(base.__file__)]
    files += [ROOT / p for p in ['ops/versions.lock.yaml', 'ops/inventory/networks.yaml',
              'ops/00-preparation/pki/public/cnpl-lab-root-ca.crt', 'ops/00-preparation/openwrt/mihomo/config.template.yaml',
              'ops/00-preparation/ansible/ansible.cfg', 'ops/00-preparation/ansible/inventories/lab/hosts.yml',
              'ops/00-preparation/ansible/inventories/lab/group_vars/all.yml']]
    require(all(p.is_file() for p in files), '02.06 输入不完整')
    return {'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))}}


def previous(uid):
    receipt = json.loads((PHASE / 'records/completed/02.05.json').read_text())
    require(receipt['internal_passed'] and receipt['cleanup_passed'] and receipt['cluster_uid'] == uid, '需要同集群 02.05 内部验收与清理')
    require(receipt['public_status'] == 'BLOCKED' and not receipt['phase_complete'], '公网边界与已批准范围不同')
    folder = Path(receipt['records']).resolve()
    require(folder.parent == PHASE / 'records', '前序证据路径越界')
    for name, sha, flag in [('passed_receipt', 'passed_receipt_sha256', 'internal_passed'),
                            ('cleanup_receipt', 'cleanup_receipt_sha256', 'cleanup_passed')]:
        raw = (folder / receipt[name]).read_bytes()
        value = json.loads(raw)
        require(hashlib.sha256(raw).hexdigest() == receipt[sha] and value[flag]
                and value['run'] == receipt['run'] and value['cluster_uid'] == uid, '02.05 原始回执不一致')
    return receipt


def optional(kind, name, namespace=None):
    require(kind.lower() not in ['secret', 'secrets'], '不允许读取完整 Secret')
    raw = call(K + ['get', kind, name] + (['-n', namespace] if namespace else []) + ['--ignore-not-found', '-o', 'json']).strip()
    return json.loads(raw) if raw else None


def protected():
    result = {k: v for k, v in gw.l2.protected().items() if k.split('/')[1] not in NS}
    for kind, name, namespace in [('Gateway', 'primary', 'cnpl-gateway'), ('EnvoyProxy', 'primary', 'cnpl-gateway')]:
        obj = get(kind, name, namespace)
        result[kind + '/' + namespace + '/' + name] = {'uid': obj['metadata']['uid'], 'spec_sha256': digest(obj['spec'])}
    for obj in json.loads(call(K + ['get', 'pods,networkpolicies,ciliumnetworkpolicies', '-A', '-o', 'json']))['items']:
        if obj['metadata']['namespace'] not in NS:
            key = obj['kind'] + '/' + obj['metadata']['namespace'] + '/' + obj['metadata']['name']
            result[key] = {'uid': obj['metadata']['uid'], 'spec_sha256': digest(obj.get('spec'))}
    return result


def preflight(records, identity=False):
    if identity:
        context = json.loads((records / 'context.json').read_text())
        require(call(K + ['config', 'view', '--minify', '-o', 'jsonpath={.clusters[0].cluster.server}']).strip() == 'https://api.k8s.internal.egon.top:6443', '恢复 kubeconfig 指向其他集群')
        require(get('namespace', 'kube-system')['metadata']['uid'] == context['cluster_uid'], '恢复集群身份不同')
        return context
    context = base.preflight(records)
    require(context.get('stage', '02.06') == '02.06', '批次属于其他专题')
    context.update(stage='02.06', previous=previous(context['cluster_uid']))
    config = get('cm', 'cilium-config', 'kube-system')['data']
    require(config.get('enable-l7-proxy') == 'true' and config.get('enable-hubble') == 'true', '需要既有 L7 代理和 Hubble')
    require(config.get('enable-policy', 'default') == 'default', '策略执行模式与本轮基线不同')
    require(config.get('tofqdns-dns-reject-response-code', 'refused') == 'refused', '本轮 DNS 拒绝预期需要 REFUSED 配置')
    require(config.get('enable-egress-gateway', 'false') == 'false', 'CNI 模式已改变，需要重新审阅出口方案')
    context['capabilities'] = {k: config.get(k, 'false') for k in ['kube-proxy-replacement', 'enable-bpf-masquerade', 'enable-egress-gateway', 'enable-l7-proxy']}
    context['egress_gateway_crd_installed'] = 'ciliumegressgatewaypolicies.cilium.io' in gw.crd_names()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect(('192.168.9.100', 6443))
        context['mac_ip'] = sock.getsockname()[0]
    require(context['mac_ip'] == '192.168.9.200', '管理端来源发生变化')
    gw.data_plane(context, laboratory=False)
    tls = gw.probe.http('192.168.9.201', '/cnpl-policy-preflight')
    require(tls['status'] == 404 and tls['tls_peer_sha256'], '原主入口的可信 TLS 或空路由预期不同')
    context['main_tls'] = {'status': tls['status'], 'sha256': tls['tls_peer_sha256']}
    for name in NS:
        obj = optional('namespace', name)
        if obj:
            require(obj['metadata'].get('labels', {}).get(LABEL) == context['run'], '实验空间属于其他批次：' + name)
            require(not obj['metadata'].get('deletionTimestamp'), '实验空间仍在删除：' + name)
    require(optional('namespace', 'lab-tls') is None, '02.05 故障空间尚未清理')
    agent = agents()['worker01.k8s.internal.egon.top']
    version = call(K + ['exec', '-n', 'kube-system', agent, '-c', 'cilium-agent', '--', 'cilium-dbg', 'version'])
    require(re.search(r'\b1\.20\.2\b', version), '实际 Cilium 版本与本轮审阅的 1.20.2 不同')
    context['cilium_version'] = version.strip()
    prefix, context['hubble_status'] = hubble_access('worker01.k8s.internal.egon.top')
    probe = {'metadata': {'namespace': NS[0], 'name': 'client'}}
    since = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    context['hubble_query_filters'] = yaml.safe_load(call(prefix + hubble_query(probe, ['192.168.20.10'], 53, since)
        + ['--print-raw-filters'], timeout=25))
    require(not yaml.safe_load((PHASE / 'networking/policies/capabilities.yaml').read_text())['egress_gateway']['execution_enabled'], '本轮不允许自动切换全局 CNI')
    save(records / 'context.json', context)
    return context


def ssh(ip, command):
    return ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', '-i',
            str(Path.home() / '.ssh/cnpl_lab_ed25519'), 'root@' + ip, command]


def hosts(output):
    results = {}
    for last in [106, 107, 108, 109, 110]:
        ip = '192.168.9.' + str(last)
        name = base.NODE_NAMES[last - 101] + '.k8s.internal.egon.top'
        command = 'set -e; test "$(hostname)" = ' + name + '; test "$(getenforce)" = Enforcing; test "$(firewall-cmd --get-zone-of-interface=ens33)" = public; systemctl is-active firewalld containerd kubelet chronyd; test "$(timedatectl show -p NTPSynchronized --value)" = yes; command -v tcpdump; command -v timeout; ip -j route get 192.168.9.12; ip -j route get 192.168.9.10'
        results[ip] = call(ssh(ip, command), timeout=25)
    results['harbor-capture'] = call(ssh('192.168.9.12', 'command -v tcpdump; command -v timeout; ip -j route get 192.168.9.109'), timeout=20)
    results['openwrt'] = call(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', 'openwrt',
        'pidof mihomo >/dev/null && echo proxy-running; ip -4 route get 192.168.9.109'], timeout=20)
    require('proxy-running' in results['openwrt'], '既有显式代理没有运行')
    results['external_proxy_prerequisite'] = call(['/usr/bin/curl', '--silent', '--show-error', '--noproxy', '',
        '--proxy', PROXY, '--max-time', '20', '--output', '/dev/null', '--write-out', '%{http_code}', EXTERNAL], timeout=25)
    require(results['external_proxy_prerequisite'] == '204', '既有显式代理没有通过外网 TLS 前检')
    results['transparent_proxy_firewall'] = firewall_snapshot('worker01.k8s.internal.egon.top')
    for last in [106, 107, 108]:
        ip = '192.168.9.' + str(last)
        results['ceph-listeners-' + ip] = call(ssh(ip, "ss -H -ltn '( sport = :3300 or sport = :6789 )'"), timeout=20)
    save(output, {'passed': True, 'vm_only': True, 'checks': results, 'ceph_service_status': 'BLOCKED', 'ceph_reason': 'Phase03 尚未验收；这里只验证存储 VM 网络路径'})
    return {'passed': True, 'vm_only': True, 'ceph_service_status': 'BLOCKED'}


def key(obj):
    m = obj['metadata']
    return obj['kind'] + '/' + m.get('namespace', '') + '/' + m['name']


def state_path(records, obj):
    return records / 'state' / ('object-' + key(obj).replace('/', '-') + '.json')


def object_plan(records, context, obj):
    kind, m = obj['kind'], obj['metadata']
    require(kind in KINDS, '禁止应用类型：' + kind)
    require((kind == 'Namespace' and m['name'] in NS and not m.get('namespace'))
            or (kind != 'Namespace' and m.get('namespace') in NS), '对象范围越界')
    require(m.get('labels', {}).get(LABEL) == context['run'], '运行标签不符')
    if kind != 'Namespace':
        parent = get('namespace', m['namespace'])
        parent_path = state_path(records, parent)
        require(parent_path.exists() and parent['metadata'].get('labels', {}).get(LABEL) == context['run']
                and json.loads(parent_path.read_text()).get('uid') == parent['metadata']['uid'], '父 Namespace 身份改变')
    current = optional(kind, m['name'], m.get('namespace'))
    receipt = state_path(records, obj)
    saved = json.loads(receipt.read_text()) if receipt.exists() else None
    if current:
        require(saved and saved.get('uid') == current['metadata']['uid'] and current['metadata'].get('labels', {}).get(LABEL) == context['run'], '拒绝接管或覆盖同名对象：' + key(obj))
    else:
        require(not saved or not saved.get('uid'), '原对象已经消失，不能在同一批次隐式重建：' + key(obj))
    # 预先保存创建意图；崩溃后恢复只会回收带本次随机 run 的对象。
    if not saved:
        save(receipt, {'key': key(obj), 'uid': None, 'run': context['run'], 'creation_planned': True})
    return {'receipt': str(receipt), 'exists': bool(current)}


def record(records, context, obj):
    path = state_path(records, obj)
    saved = json.loads(path.read_text())
    require(saved['run'] == context['run'] and obj['metadata'].get('labels', {}).get(LABEL) == context['run'], '对象归属不同')
    require(not saved.get('uid') or saved['uid'] == obj['metadata']['uid'], 'UID 在应用时改变')
    value = {'key': key(obj), 'uid': obj['metadata']['uid'], 'run': context['run'], 'creation_planned': True}
    save(path, value)
    return value


def delete_row(records, context, obj, output):
    current = optional(obj['kind'], obj['metadata']['name'], obj['metadata'].get('namespace'))
    if not current:
        return None
    receipt = state_path(records, obj)
    require(receipt.exists(), '缺少原对象创建意图')
    saved = json.loads(receipt.read_text())
    uid = current['metadata']['uid']
    require(current['metadata'].get('labels', {}).get(LABEL) == context['run'] and saved['run'] == context['run'], '删除对象属于其他批次')
    require(saved.get('uid') == uid or (saved.get('uid') is None and saved.get('creation_planned')), '删除前 UID 改变')
    kind, m = obj['kind'], obj['metadata']
    require(kind in ['Namespace', 'NetworkPolicy', 'CiliumNetworkPolicy'], '删除类型越界')
    namespace = m.get('namespace')
    require((kind == 'Namespace' and m['name'] in NS) or (kind != 'Namespace' and namespace in NS), '删除范围越界')
    prefix = '/api/v1/' if kind == 'Namespace' else '/apis/' + ('networking.k8s.io/v1/' if kind == 'NetworkPolicy' else 'cilium.io/v2/')
    url = prefix + ('namespaces/' + namespace + '/' if namespace else '') + KINDS[kind] + '/' + m['name']
    body = output.parent / ('delete-' + key(obj).replace('/', '-') + '.json')
    save(body, {'apiVersion': 'v1', 'kind': 'DeleteOptions', 'preconditions': {'uid': uid}, 'propagationPolicy': 'Foreground'})
    return {'url': url, 'body': str(body), 'key': key(obj)}


def delete_plan(records, context, manifest, output):
    return {'objects': [row for obj in yaml.safe_load_all(manifest.read_text()) if obj
                        for row in [delete_row(records, context, obj, output)] if row]}


def validate(attempt):
    results = {}
    for file in sorted(attempt.glob('*.yaml')):
        count = 0
        for obj in yaml.safe_load_all(file.read_text()):
            if not obj:
                continue
            clone = json.loads(json.dumps(obj))
            if clone['kind'] != 'Namespace':
                clone['metadata']['namespace'] = 'lab-core'
                clone['metadata']['name'] = 'cnpl-06-preview-' + clone['metadata']['name']
            call(K + ['apply', '--dry-run=server', '--validate=strict', '-f', '-'], json.dumps(clone))
            count += 1
        results[file.name] = count
    reference = PHASE / 'networking/policies/egress-gateway-reference.yaml'
    lock = yaml.safe_load((ROOT / 'ops/versions.lock.yaml').read_text())['components']['policy_fixture']
    crd = Path(lock['egress_crd_path'])
    require(crd.is_file() and hashlib.sha256(crd.read_bytes()).hexdigest() == lock['egress_crd_sha256'], '出口参考的官方 CRD schema 摘要不符')
    call(K + ['apply', '--dry-run=server', '--validate=strict', '-f', crd])
    model = yaml.safe_load(crd.read_text())
    custom = gw.mat.validate_custom([yaml.safe_load(reference.read_text())], [model])
    installed = 'ciliumegressgatewaypolicies.cilium.io' in gw.crd_names()
    if installed:
        call(K + ['apply', '--dry-run=server', '--validate=strict', '-f', reference])
    return {'passed': True, 'server_dry_run': results, 'reference_crd_server_dry_run': True,
        'reference_instance_structure': custom, 'reference_instance_server_dry_run': installed,
        'reference_admission_status': 'PASS' if installed else 'BLOCKED_CRD_NOT_INSTALLED', 'persisted': False}


def pods(context):
    result = {}
    image = yaml.safe_load((ROOT / 'ops/versions.lock.yaml').read_text())['components']['policy_fixture']['internal_source']
    for name, ns, vm in PODS:
        obj = get('pod', name, ns)
        require(base.ready(obj) and not obj['metadata'].get('deletionTimestamp'), 'Pod 尚未 Ready：' + name)
        require(obj['metadata'].get('labels', {}).get(LABEL) == context['run'] and obj['spec']['nodeName'] == vm + '.k8s.internal.egon.top', 'Pod VM 或批次不符')
        container = obj['spec']['containers'][0]
        require(container['image'] == image and not obj['spec'].get('hostNetwork') and not obj['spec']['automountServiceAccountToken'], 'Pod 隔离模式或镜像不符')
        status = obj['status']['containerStatuses'][0]
        require(status['imageID'].split('@')[-1] == image.split('@')[-1], '实际镜像摘要不同')
        require(ipaddress.ip_address(obj['status']['podIP']) in ipaddress.ip_network('10.244.0.0/16'), 'Pod 地址不在规划 CIDR')
        result[name] = obj
    return result


def agents():
    return {p['spec']['nodeName']: p['metadata']['name'] for p in get('pods', namespace='kube-system')['items']
            if p['metadata'].get('labels', {}).get('k8s-app') == 'cilium' and base.ready(p)}


def firewall_rules(inventory, dns_ips):
    rules = []
    pairs = [('client', inventory['api']['status']['podIP'], 8080, 'tcp')]
    pairs += [(name, ip, 53, protocol) for name in ['fqdn', 'egress'] for ip in sorted(set(dns_ips))
              for protocol in ['tcp', 'udp']]
    for name, target, port, protocol in pairs:
        source = inventory[name]['status']['podIP']
        require(ipaddress.ip_address(source) in ipaddress.ip_network('10.244.0.0/16'), '代理源不在 Pod CIDR')
        require(ipaddress.ip_address(target) in ipaddress.ip_network('10.244.0.0/16') or target == '192.168.20.10', '代理目标越界')
        for src, dst, element in [(source, target, 'port'), (target, source, 'source-port')]:
            rules.append('rule priority="-100" family="ipv4" source address="' + src + '/32" destination address="'
                + dst + '/32" ' + element + ' port="' + str(port) + '" protocol="' + protocol + '" accept')
    return sorted(set(rules))


def firewall_snapshot(vm, rules=()):
    require(vm == 'worker01.k8s.internal.egon.top', '透明代理规则只属于本批 worker01')
    # 只读调用 VM 自带的 firewalld 解析器；不改 backend、接口所属区域或永久配置。
    program = '''import json,subprocess,sys
from firewall.core.rich import Rich_Rule
def run(*args):
    return subprocess.check_output(args,text=True).strip()
rules=json.loads(sys.argv[1])
value={'hostname':run('hostname'),'selinux':run('getenforce'),
 'active':run('systemctl','is-active','firewalld'),
 'zone':run('firewall-cmd','--get-zone-of-interface=ens33'),
 'runtime':sorted(run('firewall-cmd','--zone=public','--list-rich-rules').splitlines()),
 'permanent':sorted(run('firewall-cmd','--permanent','--zone=public','--list-rich-rules').splitlines()),
 'parsed':[str(Rich_Rule(rule_str=rule)) for rule in rules]}
print(json.dumps(value))
'''
    value = json.loads(call(ssh(base.NODES[vm], shlex.join(['python3', '-c', program, json.dumps(list(rules))])), timeout=30))
    require(value['hostname'] == vm and value['selinux'] == 'Enforcing' and value['active'] == 'active'
            and value['zone'] == 'public', '透明代理 VM 安全状态或区域改变')
    return value


def firewall_plan(records, context, cleanup=False):
    path = records / 'state/l7-firewall.json'
    if cleanup and not path.exists():
        return {'objects': []}
    if not cleanup:
        require(not path.exists(), '透明代理防火墙计划已经存在，不能覆盖原始基线')
        inventory = pods(context)
        require(all(inventory[name]['spec']['nodeName'] == 'worker01.k8s.internal.egon.top'
                    for name in ['client', 'fqdn', 'egress']), '代理源 VM 与计划不同')
        dns_ips = [p['status']['podIP'] for p in get('pods', namespace='kube-system')['items']
                   if p['metadata'].get('labels', {}).get('k8s-app') == 'kube-dns' and base.ready(p)]
        require(dns_ips, '没有 Ready CoreDNS')
        rules = firewall_rules(inventory, dns_ips + ['192.168.20.10'])
        vm = 'worker01.k8s.internal.egon.top'
        before = firewall_snapshot(vm, rules)
        require(before['parsed'] == rules, 'firewalld 解析后的规则与预览不同')
        require(not set(rules) & (set(before['runtime']) | set(before['permanent'])), '临时规则已经存在，不能接管')
        value = {'run': context['run'], 'cluster_uid': context['cluster_uid'], 'vm': vm,
            'node_uid': get('node', vm)['metadata']['uid'], 'rules': rules,
            'pod_uids': {name: inventory[name]['metadata']['uid'] for name in ['client', 'api', 'fqdn', 'egress']},
            'before': {key: before[key] for key in ['runtime', 'permanent']}}
        # 写入创建意图后才交给 Ansible 修改；即使中途退出也能撤销已添加的子集。
        save(path, value)
    else:
        value = json.loads(path.read_text())
        require(value['run'] == context['run'] and value['cluster_uid'] == context['cluster_uid'], '防火墙计划属于其他批次')
        require(get('node', value['vm'])['metadata']['uid'] == value['node_uid'], '代理 VM Node UID 改变')
        current = firewall_snapshot(value['vm'])
        rules = [rule for rule in value['rules'] if rule in current['runtime']]
        require(not set(value['rules']) & set(value['before']['runtime']), '禁止删除原有防火墙规则')
    objects = []
    for rule in rules:
        command = ['firewall-cmd', '--zone=public', ('--remove-rich-rule=' if cleanup else '--add-rich-rule=') + rule]
        if not cleanup:
            command += ['--timeout=3600']
        objects.append({'rule': rule, 'argv': ssh(base.NODES[value['vm']], shlex.join(command))})
    return {'objects': objects, 'vm': value['vm'], 'runtime_only': True}


def firewall_verify(records, context, restored=False):
    path = records / 'state/l7-firewall.json'
    if restored and not path.exists():
        return {'passed': True, 'modified': False}
    value = json.loads(path.read_text())
    require(value['run'] == context['run'] and value['cluster_uid'] == context['cluster_uid'], '防火墙回执批次不符')
    require(get('node', value['vm'])['metadata']['uid'] == value['node_uid'], '代理 VM Node UID 改变')
    current = firewall_snapshot(value['vm'])
    expected = set(value['before']['runtime']) | (set() if restored else set(value['rules']))
    require(set(current['runtime']) == expected and current['permanent'] == value['before']['permanent'],
            '代理运行规则未收敛或原有/永久规则发生变化')
    if not restored:
        inventory = pods(context)
        require(all(inventory[name]['metadata']['uid'] == uid for name, uid in value['pod_uids'].items()), '代理源/目标 Pod UID 改变')
    return {'passed': True, 'restored': restored, 'runtime_only': True, 'vm': value['vm'], 'rules': len(value['rules'])}


def endpoint_state(context):
    inventory, agent_map = pods(context), agents()
    states = {}
    for vm in {p['spec']['nodeName'] for p in inventory.values()}:
        raw = call(K + ['exec', '-n', 'kube-system', agent_map[vm], '-c', 'cilium-agent', '--', 'cilium-dbg', 'endpoint', 'list', '-o', 'json'])
        endpoints = {e['id']: e['status'] for e in json.loads(raw)}
        for name, p in inventory.items():
            if p['spec']['nodeName'] != vm:
                continue
            cep = get('ciliumendpoint', name, p['metadata']['namespace'])
            status = endpoints[cep['status']['id']]
            policy = status.get('policy') or {}
            realized, desired = policy.get('realized') or {}, policy.get('spec') or {}
            require(status['state'] == 'ready' and realized.get('policy-enabled') == 'both', '等待默认拒绝双向生效：' + name)
            require(realized.get('policy-revision', 0) >= desired.get('policy-revision', 1), '等待策略版本收敛：' + name)
            if policy.get('proxy-statistics'):
                # 无关策略也会推进全局 revision；代理内容未变时不会产生新 ACK。
                # 首次代理下发及端口分配只负责就绪，精确行为由后续三次实际请求验收。
                require(policy.get('proxy-policy-revision', 0) > 0, '等待代理策略首次 ACK：' + name)
                require(all(p.get('allocated-proxy-port', 0) > 0 for p in policy['proxy-statistics']), '等待代理端口分配：' + name)
            require(cep['status']['identity']['id'] > 255, '缺少工作负载安全身份')
            states[name] = {'id': cep['status']['id'], 'identity': cep['status']['identity'], 'policy': policy}
    return {'passed': True, 'endpoints': states}


def policy_state(context, attempt, mode):
    files = ['default-deny']
    if mode == 'standard':
        files += ['standard']
    elif mode != 'denied':
        files += ['cilium']
    if mode in ['egress', 'proxy-unreachable', 'proxy-restored']:
        files += ['egress']
    if mode == 'proxy-unreachable':
        files += ['proxy-unreachable']
    expected = {}
    for name in files:
        for obj in yaml.safe_load_all((attempt / (name + '.yaml')).read_text()):
            if obj:
                m = obj['metadata']
                applied = json.loads((attempt / ('applied-' + obj['kind'] + '-' + m['namespace'] + '-' + m['name'] + '.json')).read_text())
                expected[key(obj)] = {'uid': applied['metadata']['uid'], 'spec_sha256': digest(applied['spec'])}
    actual = {}
    for ns in NS:
        for obj in get('networkpolicies,ciliumnetworkpolicies', namespace=ns)['items']:
            require(obj['metadata'].get('labels', {}).get(LABEL) == context['run'], '实验空间出现外来策略')
            actual[key(obj)] = {'uid': obj['metadata']['uid'], 'spec_sha256': digest(obj['spec'])}
    require(actual == expected, '策略对象与本轮已应用版本不一致，不能进行用例判定')
    return actual


def request(pod, protocol, target, timeout=1800, method='GET', proxy='', ca=''):
    nonce = uuid.uuid4().hex
    value = {'protocol': protocol, 'target': target, 'method': method, 'proxy': proxy, 'ca': ca, 'nonce': nonce, 'timeout_ms': timeout}
    raw = call(K[:-1] + ['--request-timeout=0', 'exec', '-i', '-n', pod['metadata']['namespace'], pod['metadata']['name'], '-c', 'net', '--', '/policy-lab', 'probe'], json.dumps(value), timeout=25)
    row = json.loads(raw)
    require(row['nonce'] == nonce and row['target'] == target and row['protocol'] == protocol, '探测响应关联失败')
    return row


def matched(row, expected, backend=None):
    if expected == 'drop':
        return bool(row.get('error') and row.get('timeout') and not row.get('status'))
    if expected == 'dns-deny':
        return not row.get('error') and row.get('rcode') == 5
    if expected == 'dns':
        return not row.get('error') and row.get('rcode') == 0 and bool(row.get('addresses'))
    if row.get('error') or (isinstance(expected, int) and row.get('status') != expected):
        return False
    if backend is not None:
        try:
            echo = json.loads(row.get('body', ''))
        except ValueError:
            return False
        return echo.get('uid') == backend['metadata']['uid'] and echo.get('nonce') == row['nonce']
    return expected in ['tcp', 200, 204, 401, 403]


def flow_matches(flow, pod, ip, port, mode, dns_query=None, client_ports=None):
    source, dest = flow.get('source') or {}, flow.get('destination') or {}
    def is_client(endpoint):
        return endpoint.get('namespace') == pod['metadata']['namespace'] and endpoint.get('pod_name', endpoint.get('podName')) == pod['metadata']['name'] and endpoint.get('identity', 0) > 255
    ips = flow.get('IP', flow.get('ip')) or {}
    l4 = flow.get('l4') or {}
    transport = l4.get('TCP', l4.get('tcp', l4.get('UDP', l4.get('udp')))) or {}
    targets = set(ip if isinstance(ip, (list, tuple, set)) else [ip])
    forward = is_client(source) and ips.get('destination') in targets and transport.get('destination_port', transport.get('destinationPort')) == int(port)
    reverse = is_client(dest) and ips.get('source') in targets and transport.get('source_port', transport.get('sourcePort')) == int(port)
    if not (forward or (mode in [403, 'dns-deny'] and reverse)):
        return False
    client_port = transport.get('source_port', transport.get('sourcePort')) if forward else transport.get('destination_port', transport.get('destinationPort'))
    if client_ports and client_port not in client_ports:
        return False
    if mode == 'drop':
        # 默认拒绝为 POLICY_DENIED；显式 ingress/egressDeny 为 POLICY_DENY。
        return flow.get('verdict') == 'DROPPED' and flow.get('drop_reason_desc', flow.get('dropReasonDesc')) in ['POLICY_DENIED', 'POLICY_DENY']
    if mode == 'dns-deny':
        l7 = flow.get('l7') or {}
        dns = l7.get('dns') or {}
        if dns_query and dns.get('query', '').rstrip('.').lower() != dns_query.rstrip('.').lower():
            return False
        # 1.20.2 把代理拒绝记录为 L7 REQUEST/DROPPED，不生成带 RCODE 的响应事件。
        # RCODE=5 由三次实际探测证明；Hubble 再核对同域名、socket 与工作负载身份。
        return dns.get('rcode') == 5 or (forward and flow.get('verdict') == 'DROPPED'
            and l7.get('type') == 'REQUEST' and bool(dns.get('query')))
    if mode == 403:
        return ((flow.get('l7') or {}).get('http') or {}).get('code') == 403
    return flow.get('verdict') == 'FORWARDED'


def hubble_access(node):
    agent = agents()[node]
    relay = get('service', 'hubble-relay', 'kube-system')['spec']['clusterIP']
    prefix = K[:-1] + ['--request-timeout=0', 'exec', '-n', 'kube-system', agent, '-c', 'cilium-agent', '--', 'hubble', '--server', relay + ':80']
    status = call(prefix + ['status'], timeout=25)
    require(re.search(r'Connected Nodes:\s*10/10', status), 'Hubble 未连通十台 VM')
    return prefix, status


def hubble_query(pod, targets, port, since):
    name = pod['metadata']['namespace'] + '/' + pod['metadata']['name']
    # --pod 与 --ip 互斥；--pod + --port 会把端口约束在 Pod 同侧。
    # 显式关联对端端口，并保留 L7 拒绝/DNS 回包的反向记录。
    forward = {'source_pod': [name], 'destination_ip': targets, 'destination_port': [str(port)]}
    reverse = {'destination_pod': [name], 'source_ip': targets, 'source_port': [str(port)]}
    return ['observe', '--since', since, '--last', '200', '--allowlist', json.dumps(forward),
            '--allowlist', json.dumps(reverse), '-o', 'json']


def flows(pod, ip, port, since, mode, output, dns_query=None, client_ports=None):
    prefix, status = hubble_access(pod['spec']['nodeName'])
    targets = list(ip) if isinstance(ip, (list, tuple, set)) else [ip]
    if int(port) == 53:
        # Hubble 的记录可能位于 Service DNAT 前后；同时关联 Service 与实际 CoreDNS IP。
        targets += [p['status']['podIP'] for p in get('pods', namespace='kube-system')['items']
                    if p['metadata'].get('labels', {}).get('k8s-app') == 'kube-dns' and base.ready(p)]
    targets = sorted(set(targets))
    for _ in range(6):
        raw = call(prefix + hubble_query(pod, targets, port, since), timeout=25)
        output.write_text(raw)
        envelopes = [json.loads(line) for line in raw.splitlines()]
        require(not any(e.get('lost_events') or e.get('lostEvents') for e in envelopes), 'Hubble 丢失事件，不能接受不完整证据')
        matches = [e['flow'] for e in envelopes if e.get('flow') and flow_matches(e['flow'], pod, targets, port, mode, dns_query, client_ports)]
        if matches:
            identities = {e['identity'] for f in matches for e in [f.get('source') or {}, f.get('destination') or {}]
                if e.get('namespace') == pod['metadata']['namespace'] and e.get('pod_name', e.get('podName')) == pod['metadata']['name']}
            return {'passed': True, 'matching_flows': len(matches), 'target_ips': targets,
                'workload_identities': sorted(identities), 'relay_status': status}
        time.sleep(1)
    raise ValueError('缺少本次实际 Hubble 流量：' + mode.__str__() + ' ' + str(output))


def case(context, attempt, name, pod, protocol, target, expected, backend=None, flow_ip=None, flow_port=None, **options):
    path = attempt / 'observations' / name
    path.mkdir(parents=True, exist_ok=True)
    since = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    streak, attempts = [], []
    for i in range(12):
        row = request(pod, protocol, target, **options)
        attempts.append(row)
        save(path / 'requests.json', attempts)
        streak = streak + [row] if matched(row, expected, backend) else []
        if len(streak) >= 3:
            break
        time.sleep(1)
    parsed = urlparse(target)
    ip = flow_ip or (backend['status']['podIP'] if backend else parsed.hostname)
    port = flow_port or (parsed.port or (443 if parsed.scheme == 'https' else 8080))
    if protocol.startswith('dns-'):
        ip, port = '192.168.20.10', 53
    dns = {'dns_query': target, 'client_ports': [int(row['local'].rsplit(':', 1)[1])
        for row in (streak or attempts) if row.get('local')]} if protocol.startswith('dns-') else {}
    # 行为不符合预期也先取证，不能在清理前丢掉 TO_PROXY/DROP/反向 L7 线索。
    try:
        evidence = flows(pod, ip, port, since, expected, path / 'hubble.jsonl', **dns)
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as error:
        save(path / 'result.json', {'passed': False, 'expected': expected, 'consecutive_matches': len(streak),
            'hubble_error': str(error), 'samples': len(attempts)})
        raise
    value = {'passed': len(streak) >= 3, 'name': name, 'source_uid': pod['metadata']['uid'],
        'expected': expected, 'requests': streak, 'flow': evidence}
    save(path / 'result.json', value)
    require(value['passed'], '用例没有连续三次符合预期：' + name + '；预期 ' + str(expected)
        + '，超时 ' + str(sum(bool(row.get('timeout')) for row in attempts)) + '/' + str(len(attempts))
        + '；请求与 Hubble 证据：' + str(path))
    return value


def matrix(context, attempt, mode):
    policies = policy_state(context, attempt, mode)
    inventory = pods(context)
    client, api, dep = (inventory[n] for n in ['client', 'api', 'dependency'])
    url = 'http://' + api['status']['podIP'] + ':8080'
    service = get('service', 'api', NS[0])['spec']['clusterIP']
    results = {}
    def run(name, pod, protocol, target, expected, backend=None, **options):
        results[name] = case(context, attempt, mode + '-' + name, pod, protocol, target, expected, backend, **options)
    if mode == 'denied':
        run('api-drop', client, 'http', url + '/allowed', 'drop', flow_ip=api['status']['podIP'], flow_port=8080)
        run('dns-drop', client, 'dns-udp', 'api.lab-policy.svc.cluster.local', 'drop', flow_ip='192.168.20.10', flow_port=53)
        return {'passed': True, 'cases': results, 'policies': policies}
    for protocol in ['dns-udp', 'dns-tcp']:
        run(protocol, client, protocol, 'api.lab-policy.svc.cluster.local', 'dns')
        require(service in results[protocol]['requests'][-1]['addresses'], 'DNS 返回了其他 Service')
    run('api-allowed', client, 'http', url + '/allowed', 200, api)
    run('service-allowed', client, 'http', 'http://' + service + ':8080/allowed', 200, api, flow_ip=[api['status']['podIP'], service], flow_port=8080)
    run('path-comparison', client, 'http', url + '/blocked', 200 if mode == 'standard' else 403, api if mode == 'standard' else None)
    run('method-comparison', client, 'http', url + '/allowed', 200 if mode == 'standard' else 403, api if mode == 'standard' else None, method='POST')
    run('dependency', client, 'http', 'http://' + dep['status']['podIP'] + ':8080/allowed', 200, dep)
    run('ingress', inventory['ingress'], 'http', url + '/allowed', 200, api)
    run('monitor', inventory['monitor'], 'http', 'http://' + api['status']['podIP'] + ':9090/metrics', 200, api)
    run('outsider-drop', inventory['outsider'], 'http', url + '/allowed', 'drop', flow_ip=api['status']['podIP'], flow_port=8080)
    run('metrics-drop', client, 'http', 'http://' + api['status']['podIP'] + ':9090/metrics', 'drop', flow_ip=api['status']['podIP'], flow_port=9090)
    run('dependency-drop', inventory['ingress'], 'http', 'http://' + dep['status']['podIP'] + ':8080/allowed', 'drop', flow_ip=dep['status']['podIP'], flow_port=8080)
    if mode == 'cilium':
        fqdn = inventory['fqdn']
        run('fqdn-dns', fqdn, 'dns-udp', 'harbor.k8s.internal.egon.top', 'dns')
        run('fqdn-harbor', fqdn, 'http', 'https://harbor.k8s.internal.egon.top/v2/', 401, ca=CA, timeout=5000, flow_ip='192.168.9.12', flow_port=443)
        run('fqdn-dns-drop', fqdn, 'dns-udp', 'nexus.svc.internal.egon.top', 'dns-deny')
        run('fqdn-ip-drop', fqdn, 'tcp', '192.168.9.14:443', 'drop', flow_ip='192.168.9.14', flow_port=443)
        run('fqdn-port-drop', fqdn, 'tcp', '192.168.9.12:8443', 'drop', flow_ip='192.168.9.12', flow_port=8443)
    return {'passed': True, 'enforcer': 'Cilium 1.20.2 agent/Envoy', 'cases': results, 'policies': policies}


def wire(context, attempt, pod, destination, port, target, protocol='http', proxy='', ca=''):
    pod_ip, vm_ip = pod['status']['podIP'], base.NODES[pod['spec']['nodeName']]
    capture_ip = vm_ip if destination == '192.168.9.10' else destination
    name = destination + '-' + str(port)
    folder = attempt / 'observations' / ('wire-' + name)
    folder.mkdir(parents=True, exist_ok=True)
    bpf = 'tcp dst port ' + str(port) + ' and dst host ' + destination + ' and (src host ' + pod_ip + ' or src host ' + vm_ip + ') and tcp[tcpflags] & tcp-syn != 0'
    # 存储节点可能在隧道解封后接收 Pod 原地址；any 覆盖该 VM 内接口，避免只看 ens33 外层。
    interface = 'any' if destination in ['192.168.9.106', '192.168.9.107', '192.168.9.108'] else 'ens33'
    command = "timeout 8 tcpdump -l -nn -i " + interface + " -c 20 '" + bpf + "'"
    process = subprocess.Popen(ssh(capture_ip, command), stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    banner = ''
    try:
        deadline = time.monotonic() + 6
        while 'listening on' not in banner and time.monotonic() < deadline:
            if select.select([process.stderr], [], [], 0.3)[0]:
                # select 只能看到内核缓冲；TextIOWrapper.readline 的预读会藏住下一行启动信息。
                line = os.read(process.stderr.fileno(), 4096).decode(errors='replace')
                require(line, '抓取进程提前退出：' + banner)
                banner += line
        require('listening on' in banner, '抓取进程没有完成监听')
        row = request(pod, protocol, target, timeout=12000 if proxy else 5000, proxy=proxy, ca=ca)
        stdout, stderr = process.communicate(timeout=15)
        stdout, stderr = stdout.decode(errors='replace'), stderr.decode(errors='replace')
        (folder / 'tcp-syn.txt').write_text(stdout)
        (folder / 'observer.txt').write_text(banner + stderr)
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=12)
    require(process.returncode in [0, 124], '抓取命令失败')
    require(not row.get('error') and (protocol == 'tcp' or row.get('status') in [204, 401]), '带抓取的实际探测失败')
    save(folder / 'request.json', row)
    local_port = row['local'].rsplit(':', 1)[1]
    pattern = r'IP (\d+\.\d+\.\d+\.\d+)\.' + re.escape(local_port) + r' > ' + re.escape(destination) + r'\.' + str(port) + ':'
    sources = set(re.findall(pattern, stdout))
    require(len(sources) == 1 and sources <= {pod_ip, vm_ip}, '无法关联本次 Pod socket 与对端/网卡实际 SYN')
    source_ip = next(iter(sources))
    route = json.loads(call(ssh(capture_ip, 'ip -j route get ' + source_ip), timeout=20))
    require(route and route[0].get('dev'), '缺少真实源地址的回程路由')
    for ip in [destination, '192.168.9.10']:
        route_out = json.loads(call(ssh(vm_ip, 'ip -j route get ' + ip), timeout=20))
        require(route_out[0]['dev'] == 'ens33' and not route_out[0].get('gateway'), '内网 VM 经过了非直连路径')
    return {'passed': True, 'pod_ip': pod_ip, 'pod_uid': pod['metadata']['uid'], 'node_ip': vm_ip,
            'wire_source': source_ip, 'snat': source_ip != pod_ip, 'capture_vm': capture_ip,
            'destination': destination, 'port': port, 'socket': row['local'], 'return_route': route,
            'capture_interface': interface,
            'capture_scope': 'worker ens33 上的出站 SYN' if capture_ip == vm_ip else '目标 VM 内核在 ' + interface + ' 收到的 SYN'}


def egress(context, attempt, mode):
    policies = policy_state(context, attempt, mode)
    pod = pods(context)['egress']
    results = {}
    results['harbor'] = case(context, attempt, mode + '-harbor', pod, 'http', 'https://harbor.k8s.internal.egon.top/v2/', 401,
        ca=CA, timeout=5000, flow_ip='192.168.9.12', flow_port=443)
    for last in [106, 107, 108]:
        ip = '192.168.9.' + str(last)
        results['storage-' + str(last)] = case(context, attempt, mode + '-storage-' + str(last), pod, 'tcp', ip + ':10250',
            'tcp', flow_ip=ip, flow_port=10250)
    blocked = mode == 'proxy-unreachable'
    results['proxy'] = case(context, attempt, mode + '-proxy', pod, 'http', EXTERNAL, 'drop' if blocked else 204,
        proxy=PROXY, timeout=2000 if blocked else 12000, flow_ip='192.168.9.10', flow_port=7890)
    results['no-direct-fallback'] = case(context, attempt, mode + '-direct-drop', pod, 'tcp', '1.1.1.1:443', 'drop',
        flow_ip='1.1.1.1', flow_port=443)
    results['api-drop'] = case(context, attempt, mode + '-api-drop', pod, 'tcp', '192.168.9.101:6443', 'drop',
        flow_ip='192.168.9.101', flow_port=6443)
    wires = {}
    if mode == 'egress':
        wires['harbor'] = wire(context, attempt, pod, '192.168.9.12', 443, 'https://harbor.k8s.internal.egon.top/v2/', ca=CA)
        for last in [106, 107, 108]:
            ip = '192.168.9.' + str(last)
            wires['storage-' + str(last)] = wire(context, attempt, pod, ip, 10250, ip + ':10250', protocol='tcp')
        wires['proxy'] = wire(context, attempt, pod, '192.168.9.10', 7890, EXTERNAL, proxy=PROXY)
    return {'passed': True, 'cases': results, 'wire': wires, 'policies': policies, 'ceph_service_status': 'BLOCKED',
            'fault_scope': '只对 lab-egress 探测 Pod 拒绝代理 TCP；不是切断真实 VPN', 'public_source_ip_verified': False}


def blocked(context):
    value = yaml.safe_load((PHASE / 'networking/policies/capabilities.yaml').read_text())
    required = value['egress_gateway']['required']
    missing = {k: {'required': v, 'observed': context['capabilities'].get(k)} for k, v in required.items() if context['capabilities'].get(k) != v}
    require(missing, 'CNI 功能模式改变，不能复用本轮 BLOCKED 结论')
    return {'status': 'BLOCKED', 'passed': False, 'phase_complete': False, 'observed': context['capabilities'],
            'missing': missing, 'crd_installed': context.get('egress_gateway_crd_installed', False),
            'reason': value['egress_gateway']['reason'], 'not_executed': value['egress_gateway']['not_executed']}


def cleanup_plan(records, context, output):
    objects = []
    for ns in NS:
        obj = optional('Namespace', ns)
        if not obj:
            continue
        require(obj['metadata'].get('labels', {}).get(LABEL) == context['run'], '命名空间已经属于其他运行')
        for kind in ['pods', 'services', 'configmaps', 'networkpolicies', 'ciliumnetworkpolicies', 'serviceaccounts',
                     'deployments', 'daemonsets', 'statefulsets', 'jobs', 'cronjobs', 'roles', 'rolebindings',
                     'persistentvolumeclaims', 'ingresses', 'httproutes', 'resourcequotas', 'limitranges']:
            for item in get(kind, namespace=ns)['items']:
                m = item['metadata']
                if (kind, m['name']) in [('serviceaccounts', 'default'), ('configmaps', 'kube-root-ca.crt')]:
                    continue
                require(m.get('labels', {}).get(LABEL) == context['run'], '空间中出现外来对象，停止删除：' + key(item))
                path = state_path(records, item)
                require(path.exists(), '对象没有原始记录：' + key(item))
                saved = json.loads(path.read_text())
                require(not saved.get('uid') or saved['uid'] == m['uid'], '清理前对象 UID 改变')
        # 只读取 Secret 元信息；本实验没有创建 Secret。
        require(not gw.secret_list(ns), '实验空间出现 Secret，停止删除以保留数据')
        row = delete_row(records, context, obj, output)
        if row:
            objects.append(row)
    return {'objects': objects}


def accept(records, context, attempt):
    names = ['denied', 'standard', 'cilium', 'egress', 'proxy-unreachable', 'proxy-restored']
    results = {n: json.loads((attempt / (n + '.json')).read_text()) for n in names}
    require(all(v['passed'] for v in results.values()), '缺少整组行为验证')
    boundary = json.loads((attempt / 'egress-gateway.json').read_text())
    require(boundary['status'] == 'BLOCKED' and boundary['passed'] is False, '出口模式边界不符')
    require(source() == json.loads((records / 'state/source.json').read_text()), '执行期间输入改变')
    require(protected() == json.loads((records / 'state/protected.json').read_text()), '既有网络、策略或工作负载发生变化')
    firewall_verify(records, context)
    return {'stage': '02.06', 'available_cases_passed': True, 'passed': False, 'phase_complete': False,
        'cluster_uid': context['cluster_uid'], 'run': context['run'], 'attempt': str(attempt),
        'steps': {'02.06.01': 'PASS', '02.06.02': 'PASS', '02.06.03': 'PARTIAL_CEPH_BLOCKED', '02.06.04': 'BLOCKED'},
        'results': results, 'egress_gateway': boundary, 'public_source_ip_verified': False}


def final(records, context):
    require(all(optional('namespace', ns) is None for ns in NS), '临时命名空间未完全删除')
    path = records / 'state/protected.json'
    require(not path.exists() or protected() == json.loads(path.read_text()), '清理后原有资源发生变化')
    firewall = firewall_verify(records, context, restored=True)
    gw.data_plane(context, laboratory=False)
    tls = gw.probe.http('192.168.9.201', '/cnpl-policy-preflight')
    require(tls['status'] == 404 and tls['tls_peer_sha256'], '清理后主入口可信 TLS 异常')
    value = json.loads((records / 'passed.json').read_text()) if (records / 'passed.json').exists() else {}
    return {'stage': '02.06', 'cleanup_passed': True, 'cluster_uid': context['cluster_uid'], 'run': context['run'],
        'temporary_namespaces_absent': True, 'existing_resources_unchanged': True,
        'temporary_firewall_rules_restored': firewall['passed'],
        'available_cases_passed': value.get('available_cases_passed', False), 'phase_complete': False,
        'main_tls_status': tls['status'], 'main_tls_sha256': tls['tls_peer_sha256']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--records', type=Path, required=True)
    parser.add_argument('--attempt', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--case')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    records, attempt = args.records.resolve(), args.attempt
    require(records.parent == PHASE / 'records' and records.name.startswith('02.06-'), '证据目录越界')
    context = json.loads((records / 'context.json').read_text()) if (records / 'context.json').exists() else None
    action = args.action
    if action in ['preflight', 'identity']:
        value = preflight(records, action == 'identity')
    elif action == 'source':
        value = source()
    elif action == 'hosts':
        value = hosts(args.output)
    elif action == 'protected':
        value = protected()
    elif action == 'validate':
        value = validate(attempt)
    elif action in ['object-plan', 'record']:
        document = json.loads(args.manifest.read_text())
        value = (object_plan if action == 'object-plan' else record)(records, context, document)
    elif action == 'delete-plan':
        value = delete_plan(records, context, args.manifest, args.output)
    elif action == 'ready':
        value = endpoint_state(context)
    elif action in ['firewall-plan', 'firewall-cleanup-plan']:
        value = firewall_plan(records, context, action == 'firewall-cleanup-plan')
    elif action in ['firewall-verify', 'firewall-restored']:
        value = firewall_verify(records, context, action == 'firewall-restored')
    elif action == 'matrix':
        value = matrix(context, attempt, args.case)
    elif action == 'egress':
        value = egress(context, attempt, args.case)
    elif action == 'blocked':
        value = blocked(context)
    elif action == 'cleanup-plan':
        value = cleanup_plan(records, context, args.output)
    elif action == 'accept':
        value = accept(records, context, attempt)
    elif action == 'final':
        value = final(records, context)
    else:
        raise ValueError('未知动作：' + action)
    save(args.output, value)
    print(json.dumps(value, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as error:
        sys.exit(str(error))
