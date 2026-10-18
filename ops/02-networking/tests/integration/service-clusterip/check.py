#!/usr/bin/env python3
"""02.02.01 只读检查与请求取证；所有集群对象变更和 Readiness 切换由 Ansible 执行。"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

import yaml

spec = importlib.util.spec_from_file_location('network_baseline', Path(__file__).resolve().parents[1] / 'network-baseline/check.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
ROOT, K = base.ROOT, base.K
NS = 'lab-service-clusterip'
LABEL = 'cnpl.io/service-run'
WORKERS = {'worker01.k8s.internal.egon.top', 'worker02.k8s.internal.egon.top'}
INPUTS = yaml.safe_load((ROOT / 'ops/02-networking/ansible/vars/service-clusterip.yml').read_text())
require, save, get, call, ready = base.require, base.save, base.get, base.call, base.ready


def handoff(uid):
    pointer = json.loads((ROOT / 'ops/02-networking/records/completed/02.01.json').read_text())
    require(pointer['passed'] and pointer['cleanup_passed'] and pointer['cluster_uid'] == uid and pointer['next_step'] == '02.02.01', '02.01 完成指针不符合前置')
    records = Path(pointer['records'])
    require(records.resolve().is_relative_to(ROOT / 'ops/02-networking/records'), '前序证据路径越界')
    for path_key, hash_key in [('passed_receipt', 'passed_receipt_sha256'), ('cleanup_receipt', 'cleanup_receipt_sha256')]:
        path = records / pointer[path_key]
        require(hashlib.sha256(path.read_bytes()).hexdigest() == pointer[hash_key], '02.01 原始回执已改变')
        receipt = json.loads(path.read_text())
        require(receipt['run'] == pointer['run'] and receipt['cluster_uid'] == uid, '02.01 回执身份不一致')
        require(receipt.get('passed') if path_key == 'passed_receipt' else receipt.get('cleanup_passed'), '02.01 原始实验或清理回执没有通过')
    return pointer


def namespace(records, run):
    raw = call(K + ['get', 'namespace', NS, '--ignore-not-found', '-o', 'json']).strip()
    if not raw:
        return None
    ns = json.loads(raw)
    require(ns['metadata'].get('labels', {}).get(LABEL) == run, '同名空间属于其他运行')
    saved = records / 'state/namespace.json'
    if saved.exists():
        require(json.loads(saved.read_text())['uid'] == ns['metadata']['uid'], 'Namespace UID 已改变')
    return ns


def preflight(records, identity_only=False):
    if identity_only:
        context = json.loads((records / 'context.json').read_text())
        server = call(K + ['config', 'view', '--minify', '-o', 'jsonpath={.clusters[0].cluster.server}']).strip()
        require(server == 'https://api.k8s.internal.egon.top:6443', 'kubeconfig 目标不符')
        require(get('namespace', 'kube-system')['metadata']['uid'] == context['cluster_uid'], '集群 UID 已改变')
    else:
        context = base.preflight(records)
    prior = handoff(context['cluster_uid'])
    require(context.get('stage', '02.02.01') == '02.02.01', '批次所属步骤不符')
    context.update(stage='02.02.01', previous_run=prior['run'], namespace=NS)
    ns = namespace(records, context['run'])
    require(identity_only or not ns or not ns['metadata'].get('deletionTimestamp'), '空间仍在删除')
    save(records / 'context.json', context)
    return context


def sources():
    phase = ROOT / 'ops/02-networking'
    paths = [phase / 'ansible/playbooks/service-clusterip.yml', phase / 'ansible/vars/service-clusterip.yml', phase / 'networking/services/clusterip.yaml.j2', phase / 'scripts/clusterip.sh', phase / 'examples/service-clusterip/README.md', Path(base.__file__), ROOT / 'ops/00-preparation/ansible/ansible.cfg', ROOT / 'ops/00-preparation/ansible/inventories/lab/hosts.yml', ROOT / 'ops/00-preparation/ansible/inventories/lab/group_vars/all.yml', ROOT / 'ops/00-preparation/ansible/inventories/lab/group_vars/k8s_nodes.yml']
    paths += list((phase / 'ansible/tasks').glob('service-clusterip*.yml'))
    paths += [p for p in Path(__file__).parent.glob('*.py')]
    paths += [ROOT / 'ops/versions.lock.yaml', phase / 'records/completed/02.01.json']
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def owner(obj):
    return next((o.get('uid') for o in obj['metadata'].get('ownerReferences', []) if o.get('controller')), None)


def backend_cache(document):
    status = document.get('status') or {}
    image = INPUTS['svc_backend_image']
    image_id = status.get('id')
    digests = status.get('repoDigests') or []
    require(isinstance(image_id, str) and re.fullmatch(r'sha256:[a-f0-9]{64}', image_id) and isinstance(digests, list) and image in digests, '后端 OCI 缓存没有有效 ID 或完整摘要；不能仅凭 inspecti 退出码判定存在')
    return {'backend_cached': True, 'image': image, 'id': status['id']}


def inspect(deployment, sets, all_pods, service, slices, run, count, ready_count, blocked=None):
    require(deployment['metadata'].get('labels', {}).get(LABEL) == run, 'Deployment 归属不符')
    require(service['metadata'].get('labels', {}).get(LABEL) == run, 'Service 归属不符')
    require(service['spec']['type'] == 'ClusterIP' and not service['spec'].get('publishNotReadyAddresses', False), 'Service 类型或就绪语义被改变')
    require(service['spec']['selector'] == {'app': 'svc-echo', LABEL: run}, 'Service selector 不符')
    require(service['spec']['ports'] == [{'name': 'http', 'port': 80, 'protocol': 'TCP', 'targetPort': 'http'}], 'Service 端口映射不符')
    require(ipaddress.ip_address(service['spec']['clusterIP']) in ipaddress.ip_network('192.168.20.0/24'), 'Service IP 不在规划网段')
    set_uids = {s['metadata']['uid'] for s in sets if owner(s) == deployment['metadata']['uid']}
    pods = [p for p in all_pods if owner(p) in set_uids and not p['metadata'].get('deletionTimestamp')]
    clients = [p for p in all_pods if p['metadata'].get('labels', {}).get('app') == 'svc-client']
    for p in pods + clients:
        require(p['metadata'].get('labels', {}).get(LABEL) == run, 'Pod 不属于本次实验')
        require(not p['spec'].get('hostNetwork') and not p['spec'].get('automountServiceAccountToken', True), 'Pod 安全基线不符')
        require(not p['spec'].get('nodeName') or p['spec']['nodeName'] in WORKERS, 'Pod 不在两个 worker VM 上')
        image = INPUTS['svc_backend_image'] if p in pods else INPUTS['svc_client_image']
        require(p['spec']['containers'][0]['image'] == image, '镜像摘要漂移')
    active = {(p['metadata']['uid'], p.get('status', {}).get('podIP')): ready(p) for p in pods}
    expected_ready = {key for key, value in active.items() if value}
    observed = {}
    valid = all(p['spec'].get('nodeName') in WORKERS and p.get('status', {}).get('phase') == 'Running' for p in pods + clients)
    issues = []
    for p in pods + clients:
        if not ready(p):
            waiting = [c.get('state', {}).get('waiting', {}).get('reason') for c in p.get('status', {}).get('containerStatuses', [])]
            issues.append(p['metadata']['name'] + ': ' + ', '.join(r for r in waiting if r) if any(waiting) else p['metadata']['name'] + ': 尚未 Ready')
    for s in slices:
        valid = valid and any(o['uid'] == service['metadata']['uid'] for o in s['metadata'].get('ownerReferences', []))
        # 创建和回收端点时 ports/endpoints 可以为 null；这是未收敛状态，不是通过条件。
        ports = s.get('ports') or []
        endpoints = s.get('endpoints') or []
        require(isinstance(ports, list) and isinstance(endpoints, list), 'EndpointSlice ports/endpoints 必须为列表或 null')
        if not ports or not endpoints:
            issues.append('EndpointSlice ' + s['metadata'].get('name', '') + ': ports/endpoints 尚未就绪')
        valid = valid and s.get('addressType') == 'IPv4'
        if not endpoints:
            continue
        valid = valid and any(p.get('name') == 'http' and p.get('port') == 8080 and p.get('protocol') == 'TCP' for p in ports)
        for endpoint in endpoints:
            ref = endpoint.get('targetRef', {})
            valid = valid and ref.get('kind') == 'Pod'
            for address in endpoint.get('addresses') or []:
                key = (ref.get('uid'), address)
                observed.setdefault(key, set()).add((endpoint.get('conditions') or {}).get('ready') is True)
    observed_ready = {key for key, values in observed.items() if values == {True}}
    valid = valid and all(len(v) == 1 for v in observed.values()) and set(observed) == set(active) and observed_ready == expected_ready
    status = deployment.get('status', {})
    valid = valid and deployment['spec']['replicas'] == count and len(pods) == count and len(expected_ready) == ready_count
    valid = valid and status.get('observedGeneration', 0) >= deployment['metadata'].get('generation', 1) and status.get('updatedReplicas', 0) == count and status.get('readyReplicas', 0) == ready_count
    valid = valid and len(clients) == 2 and all(ready(p) for p in clients) and {p['spec'].get('nodeName') for p in clients} == WORKERS
    if blocked:
        valid = valid and any(p['metadata']['name'] == blocked['name'] and p['metadata']['uid'] == blocked['uid'] and not ready(p) and p['status'].get('phase') == 'Running' for p in pods)
    return {'ok': bool(valid), 'issues': issues if not valid else [], 'deployment': deployment, 'pods': pods, 'clients': clients, 'service': service, 'slices': slices, 'ready_backends': {p['metadata']['name']: p['metadata']['uid'] for p in pods if ready(p)}}


def graph(context, count, ready_count, blocked=None, raw_output=None):
    documents = {'deployment': get('deploy', 'svc-echo', NS), 'sets': get('replicasets', namespace=NS)['items'], 'all_pods': get('pods', namespace=NS)['items'], 'service': get('service', 'svc-echo', NS), 'slices': get('endpointslices', namespace=NS)['items']}
    if raw_output:
        save(raw_output, documents)
    return inspect(**documents, run=context['run'], count=count, ready_count=ready_count, blocked=blocked)


def wait(context, count, ready_count, blocked, output):
    deadline = time.monotonic() + 90
    sequence = 0
    observation = uuid.uuid4().hex[:8]
    while True:
        sequence += 1
        prefix = output.stem + '-' + observation + '-poll-' + str(sequence)
        raw = output.with_name(prefix + '-input.json')
        value = graph(context, count, ready_count, blocked, raw_output=raw)
        save(output.with_name(prefix + '.json'), value)
        if value['ok']:
            return value
        require(time.monotonic() < deadline, 'Deployment/Readiness/EndpointSlice 未在 90 秒内收敛：' + '; '.join(value['issues']) + '；原始快照：' + str(raw))
        time.sleep(2)


def probe(graph_path, output):
    state = json.loads(graph_path.read_text())
    require(state['ok'] and state['ready_backends'], '没有已收敛的就绪端点')
    ip = state['service']['spec']['clusterIP']
    urls = ['http://' + ip + '/identity', 'http://svc-echo.' + NS + '.svc.cluster.local/identity', 'http://svc-echo/identity']
    observations = []
    for client in state['clients']:
        for url in urls:
            for _ in range(5):
                row = {'at': datetime.now(timezone.utc).isoformat(), 'client': client['metadata']['name'], 'url': url, 'passed': False, 'response': {}}
                try:
                    result = subprocess.run(K[:-1] + ['--request-timeout=0', '-n', NS, 'exec', client['metadata']['name'], '-c', 'client', '--', 'wget', '-q', '-S', '-T', '3', '-O', '-', url], capture_output=True, text=True, timeout=10)
                    row.update(rc=result.returncode, response_headers=result.stderr)
                    statuses = re.findall(r'HTTP/\d(?:\.\d)?\s+(\d{3})', result.stderr)
                    row['response_body'] = result.stdout
                    reply = json.loads(result.stdout) if result.stdout.strip() else {}
                    require(isinstance(reply, dict), 'HTTP 响应必须为 JSON 对象')
                    row['response'] = reply
                    row['passed'] = result.returncode == 0 and statuses[-1:] == ['200'] and isinstance(reply.get('pod'), str) and reply['pod'] in state['ready_backends'] and state['ready_backends'][reply['pod']] == reply.get('uid')
                except (subprocess.SubprocessError, ValueError, OSError) as error:
                    row['error'] = str(error)
                observations.append(row)
    raw = output.with_name(output.stem + '-' + uuid.uuid4().hex[:8] + '.jsonl')
    raw.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in observations))
    value = {'passed': all(r['passed'] for r in observations) and len(observations) == 30, 'requests': len(observations), 'ready_backends': state['ready_backends'], 'observed_backends': sorted({r['response']['pod'] for r in observations if isinstance(r['response'].get('pod'), str)}), 'requests_file': raw.name, 'service_uid': state['service']['metadata']['uid'], 'service_ip': ip}
    save(output, value)
    require(value['passed'], '请求仍命中非就绪/旧 UID 后端，或 HTTP/DNS 失败；详见 ' + raw.name)
    return value


def cleanup_plan(records, context):
    ns = namespace(records, context['run'])
    if not ns:
        return {'namespace_exists': False}
    objects = get('pods,deploy,rs,ds,sts,svc,cm,secret,sa,networkpolicy,ciliumnetworkpolicy,pvc,job,cronjob,role,rolebinding,resourcequota,limitrange,ingress,hpa', namespace=NS)['items']
    for obj in objects:
        if (obj['kind'], obj['metadata']['name']) in [('ConfigMap', 'kube-root-ca.crt'), ('ServiceAccount', 'default')]:
            continue
        require(obj['metadata'].get('labels', {}).get(LABEL) == context['run'], '空间有外来资源，停止清理：' + obj['kind'] + '/' + obj['metadata']['name'])
    return {'namespace_exists': True, 'namespace_uid': ns['metadata']['uid']}


def recover(records, context):
    path = records / 'state/not-ready.json'
    if not path.exists() or not namespace(records, context['run']):
        return {'pod': None}
    blocked = json.loads(path.read_text())
    raw = call(K + ['get', 'pod', blocked['name'], '-n', NS, '--ignore-not-found', '-o', 'json']).strip()
    if not raw:
        return {'pod': None}
    pod = json.loads(raw)
    require(pod['metadata']['uid'] == blocked['uid'] and pod['metadata'].get('labels', {}).get(LABEL) == context['run'], '恢复目标 UID/归属已改变')
    return {'pod': blocked['name']}


def accept(records, attempt, context):
    require(attempt.resolve().is_relative_to(records.resolve() / 'attempts'), '验收 attempt 路径越界')
    counts = {'initial': (2, 2), 'expanded': (3, 3), 'not-ready': (3, 2), 'restored': (3, 3), 'scaled-down': (2, 2)}
    states = {}
    service_uids, addresses, deployment_uids = set(), set(), set()
    for name, (count, ready_count) in counts.items():
        state = json.loads((attempt / ('state-' + name + '.json')).read_text())
        require(state['ok'] and len(state['pods']) == count and len(state['ready_backends']) == ready_count, name + ' 端点计数不符')
        requests = json.loads((attempt / ('requests-' + name + '.json')).read_text())
        require(requests['passed'] and requests['requests'] == 30 and requests['ready_backends'] == state['ready_backends'], name + ' 请求与实际就绪集合不符')
        raw = attempt / requests['requests_file']
        require(raw.resolve().parent == attempt.resolve(), '请求记录路径越界')
        rows = [json.loads(line) for line in raw.read_text().splitlines()]
        require(len(rows) == 30 and all(row['passed'] and row['response']['pod'] in state['ready_backends'] and state['ready_backends'][row['response']['pod']] == row['response']['uid'] for row in rows), name + ' 原始请求未全部通过')
        service_uids.add(state['service']['metadata']['uid'])
        addresses.add(state['service']['spec']['clusterIP'])
        deployment_uids.add(state['deployment']['metadata']['uid'])
        states[name] = state
    require(len(service_uids) == len(addresses) == len(deployment_uids) == 1, 'Service/ClusterIP/Deployment 在实验中被替换')
    target = json.loads((records / 'state/not-ready.json').read_text())
    identity = []
    for name in ['expanded', 'not-ready', 'restored']:
        matches = [p for p in states[name]['pods'] if p['metadata']['name'] == target['name'] and p['metadata']['uid'] == target['uid']]
        require(len(matches) == 1, 'Readiness 实验替换了原 Pod')
        pod = matches[0]
        require(ready(pod) == (name != 'not-ready') and pod['status']['phase'] == 'Running', 'Readiness 与进程状态不符')
        identity.append([c.get('restartCount', 0) for c in pod['status'].get('containerStatuses', [])])
    require(identity[0] == identity[1] == identity[2], 'Readiness 实验伴随容器重启，不能视为单纯端点摘除')
    source = json.loads((records / 'state/source.json').read_text())
    require(source['source_sha256'] == sources(), '执行期间源码发生变化')
    return {'stage': '02.02.01', 'run': context['run'], 'cluster_uid': context['cluster_uid'], 'attempt': str(attempt), 'passed': True, 'cleanup_passed': False, 'requests': 150, 'service_uid': next(iter(service_uids)), 'service_ip': next(iter(addresses)), 'readiness_pod': target, 'pod_uid_preserved': True, 'readiness_without_container_restart': True, 'source': source}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['preflight', 'identity', 'source', 'validate', 'wait', 'probe', 'pick', 'recover', 'cleanup-plan', 'accept', 'backend-cache'])
    parser.add_argument('--records', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--graph', type=Path)
    parser.add_argument('--attempt', type=Path)
    parser.add_argument('--count', type=int, default=2)
    parser.add_argument('--ready-count', type=int, default=2)
    parser.add_argument('--blocked', action='store_true')
    args = parser.parse_args()
    if args.mode in ['preflight', 'identity']:
        value = preflight(args.records, args.mode == 'identity')
    elif args.mode == 'source':
        value = {'source_sha256': sources()}
    elif args.mode == 'validate':
        value = base.validate(args.manifest, args.output)
    elif args.mode == 'backend-cache':
        value = backend_cache(json.load(sys.stdin))
    else:
        context = json.loads((args.records / 'context.json').read_text())
        if args.mode == 'wait':
            blocked = json.loads((args.records / 'state/not-ready.json').read_text()) if args.blocked else None
            value = wait(context, args.count, args.ready_count, blocked, args.output)
        elif args.mode == 'probe':
            value = probe(args.graph, args.output)
        elif args.mode == 'pick':
            state = json.loads(args.graph.read_text())
            require(state['ok'] and len(state['pods']) == 3, '必须先取得三副本的完整快照')
            pod = sorted(state['pods'], key=lambda p: p['metadata']['name'])[0]
            value = {'name': pod['metadata']['name'], 'uid': pod['metadata']['uid']}
        elif args.mode == 'recover':
            value = recover(args.records, context)
        elif args.mode == 'accept':
            value = accept(args.records, args.attempt, context)
        else:
            value = cleanup_plan(args.records, context)
    save(args.output, value)
    print(json.dumps({'ok': value['ok'], 'ready_backends': value['ready_backends']} if args.mode == 'wait' else value, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
