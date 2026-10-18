#!/usr/bin/env python3
"""01.05 有界实验编排；check/render 不部署，run.sh 由用户执行。"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import secrets
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
spec = importlib.util.spec_from_file_location('pod04', HERE.parent / 'pods/lab.py')
pod04 = importlib.util.module_from_spec(spec); spec.loader.exec_module(pod04)
api, command, client = pod04.api, pod04.command, pod04.client
NS = 'lab-core'
LABEL = 'cnpl.io/probe-run'
PHASE = 'cnpl.io/probe-stage'
PART = {'app.kubernetes.io/part-of': 'cnpl-probe-lab'}
FINALIZER = 'cnpl.io/observe-probe-termination'
WORKERS = {'worker01.k8s.internal.egon.top': '192.168.9.109', 'worker02.k8s.internal.egon.top': '192.168.9.110'}
ETCD = 'harbor.k8s.internal.egon.top/bootstrap/etcd@sha256:aa2b41e3f99c9a337b82f687875a63c5119e6d39bc43fc76b6c40a96f55cf391'
STAGES = ['startup', 'liveness', 'readiness', 'termination', 'protocols', 'verify', 'cleanup']
KINDS = 'pods,services,networkpolicies'


def ensure(ok, message):
    if not ok: raise ValueError(message)


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    pod04.write_state(path, data)


def stamp(): return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ-') + secrets.token_hex(3)


def get(kind, name):
    return json.loads(api('-n', NS, 'get', kind, name, '-o', 'json'))


def owned(obj, state):
    ensure(obj['metadata'].get('labels', {}).get(LABEL) == state['run'], '对象不属于本批：' + obj['metadata']['name'])


def ssh(host, *args, timeout=30):
    return command(['ssh', '-i', Path.home() / '.ssh/cnpl_lab_ed25519', '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
                    '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=5', 'root@' + host, *args], timeout=timeout)


def check():
    identity = pod04.check()
    for host in WORKERS.values():
        # 查已有 etcd 镜像，不导入、不启动容器，不要求节点安装 OpenSSL。
        ssh(host, '/usr/bin/crictl inspecti ' + ETCD + ' >/dev/null')
    for verb, resource in [('create', 'pods'), ('delete', 'pods'), ('patch', 'pods'), ('create', 'services'),
                           ('create', 'networkpolicies'), ('get', 'endpointslices.discovery.k8s.io'), ('create', 'pods/exec')]:
        ensure(api('auth', 'can-i', verb, resource, '-n', NS) == 'yes', f'受限运维身份缺少 {verb} {resource}')
    return identity


def probe(path='/ready', threshold=1):
    return {'httpGet': {'path': path, 'port': 8080}, 'periodSeconds': 2, 'timeoutSeconds': 3, 'failureThreshold': threshold}


def pod(name, stage, image, worker=0, delay=0, broker=False, grace=25, hook=None):
    env = [{'name': 'POD_NAME', 'valueFrom': {'fieldRef': {'fieldPath': 'metadata.name'}}},
           {'name': 'POD_UID', 'valueFrom': {'fieldRef': {'fieldPath': 'metadata.uid'}}},
           {'name': 'START_SECONDS', 'value': str(delay)}]
    if broker: env.append({'name': 'BROKER_URL', 'value': 'http://p05-broker:9090'})
    container = {'name': 'app', 'image': image, 'imagePullPolicy': 'Never', 'command': ['/probe-lab', 'server'],
                 'env': env, 'terminationMessagePath': '/dev/termination-log', 'terminationMessagePolicy': 'File',
                 'securityContext': {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True, 'capabilities': {'drop': ['ALL']}},
                 'resources': {'requests': {'cpu': '20m', 'memory': '32Mi', 'ephemeral-storage': '1Mi'},
                               'limits': {'cpu': '500m', 'memory': '128Mi', 'ephemeral-storage': '32Mi'}},
                 'volumeMounts': [{'name': 'work', 'mountPath': '/work'}],
                 'startupProbe': dict(probe('/startup', 15)), 'livenessProbe': probe('/live', 3), 'readinessProbe': probe()}
    if hook is not None: container['lifecycle'] = {'preStop': {'exec': {'command': ['/probe-lab', 'prestop', str(hook)]}}}
    return {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': 'p05-' + name, 'namespace': NS,
            'labels': dict(PART, **{PHASE: stage, 'cnpl.io/probe-role': name})},
            'spec': {'restartPolicy': 'Always', 'automountServiceAccountToken': False,
                     'nodeSelector': {'kubernetes.io/hostname': list(WORKERS)[worker]}, 'terminationGracePeriodSeconds': grace,
                     'securityContext': {'runAsUser': 1000, 'runAsGroup': 1000, 'runAsNonRoot': True,
                                         'fsGroup': 1000, 'seccompProfile': {'type': 'RuntimeDefault'}},
                     'containers': [container], 'volumes': [{'name': 'work', 'emptyDir': {'sizeLimit': '32Mi'}}]}}


def service(name, stage, selector, port=8080):
    return {'apiVersion': 'v1', 'kind': 'Service', 'metadata': {'name': 'p05-' + name, 'namespace': NS, 'labels': dict(PART, **{PHASE: stage})},
            'spec': {'selector': selector, 'ports': [{'port': port, 'targetPort': port}]}}


def objects(image):
    policy = {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
              'metadata': {'name': 'p05-isolation', 'namespace': NS, 'labels': dict(PART, **{PHASE: 'prepare'})},
              'spec': {'podSelector': {'matchLabels': dict(PART)}, 'policyTypes': ['Ingress', 'Egress'],
                       'ingress': [{'from': [{'podSelector': {'matchLabels': dict(PART)}}]},
                                   {'from': [{'ipBlock': {'cidr': ip + '/32'}} for ip in WORKERS.values()],
                                    'ports': [{'port': port} for port in [8080, 9090, 2379, 2381]]}],
                       'egress': [{'to': [{'podSelector': {'matchLabels': dict(PART)}}]},
                                  {'to': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'kube-system'}},
                                           'podSelector': {'matchLabels': {'k8s-app': 'kube-dns'}}}],
                                   'ports': [{'protocol': 'UDP', 'port': 53}, {'protocol': 'TCP', 'port': 53}]}]}}
    result = [policy]
    for seconds in [6, 12, 20]:
        obj = pod('start-' + str(seconds), 'startup', image, delay=seconds)
        obj['spec']['containers'][0]['startupProbe']['failureThreshold'] = 30
        result.append(obj)
    over = pod('start-over', 'startup', image, delay=45)
    over['spec']['containers'][0]['startupProbe'].update(failureThreshold=4, terminationGracePeriodSeconds=1)
    result.append(over)
    dependency = pod('dependency', 'liveness', image, worker=1)
    # 故障依赖保留端口和就绪端点，只延迟业务响应，确保注入的是 HTTP 超时。
    dependency['spec']['containers'][0]['readinessProbe'] = probe('/live')
    result += [dependency, service('dependency-service', 'liveness', {'cnpl.io/probe-role': 'dependency'})]
    for stage, prefix in [('liveness', 'live'), ('readiness', 'route')]:
        for i, letter in enumerate(['a', 'b']):
            obj = pod(prefix + '-' + letter, stage, image, worker=i)
            obj['metadata']['labels']['cnpl.io/probe-pool'] = prefix
            if stage == 'liveness':
                obj['spec']['containers'][0]['env'].append({'name': 'DEPENDENCY_URL', 'value': 'http://p05-dependency-service:8080/dependency'})
            result.append(obj)
    result.append(service('route', 'readiness', {'cnpl.io/probe-pool': 'route'}))
    for prefix, stage in [('route', 'readiness'), ('term', 'termination')]:
        obj = pod(prefix + '-client', stage, image)
        c = obj['spec']['containers'][0]; c['command'] = ['/probe-lab', 'relay']
        c['env'] = [{'name': 'RELAY_TARGET', 'value': 'p05-' + prefix + ':8080'}]
        c.pop('startupProbe'); c.pop('livenessProbe')
        c['readinessProbe'] = {'tcpSocket': {'port': 8080}, 'periodSeconds': 2, 'timeoutSeconds': 3}
        result.append(obj)
    broker = pod('broker-pod', 'termination', image)
    broker['metadata']['labels']['cnpl.io/probe-role'] = 'broker'
    c = broker['spec']['containers'][0]; c['command'] = ['/probe-lab', 'broker']; c.pop('startupProbe'); c.pop('livenessProbe')
    c['readinessProbe'] = {'httpGet': {'path': '/status', 'port': 9090}, 'periodSeconds': 2, 'timeoutSeconds': 3}
    result += [broker, service('broker', 'termination', {'cnpl.io/probe-role': 'broker'}, 9090)]
    for name, worker, consume, grace, hook in [('term-main', 0, True, 25, 5), ('term-spare', 1, False, 25, 5),
                                               ('force', 0, True, 6, 4), ('recover', 1, True, 25, 0)]:
        obj = pod(name, 'termination', image, worker, broker=consume, grace=grace, hook=hook)
        if name != 'term-spare': obj['spec']['restartPolicy'] = 'Never'
        if name.startswith('term-'): obj['metadata']['labels']['cnpl.io/probe-pool'] = 'term'
        result.append(obj)
    result.append(service('term', 'termination', {'cnpl.io/probe-pool': 'term'}))
    for mode in ['http', 'tcp', 'exec']:
        obj = pod('protocol-' + mode, 'protocols', image)
        c = obj['spec']['containers'][0]; c.pop('livenessProbe')
        handler = {'http': {'httpGet': {'path': '/ready', 'port': 8080}}, 'tcp': {'tcpSocket': {'port': 8080}},
                   'exec': {'exec': {'command': ['/probe-lab', 'probe', 'http://127.0.0.1:8080/ready']}}}[mode]
        c['readinessProbe'] = dict(handler, periodSeconds=2, timeoutSeconds=3, failureThreshold=1)
        result.append(obj)
    for mode in ['good', 'wrong-service']:
        obj = pod('grpc-' + mode, 'protocols', ETCD)
        c = obj['spec']['containers'][0]; c['imagePullPolicy'] = 'IfNotPresent'
        c['command'] = ['/usr/local/bin/etcd', '--name=p05', '--data-dir=/work/etcd',
                        '--listen-client-urls=http://0.0.0.0:2379', '--advertise-client-urls=http://127.0.0.1:2379',
                        '--listen-peer-urls=http://127.0.0.1:2380', '--initial-advertise-peer-urls=http://127.0.0.1:2380',
                        '--initial-cluster=p05=http://127.0.0.1:2380', '--listen-metrics-urls=http://0.0.0.0:2381',
                        '--quota-backend-bytes=16777216', '--log-level=warn']
        # etcd 会预分配 64Mi WAL，并可能提前分配下一段；不能把数据卷设成 64Mi。
        c['resources']['limits'].update(memory='256Mi', **{'ephemeral-storage': '384Mi'})
        obj['spec']['volumes'][0]['emptyDir']['sizeLimit'] = '256Mi'
        c['startupProbe'] = {'httpGet': {'path': '/health', 'port': 2381}, 'periodSeconds': 2, 'timeoutSeconds': 3, 'failureThreshold': 30}
        c['livenessProbe'] = {'grpc': {'port': 2379}, 'periodSeconds': 2, 'timeoutSeconds': 3, 'failureThreshold': 5}
        c['readinessProbe'] = {'grpc': {'port': 2379}, 'periodSeconds': 2, 'timeoutSeconds': 3, 'failureThreshold': 1}
        if mode == 'wrong-service': c['readinessProbe']['grpc']['service'] = 'cnpl-intentionally-missing'
        result.append(obj)
    ensure(len({obj['metadata']['name'] for obj in result}) == len(result), '实验清单内部名称重复')
    return {obj['metadata']['name']: obj for obj in result}


def create(name, args, state):
    obj = objects(state['artifact']['image'])[name]
    obj['metadata']['labels'][LABEL] = state['run']
    # Service selector 也绑定批次；不能路由到其他批次的同名角色。
    if obj['kind'] == 'Service': obj['spec']['selector'][LABEL] = state['run']
    if obj['kind'] == 'NetworkPolicy':
        obj['spec']['podSelector']['matchLabels'][LABEL] = state['run']
        for direction in ['ingress', 'egress']:
            for rule in obj['spec'][direction]:
                for peer in rule.get('from' if direction == 'ingress' else 'to', []):
                    if peer.get('podSelector', {}).get('matchLabels') == PART:
                        peer['podSelector']['matchLabels'][LABEL] = state['run']
    api('create', '-f', '-', payload=obj)


def wait_for(description, callback, seconds=150):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = callback()
        if value: return value
        time.sleep(1)
    raise ValueError('等待超时：' + description + '；已保留现场，查看 failure 目录')


def ready(name):
    obj = get('pod', name)
    return obj if pod04.condition(obj, 'Ready', 'True') else None


def started(name):
    obj = get('pod', name); status = pod04.state_of(obj)
    return obj if status.get('state', {}).get('running') and obj['status'].get('podIP') else None


def restarts(obj): return pod04.state_of(obj).get('restartCount', 0)


def capture(args, state, suffix):
    directory = args.records / ('snapshots/' + stamp() + '-' + suffix); directory.mkdir(parents=True)
    found = json.loads(api('-n', NS, 'get', KINDS, '-l', LABEL + '=' + state['run'], '-o', 'json'))
    save(directory / 'objects.json', found)
    save(directory / 'endpointslices.json', json.loads(api('-n', NS, 'get', 'endpointslices', '-o', 'json')))
    for obj in found['items']:
        if obj['kind'] != 'Pod': continue
        name = obj['metadata']['name']; uid = obj['metadata']['uid']
        events = json.loads(api('-n', NS, 'get', 'events', '--field-selector=involvedObject.uid=' + uid, '-o', 'json'))
        save(directory / (name + '.events.json'), events)
        if obj['metadata'].get('deletionTimestamp'): continue
        mode = obj['spec']['containers'][0].get('command', [])
        if mode in [['/probe-lab', 'server'], ['/probe-lab', 'broker']] and pod04.state_of(obj).get('state', {}).get('running'):
            # 重建失败组前把卷内消息状态/应用状态取到 Mac，不能只留 API 元数据后删卷。
            url, suffix = ('http://127.0.0.1:9090/status', '.queue') if mode[-1] == 'broker' else ('http://127.0.0.1:8080/metrics', '.metrics')
            result = command(client() + ['-n', NS, 'exec', name, '--', '/probe-lab', 'probe', url], check=False, timeout=10)
            (directory / (name + suffix + ('.json' if result.returncode == 0 else '-error.txt'))).write_text(result.stdout + result.stderr)
        for previous in [False, True]:
            if previous and restarts(obj) == 0: continue
            output = command(client() + ['-n', NS, 'logs', name, '--tail=150'] + (['--previous'] if previous else []), check=False, timeout=25)
            (directory / (name + ('.previous' if previous else '') + '.txt')).write_text(output.stdout + output.stderr)
    return directory


def remove(args, state, stage=None):
    selector = LABEL + '=' + state['run'] + (',' + PHASE + '=' + stage if stage else '')
    items = json.loads(api('-n', NS, 'get', KINDS, '-l', selector, '-o', 'json'))['items']
    # 先验证整组，不能删到一半才发现外来 finalizer。
    for obj in items:
        owned(obj, state)
        ensure(set(obj['metadata'].get('finalizers', [])) <= {FINALIZER}, '存在外来 finalizer：' + obj['metadata']['name'])
    if items: capture(args, state, 'before-reset-' + (stage or 'all'))
    for obj in items:
        if FINALIZER in obj['metadata'].get('finalizers', []):
            api('-n', NS, 'patch', obj['kind'], obj['metadata']['name'], '--type=merge', '-p', json.dumps({'metadata': {'finalizers': []}}))
        api('-n', NS, 'delete', obj['kind'], obj['metadata']['name'], '--ignore-not-found', '--wait=true', '--timeout=65s', timeout=80)


def request(port, path, post=False, timeout=3):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=timeout)
    try:
        connection.request('POST' if post else 'GET', path)
        response = connection.getresponse(); data = response.read()
        ensure(response.status == 200, f'HTTP {response.status} {path}: ' + data.decode()[:300])
        return json.loads(data)
    finally: connection.close()


@contextmanager
def tunnel(obj, args, target=None, target_port=8080):
    with socket.socket() as sock: sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    host = WORKERS[obj['spec']['nodeName']]
    argv = ['ssh', '-N', '-T', '-S', 'none', '-i', str(Path.home() / '.ssh/cnpl_lab_ed25519'), '-o', 'IdentitiesOnly=yes',
            '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=5', '-o', 'ExitOnForwardFailure=yes',
            '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=2',
            '-L', f'127.0.0.1:{port}:{target or obj["status"]["podIP"]}:{target_port}', 'root@' + host]
    errors = (args.records / ('ssh-' + stamp() + '.txt')).open('w')
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=errors)
    try:
        def listening():
            ensure(process.poll() is None, 'SSH 转发失败，检查 ssh-*.txt')
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2): return True
            except OSError: return False
        wait_for('SSH 本地转发监听', listening, 10)
        yield port
    finally:
        process.terminate()
        try: process.wait(timeout=3)
        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=3)
        errors.close()


@contextmanager
def traffic(port, output):
    stop = threading.Event(); rows = []
    def loop():
        with output.open('w') as stream:
            while not stop.is_set():
                row = {'at': time.time()}
                try: row.update(ok=True, response=request(port, '/work?id=short', timeout=2))
                except (OSError, ValueError, http.client.HTTPException) as exc: row.update(ok=False, error=str(exc))
                rows.append(row); stream.write(json.dumps(row) + '\n'); stream.flush(); stop.wait(.2)
    thread = threading.Thread(target=loop, daemon=True); thread.start()
    try: yield rows
    finally:
        stop.set(); thread.join(timeout=4); ensure(not thread.is_alive(), '流量观测线程未退出')


def endpoints(service_name):
    uid = get('service', service_name)['metadata']['uid']
    value = json.loads(api('-n', NS, 'get', 'endpointslices', '-l', 'kubernetes.io/service-name=' + service_name, '-o', 'json'))
    value['items'] = [item for item in value['items'] if any(owner.get('uid') == uid for owner in item['metadata'].get('ownerReferences', []))]
    return value


def endpoint_map(value):
    return {ep['targetRef']['name']: ep.get('conditions', {}) for item in value['items'] for ep in item.get('endpoints', []) if ep.get('targetRef')}


def control(port, kind, on): return request(port, '/control?kind=' + kind + '&value=' + str(on).lower(), post=True)


def receipt(args, state, stage, data):
    save(args.records / ('receipts/' + stage + '.json'), dict(data, stage=stage, run=state['run'], passed=True, at=stamp()))
    state['passed'].append(stage); save(args.records / 'state.json', state)
    print(stage.upper() + ' PASS')


def startup(args, state):
    remove(args, state, 'startup'); measured = []
    for seconds in [6, 12, 20]:
        name = 'p05-start-' + str(seconds); create(name, args, state)
        obj = wait_for(name + ' 容器开始', lambda: started(name))
        samples = []
        with tunnel(obj, args) as port:
            end = time.monotonic() + 90
            while time.monotonic() < end:
                metrics = request(port, '/metrics'); actual = get('pod', name)
                samples.append({'metrics': metrics, 'ready': pod04.condition(actual, 'Ready', 'True'), 'restarts': restarts(actual)})
                if samples[-1]['ready']: break
                time.sleep(.5)
            ensure(samples[-1]['ready'], name + ' 未 Ready')
            probe_counts = request(port, '/metrics')['counts']
            ensure(all(probe_counts.get(path, 0) > 0 for path in ['/startup', '/ready']), '没有实际 kubelet startup/readiness 调用计数')
        before = [s for s in samples if s['metrics']['uptime'] < seconds]
        ensure(before, '未取得启动窗口样本；不能把缺测写成通过')
        ensure(all(s['metrics']['counts'].get('/live', 0) == 0 and s['metrics']['counts'].get('/ready', 0) == 0 for s in before), 'startup 成功前出现其他探针调用')
        ensure(all(s['restarts'] == 0 for s in samples), '容忍窗口内发生重启')
        measured.append({'configured_delay': seconds, 'observed_ready_uptime': samples[-1]['metrics']['uptime'], 'uid': obj['metadata']['uid'], 'samples': samples})
        api('-n', NS, 'delete', 'pod', name, '--wait=true', '--timeout=40s')
    name = 'p05-start-over'; create(name, args, state)
    failed = wait_for('超出 startup 窗口后发生重启', lambda: (lambda o: o if restarts(o) >= 1 else None)(get('pod', name)), 120)
    snap = capture(args, state, 'startup-over-window')
    events = json.loads((snap / (name + '.events.json')).read_text())
    ensure(any('startup probe failed' in e.get('message', '').lower() for e in events['items']), '没有 kubelet startup 失败事件')
    remove(args, state, 'startup')
    receipt(args, state, 'startup', {'measurements': measured, 'window_seconds': 60, 'over_window_pod': failed, 'failure_snapshot': str(snap)})


def pair(args, state, prefix):
    pods = []
    for letter in ['a', 'b']:
        name = 'p05-' + prefix + '-' + letter; create(name, args, state)
        pods.append(wait_for(name + ' Ready', lambda name=name: ready(name)))
    return pods


def liveness(args, state):
    remove(args, state, 'liveness')
    create('p05-dependency', args, state)
    # 独立的 Service 采用不同名字，清单字典不允许 Pod/Service 同键覆盖。
    create('p05-dependency-service', args, state)
    dependency = wait_for('依赖 fixture Ready', lambda: ready('p05-dependency'))
    a, b = pair(args, state, 'live'); samples = []
    with tunnel(a, args) as pa, tunnel(b, args) as pb, tunnel(dependency, args) as pd:
        baseline = [restarts(a), restarts(b)]
        control(pd, 'dependency', True)
        wait_for('两个副本依赖故障而未就绪', lambda: all(not pod04.condition(get('pod', x['metadata']['name']), 'Ready', 'True') for x in [a, b]))
        for _ in range(14):
            current = [get('pod', x['metadata']['name']) for x in [a, b]]
            metrics = [request(port, '/metrics') for port in [pa, pb]]
            samples.append({'at': time.time(), 'restarts': list(map(restarts, current)), 'metrics': metrics})
            ensure(samples[-1]['restarts'] == baseline and all(m['live'] for m in metrics), '依赖中断触发错误重启')
            time.sleep(1)
        ensure(all(any(m['dependency_failures'] > 0 and m['dependency_elapsed_ms'] >= 450 for s in samples for m in [s['metrics'][i]]) for i in [0, 1]), '未观测到两个副本的真实依赖请求超时')
        control(pd, 'dependency', False)
        for x in [a, b]: wait_for('恢复依赖后的 Ready', lambda x=x: ready(x['metadata']['name']))
        control(pa, 'hang', True)
        recovered = wait_for('本地 worker 心跳停止后由 liveness 重启恢复', lambda: (lambda o: o if restarts(o) > baseline[0] and pod04.condition(o, 'Ready', 'True') else None)(get('pod', a['metadata']['name'])), 120)
        # 重启后原 TCP 转发仍指同 Pod IP，应用内 hang 标志应已清空。
        ensure(request(pa, '/metrics')['live'], '重启后本地心跳未恢复')
    snap = capture(args, state, 'liveness')
    events = json.loads((snap / (a['metadata']['name'] + '.events.json')).read_text())
    ensure(any('liveness probe failed' in e.get('message', '').lower() for e in events['items']), '没有 kubelet liveness 失败事件')
    ensure(restarts(get('pod', b['metadata']['name'])) == baseline[1], '健康对照副本发生重启')
    remove(args, state, 'liveness')
    receipt(args, state, 'liveness', {'dependency_samples': samples, 'recovered': recovered, 'snapshot': str(snap)})


def readiness(args, state):
    remove(args, state, 'readiness'); a, b = pair(args, state, 'route'); create('p05-route', args, state)
    namea, nameb = a['metadata']['name'], b['metadata']['name']
    wait_for('两个 Ready EndpointSlice 端点', lambda: sum(c.get('ready') is True for c in endpoint_map(endpoints('p05-route')).values()) == 2)
    create('p05-route-client', args, state)
    observer = wait_for('Pod 内流量客户端就绪', lambda: ready('p05-route-client'))
    with tunnel(a, args) as pa, tunnel(observer, args) as service_port:
        existing = None
        try:
            for _ in range(80):
                conn = http.client.HTTPConnection('127.0.0.1', service_port, timeout=3)
                conn.request('GET', '/identity'); response = conn.getresponse(); body = json.loads(response.read())
                if body['pod'] == namea:
                    existing = conn; connection_id = response.getheader('X-Connection-ID'); local_port = conn.sock.getsockname()[1]; break
                conn.close()
            ensure(existing is not None, '未建立路由到 a 的持久连接')
            with traffic(service_port, args.records / ('readiness-traffic-' + stamp() + '.jsonl')) as rows:
                wait_for('短请求观测开始', lambda: len(rows) >= 4)
                control(pa, 'ready', False)
                observed = wait_for('a 从就绪端点摘除', lambda: (lambda s: s if endpoint_map(s).get(namea, {}).get('ready') is False else None)(endpoints('p05-route')))
                converged = time.time() + 3; time.sleep(3)
                # 不假定 EndpointSlice 更新等于数据平面瞬间收敛；检查收敛后连续新连接。
                wait_for('新连接只路由到 b', lambda: len([r for r in rows if r['at'] >= converged]) >= 15, 20)
                later = [r for r in rows if r['at'] >= converged]
                ensure(all(r.get('ok') and r['response']['pod'] == nameb for r in later), '收敛后新连接仍到未就绪端点或请求失败')
                existing.request('GET', '/identity'); response = existing.getresponse(); after = json.loads(response.read())
                ensure(after['pod'] == namea and response.getheader('X-Connection-ID') == connection_id and existing.sock.getsockname()[1] == local_port, '已有连接被关闭或悄悄重连，不能证明连接保留')
                ensure(restarts(get('pod', namea)) == restarts(a), 'readiness 变化触发重启')
                control(pa, 'ready', True); wait_for('a 恢复 Ready', lambda: ready(namea))
                wait_for('a 重回就绪端点', lambda: endpoint_map(endpoints('p05-route')).get(namea, {}).get('ready') is True)
            evidence = {'unready_endpoints': observed, 'new_connection_samples': later, 'existing_response': after, 'connection_id': connection_id, 'local_port': local_port}
        finally:
            if existing: existing.close()
    capture(args, state, 'readiness-restored'); remove(args, state, 'readiness'); receipt(args, state, 'readiness', evidence)


def retain_and_delete(obj, state):
    owned(obj, state); name = obj['metadata']['name']
    ensure(not obj['metadata'].get('finalizers'), '已有 finalizer，拒绝覆盖')
    api('-n', NS, 'patch', 'pod', name, '--type=merge', '-p', json.dumps({'metadata': {'finalizers': [FINALIZER]}}))
    api('-n', NS, 'delete', 'pod', name, '--wait=false')


def terminated(name):
    obj = get('pod', name)
    return obj if pod04.state_of(obj).get('state', {}).get('terminated') else None


def release(obj):
    api('-n', NS, 'patch', 'pod', obj['metadata']['name'], '--type=merge', '-p', json.dumps({'metadata': {'finalizers': []}}))
    api('-n', NS, 'wait', '--for=delete', 'pod/' + obj['metadata']['name'], '--timeout=40s')


def validate_term(obj, completed):
    status = pod04.state_of(obj).get('state', {}).get('terminated', {})
    ensure(obj['metadata'].get('deletionTimestamp') and obj['status']['phase'] == 'Succeeded' and status.get('exitCode') == 0 and status.get('reason') == 'Completed', '没有观察到删除后的 Completed/0')
    message = json.loads(status.get('message', '{}'))
    ensure(message.get('uid') == obj['metadata']['uid'] and message.get('signal') == 'TERM' and message.get('drained') is True, 'UID/TERM/排空回执不匹配')
    ensure(completed in message.get('completed', []), '消息未在终止前提交')
    before, term = [datetime.fromisoformat(message[k].replace('Z', '+00:00')) for k in ['prestop_at', 'term_at']]
    ensure((term - before).total_seconds() >= 4.8, '没有证明 PreStop 先执行并占用宽限期')
    finished = datetime.fromisoformat(message['finished_at'].replace('Z', '+00:00'))
    ensure(finished >= term, '终止回执完成时间早于信号')
    return message


def termination(args, state):
    remove(args, state, 'termination')
    create('p05-broker-pod', args, state); create('p05-broker', args, state)
    broker = wait_for('broker Ready', lambda: ready('p05-broker-pod'))
    for name in ['p05-term-main', 'p05-term-spare']: create(name, args, state)
    main = wait_for('term-main Ready', lambda: ready('p05-term-main')); wait_for('term-spare Ready', lambda: ready('p05-term-spare'))
    create('p05-term', args, state)
    wait_for('终止实验两个 Ready 端点', lambda: sum(c.get('ready') is True for c in endpoint_map(endpoints('p05-term')).values()) == 2)
    create('p05-term-client', args, state)
    observer = wait_for('Pod 内终止流量客户端就绪', lambda: ready('p05-term-client'))
    with tunnel(broker, args, target_port=9090) as queue_port, tunnel(main, args) as main_port, \
            tunnel(observer, args) as service_port, ThreadPoolExecutor(max_workers=1) as pool:
        capture(args, state, 'before-graceful-work')
        request(queue_port, '/submit?id=graceful&seconds=12&lease=30', True)
        wait_for('消费者已领取 graceful', lambda: request(main_port, '/metrics')['current_job'] == 'graceful')
        future = pool.submit(request, main_port, '/work?seconds=12&id=long-graceful', False, 20)
        wait_for('长请求进入处理', lambda: request(main_port, '/metrics')['active'] == 1)
        with traffic(service_port, args.records / ('termination-traffic-' + stamp() + '.jsonl')) as rows:
            wait_for('短请求已开始', lambda: len(rows) >= 4)
            retain_and_delete(main, state)
            terminating = wait_for('EndpointSlice 标记 terminating', lambda: (lambda s: s if endpoint_map(s).get('p05-term-main', {}).get('terminating') is True else None)(endpoints('p05-term')), 20)
            final = wait_for('优雅终止 Completed', lambda: terminated('p05-term-main'), 45)
            outcome = future.result(timeout=15)
            ensure(outcome.get('id') == 'long-graceful' and outcome.get('result') == 'completed' and outcome.get('uid') == main['metadata']['uid'], '长请求未完整完成或 UID 不符')
            message = validate_term(final, 'graceful')
            term_time = datetime.fromisoformat(message['term_at'].replace('Z', '+00:00'))
            ensure(datetime.fromisoformat(outcome['completed_at'].replace('Z', '+00:00')) > term_time, '长请求在 TERM 之前就结束，未证明实际排空')
            ensure(rows and all(r.get('ok') for r in rows), '优雅终止期间短请求失败')
            ensure(any(r['response']['pod'] == 'p05-term-spare' for r in rows), '未观察到备用副本承接短请求')
        save(args.records / 'graceful-final-pod.json', final); release(final)
        graceful_job = request(queue_port, '/status')['graceful']
        ensure(graceful_job['effects'] == 1, '优雅消费者效果次数不为 1')
        ensure(datetime.fromisoformat(graceful_job['committed_at'].replace('Z', '+00:00')) > term_time, '消息在 TERM 前已完成，未证明实际排空')
        create('p05-force', args, state); forced = wait_for('force Ready', lambda: ready('p05-force'))
        with tunnel(forced, args) as forced_port:
            capture(args, state, 'before-forced-work')
            request(queue_port, '/submit?id=compensate&seconds=20&lease=6', True)
            wait_for('force 已领取消息', lambda: request(forced_port, '/metrics')['current_job'] == 'compensate')
            lost = pool.submit(request, forced_port, '/work?seconds=30&id=long-force', False, 38)
            wait_for('强制场景长请求进入处理', lambda: request(forced_port, '/metrics')['active'] == 1)
            retain_and_delete(forced, state)
            killed = wait_for('6 秒总宽限期耗尽后 SIGKILL', lambda: terminated('p05-force'), 40)
            status = pod04.state_of(killed)['state']['terminated']
            ensure(killed['metadata'].get('deletionTimestamp') and status.get('exitCode') == 137 and status.get('reason') != 'OOMKilled', '没有观察到预期的宽限期超时强杀')
            try: lost.result(timeout=28)
            except (OSError, ValueError, http.client.HTTPException) as exc: forced_error = str(exc)
            else: raise ValueError('宽限期不足的长请求竟完整返回，不能证明失败场景')
        save(args.records / 'forced-final-pod.json', killed); release(killed)
        pending = request(queue_port, '/status')['compensate']; ensure(pending['effects'] == 0, '被强杀消息已提交，不能证明补偿')
        create('p05-recover', args, state); wait_for('补偿消费者 Ready', lambda: ready('p05-recover'))
        recovered = wait_for('租约超时后重新消费并提交', lambda: (lambda s: s if s.get('effects') == 1 else None)(request(queue_port, '/status')['compensate']), 60)
        ensure(recovered['attempts'] == 2 and recovered['owner'] != forced['metadata']['uid'], '没有由另一个消费者重新领取')
        # 相同业务 ID 和有效 token 重复提交，核对可观察副作用仍然只有一次。
        from urllib.parse import urlencode
        for _ in range(2): request(queue_port, '/commit?' + urlencode({'id': 'compensate', 'token': recovered['token']}), True)
        result = request(queue_port, '/status'); ensure(result['compensate']['effects'] == 1, '重复提交产生重复效果')
    capture(args, state, 'termination-completed'); remove(args, state, 'termination')
    receipt(args, state, 'termination', {'graceful_receipt': message, 'long_request': outcome, 'terminating_endpoints': terminating,
                                       'forced_pod': killed, 'forced_request_error': forced_error, 'pending_after_kill': pending, 'queue_final': result})


def protocols(args, state):
    remove(args, state, 'protocols'); observed = {}
    for mode in ['http', 'tcp', 'exec']:
        name = 'p05-protocol-' + mode; create(name, args, state); obj = wait_for(name + ' Ready', lambda name=name: ready(name))
        with tunnel(obj, args) as port:
            control(port, 'business', True)
            if mode != 'tcp': wait_for(mode + ' 业务失败后 NotReady', lambda: not ready(name))
            else:
                time.sleep(8); ensure(ready(name), 'TCP 不应识别应用层错误')
            metrics = request(port, '/metrics')
            ensure(metrics['live'] and not metrics['ready'] and restarts(get('pod', name)) == 0, '业务失败与本地进程活性未区分')
            if mode == 'exec':
                exec_result = command(client() + ['-n', NS, 'exec', name, '--', '/probe-lab', 'probe', 'http://127.0.0.1:8080/ready'], check=False)
                ensure(exec_result.returncode != 0 and 'HTTP 503' in exec_result.stderr, 'Exec 探针未返回明确失败码')
            observed[mode] = {'pod': get('pod', name), 'application_metrics': metrics}
            control(port, 'business', False); wait_for(mode + ' 恢复', lambda: ready(name))
    for mode in ['good', 'wrong-service']:
        name = 'p05-grpc-' + mode; create(name, args, state)
        if mode == 'good': obj = wait_for('原生 gRPC SERVING 后 Ready', lambda: ready(name))
        else:
            obj = wait_for('错误 gRPC service 的容器启动成功', lambda: (lambda o: o if pod04.state_of(o).get('started') is True else None)(get('pod', name)))
            def grpc_failed():
                events = json.loads(api('-n', NS, 'get', 'events', '--field-selector=involvedObject.uid=' + obj['metadata']['uid'], '-o', 'json'))
                return events if any(e.get('reason') == 'Unhealthy' and 'readiness probe failed' in e.get('message', '').lower()
                                     and any(word in e.get('message', '').lower() for word in ['notfound', 'unknown service']) for e in events['items']) else None
            failed_events = wait_for('原生 gRPC service 不存在的 kubelet 事件', grpc_failed)
            ensure(not ready(name), '错误 gRPC service 不应 Ready'); observed['grpc_wrong_service_events'] = failed_events
        health = command(client() + ['-n', NS, 'exec', name, '--', '/usr/local/bin/etcdctl', '--endpoints=http://127.0.0.1:2379', 'endpoint', 'health'])
        ensure('healthy' in health.stdout + health.stderr and restarts(get('pod', name)) == 0, 'etcd 本地业务不健康或发生重启')
        observed['grpc_' + mode] = {'pod': get('pod', name), 'endpoint_health': health.stdout + health.stderr}
    capture(args, state, 'protocols'); remove(args, state, 'protocols'); receipt(args, state, 'protocols', observed)


def prepare(args, artifact):
    identity = check(); state_path = args.records / 'state.json'
    if state_path.exists():
        state = json.loads(state_path.read_text())
        ensure(all(state.get(k) == v for k, v in identity.items()), '续跑集群身份发生变化')
        ensure(state['artifact'] == artifact, '续跑应用物料变化，拒绝将不同实现当作同一次实验')
        ensure(state['passed'] == STAGES[:len(state['passed'])], '检查点顺序异常')
        ensure('cleanup' not in state['passed'], '本批已完成清理，无需重跑')
        policy = api('-n', NS, 'get', 'networkpolicy', 'p05-isolation', '--ignore-not-found', '-o', 'json')
        if policy: owned(json.loads(policy), state)
        else: create('p05-isolation', args, state)
        return state
    existing = json.loads(api('-n', NS, 'get', KINDS, '-l', 'app.kubernetes.io/part-of=cnpl-probe-lab', '-o', 'json'))['items']
    ensure(not existing, '存在其他 01.05 批次；先用原证据目录继续或清理')
    ensure(artifact['schema_version'] == 1 and len(artifact['binary_sha256']) == 64, '物料格式错误')
    state = dict(identity, run=stamp().lower().replace('.', '-'), passed=[], artifact=artifact)
    save(state_path, state); create('p05-isolation', args, state)
    return state


def verify(args, state):
    ensure(state['passed'] == STAGES[:5], '五组实验未全部通过')
    current = check(); ensure(current['cluster_uid'] == state['cluster_uid'], '集群 UID 变化')
    for stage in STAGES[:5]:
        doc = json.loads((args.records / ('receipts/' + stage + '.json')).read_text())
        ensure(doc.get('passed') is True and doc.get('run') == state['run'] and doc.get('stage') == stage, '回执不匹配：' + stage)
    term = json.loads((args.records / 'receipts/termination.json').read_text())
    graceful = json.loads((args.records / 'graceful-final-pod.json').read_text())
    validate_term(graceful, 'graceful')
    ensure(term['queue_final']['compensate']['effects'] == 1 and term['queue_final']['compensate']['attempts'] == 2, '消息补偿证据不满足')
    receipt(args, state, 'verify', current); print('PROBE LIFECYCLE ACCEPTANCE PASS')


def render(args, artifact):
    args.records.mkdir(parents=True, exist_ok=True)
    for obj in objects(artifact['image']).values():
        (args.records / (obj['kind'].lower() + '-' + obj['metadata']['name'] + '.yaml')).write_text(yaml.safe_dump(obj, sort_keys=False))
        api('create', '--dry-run=server', '-f', '-', payload=obj)
    print('PROBE MANIFEST SERVER DRY-RUN PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'render', 'prepare', 'cleanup'] + STAGES[:-1])
    parser.add_argument('--records', type=Path, required=True)
    parser.add_argument('--artifact', type=Path)
    args = parser.parse_args(); args.records = args.records.expanduser().resolve(); args.records.mkdir(parents=True, exist_ok=True)
    state = None
    try:
        if args.action == 'check': save(args.records / ('preflight-' + stamp() + '.json'), check()); print('PROBE PREFLIGHT PASS'); return
        if args.action in ['render', 'prepare']:
            ensure(args.artifact is not None, 'render/prepare 需要 --artifact 物料索引')
            artifact = json.loads(args.artifact.read_text())
            if args.action == 'render': render(args, artifact); return
            state = prepare(args, artifact); print('PROBE PREPARE PASS'); return
        state = json.loads((args.records / 'state.json').read_text())
        ensure(pod04.check()['cluster_uid'] == state['cluster_uid'], '集群身份不符')
        if args.action == 'cleanup':
            remove(args, state)
            remaining = json.loads(api('-n', NS, 'get', KINDS, '-l', LABEL + '=' + state['run'], '-o', 'json'))
            ensure(not remaining['items'], '清理后仍有残留')
            def slices_gone():
                value = json.loads(api('-n', NS, 'get', 'endpointslices', '-l',
                                      'kubernetes.io/service-name in (p05-route,p05-term,p05-broker,p05-dependency-service)', '-o', 'json'))
                return value if not value['items'] else None
            remaining['endpointslices'] = wait_for('Service 派生 EndpointSlice 回收', slices_gone, 30)
            save(args.records / 'cleanup-confirm.json', remaining)
            if state['passed'] == STAGES[:-1]: receipt(args, state, 'cleanup', remaining)
            else: save(args.records / 'cleanup-without-acceptance.json', {'at': stamp(), 'passed': state['passed']})
            print('PROBE LAB CLEANUP PASS'); return
        ensure(state['passed'] == STAGES[:STAGES.index(args.action)], '只能执行首个未通过步骤；使用 run.sh --resume')
        globals()[args.action](args, state)
    except (ValueError, KeyError, OSError, subprocess.SubprocessError, http.client.HTTPException) as exc:
        failure = {'action': args.action, 'error': str(exc), 'at': stamp()}
        if state:
            try: failure['snapshot'] = str(capture(args, state, 'failure-' + args.action))
            except Exception as diagnostic: failure['capture_error'] = str(diagnostic)
        save(args.records / ('failure-' + stamp() + '.json'), failure)
        print('PROBE LAB FAIL: ' + str(exc)); raise SystemExit(1)


if __name__ == '__main__': main()
