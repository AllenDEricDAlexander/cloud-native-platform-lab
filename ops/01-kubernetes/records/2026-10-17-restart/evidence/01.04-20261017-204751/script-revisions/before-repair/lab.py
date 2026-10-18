#!/usr/bin/env python3
"""01.04 有界 Pod 实验；默认 check 只读。真实场景由用户逐组调用，失败保留证据和现场。"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import time

import yaml


HERE = Path(__file__).resolve().parent
KUBECTL = Path.home() / '.cnpl/bin/kubectl'
MAC = Path.home() / '.cnpl-secrets/access/lab-primary/mac.conf'
ADMIN = Path.home() / '.cnpl-secrets/kubeconfig-lab-primary'
NS = 'lab-core'
LABEL = 'cnpl.io/pod-run'
PART = {'app.kubernetes.io/part-of': 'cnpl-pod-lab'}
WORKER = 'worker01.k8s.internal.egon.top'
PRESSURE_WORKER = 'worker02.k8s.internal.egon.top'
EXPECTED = {name + '.k8s.internal.egon.top' for name in [
    'cp01', 'cp02', 'cp03', 'infra01', 'infra02', 'storage01', 'storage02', 'storage03', 'worker01', 'worker02']}
BUSYBOX = 'harbor.k8s.internal.egon.top/bootstrap/busybox@sha256:7d31f97bcfddb5ee2912c5e7479c23ab31a4e340e80d1c874a9c40b81eef340f'
COREDNS = 'harbor.k8s.internal.egon.top/bootstrap/coredns@sha256:fd5079792b93909db3adefa91e41c3995455013394f0197c7346786ae19079fc'
SECURITY = {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True, 'capabilities': {'drop': ['ALL']}}


def command(argv, payload=None, timeout=90, check=True):
    result = subprocess.run([str(x) for x in argv], input=json.dumps(payload) if payload is not None else None,
                            text=True, capture_output=True, timeout=timeout)
    if check and result.returncode:
        raise ValueError(f'{Path(str(argv[0])).name} rc={result.returncode}: {result.stderr[-2000:]}')
    return result


def client(platform=False):
    argv = [KUBECTL, '--kubeconfig', ADMIN if platform else MAC, '--request-timeout=15s']
    if not platform:
        argv += ['--context=lab-primary-lab-ops']
    return argv


def api(*argv, payload=None, platform=False, timeout=90):
    return command(client(platform) + list(argv), payload, timeout).stdout.strip()


def get(kind, name, platform=False):
    return json.loads(api('-n', NS, 'get', kind, name, '-o', 'json', platform=platform))


def check():
    for platform in [False, True]:
        server = api('config', 'view', '--minify', '-o', 'jsonpath={.clusters[0].cluster.server}', platform=platform)
        if server != 'https://api.k8s.internal.egon.top:6443':
            raise ValueError('kubeconfig 不是本实验集群')
    nodes = json.loads(api('get', 'nodes', '-o', 'json'))['items']
    if len(nodes) != 10 or {n['metadata']['name'] for n in nodes} != EXPECTED or any(not condition(n, 'Ready', 'True') for n in nodes):
        raise ValueError('需要十节点全部 Ready')
    for node in nodes:
        if node['metadata']['name'] in [WORKER, PRESSURE_WORKER]:
            if node['spec'].get('unschedulable') or node['spec'].get('taints'):
                raise ValueError('实验 worker 已被 cordon/taint，先检查现有维护任务')
            if node['status']['allocatable']['cpu'] != '7':
                raise ValueError('worker Allocatable 已变化，需要重新设计 8 核请求的 Pending 用例')
        if any(condition(node, key, 'True') for key in ['MemoryPressure', 'DiskPressure', 'PIDPressure']):
            raise ValueError('节点已有压力，拒绝叠加实验')
    namespace = get('namespace', NS)
    if namespace['metadata']['labels'].get('pod-security.kubernetes.io/enforce') != 'restricted' or namespace['metadata']['labels'].get('pod-security.kubernetes.io/enforce-version') != 'v1.36':
        raise ValueError('lab-core 必须保持 restricted')
    version = json.loads(api('version', '-o', 'json'))['serverVersion']['gitVersion']
    if version != 'v1.36.5':
        raise ValueError('需重新核对当前版本与 Sidecar/调试行为：' + version)
    return {'cluster_uid': get('namespace', 'kube-system')['metadata']['uid'], 'version': version}


def condition(obj, name, value):
    return any(c['type'] == name and c['status'] == value for c in obj.get('status', {}).get('conditions', []))


def container(name='app', script='sleep 600', image=BUSYBOX):
    return {'name': name, 'image': image, 'imagePullPolicy': 'IfNotPresent', 'command': ['/bin/sh', '-ec', script],
            'securityContext': copy.deepcopy(SECURITY),
            'resources': {'requests': {'cpu': '10m', 'memory': '16Mi', 'ephemeral-storage': '1Mi'},
                          'limits': {'cpu': '200m', 'memory': '64Mi', 'ephemeral-storage': '16Mi'}},
            'volumeMounts': [{'name': 'work', 'mountPath': '/work'}]}


def pod(name, script='sleep 600', restart='Never', worker=WORKER):
    return {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': 'p04-' + name, 'namespace': NS, 'labels': dict(PART)},
            'spec': {'restartPolicy': restart, 'automountServiceAccountToken': False,
                     'nodeSelector': {'kubernetes.io/hostname': worker}, 'terminationGracePeriodSeconds': 10,
                     'activeDeadlineSeconds': 900,
                     'securityContext': {'runAsUser': 1000, 'runAsGroup': 1000, 'runAsNonRoot': True,
                                         'fsGroup': 1000, 'seccompProfile': {'type': 'RuntimeDefault'}},
                     'containers': [container(script=script)], 'volumes': [{'name': 'work', 'emptyDir': {'sizeLimit': '128Mi'}}]}}


def objects():
    quota = {'apiVersion': 'v1', 'kind': 'ResourceQuota', 'metadata': {'name': 'p04-budget', 'namespace': NS},
             'spec': {'hard': {'pods': '24', 'requests.cpu': '10', 'limits.cpu': '12', 'requests.memory': '1Gi',
                               'limits.memory': '2Gi', 'requests.ephemeral-storage': '256Mi', 'limits.ephemeral-storage': '1Gi'}}}
    limits = {'apiVersion': 'v1', 'kind': 'LimitRange', 'metadata': {'name': 'p04-defaults', 'namespace': NS},
              'spec': {'limits': [{'type': 'Container', 'defaultRequest': {'cpu': '10m', 'memory': '16Mi', 'ephemeral-storage': '1Mi'},
                                   'default': {'cpu': '200m', 'memory': '64Mi', 'ephemeral-storage': '16Mi'},
                                   'max': {'cpu': '8', 'memory': '256Mi', 'ephemeral-storage': '128Mi'}}]}}
    policy = {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
              'metadata': {'name': 'p04-isolation', 'namespace': NS},
              'spec': {'podSelector': {'matchLabels': dict(PART)}, 'policyTypes': ['Ingress', 'Egress'],
                       'ingress': [{'from': [{'podSelector': {'matchLabels': dict(PART)}}]}],
                       'egress': [{'to': [{'podSelector': {'matchLabels': dict(PART)}}]},
                                  {'to': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'kube-system'}},
                                           'podSelector': {'matchLabels': {'k8s-app': 'kube-dns'}}}],
                                   'ports': [{'protocol': 'UDP', 'port': 53}, {'protocol': 'TCP', 'port': 53}]}]}}
    config = {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': 'p04-app', 'namespace': NS},
              'data': {'app.sh': (HERE / 'app.sh').read_text(),
                       'Corefile': '.:1053 {\n    errors\n    health :18080\n    ready :18181\n}\n'}}
    baseline = pod('baseline', 'exec /bin/sh /app/app.sh', restart='Always')
    baseline['spec'].pop('activeDeadlineSeconds')
    baseline['spec']['volumes'].append({'name': 'app', 'configMap': {'name': 'p04-app'}})
    app = baseline['spec']['containers'][0]
    app['volumeMounts'].append({'name': 'app', 'mountPath': '/app', 'readOnly': True})
    app['env'] = [{'name': key, 'valueFrom': {'fieldRef': {'fieldPath': field}}}
                  for key, field in [('POD_NAME', 'metadata.name'), ('NODE_NAME', 'spec.nodeName')]]
    app['env'].append({'name': 'START_DELAY', 'value': '2'})
    app['readinessProbe'] = {'httpGet': {'path': '/', 'port': 8080}, 'periodSeconds': 2}
    service = {'apiVersion': 'v1', 'kind': 'Service', 'metadata': {'name': 'p04-entry', 'namespace': NS},
               'spec': {'selector': {'app.kubernetes.io/name': 'p04-baseline'}, 'ports': [{'port': 8080, 'targetPort': 8080}]}}
    baseline['metadata']['labels']['app.kubernetes.io/name'] = 'p04-baseline'
    success = pod('success', 'echo application-exit=0; exit 0')
    failed = pod('failed', 'echo application-exit=7; exit 7')
    crash = pod('crash', 'if test -f /work/fixed; then echo fixed; exec sleep 600; fi; echo application-exit=7; sleep 2; exit 7', 'Always')
    bad = pod('bad-image')
    # Never 拉取策略使缺失镜像稳定表现为 ErrImageNeverPull；不访问外部仓库。
    bad['spec']['containers'][0].update(image='harbor.k8s.internal.egon.top/bootstrap/p04-intentionally-missing:invalid', imagePullPolicy='Never')
    pending = pod('pending')
    pending['spec']['containers'][0]['resources']['requests']['cpu'] = '8'
    pending['spec']['containers'][0]['resources']['limits']['cpu'] = '8'
    init = pod('init', 'test -f /work/data; echo main-read=$(cat /work/data); sleep 600', 'Always')
    init['spec']['initContainers'] = [container('prepare', 'if ! test -f /work/unblock; then echo init-blocked; sleep 2; exit 11; fi; echo init-ok > /work/data')]
    ordinary = pod('ordinary', 'echo main-start >> /work/trace; sleep 3; echo main-stop >> /work/trace')
    ordinary['spec']['containers'].append(container('side', 'echo side-start >> /work/trace; while ! test -f /work/stop; do sleep 1; done; echo side-stop >> /work/trace; cat /work/trace'))
    native = pod('native', 'test -f /work/data; test -f /work/side-ready; echo main-start >> /work/trace; sleep 3; echo main-stop >> /work/trace')
    native['spec']['initContainers'] = [container('prepare', 'echo init-ok > /work/data; echo init-done >> /work/trace')]
    side = container('side', 'trap \'echo side-stop >> /work/trace; cat /work/trace; exit 0\' TERM; echo side-start >> /work/trace; touch /work/side-ready; while :; do sleep 1; done')
    side['restartPolicy'] = 'Always'
    side['startupProbe'] = {'exec': {'command': ['/bin/sh', '-ec', 'test -f /work/side-ready']}, 'periodSeconds': 1, 'failureThreshold': 15}
    native['spec']['initContainers'].append(side)
    shellless = pod('shellless')
    shellless['spec']['volumes'].append({'name': 'app', 'configMap': {'name': 'p04-app'}})
    c = shellless['spec']['containers'][0]
    c.update(image=COREDNS, command=['/coredns', '-conf', '/app/Corefile'])
    # 官方二进制带 cap_net_bind_service 文件能力；沿用现有 CoreDNS 的 restricted 兼容配置。
    c['securityContext']['capabilities']['add'] = ['NET_BIND_SERVICE']
    c['volumeMounts'].append({'name': 'app', 'mountPath': '/app', 'readOnly': True})
    c['readinessProbe'] = {'httpGet': {'path': '/health', 'port': 18080}, 'periodSeconds': 2}
    oom = pod('oom', 'exec dd if=/dev/zero of=/work/fill bs=1048576 count=96', worker=PRESSURE_WORKER)
    oom['spec']['containers'][0]['resources']['limits']['memory'] = '32Mi'
    oom['spec']['volumes'][0]['emptyDir']['medium'] = 'Memory'
    pressure = pod('pressure', 'dd if=/dev/zero of=/work/fill bs=1048576 count=96; echo pressure-ready; exec sleep 600', worker=PRESSURE_WORKER)
    pressure['spec']['containers'][0]['resources']['limits']['memory'] = '160Mi'
    pressure['spec']['volumes'][0]['emptyDir']['medium'] = 'Memory'
    pressure['spec']['containers'][0]['readinessProbe'] = {'exec': {'command': ['/bin/sh', '-ec', 'test -f /work/fill && test "$(wc -c < /work/fill)" -eq 100663296']}, 'periodSeconds': 2}
    term = copy.deepcopy(baseline)
    term['metadata']['name'] = 'p04-term'
    term['metadata']['labels'].pop('app.kubernetes.io/name')
    term['spec']['restartPolicy'] = 'Never'
    # 最小普通非 root 容器也挂 emptyDir；init、native sidecar 的资源均参与有效 Pod 预算。
    result = [quota, limits, policy, config, baseline, service, success, failed, crash, bad, pending, init, ordinary, native, shellless, oom, pressure, term]
    for obj in result:
        obj['metadata'].setdefault('labels', {}).update(PART)
    return {x['metadata']['name']: x for x in result}


def owned(obj, state):
    if obj['metadata'].get('labels', {}).get(LABEL) != state['run']:
        raise ValueError('拒绝修改/删除其他批次对象：' + obj['metadata']['name'])


def write_state(path, data):
    # 恢复入口依赖完整状态；SSH/终端中断时不能留下半份 JSON。
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.cnpl-state-', delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(data, stream, indent=2)
        stream.write('\n')
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def create(obj, state, platform=False):
    item = copy.deepcopy(obj)
    item['metadata']['labels'][LABEL] = state['run']
    return api('create', '-f', '-', payload=item, platform=platform)


def wait(name, predicate, seconds=180):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        obj = get('pod', 'p04-' + name)
        if predicate(obj):
            return obj
        time.sleep(2)
    raise ValueError('等待超时 p04-' + name + '；用 describe / Events 检查，证据和对象保留')


def state_of(obj, container_name='app', initial=False):
    statuses = obj.get('status', {}).get('initContainerStatuses' if initial else 'containerStatuses', [])
    return next((x for x in statuses if x['name'] == container_name), {})


def execute(name, script, container_name='app', check_result=True):
    argv = client() + ['--request-timeout=0', '-n', NS, 'exec', 'p04-' + name, '-c', container_name, '--', '/bin/sh', '-ec', script]
    return command(argv, timeout=45, check=check_result)


def capture(name, args, suffix='observed'):
    obj = get('pod', 'p04-' + name)
    prefix = args.records / (name + '-' + suffix)
    prefix.with_suffix('.json').write_text(json.dumps(obj, indent=2) + '\n')
    prefix.with_suffix('.txt').write_text(api('-n', NS, 'describe', 'pod', 'p04-' + name))
    events = api('-n', NS, 'get', 'events', '--field-selector=involvedObject.uid=' + obj['metadata']['uid'], '-o', 'json')
    prefix.with_suffix('.events.json').write_text(events + '\n')
    summary = {'phase': obj['status'].get('phase'), 'reason': obj['status'].get('reason'),
               'containers': {key: obj['status'].get(key, []) for key in ['containerStatuses', 'initContainerStatuses', 'ephemeralContainerStatuses']}}
    print(name + ': ' + json.dumps(summary, ensure_ascii=False), flush=True)
    for c in obj['spec'].get('containers', []) + obj['spec'].get('initContainers', []) + obj['spec'].get('ephemeralContainers', []):
        for previous in [False, True]:
            result = command(client() + ['-n', NS, 'logs', obj['metadata']['name'], '-c', c['name'], '--tail=100'] + (['--previous'] if previous else []), check=False)
            prefix.with_name(prefix.name + '-' + c['name'] + ('-previous' if previous else '') + '.txt').write_text(result.stdout + result.stderr)
    return obj


def delete(name, state):
    obj = get('pod', 'p04-' + name)
    owned(obj, state)
    api('-n', NS, 'delete', 'pod', 'p04-' + name, '--wait=true', '--timeout=60s')


def mark(args, state, stage):
    state.setdefault('passed', [])
    if stage not in state['passed']:
        state['passed'].append(stage)
    write_state(args.records / 'state.json', state)
    print(stage.upper() + ' PASS', flush=True)


def require(state, *stages):
    if any(x not in state.get('passed', []) for x in stages):
        raise ValueError('需要先通过：' + ', '.join(stages))


def baseline(args):
    output = execute('baseline', 'wget -q -T 5 -O - http://p04-entry:8080/; wget -q -T 5 -O - "http://127.0.0.1:8080/cgi-bin/check?ready"').stdout
    if 'mode=ready' not in output:
        raise ValueError('基准 CGI 接口未正常启动')
    print(output)
    capture('baseline', args)


def prepare(args):
    current = check()
    if (args.records / 'state.json').exists():
        raise ValueError('本目录已有运行状态；使用新目录或先按 cleanup 回收旧实验')
    existing = json.loads(api('-n', NS, 'get', 'pods', '-o', 'json'))['items']
    if existing:
        raise ValueError('lab-core 尚有 Pod；先核实旧实验，拒绝叠加预算/故障')
    state = {**current, 'run': datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + secrets.token_hex(4), 'passed': [],
             'source_commit': command(['git', '-C', HERE, 'rev-parse', 'HEAD']).stdout.strip(),
             'implementation_sha256': {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                                        for name in ['lab.py', 'pressure.py', 'node-pressure.py', 'app.sh', 'run.sh']}}
    write_state(args.records / 'state.json', state)
    all_objects = objects()
    for name in ['p04-budget', 'p04-defaults', 'p04-isolation', 'p04-app', 'p04-baseline']:
        # create 而不是 apply：同名旧对象拒绝覆盖；失败时 state 供 cleanup 精确识别。
        obj = all_objects[name]
        create(obj, state, platform=obj['kind'] in ['ResourceQuota', 'LimitRange'])
    create(all_objects['p04-entry'], state)
    wait('baseline', lambda x: condition(x, 'Ready', 'True'))
    baseline(args)
    execute('baseline', 'rm /work/ready')
    try:
        result = execute('baseline', 'wget -T 3 -O - "http://127.0.0.1:8080/cgi-bin/check?ready"', check_result=False)
        (args.records / 'baseline-ready-false.txt').write_text(result.stdout + result.stderr)
        if result.returncode == 0 or '503' not in result.stderr:
            raise ValueError('ready 控制未返回 503')
    finally:
        execute('baseline', 'touch /work/ready')
    mark(args, state, 'prepare')


def states(args, state):
    require(state, 'prepare')
    data = objects()
    for name in ['success', 'failed', 'crash', 'bad-image', 'pending']:
        create(data['p04-' + name], state)
    wait('success', lambda x: x['status'].get('phase') == 'Succeeded')
    wait('failed', lambda x: state_of(x).get('state', {}).get('terminated', {}).get('exitCode') == 7)
    wait('crash', lambda x: state_of(x).get('state', {}).get('waiting', {}).get('reason') == 'CrashLoopBackOff')
    wait('bad-image', lambda x: state_of(x).get('state', {}).get('waiting', {}).get('reason') == 'ErrImageNeverPull')
    wait('pending', lambda x: any(c['type'] == 'PodScheduled' and c['status'] == 'False' and c.get('reason') == 'Unschedulable' for c in x['status'].get('conditions', [])))
    for name in ['success', 'failed', 'crash', 'bad-image', 'pending']:
        observed = capture(name, args)
        expected = {'success': 'Succeeded', 'failed': 'Failed', 'crash': 'Running', 'bad-image': 'Pending', 'pending': 'Pending'}[name]
        if observed['status'].get('phase') != expected:
            raise ValueError(name + ' 的 Pod phase 不符合预期：' + str(observed['status'].get('phase')))
    # 只变更允许更新的 image；请求/命令属于不可变 Pod spec，需保存后重建。
    api('-n', NS, 'patch', 'pod', 'p04-bad-image', '--type=strategic', '-p', json.dumps({'spec': {'containers': [{'name': 'app', 'image': BUSYBOX}]}}))
    wait('bad-image', lambda x: condition(x, 'Ready', 'True'))
    capture('bad-image', args, 'fixed')
    # crash Pod 有短暂运行窗口；重试 exec 直至能写入 emptyDir，重启后同卷文件仍在。
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline:
        if execute('crash', 'touch /work/fixed', check_result=False).returncode == 0:
            break
        time.sleep(1)
    else:
        raise ValueError('未抓到 crash 容器运行窗口，保留现场')
    wait('crash', lambda x: condition(x, 'Ready', 'True') and 'running' in state_of(x).get('state', {})
         and 'fixed' in api('-n', NS, 'logs', 'p04-crash', '-c', 'app'))
    capture('crash', args, 'fixed')
    delete('pending', state)
    fixed = data['p04-pending']
    fixed['spec']['containers'][0]['resources']['requests']['cpu'] = '10m'
    fixed['spec']['containers'][0]['resources']['limits']['cpu'] = '200m'
    create(fixed, state)
    wait('pending', lambda x: condition(x, 'Ready', 'True'))
    capture('pending', args, 'fixed')
    for name in ['success', 'failed', 'crash', 'bad-image', 'pending']:
        delete(name, state)
    mark(args, state, 'states')


def sidecars(args, state):
    require(state, 'states')
    data = objects()
    create(data['p04-init'], state)
    wait('init', lambda x: state_of(x, 'prepare', True).get('restartCount', 0) >= 1)
    blocked = capture('init', args, 'blocked')
    if 'running' in state_of(blocked).get('state', {}):
        raise ValueError('init 失败时主容器不应运行')
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline:
        if execute('init', 'touch /work/unblock', 'prepare', False).returncode == 0:
            break
        time.sleep(1)
    else:
        raise ValueError('未抓到 init 运行窗口')
    wait('init', lambda x: condition(x, 'Ready', 'True'))
    capture('init', args, 'fixed')
    for name in ['ordinary', 'native']:
        create(data['p04-' + name], state)
    wait('ordinary', lambda x: 'terminated' in state_of(x).get('state', {}) and 'running' in state_of(x, 'side').get('state', {}))
    ordinary = capture('ordinary', args, 'main-exited')
    if ordinary['status']['phase'] != 'Running':
        raise ValueError('普通多容器的 side 尚活，应仍为 Running')
    execute('ordinary', 'touch /work/stop', 'side')
    wait('ordinary', lambda x: x['status'].get('phase') == 'Succeeded')
    wait('native', lambda x: x['status'].get('phase') == 'Succeeded')
    trace = api('-n', NS, 'logs', 'p04-native', '-c', 'side')
    ordered = ['init-done', 'side-start', 'main-start', 'main-stop', 'side-stop']
    if any(word not in trace for word in ordered) or sorted(trace.index(x) for x in ordered) != [trace.index(x) for x in ordered]:
        raise ValueError('原生 sidecar 启停顺序证据不完整：' + trace)
    for name in ['ordinary', 'native']:
        capture(name, args, 'completed')
    for name in ['init', 'ordinary', 'native']:
        delete(name, state)
    mark(args, state, 'sidecars')


def debug(args, state):
    require(state, 'sidecars')
    create(objects()['p04-shellless'], state)
    wait('shellless', lambda x: condition(x, 'Ready', 'True'))
    missing = execute('shellless', 'true', check_result=False)
    (args.records / 'shellless-no-shell.txt').write_text(missing.stdout + missing.stderr)
    if missing.returncode == 0 or not any(x in missing.stderr for x in ['no such file', 'not found', 'executable file']):
        raise ValueError('未证实目标镜像缺少 shell：' + missing.stderr)
    # 临时容器不能设置 resources；小型固定命令在几十秒内退出，不能永久扩权给应用 SA。
    profile = args.records / 'debug-profile.json'
    profile.write_text(json.dumps({'securityContext': {**SECURITY, 'runAsNonRoot': True, 'runAsUser': 1000, 'runAsGroup': 1000,
                                                      'seccompProfile': {'type': 'RuntimeDefault'}}}, indent=2))
    script = '''set -eu
echo '=== shared network/process ==='
wget -q -T 3 -O - http://127.0.0.1:18080/health
ps
ps | grep '[c]oredns' >/dev/null
echo '=== DNS NXDOMAIN ==='
nslookup -timeout=2 -retry=1 -type=A kubernetes.default.svc.cluster.local 192.168.20.10
if nslookup -timeout=2 -retry=1 -type=A absent.p04.invalid. 192.168.20.10; then echo unexpected-dns-success; exit 1; fi
echo '=== connection refused ==='
if wget -q -T 2 -O - http://127.0.0.1:18082/; then echo unexpected-connect-success; exit 1; fi
echo '=== slow response: 1s timeout / 5s success ==='
if wget -q -T 1 -O - 'http://p04-entry:8080/cgi-bin/check?delay'; then echo unexpected-fast-response; exit 1; fi
wget -q -T 5 -O - 'http://p04-entry:8080/cgi-bin/check?delay'
echo DEBUG_COMPLETE
'''
    execute('baseline', 'echo 2 > /work/delay')
    try:
        api('-n', NS, 'debug', 'p04-shellless', '--image=' + BUSYBOX, '--container=diag', '--target=app',
            '--profile=restricted', '--custom=' + str(profile), '--attach=false', '--', '/bin/sh', '-ec', script)
        target = wait('shellless', lambda x: any(c['name'] == 'diag' and 'terminated' in c.get('state', {}) for c in x['status'].get('ephemeralContainerStatuses', [])))
        capture('shellless', args, 'debugged')
        status = next(c for c in target['status']['ephemeralContainerStatuses'] if c['name'] == 'diag')
        if status['state']['terminated']['exitCode'] != 0:
            raise ValueError('临时诊断失败，查看 shellless-debugged-diag.txt')
    finally:
        execute('baseline', 'echo 0 > /work/delay')
    permission = command(client(True) + ['auth', 'can-i', 'patch', 'pods/ephemeralcontainers', '-n', NS,
                                         '--as=system:serviceaccount:lab-core:default'], check=False)
    (args.records / 'application-sa-debug-permission.txt').write_text(permission.stdout + permission.stderr)
    if permission.returncode != 1 or permission.stdout.strip() != 'no':
        raise ValueError('普通应用 SA 意外具有调试权限')
    delete('shellless', state)
    mark(args, state, 'debug')


def memory(args, state):
    require(state, 'debug')
    create(objects()['p04-oom'], state)
    obj = wait('oom', lambda x: 'terminated' in state_of(x).get('state', {}))
    capture('oom', args)
    terminated = state_of(obj)['state']['terminated']
    if terminated.get('reason') != 'OOMKilled' or terminated.get('exitCode') != 137:
        raise ValueError('预期 cgroup OOMKilled/137，实际：' + json.dumps(terminated))
    delete('oom', state)
    mark(args, state, 'memory')


def termination(args, state):
    require(state, 'pressure')
    create(objects()['p04-term'], state)
    wait('term', lambda x: 'running' in state_of(x).get('state', {}))
    # 先验证服务已启动，再异步删除并持续保存 terminating 状态和 TERM 日志。
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if execute('term', 'test -f /work/ready', check_result=False).returncode == 0:
            break
        time.sleep(1)
    else:
        raise ValueError('term 应用未启动')
    owned(get('pod', 'p04-term'), state)
    # 临时 finalizer 只用于保留删除后的退出状态，观察完后删除；不强制终止容器。
    api('-n', NS, 'patch', 'pod', 'p04-term', '--type=merge', '-p', json.dumps({'metadata': {'finalizers': ['cnpl.io/observe-termination']}}))
    try:
        api('-n', NS, 'delete', 'pod', 'p04-term', '--wait=false')
        obj = wait('term', lambda x: 'terminated' in state_of(x).get('state', {}))
        capture('term', args, 'graceful')
        log = api('-n', NS, 'logs', 'p04-term', '-c', 'app')
        if state_of(obj)['state']['terminated']['exitCode'] != 0 or 'TERM complete' not in log:
            raise ValueError('未观察到 SIGTERM 后主动退出 0')
    finally:
        api('-n', NS, 'patch', 'pod', 'p04-term', '--type=merge', '-p', '{"metadata":{"finalizers":null}}')
    mark(args, state, 'termination')


def verify(args, state):
    require(state, 'prepare', 'states', 'sidecars', 'debug', 'memory', 'pressure', 'termination')
    current = check()
    if current['cluster_uid'] != state['cluster_uid']:
        raise ValueError('集群 UID 变化')
    baseline(args)
    mark(args, state, 'verify')
    print('POD LIFECYCLE ACCEPTANCE PASS')


def cleanup(args, state):
    check()
    # 失败实验也允许清理，但压力配置恢复必须先完成。
    pressure_state = args.records / 'pressure.json'
    if pressure_state.exists() and not json.loads(pressure_state.read_text()).get('restored'):
        raise ValueError('先运行 pressure.py restore 恢复 worker02 配置和 cordon 状态')
    for kind in ['pods', 'services', 'configmaps', 'networkpolicies', 'resourcequotas', 'limitranges']:
        items = json.loads(api('-n', NS, 'get', kind, '-l', LABEL + '=' + state['run'], '-o', 'json'))['items']
        for obj in items:
            owned(obj, state)
            if obj['kind'] == 'Pod' and obj['metadata'].get('finalizers') == ['cnpl.io/observe-termination']:
                api('-n', NS, 'patch', 'pod', obj['metadata']['name'], '--type=merge', '-p', '{"metadata":{"finalizers":null}}')
            api('-n', NS, 'delete', kind, obj['metadata']['name'], '--wait=true', '--timeout=60s',
                platform=kind in ['resourcequotas', 'limitranges'])
    mark(args, state, 'cleanup')
    print('POD LAB CLEANUP PASS；lab-core、RBAC 和其他对象保留')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', nargs='?', default='check', choices=['check', 'render', 'prepare', 'states', 'sidecars', 'debug', 'memory', 'termination', 'verify', 'cleanup'])
    parser.add_argument('--records', type=Path, required=True)
    args = parser.parse_args()
    args.records = args.records.expanduser().resolve()
    args.records.mkdir(parents=True, exist_ok=True)
    if args.mode == 'render':
        for name, obj in objects().items():
            (args.records / (name + '.yaml')).write_text(yaml.safe_dump(obj, sort_keys=False))
        print('RENDER PASS；仅写本地 YAML，不连接集群')
    elif args.mode == 'check':
        print(json.dumps(check()))
        print('POD LAB PREFLIGHT PASS；只读检查，没有创建负载')
    elif args.mode == 'prepare':
        prepare(args)
    else:
        state = json.loads((args.records / 'state.json').read_text())
        current_uid = get('namespace', 'kube-system')['metadata']['uid']
        if current_uid != state['cluster_uid'] or not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}', state['run']):
            raise ValueError('运行状态不属于当前集群或格式错误')
        globals()[args.mode](args, state)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit('POD LAB FAIL: ' + str(error))
