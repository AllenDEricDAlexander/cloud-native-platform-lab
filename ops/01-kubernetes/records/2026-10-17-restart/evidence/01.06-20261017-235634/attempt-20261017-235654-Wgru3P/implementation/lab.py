#!/usr/bin/env python3
"""01.06 受限控制器实验；默认 check/render 不部署，用户启动完整批次。"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import copy
from datetime import datetime
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import subprocess
import time
from urllib.parse import urlencode

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sp = importlib.util.spec_from_file_location('probe05', HERE.parent / 'probes/lab.py')
previous = importlib.util.module_from_spec(sp); sp.loader.exec_module(previous)
api, command, client = previous.api, previous.command, previous.client
save, stamp, ensure, wait_for = previous.save, previous.stamp, previous.ensure, previous.wait_for
tunnel, request, traffic = previous.tunnel, previous.request, previous.traffic
NS = 'lab-core'
LABEL = 'cnpl.io/controller-run'
PHASE = 'cnpl.io/controller-stage'
POOL = 'cnpl.io/controller-pool'
PART = {'app.kubernetes.io/part-of': 'cnpl-controller-lab'}
FINALIZER = 'cnpl.io/observe-controller-stop'
KINDS = 'deployments,replicasets,replicationcontrollers,pods,services,networkpolicies'
STAGES = ['replicas', 'history', 'scale', 'strategies', 'rollbacks', 'split', 'verify', 'cleanup']


def get(kind, name): return json.loads(api('-n', NS, 'get', kind, name, '-o', 'json'))


def owned(obj, state):
    ensure(obj['metadata'].get('labels', {}).get(LABEL) == state['run'], '拒绝修改其他批次：' + obj['metadata']['name'])


def listing(kind, state, stage=None):
    selector = LABEL + '=' + state['run'] + (',' + PHASE + '=' + stage if stage else '')
    return json.loads(api('-n', NS, 'get', kind, '-l', selector, '-o', 'json'))['items']


def labels(stage, state, pool=None):
    result = dict(PART, **{LABEL: state['run'], PHASE: stage})
    if pool: result[POOL] = pool
    return result


def template(stage, state, image, pool):
    base = previous.pod('template', stage, image)['spec']
    base.pop('nodeSelector')
    base['affinity'] = {'nodeAffinity': {'requiredDuringSchedulingIgnoredDuringExecution': {'nodeSelectorTerms': [
        {'matchExpressions': [{'key': 'kubernetes.io/hostname', 'operator': 'In', 'values': list(previous.WORKERS)}]}]}}}
    base['topologySpreadConstraints'] = [{'maxSkew': 1, 'topologyKey': 'kubernetes.io/hostname', 'whenUnsatisfiable': 'ScheduleAnyway',
                                          'labelSelector': {'matchLabels': {LABEL: state['run'], POOL: pool}}}]
    c = base['containers'][0]; c['command'] = ['/controller-app', 'server']
    c['env'] = [env for env in c['env'] if env['name'] != 'START_SECONDS']
    c['env'].append({'name': 'FORCE_NOT_READY', 'value': 'false'})
    c['lifecycle'] = {'preStop': {'exec': {'command': ['/controller-app', 'prestop', '5']}}}
    return {'metadata': {'labels': labels(stage, state, pool), 'annotations': {'cnpl.io/template-note': 'baseline'}}, 'spec': base}


def deploy(name, stage, state, image, count=2, pool='main', strategy='RollingUpdate'):
    spec = {'replicas': count, 'selector': {'matchLabels': {LABEL: state['run'], POOL: pool}},
            'template': template(stage, state, image, pool), 'minReadySeconds': 3, 'progressDeadlineSeconds': 45,
            'revisionHistoryLimit': 10, 'strategy': {'type': strategy}}
    if strategy == 'RollingUpdate': spec['strategy']['rollingUpdate'] = {'maxSurge': 1, 'maxUnavailable': 0}
    return {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': {'name': name, 'namespace': NS, 'labels': labels(stage, state)}, 'spec': spec}


def service(name, stage, state, pool):
    return {'apiVersion': 'v1', 'kind': 'Service', 'metadata': {'name': name, 'namespace': NS, 'labels': labels(stage, state)},
            'spec': {'selector': {LABEL: state['run'], POOL: pool}, 'ports': [{'port': 8080, 'targetPort': 8080}]}}


def observer(name, stage, state, target):
    item = template(stage, state, state['bundle']['images']['v1']['image'], 'client-' + name)
    c = item['spec']['containers'][0]; c['command'] = ['/controller-app', 'relay']; c['env'] = [{'name': 'RELAY_TARGET', 'value': target + ':8080'}]
    for key in ['startupProbe', 'livenessProbe', 'lifecycle']: c.pop(key)
    c['readinessProbe'] = {'tcpSocket': {'port': 8080}, 'periodSeconds': 2, 'timeoutSeconds': 3}
    # SSH 只连客户端所在 worker；Service 连接由客户端 Pod 内发起。
    item['spec']['nodeSelector'] = {'kubernetes.io/hostname': list(previous.WORKERS)[0]}
    return {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': dict(item['metadata'], name=name, namespace=NS), 'spec': item['spec']}


def policy(state):
    peers = {'podSelector': {'matchLabels': dict(PART, **{LABEL: state['run']})}}
    return {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
            'metadata': {'name': 'p06-isolation', 'namespace': NS, 'labels': labels('prepare', state)},
            'spec': {'podSelector': {'matchLabels': dict(PART, **{LABEL: state['run']})}, 'policyTypes': ['Ingress', 'Egress'],
                     'ingress': [{'from': [copy.deepcopy(peers)]}, {'from': [{'ipBlock': {'cidr': ip + '/32'}} for ip in previous.WORKERS.values()], 'ports': [{'port': 8080}]}],
                     'egress': [{'to': [copy.deepcopy(peers)]}, {'to': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'kube-system'}},
                                                                 'podSelector': {'matchLabels': {'k8s-app': 'kube-dns'}}}],
                                                            'ports': [{'protocol': 'UDP', 'port': 53}, {'protocol': 'TCP', 'port': 53}]}]}}


def create(obj, state):
    owned(obj, state)
    return json.loads(api('create', '-f', '-', '-o', 'json', payload=obj))


def patch(kind, name, body, state):
    owned(get(kind, name), state)
    patch_type = 'merge' if 'finalizers' in body.get('metadata', {}) else 'strategic'
    return api('-n', NS, 'patch', kind, name, '--type=' + patch_type, '-p', json.dumps(body))


def scale_to(name, count, state):
    owned(get('deployment', name), state)
    return api('-n', NS, 'scale', 'deployment/' + name, '--replicas=' + str(count))


def image_to(name, version, state):
    owned(get('deployment', name), state)
    return api('-n', NS, 'set', 'image', 'deployment/' + name, 'app=' + state['bundle']['images'][version]['image'])


def controller_ref(obj):
    return next((ref for ref in obj['metadata'].get('ownerReferences', []) if ref.get('controller')), None)


def children(obj, kind, state):
    return [item for item in listing(kind, state) if (controller_ref(item) or {}).get('uid') == obj['metadata']['uid']]


def active_pods(dep, state):
    uids = {rs['metadata']['uid'] for rs in children(dep, 'replicasets', state)}
    return [p for p in listing('pods', state) if not p['metadata'].get('deletionTimestamp') and (controller_ref(p) or {}).get('uid') in uids]


def ready(obj): return previous.pod04.condition(obj, 'Ready', 'True')


def converged(dep, pods):
    wanted = dep['spec']['replicas']; status = dep.get('status', {})
    return (status.get('observedGeneration', 0) >= dep['metadata']['generation']
            and all(status.get(key, 0) == wanted for key in ['replicas', 'updatedReplicas', 'readyReplicas', 'availableReplicas'])
            and len(pods) == wanted and all(ready(p) for p in pods))


def revision(dep):
    value = dep['metadata'].get('annotations', {}).get('deployment.kubernetes.io/revision', '')
    ensure(value.isdecimal(), 'Deployment 没有有效 revision'); return int(value)


def cpu(value): return int(value[:-1]) if value.endswith('m') else int(float(value) * 1000)


def observation(args, name, value):
    path = args.records / name
    if path.exists(): save(args.records / ('observations/' + path.stem + '-' + stamp() + path.suffix), json.loads(path.read_text()))
    save(path, value)


def snapshot(args, state, reason):
    directory = args.records / ('snapshots/' + stamp() + '-' + reason); directory.mkdir(parents=True)
    items = listing(KINDS, state); save(directory / 'objects.json', {'items': items})
    slices = json.loads(api('-n', NS, 'get', 'endpointslices', '-l', 'kubernetes.io/service-name in (p06-entry,p06-stable,p06-canary)', '-o', 'json'))
    save(directory / 'endpointslices.json', slices)
    for pod in [o for o in items if o['kind'] == 'Pod']:
        name, uid = pod['metadata']['name'], pod['metadata']['uid']
        save(directory / (name + '.events.json'), json.loads(api('-n', NS, 'get', 'events', '--field-selector=involvedObject.uid=' + uid, '-o', 'json')))
        if pod['metadata'].get('deletionTimestamp'): continue
        for url, suffix in [('/metrics', '.metrics'), ('/local', '.local')]:
            if pod['spec']['containers'][0]['command'] != ['/controller-app', 'server']: continue
            if not previous.pod04.state_of(pod).get('state', {}).get('running'): continue
            out = command(client() + ['-n', NS, 'exec', name, '--', '/controller-app', 'probe', 'http://127.0.0.1:8080' + url], check=False, timeout=10)
            (directory / (name + suffix + ('.json' if out.returncode == 0 else '-error.txt'))).write_text(out.stdout + out.stderr)
        for prior in [False, True]:
            if prior and previous.pod04.state_of(pod).get('restartCount', 0) == 0: continue
            out = command(client() + ['-n', NS, 'logs', name, '--tail=100'] + (['--previous'] if prior else []), check=False, timeout=15)
            (directory / (name + ('.previous' if prior else '') + '.txt')).write_text(out.stdout + out.stderr)
    return directory


def remove(args, state, stage=None):
    items = listing(KINDS, state, stage)
    for obj in items:
        owned(obj, state)
        allowed = {FINALIZER}
        if obj['metadata'].get('deletionTimestamp'): allowed.add('foregroundDeletion')
        ensure(set(obj['metadata'].get('finalizers', [])) <= allowed, '外来 finalizer，拒绝整组清理：' + obj['metadata']['name'])
    if items: snapshot(args, state, 'before-reset-' + (stage or 'all'))
    for obj in items:
        if FINALIZER in obj['metadata'].get('finalizers', []):
            # 续跑可能遇到 Kubernetes 已开始的前台 GC；只释放本实验标记。
            remaining = [f for f in obj['metadata']['finalizers'] if f != FINALIZER]
            patch(obj['kind'], obj['metadata']['name'], {'metadata': {'finalizers': remaining}}, state)
    # 先停止补副本，再回收孤儿 Pod；不能先删受控 Pod 让控制器继续补。
    order = {'Deployment': 0, 'ReplicationController': 1, 'ReplicaSet': 2, 'Pod': 3, 'Service': 4, 'NetworkPolicy': 5}
    for obj in sorted(items, key=lambda x: order[x['kind']]):
        argv = ['-n', NS, 'delete', obj['kind'], obj['metadata']['name'], '--ignore-not-found', '--wait=true', '--timeout=90s']
        if obj['kind'] in ['Deployment', 'ReplicationController', 'ReplicaSet']: argv += ['--cascade=foreground']
        api(*argv, timeout=110)
    ensure(not listing(KINDS, state, stage), '清理后仍有本组对象')


def rollout(args, state, name='p06-main', timeout=180):
    samples = []; output = args.records / ('rollout-' + name + '-' + stamp() + '.jsonl')
    with output.open('w') as stream:
        def poll():
            dep = get('deployment', name); replica_sets = children(dep, 'replicasets', state)
            uids = {rs['metadata']['uid'] for rs in replica_sets}
            all_pods = [p for p in listing('pods', state) if (controller_ref(p) or {}).get('uid') in uids]
            pods = [p for p in all_pods if not p['metadata'].get('deletionTimestamp')]
            sample = {'at': time.time(), 'deployment': dep, 'pods': all_pods,
                      'desired_rs_replicas': sum(rs['spec']['replicas'] for rs in replica_sets),
                      'nonterminating': len(pods), 'total_pod_objects': len(all_pods),
                      'declared_cpu_m': sum(cpu(c['resources']['requests']['cpu']) for p in all_pods for c in p['spec']['containers'])}
            samples.append(sample); stream.write(json.dumps(sample) + '\n'); stream.flush()
            return dep if converged(dep, pods) else None
        dep = wait_for(name + ' rollout 收敛', poll, timeout)
    api('-n', NS, 'rollout', 'status', 'deployment/' + name, '--timeout=10s', timeout=25)
    print(f'{name}: desired={dep["spec"]["replicas"]} updated={dep["status"].get("updatedReplicas", 0)} ready={dep["status"].get("readyReplicas", 0)} available={dep["status"].get("availableReplicas", 0)}', flush=True)
    return dep, samples


def finish(args, state, stage, evidence):
    path = args.records / ('receipts/' + stage + '.json')
    if path.exists(): save(args.records / ('receipts/attempts/' + stage + '-' + stamp() + '.json'), json.loads(path.read_text()))
    save(path, dict(evidence, stage=stage, run=state['run'], passed=True, at=stamp()))
    remove(args, state, stage)
    state['passed'].append(stage); save(args.records / 'state.json', state); print(stage.upper() + ' PASS')


def baseline(args, state, stage, strategy='RollingUpdate'):
    dep = create(deploy('p06-main', stage, state, state['bundle']['images']['v1']['image'], strategy=strategy), state)
    create(service('p06-entry', stage, state, 'main'), state)
    dep, _ = rollout(args, state)
    create_observer('p06-client', stage, state, 'p06-entry')
    client_pod = wait_for('客户端 Pod Ready', lambda: (lambda p: p if ready(p) else None)(get('pod', 'p06-client')))
    return dep, client_pod


def create_observer(name, stage, state, target):
    obj = observer(name, stage, state, target)
    # 使用当前 Service UID 对应的 ClusterIP，避免同名 Service 重建时的 DNS 缓存。
    obj['spec']['containers'][0]['env'][0]['value'] = get('service', target)['spec']['clusterIP'] + ':8080'
    return create(obj, state)


def version_samples(port, version, count=6):
    samples = []; consecutive = 0; end = time.monotonic() + 30
    while time.monotonic() < end:
        row = {'at': time.time()}
        try:
            row['response'] = request(port, '/work?id=check'); row['ok'] = row['response'].get('version') == version and bool(row['response'].get('uid'))
        except (OSError, ValueError, http.client.HTTPException) as exc: row.update(ok=False, error=str(exc))
        samples.append(row); consecutive = consecutive + 1 if row['ok'] else 0
        if consecutive == count: return {'observations': samples, 'stable': samples[-count:]}
        time.sleep(.2)
    raise ValueError('真实业务没有连续恢复到 ' + version + '：' + json.dumps(samples[-5:]))


def history_text(args, name, suffix):
    value = api('-n', NS, 'rollout', 'history', 'deployment/' + name)
    (args.records / ('history-' + suffix + '-' + stamp() + '.txt')).write_text(value + '\n'); return value


def undo(args, state, good, template_before):
    owned(get('deployment', 'p06-main'), state)
    print('恢复已知模板：kubectl rollout undo deployment/p06-main --to-revision=' + str(good), flush=True)
    api('-n', NS, 'rollout', 'undo', 'deployment/p06-main', '--to-revision=' + str(good))
    restored, _ = rollout(args, state)
    ensure(restored['spec']['template'] == template_before, '回滚没有还原完整的已知模板')
    return restored


def replicas(args, state):
    remove(args, state, 'replicas'); result = {}
    for kind, short in [('ReplicationController', 'rc'), ('ReplicaSet', 'rs')]:
        print(kind + '：创建匹配/不匹配孤儿，观察接管、删除和补副本', flush=True)
        pool = 'compare-' + short; image = state['bundle']['images']['v1']['image']
        tmpl = template('replicas', state, image, pool); tmpl['metadata']['labels']['track'] = 'stable'
        orphan = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': dict(tmpl['metadata'], name='p06-' + short + '-adopt', namespace=NS), 'spec': tmpl['spec']}
        adopted = create(orphan, state)
        mismatch = copy.deepcopy(orphan); mismatch['metadata']['name'] = 'p06-' + short + '-mismatch'; mismatch['metadata']['labels']['track'] = 'other'
        foreign = create(mismatch, state)
        selector = {LABEL: state['run'], POOL: pool, 'track': 'stable'}
        spec = {'replicas': 2, 'selector': selector, 'template': copy.deepcopy(tmpl)}
        if short == 'rs': spec['selector'] = {'matchLabels': {LABEL: state['run'], POOL: pool}, 'matchExpressions': [{'key': 'track', 'operator': 'In', 'values': ['stable']}]}
        obj = create({'apiVersion': 'v1' if short == 'rc' else 'apps/v1', 'kind': kind,
                      'metadata': {'name': 'p06-' + short, 'namespace': NS, 'labels': labels('replicas', state)}, 'spec': spec}, state)
        def stable():
            pods = children(obj, 'pods', state)
            return pods if len(pods) == 2 and all(ready(p) for p in pods) else None
        before = wait_for(short + ' 接管并补足两个副本', stable)
        ensure(any(p['metadata']['uid'] == adopted['metadata']['uid'] for p in before), '未观察到原孤儿被接管')
        ensure(controller_ref(get('pod', foreign['metadata']['name'])) is None, '标签不匹配的 Pod 被错误接管')
        victim = next(p for p in before if p['metadata']['uid'] != adopted['metadata']['uid'])
        api('-n', NS, 'delete', 'pod', victim['metadata']['name'], '--wait=true', '--timeout=45s')
        def healed():
            pods = stable()
            return pods if pods and victim['metadata']['uid'] not in {p['metadata']['uid'] for p in pods} else None
        after = wait_for(short + ' 删除后的新 UID 副本', healed)
        ensure(controller_ref(get('pod', foreign['metadata']['name'])) is None, '补副本时误接管不匹配 Pod')
        result[short] = {'controller': get(kind, obj['metadata']['name']), 'adopted_uid': adopted['metadata']['uid'],
                         'before': before, 'deleted_uid': victim['metadata']['uid'], 'after': after, 'mismatch': get('pod', foreign['metadata']['name'])}
    snapshot(args, state, 'replicas'); finish(args, state, 'replicas', result)


def history(args, state):
    remove(args, state, 'history'); initial, observer_pod = baseline(args, state, 'history')
    print('记录 v1→v2 的镜像 Digest、revision 和 ownerReferences；随后只 scale 到 3', flush=True)
    with tunnel(observer_pod, args) as port:
        v1 = version_samples(port, 'v1'); before_rs = children(initial, 'replicasets', state); old_revision = revision(initial)
        image_to('p06-main', 'v2', state); updated, timeline = rollout(args, state)
        v2 = version_samples(port, 'v2'); after_rs = children(updated, 'replicasets', state)
        ensure(revision(updated) > old_revision and len(after_rs) > len(before_rs), '模板镜像更新未产生新 revision/RS')
        rs_uids = {r['metadata']['uid'] for r in after_rs}
        scale_to('p06-main', 3, state); scaled, _ = rollout(args, state)
        ensure(revision(scaled) == revision(updated) and {r['metadata']['uid'] for r in children(scaled, 'replicasets', state)} == rs_uids, '仅 scale 居然产生新版本')
        chain = [{'pod_uid': p['metadata']['uid'], 'replicaset_uid': controller_ref(p)['uid']} for p in active_pods(scaled, state)]
        ensure(all(controller_ref(rs)['uid'] == scaled['metadata']['uid'] for rs in children(scaled, 'replicasets', state)), 'RS ownerReference 不属于该 Deployment')
        history_output = history_text(args, 'p06-main', 'versions-and-scale')
    snapshot(args, state, 'history'); finish(args, state, 'history', {'v1': v1, 'v2': v2, 'initial': initial, 'updated': updated,
           'scaled': scaled, 'replicasets': after_rs, 'owner_chain': chain, 'rollout': timeline, 'history': history_output})


def term_receipt(pod):
    status = previous.pod04.state_of(pod).get('state', {}).get('terminated', {})
    ensure(pod['metadata'].get('deletionTimestamp') and status.get('exitCode') == 0 and status.get('reason') == 'Completed', '缩容没有正常完成终止')
    msg = json.loads(status.get('message', '{}'))
    ensure(msg.get('uid') == pod['metadata']['uid'] and msg.get('signal') == 'TERM' and msg.get('drained') is True, '缩容 TERM 回执不匹配')
    return msg


def scale(args, state):
    remove(args, state, 'scale'); dep, observer_pod = baseline(args, state, 'scale')
    print('正常扩容到 3；记录 emptyDir，然后带长请求缩到 1，再扩到 3', flush=True)
    scale_to('p06-main', 3, state); dep, _ = rollout(args, state); originals = active_pods(dep, state)
    local = {}; completed = {}; final = []
    with ExitStack() as stack, ThreadPoolExecutor(max_workers=3) as pool:
        ports = {p['metadata']['name']: stack.enter_context(tunnel(p, args)) for p in originals}
        for p in originals:
            name, uid = p['metadata']['name'], p['metadata']['uid']
            patch('pod', name, {'metadata': {'finalizers': [FINALIZER]}}, state)
            local[uid] = request(ports[name], '/local?' + urlencode({'value': 'temporary-' + uid}), post=True)
        snapshot(args, state, 'before-scale-down')
        futures = {p['metadata']['uid']: pool.submit(request, ports[p['metadata']['name']], '/work?seconds=12&id=' + p['metadata']['uid'], False, 20) for p in originals}
        for name, port in ports.items(): wait_for(name + ' 的请求已进入', lambda port=port: request(port, '/metrics')['active'] == 1)
        scale_to('p06-main', 1, state)
        for uid, future in futures.items():
            completed[uid] = future.result(timeout=25); ensure(completed[uid]['uid'] == uid and completed[uid].get('result') == 'completed', '缩容丢失在途请求')
        def stopped():
            pods = [get('pod', p['metadata']['name']) for p in originals]
            removed = [p for p in pods if p['metadata'].get('deletionTimestamp')]
            return removed if len(removed) == 2 and all(previous.pod04.state_of(p).get('state', {}).get('terminated') for p in removed) else None
        final = wait_for('缩容的两个终止 Pod 保留终态', stopped)
        receipts = {p['metadata']['uid']: term_receipt(p) for p in final}
        for uid, msg in receipts.items():
            ensure(datetime.fromisoformat(completed[uid]['completed_at'].replace('Z', '+00:00')) > datetime.fromisoformat(msg['term_at'].replace('Z', '+00:00')), '请求在 TERM 前就结束，未证明排空')
        observation(args, 'scale-down-final-pods.json', {'items': final})
        for p in originals: patch('pod', p['metadata']['name'], {'metadata': {'finalizers': []}}, state)
    dep, _ = rollout(args, state); survivor = active_pods(dep, state)[0]
    with tunnel(survivor, args) as port:
        retained = request(port, '/local'); ensure(retained['value'] == local[survivor['metadata']['uid']]['value'], '存活 Pod 的临时数据被错误清空')
    scale_to('p06-main', 3, state); dep, _ = rollout(args, state)
    new = [p for p in active_pods(dep, state) if p['metadata']['uid'] not in local]; ensure(len(new) == 2, '重新扩容没有得到两个新 Pod UID')
    new_data = []
    for p in new:
        with tunnel(p, args) as port:
            value = request(port, '/local'); ensure(value['value'] == p['metadata']['uid'], '新 Pod 沿用了旧 emptyDir 数据'); new_data.append(value)
    # 单独的 0→1 手动扩容：每 Pod 申请 8 核超过 worker 的 7 核，不影响正常三副本。
    capacity = deploy('p06-capacity', 'scale', state, state['bundle']['images']['v1']['image'], 0, 'capacity')
    capacity['spec']['template']['spec']['containers'][0]['resources'].update(requests={'cpu': '8', 'memory': '32Mi', 'ephemeral-storage': '1Mi'}, limits={'cpu': '8', 'memory': '128Mi', 'ephemeral-storage': '32Mi'})
    create(capacity, state); rollout(args, state, 'p06-capacity')
    print('容量反例：p06-capacity 从 0 扩到 1，每 Pod 请求 8 核，等待 FailedScheduling', flush=True)
    scale_to('p06-capacity', 1, state); pending = capacity_failure(state, 'p06-capacity')
    snapshot(args, state, 'scale-insufficient-cpu')
    scale_to('p06-capacity', 0, state); rolled_back_capacity, _ = rollout(args, state, 'p06-capacity')
    restored, _ = rollout(args, state)
    with tunnel(observer_pod, args) as port: restored_responses = version_samples(port, 'v1')
    finish(args, state, 'scale', {'three_pods': originals, 'completed_requests': completed, 'terminated_pods': final,
           'term_receipts': receipts, 'surviving_local': retained, 'new_pod_local': new_data,
           'capacity_failure': pending, 'capacity_scaled_to_zero': rolled_back_capacity, 'restored': restored, 'responses': restored_responses})


def capacity_failure(state, name='p06-main'):
    def poll():
        dep = get('deployment', name)
        for pod in active_pods(dep, state):
            if pod['spec']['containers'][0]['resources']['requests']['cpu'] != '8': continue
            events = json.loads(api('-n', NS, 'get', 'events', '--field-selector=involvedObject.uid=' + pod['metadata']['uid'], '-o', 'json'))
            if not pod.get('spec', {}).get('nodeName') and any(e.get('reason') == 'FailedScheduling' and 'insufficient cpu' in e.get('message', '').lower() for e in events['items']):
                return {'pod': pod, 'events': events, 'deployment': dep}
        return None
    return wait_for('8 核请求的真实 FailedScheduling/Insufficient cpu', poll, 100)


def strategies(args, state):
    remove(args, state, 'strategies'); comparisons = {}
    for strategy in ['RollingUpdate', 'Recreate']:
        print(strategy + '：持续发送新连接，测量 v1→v2 发布', flush=True)
        remove(args, state, 'strategies'); dep, observer_pod = baseline(args, state, 'strategies', strategy)
        with tunnel(observer_pod, args) as port:
            version_samples(port, 'v1')
            with traffic(port, args.records / ('traffic-' + strategy + '-' + stamp() + '.jsonl')) as rows:
                wait_for('连续基线短请求', lambda: len(rows) >= 8)
                start = time.monotonic(); image_to('p06-main', 'v2', state); updated, samples = rollout(args, state)
                responses = version_samples(port, 'v2'); duration = time.monotonic() - start
                time.sleep(1)
            errors = sum(not row['ok'] for row in rows)
            print(f'{strategy}: requests={len(rows)} errors={errors} observed_seconds={duration:.2f}', flush=True)
            if strategy == 'RollingUpdate':
                ensure(errors == 0, '滚动更新采样出现业务错误，保留现场')
                ensure(all(s['desired_rs_replicas'] <= 3 for s in samples), 'RS 期望副本预算超出 replicas+maxSurge')
            else: ensure(errors > 0, '没有观察到 Recreate 不可用窗口，不能声称比较成功')
            comparisons[strategy] = {'deployment': updated, 'timeline': samples, 'requests': len(rows), 'errors': errors,
                                     'error_rate': errors / len(rows), 'observed_seconds': duration,
                                     'peak_nonterminating_pods': max(s['nonterminating'] for s in samples),
                                     'peak_total_pod_objects': max(s['total_pod_objects'] for s in samples),
                                     'peak_declared_cpu_m': max(s['declared_cpu_m'] for s in samples), 'final_responses': responses}
            if strategy == 'RollingUpdate':
                print('滚动发布容量反例：maxSurge=1 的新 Pod 请求 8 核，旧两副本继续服务', flush=True)
                good = revision(updated); good_template = copy.deepcopy(updated['spec']['template'])
                with traffic(port, args.records / ('traffic-blocked-surge-' + stamp() + '.jsonl')) as blocked_rows:
                    patch('deployment', 'p06-main', {'spec': {'template': {'spec': {'containers': [{'name': 'app', 'resources': {'requests': {'cpu': '8'}, 'limits': {'cpu': '8'}}}]}}}}, state)
                    blocked = capacity_failure(state)
                    ensure(blocked['deployment'].get('status', {}).get('availableReplicas', 0) == 2, 'surge 不足时旧副本可用数下降')
                    snapshot(args, state, 'blocked-surge'); recovered = undo(args, state, good, good_template); version_samples(port, 'v2')
                ensure(blocked_rows and all(r['ok'] for r in blocked_rows), 'surge 阻塞/恢复期间出现业务失败')
                comparisons[strategy]['blocked_surge'] = {'failure': blocked, 'restored': recovered, 'traffic': blocked_rows}
        observation(args, 'strategy-' + strategy + '.json', comparisons[strategy])
    finish(args, state, 'strategies', comparisons)


def failure_candidates(state, predicate):
    dep = get('deployment', 'p06-main')
    return [p for p in active_pods(dep, state) if predicate(p)]


def rollbacks(args, state):
    remove(args, state, 'rollbacks'); dep, observer_pod = baseline(args, state, 'rollbacks'); evidence = {}
    with tunnel(observer_pod, args) as port:
        version_samples(port, 'v1'); prior_uids = {rs['metadata']['uid'] for rs in children(dep, 'replicasets', state)}
        print('暂停发布，在暂停中修改并修正模板，确认没有生成新 RS 后恢复', flush=True)
        owned(get('deployment', 'p06-main'), state)
        api('-n', NS, 'rollout', 'pause', 'deployment/p06-main')
        patch('deployment', 'p06-main', {'spec': {'template': {'spec': {'containers': [{'name': 'app', 'image': state['bundle']['images']['v2']['image'], 'env': [{'name': 'FORCE_NOT_READY', 'value': 'true'}]}]}}}}, state)
        # 暂停期间修正探针配置并合并版本说明；恢复前不能产生新 RS。
        patch('deployment', 'p06-main', {'spec': {'template': {'metadata': {'annotations': {'cnpl.io/template-note': 'paused-batch'}},
                                                              'spec': {'containers': [{'name': 'app', 'env': [{'name': 'FORCE_NOT_READY', 'value': 'false'}]}]}}}}, state)
        time.sleep(5); paused = get('deployment', 'p06-main')
        ensure(paused['spec'].get('paused') is True and {r['metadata']['uid'] for r in children(paused, 'replicasets', state)} == prior_uids, '暂停期间意外发布了新 RS')
        evidence['paused'] = {'deployment': paused, 'responses': version_samples(port, 'v1')}
        owned(get('deployment', 'p06-main'), state)
        api('-n', NS, 'rollout', 'resume', 'deployment/p06-main'); good_dep, _ = rollout(args, state)
        evidence['resumed'] = {'deployment': good_dep, 'responses': version_samples(port, 'v2')}
        for fault in ['image', 'probe', 'business']:
            print('发布失败场景：' + fault, flush=True)
            good_revision = revision(good_dep); good_template = copy.deepcopy(good_dep['spec']['template'])
            if fault == 'image':
                patch('deployment', 'p06-main', {'spec': {'template': {'spec': {'containers': [{'name': 'app', 'image': 'cnpl.local/phase01/controller-missing@sha256:' + '0'*64}]}}}}, state)
                candidates = wait_for('错误镜像 ErrImageNeverPull', lambda: failure_candidates(state, lambda p: previous.pod04.state_of(p).get('state', {}).get('waiting', {}).get('reason') == 'ErrImageNeverPull'))
                def deadline():
                    obj = get('deployment', 'p06-main')
                    return obj if any(c['type'] == 'Progressing' and c['status'] == 'False' and c.get('reason') == 'ProgressDeadlineExceeded' for c in obj.get('status', {}).get('conditions', [])) else None
                print('等待真实 ProgressDeadlineExceeded；配置期限 45 秒，保留最多 120 秒观察窗口', flush=True)
                failed = wait_for('ProgressDeadlineExceeded（不会自动回滚）', deadline, 120)
                ensure(failed['spec']['template']['spec']['containers'][0]['image'].startswith('cnpl.local/phase01/controller-missing@'), '未能证明失败版本仍被保留')
                status = command(client() + ['-n', NS, 'rollout', 'status', 'deployment/p06-main', '--timeout=1s'], check=False, timeout=20)
                ensure(status.returncode != 0 and 'progress deadline' in (status.stdout + status.stderr).lower(), 'rollout status 未明确报告进度失败')
                observed = {'candidates': candidates, 'deployment': failed, 'rollout_status': status.stdout + status.stderr, 'old_version_responses': version_samples(port, 'v2')}
            elif fault == 'probe':
                patch('deployment', 'p06-main', {'spec': {'template': {'spec': {'containers': [{'name': 'app', 'env': [{'name': 'FORCE_NOT_READY', 'value': 'true'}]}]}}}}, state)
                candidates = wait_for('失败 readiness、无容器重启', lambda: failure_candidates(state, lambda p: previous.pod04.state_of(p).get('started') is True and not ready(p)))
                events = wait_for('readiness HTTP 503 事件', lambda: probe_events(candidates[0]))
                ensure(all(previous.pod04.state_of(p).get('restartCount', 0) == 0 for p in candidates), 'readiness 失败出现了额外重启')
                observed = {'candidates': candidates, 'events': events, 'old_version_responses': version_samples(port, 'v2')}
            else:
                image_to('p06-main', 'bad', state); healthy_controller, _ = rollout(args, state)
                def all_bad():
                    try: rows = [request(port, '/identity') for _ in range(6)]
                    except (OSError, ValueError, http.client.HTTPException): return None
                    return rows if all(x['version'] == 'bad' for x in rows) else None
                wrong = wait_for('业务入口已全部切换 bad 身份', all_bad, 30)
                errors = []
                for _ in range(6):
                    try: request(port, '/work?id=business-fault')
                    except ValueError as exc:
                        ensure('HTTP 500' in str(exc), '实际失败并非预期业务 HTTP 500'); errors.append(str(exc))
                    else: raise ValueError('坏业务版本意外成功')
                observed = {'controller_reported_complete': healthy_controller, 'identities': wrong, 'business_errors': errors}
            observed['snapshot'] = str(snapshot(args, state, 'failed-rollout-' + fault))
            observed['history'] = history_text(args, 'p06-main', fault)
            observed['good_revision'] = good_revision; observed['good_template'] = good_template
            good_dep = undo(args, state, good_revision, good_template)
            observed['restored'] = good_dep; observed['restored_responses'] = version_samples(port, 'v2')
            evidence[fault] = observed; observation(args, 'rollback-' + fault + '.json', observed)
    finish(args, state, 'rollbacks', evidence)


def probe_events(pod):
    value = json.loads(api('-n', NS, 'get', 'events', '--field-selector=involvedObject.uid=' + pod['metadata']['uid'], '-o', 'json'))
    return value if any('readiness probe failed' in e.get('message', '').lower() and '503' in e.get('message', '') for e in value['items']) else None


def split(args, state):
    remove(args, state, 'split'); responses = {}; workloads = {}
    for pool, version, count in [('stable', 'v1', 2), ('canary', 'v2', 1)]:
        print(f'{pool}: {version}，{count} 副本，独立 selector 和 Service', flush=True)
        name = 'p06-' + pool
        create(deploy(name, 'split', state, state['bundle']['images'][version]['image'], count, pool), state)
        create(service(name, 'split', state, pool), state); workloads[pool], _ = rollout(args, state, name)
        create_observer(name + '-client', 'split', state, name)
        obs = wait_for(pool + ' 客户端 Ready', lambda name=name: (lambda p: p if ready(p) else None)(get('pod', name + '-client')))
        with tunnel(obs, args) as port: responses[pool] = version_samples(port, version)
    ensure(get('service', 'p06-stable')['spec']['selector'] != get('service', 'p06-canary')['spec']['selector'], '双入口 selector 重叠')
    snapshot(args, state, 'split'); finish(args, state, 'split', {'deployments': workloads, 'responses': responses,
             'services': [get('service', 'p06-stable'), get('service', 'p06-canary')], 'weighted_routing_verified': False})


def check():
    identity = previous.pod04.check()
    for verb, resource in [('create', 'replicationcontrollers'), ('create', 'replicasets'), ('create', 'deployments'),
                           ('delete', 'replicationcontrollers'), ('delete', 'replicasets'), ('delete', 'deployments'),
                           ('patch', 'deployments'), ('update', 'deployments/scale'), ('create', 'pods/exec'),
                           ('create', 'pods'), ('patch', 'pods'), ('delete', 'pods'), ('create', 'services'), ('delete', 'services'),
                           ('create', 'networkpolicies'), ('delete', 'networkpolicies'), ('list', 'events'), ('get', 'endpointslices.discovery.k8s.io')]:
        ensure(api('auth', 'can-i', verb, resource, '-n', NS) == 'yes', '运维身份缺少 ' + verb + ' ' + resource)
    runs = sorted((ROOT / 'ops/01-kubernetes/records/2026-10-17-restart/evidence').glob('01.05-*/state.json'), reverse=True)
    accepted = None
    for path in runs:
        state = json.loads(path.read_text())
        if state.get('cluster_uid') == identity['cluster_uid'] and state.get('passed') == previous.STAGES:
            cleanup = json.loads((path.parent / 'cleanup-confirm.json').read_text())
            ensure(not cleanup['items'] and not cleanup['endpointslices']['items'], '01.05 前置清理记录有残留')
            accepted = {'records': str(path.parent), 'run': state['run']}; break
    ensure(accepted is not None, '需要同一集群已通过并清理的 01.05 真实批次')
    ensure(not json.loads(api('-n', NS, 'get', 'pods', '-l', 'app.kubernetes.io/part-of=cnpl-probe-lab', '-o', 'json'))['items'], '01.05 仍有运行对象，先完成其清理')
    return dict(identity, predecessor=accepted)


def prepare(args, bundle):
    identity = check(); path = args.records / 'state.json'
    ensure(set(bundle['images']) == {'v1', 'v2', 'bad'}, '物料缺少三个固定版本')
    if path.exists():
        state = json.loads(path.read_text())
        ensure(state['cluster_uid'] == identity['cluster_uid'] and state['version'] == identity['version'], '续跑集群身份变化')
        ensure(state['bundle'] == bundle, '续跑物料变化，拒绝混合不同应用实现')
        ensure(state['passed'] == STAGES[:len(state['passed'])], '检查点顺序异常')
        ensure('cleanup' not in state['passed'], '已完成清理，无需续跑')
    else:
        ensure(not json.loads(api('-n', NS, 'get', KINDS, '-l', 'app.kubernetes.io/part-of=cnpl-controller-lab', '-o', 'json'))['items'], '已有其他 01.06 批次，不覆盖')
        state = dict(identity, run=stamp().lower().replace('.', '-'), bundle=bundle, passed=[],
                     source_commit=command(['git', 'rev-parse', 'HEAD']).stdout.strip())
        save(path, state)
    current = api('-n', NS, 'get', 'networkpolicy', 'p06-isolation', '--ignore-not-found', '-o', 'json')
    if current: owned(json.loads(current), state)
    else: create(policy(state), state)
    return state


def verify(args, state):
    ensure(state['passed'] == STAGES[:6], '六组实验尚未全部通过')
    receipts = {}
    for stage in STAGES[:6]:
        value = json.loads((args.records / ('receipts/' + stage + '.json')).read_text())
        ensure(value.get('passed') is True and value.get('stage') == stage and value.get('run') == state['run'], '回执与批次不符：' + stage)
        receipts[stage] = value
    for kind in ['rc', 'rs']:
        row = receipts['replicas'][kind]
        ensure(row['adopted_uid'] in {p['metadata']['uid'] for p in row['before']} and row['deleted_uid'] not in {p['metadata']['uid'] for p in row['after']}, '补副本/接管 UID 证据异常')
        ensure(controller_ref(row['mismatch']) is None, '不匹配 Pod 被接管')
    for pod in receipts['scale']['terminated_pods']: term_receipt(pod)
    ensure(receipts['strategies']['RollingUpdate']['errors'] == 0 and receipts['strategies']['Recreate']['errors'] > 0, '更新策略流量证据不满足')
    ensure(receipts['strategies']['RollingUpdate']['blocked_surge']['failure']['deployment']['status']['availableReplicas'] == 2, 'surge 阻塞未保留旧副本')
    for fault in ['image', 'probe', 'business']:
        row = receipts['rollbacks'][fault]
        ensure(row['restored']['spec']['template'] == row['good_template'] and len(row['restored_responses']['stable']) == 6, '没有证明业务和完整模板已回滚')
    ensure(len(receipts['rollbacks']['business']['business_errors']) == 6 and receipts['split']['weighted_routing_verified'] is False, '业务失败或流量分离证据异常')
    current = check(); ensure(current['cluster_uid'] == state['cluster_uid'], '集群身份变化')
    # 每组已回收控制器、子对象和 Service；此时只允许留下本批 NetworkPolicy。
    ensure(all(o['kind'] == 'NetworkPolicy' for o in listing(KINDS, state)), '实验组仍遗留控制器或工作负载')
    finish(args, state, 'verify', current); print('CONTROLLER ACCEPTANCE PASS')


def render(args, bundle):
    state = {'run': 'render-only', 'bundle': bundle}; output = args.records
    output.mkdir(parents=True, exist_ok=True); resources = [('prepare', 'isolation', policy(state))]
    for stage in ['history', 'scale', 'strategies', 'rollbacks']:
        resources += [(stage, 'deployment', deploy('p06-main', stage, state, bundle['images']['v1']['image'])),
                      (stage, 'service', service('p06-entry', stage, state, 'main')),
                      (stage, 'client', observer('p06-client', stage, state, 'p06-entry'))]
    for kind, short in [('ReplicationController', 'rc'), ('ReplicaSet', 'rs')]:
        tmpl = template('replicas', state, bundle['images']['v1']['image'], 'compare-' + short); tmpl['metadata']['labels']['track'] = 'stable'
        select = {LABEL: state['run'], POOL: 'compare-' + short, 'track': 'stable'}
        if short == 'rs': select = {'matchLabels': {LABEL: state['run'], POOL: 'compare-rs'}, 'matchExpressions': [{'key': 'track', 'operator': 'In', 'values': ['stable']}]}
        obj = {'apiVersion': 'v1' if short == 'rc' else 'apps/v1', 'kind': kind,
               'metadata': {'name': 'p06-' + short, 'namespace': NS, 'labels': labels('replicas', state)}, 'spec': {'replicas': 2, 'selector': select, 'template': tmpl}}
        resources.append(('replicas', short, obj))
        for track in ['stable', 'other']:
            orphan = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': dict(copy.deepcopy(tmpl['metadata']), name='p06-' + short + '-' + track, namespace=NS), 'spec': copy.deepcopy(tmpl['spec'])}
            orphan['metadata']['labels']['track'] = track; resources.append(('replicas', short + '-' + track, orphan))
    for version in ['v2', 'bad']:
        resources.append(('rollbacks', version, deploy('p06-main', 'rollbacks', state, bundle['images'][version]['image'])))
    bad_probe = deploy('p06-main', 'rollbacks', state, bundle['images']['v2']['image'])
    bad_probe['spec']['template']['spec']['containers'][0]['env'][-1]['value'] = 'true'; resources.append(('rollbacks', 'failed-probe', bad_probe))
    invalid = deploy('p06-main', 'rollbacks', state, 'cnpl.local/phase01/controller-missing@sha256:' + '0'*64)
    resources.append(('rollbacks', 'missing-image', invalid))
    paused = deploy('p06-main', 'rollbacks', state, bundle['images']['v2']['image']); paused['spec']['paused'] = True
    resources.append(('rollbacks', 'paused', paused))
    resources.append(('strategies', 'recreate', deploy('p06-main', 'strategies', state, bundle['images']['v2']['image'], strategy='Recreate')))
    capacity = deploy('p06-capacity', 'scale', state, bundle['images']['v1']['image'], 0, 'capacity')
    capacity['spec']['template']['spec']['containers'][0]['resources']['requests']['cpu'] = '8'
    capacity['spec']['template']['spec']['containers'][0]['resources']['limits']['cpu'] = '8'
    resources.append(('scale', 'capacity-zero', capacity)); expanded = copy.deepcopy(capacity); expanded['spec']['replicas'] = 1
    resources.append(('scale', 'capacity-one', expanded))
    for pool, version, count in [('stable', 'v1', 2), ('canary', 'v2', 1)]:
        resources += [('split', pool, deploy('p06-' + pool, 'split', state, bundle['images'][version]['image'], count, pool)),
                      ('split', pool + '-service', service('p06-' + pool, 'split', state, pool)),
                      ('split', pool + '-client', observer('p06-' + pool + '-client', 'split', state, 'p06-' + pool))]
    for stage, variant, obj in resources:
        path = output / (stage + '-' + variant + '-' + obj['kind'].lower() + '.yaml')
        path.write_text(yaml.safe_dump(obj, sort_keys=False))
        api('create', '--dry-run=server', '-f', '-', payload=obj)
    print('CONTROLLER MANIFEST SERVER DRY-RUN PASS；' + str(len(resources)) + ' 份清单。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'render', 'prepare'] + STAGES)
    parser.add_argument('--records', type=Path, required=True); parser.add_argument('--bundle', type=Path)
    args = parser.parse_args(); args.records = args.records.expanduser().resolve(); args.records.mkdir(parents=True, exist_ok=True)
    state = None
    try:
        if args.action == 'check': save(args.records / ('preflight-' + stamp() + '.json'), check()); print('CONTROLLER PREFLIGHT PASS'); return
        if args.action in ['render', 'prepare']:
            ensure(args.bundle is not None, '需要 --bundle 物料索引'); bundle = json.loads(args.bundle.read_text())
            if args.action == 'render': render(args, bundle); return
            state = prepare(args, bundle); print('CONTROLLER PREPARE PASS'); return
        state = json.loads((args.records / 'state.json').read_text())
        ensure(previous.pod04.check()['cluster_uid'] == state['cluster_uid'], '当前集群 UID 不符')
        if args.action == 'cleanup':
            remove(args, state)
            def slices_gone():
                value = json.loads(api('-n', NS, 'get', 'endpointslices', '-l', 'kubernetes.io/service-name in (p06-entry,p06-stable,p06-canary)', '-o', 'json'))
                return value if not value['items'] else None
            remaining = {'items': listing(KINDS, state), 'endpointslices': wait_for('派生 EndpointSlice 回收', slices_gone, 30)}
            ensure(not remaining['items'], '清理后仍有对象'); save(args.records / 'cleanup-confirm.json', remaining)
            if state['passed'] == STAGES[:-1]: finish(args, state, 'cleanup', remaining)
            else: save(args.records / 'cleanup-without-acceptance.json', {'at': stamp(), 'passed': state['passed']})
            print('CONTROLLER LAB CLEANUP PASS'); return
        ensure(state['passed'] == STAGES[:STAGES.index(args.action)], '只能执行首个未通过组；使用 run.sh --resume')
        globals()[args.action](args, state)
    except (ValueError, KeyError, OSError, subprocess.SubprocessError, http.client.HTTPException) as exc:
        failure = {'stage': args.action, 'at': stamp(), 'error': str(exc)}
        if state:
            try: failure['snapshot'] = str(snapshot(args, state, 'failure-' + args.action))
            except Exception as diagnostic: failure['capture_error'] = str(diagnostic)
        save(args.records / ('failure-' + stamp() + '.json'), failure)
        print('CONTROLLER LAB FAIL: ' + str(exc)); raise SystemExit(1)


if __name__ == '__main__': main()
