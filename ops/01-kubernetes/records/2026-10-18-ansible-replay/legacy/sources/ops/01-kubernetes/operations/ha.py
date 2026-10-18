#!/usr/bin/env python3
"""用户手动在 ESXi 关/开一台控制平面；本入口准备、独立观测、验证和清理，不操作 VM 电源。"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

import yaml


HERE = Path(__file__).resolve().parent
KUBECTL = Path.home() / '.cnpl/bin/kubectl'
MAC = Path.home() / '.cnpl-secrets/access/lab-primary/mac.conf'
ADMIN = Path.home() / '.cnpl-secrets/kubeconfig-lab-primary'
CP = {'cp01': '192.168.9.101', 'cp02': '192.168.9.102', 'cp03': '192.168.9.103'}
WORKERS = {'worker01.k8s.internal.egon.top': '192.168.9.109', 'worker02.k8s.internal.egon.top': '192.168.9.110'}
LABEL = 'cnpl.io/ha-run'


def call(argv, payload=None, timeout=180):
    result = subprocess.run([str(item) for item in argv], input=json.dumps(payload) if payload else None,
                            capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError(Path(str(argv[0])).name + ' 失败：' + result.stderr[-1500:])
    return result.stdout.strip()


def client(role='readonly', server=None):
    argv = [KUBECTL, '--kubeconfig', ADMIN if role == 'platform' else MAC, '--request-timeout=15s']
    if role != 'platform': argv += ['--context', 'lab-primary-lab-ops' if role == 'operator' else 'lab-primary-readonly']
    if server: argv += ['--server=https://' + server + ':6443']
    return argv


def identity():
    config = yaml.safe_load(MAC.read_text())
    cluster = next(item['cluster'] for item in config['clusters'] if item['name'] == 'lab-primary')
    if cluster['server'] != 'https://api.k8s.internal.egon.top:6443':
        raise ValueError('受限配置指向其他集群')
    return {'cluster_uid': call(client() + ['get', 'namespace', 'kube-system', '-o', 'jsonpath={.metadata.uid}']),
            'ca_sha256': hashlib.sha256(base64.b64decode(cluster['certificate-authority-data'])).hexdigest()}


def validate_receipt(receipt, current):
    if receipt.get('schema_version') != 1 or receipt.get('status') != 'verified' or receipt.get('offline_restore_verified') is not True or receipt.get('off_cluster_restore_verified') is not True:
        raise ValueError('必须先完成完整备份、离线恢复和集群外取回验证；身份文件备份不满足条件')
    if not all(re.fullmatch('[a-f0-9]{64}', receipt.get(key, '')) for key in ['restic_snapshot', 'manifest_sha256']):
        raise ValueError('完整备份凭据缺少准确快照 ID 或索引校验值')
    if any(receipt.get(key) != value for key, value in current.items()):
        raise ValueError('备份凭据与当前集群身份不符')
    created = datetime.fromisoformat(receipt['created_utc'])
    if created.tzinfo is None: raise ValueError('备份时间缺少时区')
    age = (datetime.now(timezone.utc) - created).total_seconds()
    if not -300 <= age <= 86400:
        raise ValueError('备份凭据超过 24 小时或时间异常，请重新完整备份')


def etcd(target, cluster=True):
    survivor = next(name for name in CP if name != target)
    endpoints = 'https://127.0.0.1:2379' if cluster else ','.join('https://' + ip + ':2379' for name, ip in CP.items() if name != target)
    argv = client('platform', CP[survivor]) + ['-n', 'kube-system', 'exec', 'etcd-' + survivor + '.k8s.internal.egon.top', '--',
            'etcdctl', '--endpoints=' + endpoints, '--cacert=/etc/kubernetes/pki/etcd/ca.crt',
            '--cert=/etc/kubernetes/pki/etcd/healthcheck-client.crt', '--key=/etc/kubernetes/pki/etcd/healthcheck-client.key', 'endpoint', 'health']
    return call(argv + (['--cluster'] if cluster else []))


def holder(target):
    survivor = next(name for name in CP if name != target)
    return call(client('platform', CP[survivor]) + ['-n', 'kube-system', 'get', 'lease', 'plndr-cp-lock', '-o', 'jsonpath={.spec.holderIdentity}'])


def healthy(target):
    for ip in CP.values(): call(client('platform', ip) + ['get', '--raw=/readyz'])
    nodes = json.loads(call(client() + ['get', 'nodes', '-o', 'json']))['items']
    if len(nodes) != 10 or not all(any(item['type'] == 'Ready' and item['status'] == 'True' for item in node['status']['conditions']) for node in nodes):
        raise ValueError('必须恢复为十节点 Ready')
    workloads = json.loads(call(client('platform') + ['-n', 'kube-system', 'get', 'daemonsets,deployments', '-o', 'json']))['items']
    desired = {'cilium': 10, 'cilium-envoy': 10, 'kube-proxy': 10, 'cilium-operator': 2, 'coredns': 2}
    ready = {item['metadata']['name']: item['status'].get('numberReady', item['status'].get('readyReplicas', 0)) for item in workloads}
    if any(ready.get(name) != count for name, count in desired.items()):
        raise ValueError('Cilium/Envoy/kube-proxy/operator/CoreDNS 尚未全部恢复')
    dns = json.loads(call(client('platform') + ['-n', 'kube-system', 'get', 'pods', '-l', 'k8s-app=kube-dns', '-o', 'json']))['items']
    active = [pod for pod in dns if not pod['metadata'].get('deletionTimestamp')]
    if len(active) != 2 or len({pod['spec'].get('nodeName') for pod in active}) != 2 or not all(any(c['type'] == 'Ready' and c['status'] == 'True' for c in pod['status'].get('conditions', [])) for pod in active):
        raise ValueError('CoreDNS 两副本必须分散到不同节点，先执行 prepare-ha-dns.yml')
    return etcd(target)


def unavailable(target):
    for port in [22, 6443]:
        try:
            with socket.create_connection((CP[target], port), timeout=1): return False
        except OSError:
            pass
    return True


def save(records, state):
    temporary = records / 'state.json.tmp'
    temporary.write_text(json.dumps(state, indent=2))
    temporary.replace(records / 'state.json')


def prepare(args):
    current = identity()
    receipt = json.loads(args.receipt.read_text())
    validate_receipt(receipt, current)
    healthy(args.target)
    if holder(args.target) != args.target + '.k8s.internal.egon.top':
        raise ValueError('目标必须是当前 VIP 持有者，先查租约后指定 --target；不随意关闭其他节点')
    for kind in ['deployment', 'service']:
        if call(client('operator') + ['-n', 'lab-core', 'get', kind, 'cnpl-ha-check', '--ignore-not-found', '-o', 'name']):
            raise ValueError('已有同名实验资源，请用其原记录清理，不覆盖')
    args.records.mkdir(parents=True, exist_ok=False)
    identifier = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + secrets.token_hex(4)
    state = {'run': identifier, 'target': args.target, 'receipt': receipt, 'phase': 'preparing', 'fault_checks': False, 'app_failures': 0}
    state['implementation_sha256'] = {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in ['ha.py', 'ha-app.yaml']}
    save(args.records, state)
    for resource in yaml.safe_load_all((HERE / 'ha-app.yaml').read_text()):
        resource['metadata']['annotations'] = {LABEL: identifier}
        if resource['kind'] == 'Deployment':
            resource['spec']['template']['metadata']['labels'][LABEL] = identifier
        call(client('operator') + ['create', '-f', '-'], resource)
    call(client('operator') + ['-n', 'lab-core', 'rollout', 'status', 'deployment/cnpl-ha-check', '--timeout=120s'])
    state['phase'] = 'prepared';save(args.records, state)
    print('HA PREPARE PASS；两副本仅在 worker01/02，尚未操作控制平面。')


def tls_context(directory):
    config = yaml.safe_load(MAC.read_text())
    user = next(item['user'] for item in config['users'] if item['name'] == 'cnpl-mac-reader')
    ca = next(item['cluster']['certificate-authority-data'] for item in config['clusters'] if item['name'] == 'lab-primary')
    for name, value in [('ca.crt', ca), ('client.crt', user['client-certificate-data']), ('client.key', user['client-key-data'])]:
        path = directory / name;path.write_bytes(base64.b64decode(value));path.chmod(0o600)
    context = ssl.create_default_context(cafile=str(directory / 'ca.crt'))
    context.load_cert_chain(str(directory / 'client.crt'), str(directory / 'client.key'))
    return context


def probe(url, context=None, expected=None):
    try:
        # 不让 shell 中的代理环境把本实验的 VIP/本机流量转发到外部代理。
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))
        with opener.open(url, timeout=2) as response:
            body = response.read(256).decode().strip()
            matches = expected is None or (body in expected if isinstance(expected, set) else body == expected)
            return {'ok': response.status == 200 and matches, 'code': response.status}
    except urllib.error.HTTPError as error:
        return {'ok': False, 'code': error.code, 'error': type(error).__name__}
    except (OSError, urllib.error.URLError) as error:
        return {'ok': False, 'error': type(error).__name__}


def tunnel(pod, processes, records, service_ip=None):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0));port = listener.getsockname()[1]
    argv = ['ssh', '-N', '-T', '-S', 'none', '-i', str(Path.home() / '.ssh/cnpl_lab_ed25519'), '-o', 'IdentitiesOnly=yes',
            '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ExitOnForwardFailure=yes',
            '-L', f'127.0.0.1:{port}:{service_ip or pod["status"]["podIP"]}:8080', 'root@' + WORKERS[pod['spec']['nodeName']]]
    with (records / ('ssh-' + str(port) + '.txt')).open('w') as errors:
        process = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=errors)
    processes.append(process)
    for _ in range(30):
        if process.poll() is not None: raise ValueError('worker SSH 转发失败；检查原 SSH 信任/端口冲突')
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.1): return 'http://127.0.0.1:' + str(port) + '/'
        except OSError: time.sleep(0.1)
    raise ValueError('worker SSH 转发未就绪')


def fault_checks(state):
    target = state['target']
    if not unavailable(target): raise ValueError('目标未保持失联，不能证明在单控制平面故障期间完成操作')
    health = etcd(target, cluster=False)
    template = next(yaml.safe_load_all((HERE / 'ha-app.yaml').read_text()))['spec']['template']
    pod = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': 'cnpl-ha-scheduled-' + state['run'].lower(), 'namespace': 'lab-core', 'labels': {LABEL: state['run']}}, 'spec': template['spec']}
    pod['spec'].pop('affinity')
    pod['spec']['restartPolicy'] = 'Never'
    pod['spec']['containers'][0]['command'] = ['/bin/sh', '-ec']
    pod['spec']['containers'][0]['args'] = ['printf "scheduled-during-control-plane-failure\\n"']
    pod['spec']['containers'][0].pop('readinessProbe')
    name = pod['metadata']['name']
    call(client('operator') + ['create', '-f', '-'], pod)
    call(client('operator') + ['-n', 'lab-core', 'wait', 'pod/' + name, '--for=jsonpath={.status.phase}=Succeeded', '--timeout=90s'])
    actual = json.loads(call(client() + ['-n', 'lab-core', 'get', 'pod', name, '-o', 'json']))
    if actual['spec'].get('nodeName') not in WORKERS or not unavailable(target):
        raise ValueError('新 Pod 未在故障期间由 scheduler 分配到存活 worker')
    return {'survivor_etcd_health': health, 'scheduled_pod': name, 'scheduled_node': actual['spec']['nodeName']}


def watch(args, state):
    validate_receipt(state['receipt'], identity())
    healthy(state['target'])
    if holder(state['target']) != state['target'] + '.k8s.internal.egon.top': raise ValueError('VIP 持有者已变，请恢复/清理旧实验后重新 prepare')
    pods = json.loads(call(client() + ['-n', 'lab-core', 'get', 'pods', '-l', LABEL + '=' + state['run'], '-o', 'json']))['items']
    if len(pods) != 2 or {pod['spec']['nodeName'] for pod in pods} != set(WORKERS) or not all(any(c['type'] == 'Ready' and c['status'] == 'True' for c in pod['status'].get('conditions', [])) for pod in pods):
        raise ValueError('应用必须恰好每个 worker 一个 Ready 副本')
    processes = []
    state['phase'] = 'observing';save(args.records, state)
    try:
        with tempfile.TemporaryDirectory(prefix='cnpl-ha-tls-') as temporary, ThreadPoolExecutor(max_workers=8) as pool:
            context = tls_context(Path(temporary))
            urls = [tunnel(pod, processes, args.records) for pod in pods]
            service_ip = call(client() + ['-n', 'lab-core', 'get', 'service', 'cnpl-ha-check', '-o', 'jsonpath={.spec.clusterIP}'])
            service_url = tunnel(pods[0], processes, args.records, service_ip)
            deadline = time.monotonic() + args.seconds
            baseline = 0;scheduled = None;recovered = None;last_holder_check = 0
            baseline_deadline = time.monotonic() + 60
            print('先验证约 10 秒基线；等待出现关机提示再操作。', flush=True)
            with (args.records / 'timeline.jsonl').open('x') as timeline:
                while time.monotonic() < deadline:
                    started = time.monotonic()
                    futures = [pool.submit(probe, 'https://api.k8s.internal.egon.top:6443/readyz', context)]
                    futures += [pool.submit(probe, url, None, pod['spec']['nodeName']) for url, pod in zip(urls, pods)]
                    futures.append(pool.submit(probe, service_url, None, set(WORKERS)))
                    down = pool.submit(unavailable, state['target'])
                    others = {name: pool.submit(unavailable, name) for name in CP if name != state['target']}
                    results = [future.result() for future in futures]
                    sample = {'utc': datetime.now(timezone.utc).isoformat(), 'phase': 'baseline' if baseline < 5 else 'fault-window',
                              'api': results[0], 'apps': results[1:], 'target_unreachable': down.result(),
                              'other_unreachable': [name for name, future in others.items() if future.result()]}
                    timeline.write(json.dumps(sample) + '\n');timeline.flush()
                    if sample['other_unreachable']:
                        state['unexpected_unreachable'] = sample['other_unreachable']
                        raise ValueError('非目标控制平面 ' + ','.join(sample['other_unreachable']) + ' 失联；立即恢复已关闭节点，不继续停机')
                    if baseline == 5:
                        state['app_failures'] += sum(not item['ok'] for item in results[1:])
                        state['api_failed_samples'] = state.get('api_failed_samples', 0) + int(not results[0]['ok'])
                        state['total_samples'] = state.get('total_samples', 0) + 1
                    if baseline < 5:
                        if sample['target_unreachable']: raise ValueError('基线完成前目标已失联，停止实验，请先恢复')
                        if time.monotonic() > baseline_deadline: raise ValueError('60 秒内未建立连续健康基线，不应关机')
                        baseline = baseline + 1 if all(result['ok'] for result in results) else 0
                        if baseline == 5: print('BASELINE PASS：现在仅在 ESXi 控制台关闭 ' + state['target'] + '，不要停止第二台。', flush=True)
                    elif sample['target_unreachable']:
                        state.setdefault('first_unreachable_utc', sample['utc'])
                        if results[0]['ok']: state.setdefault('first_api_ok_while_target_down_utc', sample['utc'])
                        if time.monotonic() - last_holder_check > 5:
                            current = holder(state['target']);last_holder_check = time.monotonic()
                            if current != state['target'] + '.k8s.internal.egon.top' and current in {name + '.k8s.internal.egon.top' for name in CP}:
                                state['new_vip_holder'] = current
                                state.setdefault('vip_takeover_observed_utc', sample['utc'])
                        if results[0]['ok'] and state.get('new_vip_holder') and scheduled is None:
                            scheduled = pool.submit(fault_checks, state.copy())
                    if scheduled and scheduled.done() and not state['fault_checks']:
                        state['fault_result'] = scheduled.result();state['fault_checks'] = True
                        print('FAULT CHECKS PASS：VIP 已接管，两存活 etcd 健康，新 Pod 已调度完成；现在开启 ' + state['target'] + '。', flush=True)
                    if state['fault_checks'] and not sample['target_unreachable']:
                        if recovered is None: recovered = pool.submit(healthy, state['target'])
                        if recovered.done():
                            try: recovered.result()
                            except ValueError: recovered = None
                            else:
                                if state['app_failures']: raise ValueError('应用独立探测出现失败，记录保留，不判 HA 通过')
                                state['phase'] = 'complete';state['recovered_utc'] = sample['utc'];save(args.records, state)
                                print('HA ACCEPTANCE PASS：目标恢复，十节点 Ready、三 etcd 健康、应用独立探测无失败。', flush=True)
                                print('采样结果：' + json.dumps({key: state.get(key) for key in ['api_failed_samples', 'app_failures', 'first_unreachable_utc', 'first_api_ok_while_target_down_utc', 'vip_takeover_observed_utc', 'recovered_utc']}, ensure_ascii=False), flush=True)
                                return
                    save(args.records, state)
                    time.sleep(max(0, 2 - (time.monotonic() - started)))
            raise ValueError('观察超时；请在 ESXi 恢复目标 VM，然后运行 verify，保留现有记录')
    finally:
        for process in processes:
            process.terminate()
            try: process.wait(timeout=3)
            except subprocess.TimeoutExpired: process.kill();process.wait()
        if state['phase'] != 'complete': state['phase'] = 'recovery_required';save(args.records, state)


def cleanup(args, state):
    healthy(state['target'])
    for kind in ['deployment', 'service']:
        text = call(client('operator') + ['-n', 'lab-core', 'get', kind, 'cnpl-ha-check', '--ignore-not-found', '-o', 'json'])
        if text:
            if json.loads(text)['metadata'].get('annotations', {}).get(LABEL) != state['run']: raise ValueError('资源所有权不符，拒绝删除')
            call(client('operator') + ['-n', 'lab-core', 'delete', kind, 'cnpl-ha-check', '--wait=true', '--timeout=90s'])
    call(client('operator') + ['-n', 'lab-core', 'delete', 'pods', '-l', LABEL + '=' + state['run'], '--wait=true', '--timeout=90s'])
    state['cleaned'] = True;save(args.records, state)
    print('HA CLEANUP PASS；仅清理本批次资源，lab-core 及其他对象保留。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'watch', 'verify', 'cleanup'])
    parser.add_argument('--records', type=Path, required=True)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--target', choices=list(CP), default='cp01')
    parser.add_argument('--seconds', type=int, default=600)
    args = parser.parse_args()
    if not 120 <= args.seconds <= 900: raise ValueError('观察时长应为 120–900 秒')
    if args.mode == 'prepare':
        if args.receipt is None: raise ValueError('prepare 必须指定完整备份的 --receipt')
        prepare(args);return
    state = json.loads((args.records / 'state.json').read_text())
    if state.get('target') not in CP or not re.fullmatch(r'\d{8}T\d{6}Z-[a-f0-9]{8}', state.get('run', '')):
        raise ValueError('实验记录的目标/批次不合法，拒绝继续')
    if identity() != {key: state['receipt'][key] for key in ['cluster_uid', 'ca_sha256']}: raise ValueError('实验记录属于其他集群')
    if args.mode == 'watch':
        if state['phase'] != 'prepared': raise ValueError('watch 只接受新 prepared 记录；失败后先恢复并 verify/cleanup')
        lock = args.records / 'watch.lock'
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        try: watch(args, state)
        finally: lock.unlink()
    elif args.mode == 'verify':
        healthy(state['target']);state['recovery_verified_utc'] = datetime.now(timezone.utc).isoformat();save(args.records, state)
        print('RECOVERY HEALTH PASS；此结果不补判缺失或失败的 HA 实验。')
    else:
        cleanup(args, state)


if __name__ == '__main__':
    try:
        main()
    except yaml.YAMLError:
        raise SystemExit('HA FAIL: 配置格式错误，私有配置正文保持隐藏。')
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as error:
        raise SystemExit('HA FAIL: ' + str(error))
