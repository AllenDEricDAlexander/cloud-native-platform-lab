#!/usr/bin/env python3
"""02.01 源码校验、只读取证与有界探测。集群对象变更由 Ansible 执行。"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import ipaddress
import json
import os
from pathlib import Path
import re
import select
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[5]
PHASE = ROOT / 'ops/02-networking'
BIN = Path.home() / '.cnpl/bin'
CONFIG = Path.home() / '.cnpl-secrets/kubeconfig-lab-primary'
K = [str(BIN / 'kubectl'), '--kubeconfig', str(CONFIG), '--request-timeout=20s']
NODE_NAMES = ['cp01', 'cp02', 'cp03', 'infra01', 'infra02', 'storage01', 'storage02', 'storage03', 'worker01', 'worker02']
NODES = {name + '.k8s.internal.egon.top': '192.168.9.' + str(i + 101) for i, name in enumerate(NODE_NAMES)}
LABEL = 'cnpl.io/net-run'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def call(args, payload=None, timeout=40):
    result = subprocess.run([str(a) for a in args], input=payload, capture_output=True, text=True, timeout=timeout)
    require(result.returncode == 0, Path(str(args[0])).name + ': ' + result.stderr[-1800:])
    return result.stdout


def get(kind, name=None, namespace=None):
    args = K + ['get', kind] + ([name] if name else []) + (['-n', namespace] if namespace else []) + ['-o', 'json']
    return json.loads(call(args))


def ready(obj):
    return any(c['type'] == 'Ready' and c['status'] == 'True' for c in obj.get('status', {}).get('conditions', []))


def relay_image_matches(image, lock):
    repository, digest = lock['source'].split('@')
    # Chart 保留 tag@digest；CRI 将其规范化成 repository@digest，两者必须锁定同一内容。
    return image in [lock['source'], repository + ':v' + lock['version'] + '@' + digest]


def sources():
    paths = [p for p in PHASE.rglob('*') if p.is_file() and 'records' not in p.relative_to(PHASE).parts and '__pycache__' not in p.parts and p.suffix != '.pyc']
    paths += [ROOT / name for name in [
        'ops/versions.lock.yaml', 'ops/00-preparation/ansible/ansible.cfg',
        'ops/00-preparation/ansible/inventories/lab/hosts.yml',
        'ops/00-preparation/ansible/inventories/lab/group_vars/all.yml',
        'ops/00-preparation/ansible/inventories/lab/group_vars/k8s_nodes.yml',
        'ops/00-preparation/pki/public/cnpl-lab-root-ca.crt']]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def preflight(records, identity_only=False):
    server = call(K + ['config', 'view', '--minify', '-o', 'jsonpath={.clusters[0].cluster.server}']).strip()
    require(server == 'https://api.k8s.internal.egon.top:6443', 'kubeconfig 指向其他集群')
    uid = get('namespace', 'kube-system')['metadata']['uid']
    handoff = json.loads((ROOT / 'ops/01-kubernetes/records/core-07-10/runs/10-20261018T132014Z/handoff.json').read_text())
    require(uid == handoff['cluster_uid'] and handoff['next_phase'] == '02' and handoff['temporary_namespace_absent'], '01 交接身份不符')
    for stage in ['07', '08', '09', '10']:
        receipt = json.loads((Path(handoff['core_progress']) / (stage + '.json')).read_text())
        require(receipt['passed'] and receipt['cleanup_passed'] and receipt['cluster_uid'] == uid, '01.' + stage + ' 交接缺失')
    prior = json.loads(Path(handoff['preceding_acceptance']).read_text())
    require(prior['all_26_checkpoints_passed'] and prior['owned_resources_remaining'] == 0 and prior['cluster_uid'] == uid, '01.03–06 交接缺失')
    path = records / 'context.json'
    context = json.loads(path.read_text()) if path.exists() else {'cluster_uid': uid, 'run': datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]}
    require(context['cluster_uid'] == uid, '同批次不能切换集群')
    for namespace in ['lab-net', 'lab-net-peer']:
        existing = call(K + ['get', 'namespace', namespace, '--ignore-not-found', '-o', 'json']).strip()
        if existing:
            ns = json.loads(existing)
            require(ns['metadata'].get('labels', {}).get(LABEL) == context['run'], '命名空间属于其他运行：' + namespace)
            saved_namespace = records / 'state' / (namespace + '.json')
            if saved_namespace.exists():
                require(json.loads(saved_namespace.read_text())['uid'] == ns['metadata']['uid'], '命名空间 UID 已改变：' + namespace)
            require(identity_only or not ns['metadata'].get('deletionTimestamp'), '命名空间仍在删除')
    if not identity_only:
        nodes = get('nodes')['items']
        require(len(nodes) == 10 and {n['metadata']['name'] for n in nodes} == NODES.keys(), '需要 .101–.110 原十台 VM')
        for n in nodes:
            name = n['metadata']['name']
            require(ready(n) and not n['spec'].get('unschedulable'), name + ' 未就绪或已封锁调度')
            require(all(c['status'] == 'False' for c in n['status']['conditions'] if c['type'].endswith('Pressure')), name + ' 有资源压力')
            require(any(a['type'] == 'InternalIP' and a['address'] == NODES[name] for a in n['status']['addresses']), name + ' IP 漂移')
            require(n['status']['nodeInfo']['kubeletVersion'] == 'v1.36.5', name + ' 版本漂移')
            allowed = {'node-role.kubernetes.io/control-plane', 'node-role.kubernetes.io/storage'}
            require(all(t['key'] in allowed and t['effect'] == 'NoSchedule' for t in n['spec'].get('taints', [])), name + ' 有未预期污点')
        require(call(K + ['get', '--raw=/readyz']).strip() == 'ok', 'API 未就绪')
        for name in ['cilium', 'cilium-envoy', 'kube-proxy']:
            ds = get('ds', name, 'kube-system')['status']
            require(ds.get('desiredNumberScheduled') == 10 and ds.get('numberReady') == 10 and ds.get('updatedNumberScheduled') == 10, name + ' 未完全就绪')
        for name in ['coredns', 'cilium-operator']:
            dep = get('deploy', name, 'kube-system')
            require(dep['status'].get('availableReplicas') == dep['spec']['replicas'] == 2, name + ' 未完全就绪')
        config = get('cm', 'cilium-config', 'kube-system')['data']
        require(config['routing-mode'] == 'tunnel' and config['tunnel-protocol'] == 'vxlan' and config['kube-proxy-replacement'] == 'false', 'CNI 基准漂移')
        if config.get('enable-hubble') == 'true':
            relay = get('deploy', 'hubble-relay', 'kube-system')
            relay_lock = yaml.safe_load((ROOT / 'ops/versions.lock.yaml').read_text())['components']['hubble_relay']
            require(relay_image_matches(relay['spec']['template']['spec']['containers'][0]['image'], relay_lock), '已有 Relay 不是本轮锁定镜像')
            require(config.get('hubble-disable-tls') == 'false', '已有 Hubble 未启用 mTLS')
            require(get('service', 'hubble-relay', 'kube-system')['spec']['type'] == 'ClusterIP', '已有 Relay 入口类型不同')
            policy = get('ciliumnetworkpolicy', 'cnpl-hubble-relay-access', 'kube-system')
            require(policy['metadata'].get('labels', {}).get('cnpl.io/component') == 'phase02-hubble', '已有 Relay 访问规则不属于本组件')
        system = get('pods', namespace='kube-system')['items']
        require(all(p['status'].get('phase') == 'Succeeded' or ready(p) for p in system if not p['metadata'].get('deletionTimestamp')), '系统 Pod 不健康')
        context['nodes'] = [{'node': n['metadata']['name'], 'ip': NODES[n['metadata']['name']]} for n in nodes]
        context['network'] = {k: config.get(k) for k in ['routing-mode', 'tunnel-protocol', 'kube-proxy-replacement', 'enable-hubble']}
    save(path, context)
    return context


def build(output):
    go = Path.home() / '.cnpl/toolchains/go1.27.2/go/bin/go'
    require(call([go, 'version']).startswith('go version go1.27.2 '), 'Go 版本不符')
    folder = PHASE / 'examples/network-baseline'
    env = dict(os.environ, GOOS='linux', GOARCH='amd64', CGO_ENABLED='0', GOTOOLCHAIN='local', GOPROXY='off', GOSUMDB='off')
    binary = output.parent / 'net-lab'
    subprocess.run([str(go), 'build', '-trimpath', '-buildvcs=false', '-ldflags=-s -w', '-o', str(binary), '.'], cwd=folder, env=env, check=True, timeout=120)
    source = hashlib.sha256((folder / 'main.go').read_bytes() + (folder / 'go.mod').read_bytes()).hexdigest()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        info = tarfile.TarInfo('net-lab')
        data = binary.read_bytes()
        info.size, info.mode = len(data), 0o555
        archive.addfile(info, io.BytesIO(data))
    raw = buffer.getvalue()
    layer = gzip.compress(raw, mtime=0)
    sha = lambda b: 'sha256:' + hashlib.sha256(b).hexdigest()
    encode = lambda v: json.dumps(v, separators=(',', ':'), sort_keys=True).encode()
    desc = lambda kind, b: {'mediaType': 'application/vnd.oci.' + kind, 'size': len(b), 'digest': sha(b)}
    config = encode({'architecture': 'amd64', 'os': 'linux', 'config': {'User': '1000:1000', 'Entrypoint': ['/net-lab'], 'Labels': {'cnpl.io/source-sha256': source}}, 'rootfs': {'type': 'layers', 'diff_ids': [sha(raw)]}})
    manifest = encode({'schemaVersion': 2, 'mediaType': 'application/vnd.oci.image.manifest.v1+json', 'config': desc('image.config.v1+json', config), 'layers': [desc('image.layer.v1.tar+gzip', layer)]})
    image = 'cnpl.local/phase02/net-lab@' + sha(manifest)
    tag = 'cnpl.local/phase02/net-lab:sha256-' + source
    descriptor = desc('image.manifest.v1+json', manifest)
    descriptor.update({'platform': {'os': 'linux', 'architecture': 'amd64'}, 'annotations': {'io.containerd.image.name': tag, 'org.opencontainers.image.ref.name': tag}})
    contents = {'oci-layout': b'{"imageLayoutVersion":"1.0.0"}', 'index.json': encode({'schemaVersion': 2, 'manifests': [descriptor]})}
    contents.update({'blobs/sha256/' + sha(b)[7:]: b for b in [config, layer, manifest]})
    archive_path = output.parent / 'net-lab.oci.tar'
    with tarfile.open(archive_path, 'w', format=tarfile.USTAR_FORMAT) as archive:
        for name, data in contents.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o644
            archive.addfile(info, io.BytesIO(data))
    require(binary.read_bytes()[:4] == b'\x7fELF', '产物不是 Linux ELF')
    result = {'image': image, 'import_tag': tag, 'archive': str(archive_path), 'archive_sha256': hashlib.sha256(archive_path.read_bytes()).hexdigest(), 'source_sha256': source, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'go_version': 'go1.27.2'}
    binary.unlink()
    save(output, result)
    return result


def relay(output):
    lock = yaml.safe_load((ROOT / 'ops/versions.lock.yaml').read_text())['components']['hubble_relay']
    layout = Path(lock['local_source'])
    index = json.loads((layout / 'index.json').read_text())
    require(len(index['manifests']) == 1 and index['manifests'][0]['digest'] == lock['platform_manifest_digest'], 'Relay OCI 平台摘要不符')
    descriptor = index['manifests'][0]
    manifest = json.loads((layout / 'blobs/sha256' / descriptor['digest'][7:]).read_text())
    config = json.loads((layout / 'blobs/sha256' / manifest['config']['digest'][7:]).read_text())
    require(config['os'] == 'linux' and config['architecture'] == 'amd64', 'Relay 平台不符')
    contents = {'oci-layout': (layout / 'oci-layout').read_bytes()}
    for blob in [descriptor, manifest['config'], *manifest['layers']]:
        name = 'blobs/sha256/' + blob['digest'][7:]
        data = (layout / name).read_bytes()
        require(hashlib.sha256(data).hexdigest() == blob['digest'][7:] and len(data) == blob['size'], 'Relay blob 损坏')
        contents[name] = data
    image = lock['source'].split('@')[0] + '@' + descriptor['digest']
    descriptor['annotations'] = {'io.containerd.image.name': image, 'org.opencontainers.image.ref.name': image}
    descriptor['platform'] = {'os': 'linux', 'architecture': 'amd64'}
    contents['index.json'] = json.dumps(index).encode()
    archive_path = output.parent / 'relay.oci.tar'
    with tarfile.open(archive_path, 'w', format=tarfile.USTAR_FORMAT) as archive:
        for name, data in contents.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o644
            archive.addfile(info, io.BytesIO(data))
    return {'image': image, 'import_tag': image, 'archive': str(archive_path), 'archive_sha256': hashlib.sha256(archive_path.read_bytes()).hexdigest()}


def pods():
    main = get('pods', namespace='lab-net')['items']
    peer = get('pods', namespace='lab-net-peer')['items']
    require(len(main) == 10 and {p['spec']['nodeName'] for p in main} == NODES.keys() and len(peer) == 1, '测试 Pod 分布不符')
    for p in main + peer:
        require(ready(p) and not p['spec'].get('hostNetwork') and not p['metadata'].get('deletionTimestamp'), '测试 Pod 未就绪')
        require(ipaddress.ip_address(p['status']['podIP']) in ipaddress.ip_network('10.244.0.0/16'), 'Pod CIDR 漂移')
    require(len({p['status']['podIP'] for p in main + peer}) == 11, '重复 Pod IP')
    require(peer[0]['spec']['nodeName'] == 'worker02.k8s.internal.egon.top', 'peer VM 不符')
    return sorted(main, key=lambda p: p['spec']['nodeName']), peer[0]


def execute(pod, probes, output):
    args = K[:-1] + ['--request-timeout=0', '-n', pod['metadata']['namespace'], 'exec', '-i', pod['metadata']['name'], '-c', 'net', '--', '/net-lab', 'matrix']
    result = subprocess.run(args, input=json.dumps(probes), capture_output=True, text=True, timeout=240)
    output.write_text(result.stdout)
    require(result.returncode == 0, pod['metadata']['name'] + ': ' + result.stderr[-1500:] + '；详见 ' + str(output))
    values = [json.loads(line) for line in result.stdout.splitlines()]
    require(len(values) == sum(p['count'] for p in probes) and all(v['passed'] for v in values), '探测数量或结果不符')
    return values


def probe(name, protocol, target, expected='', size=0, count=5, timeout=3000, ca=''):
    return {'name': name, 'protocol': protocol, 'target': target, 'expected': expected, 'size': size, 'count': count, 'timeout_ms': timeout, 'ca': ca}


def matrix(output):
    main, peer = pods()
    service = get('service', 'net-echo', 'lab-net')['spec']['clusterIP']
    all_results = []
    for source in main:
        probes = []
        for target in main:
            ip, node = target['status']['podIP'], target['spec']['nodeName']
            probes += [probe('pod-http', 'http', 'http://' + ip + ':8080/', node, 131072), probe('pod-udp', 'udp', ip + ':9090', node, 1200)]
        probes += [probe('udp-fragmentation', 'udp', peer['status']['podIP'] + ':9090', peer['spec']['nodeName'], size) for size in [1400, 4096]]
        probes += [probe('service-ip', 'http', 'http://' + service + ':8080/'), probe('service-dns', 'http', 'http://net-echo.lab-net.svc.cluster.local:8080/'),
                   probe('cross-namespace', 'http', 'http://net-echo.lab-net-peer.svc.cluster.local:8080/', peer['spec']['nodeName'])]
        for name, expected in [('net-echo.lab-net.svc.cluster.local', service), ('kubernetes.default.svc.cluster.local', '192.168.20.1'), ('harbor.k8s.internal.egon.top', '192.168.9.12')]:
            probes += [probe('dns', proto, name, expected, count=1) for proto in ['dns-udp', 'dns-tcp']]
        info = json.loads(call(K + ['-n', 'lab-net', 'exec', source['metadata']['name'], '--', '/net-lab', 'info']))
        save(output.parent / (source['spec']['nodeName'] + '-interfaces.json'), info)
        all_results += execute(source, probes, output.parent / (source['spec']['nodeName'] + '-requests.jsonl'))
        # 只捕获 SYN 的地址元数据；不读取 HTTPS 载荷或凭据。每个源 VM 单独关联五次 TLS 请求。
        node = source['spec']['nodeName']
        ip = NODES[node]
        ssh = ['ssh', '-i', str(Path.home() / '.ssh/cnpl_lab_ed25519'), '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', 'root@' + ip,
               "timeout 20 tcpdump -nn -l -i ens33 -s 96 -c 5 'dst host 192.168.9.12 and dst port 443 and tcp[tcpflags] & tcp-syn != 0'"]
        capture = subprocess.Popen(ssh, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        lines = []
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if select.select([capture.stdout], [], [], 1)[0]:
                    line = os.read(capture.stdout.fileno(), 8192).decode()
                    lines.append(line)
                    if 'listening on' in ''.join(lines):
                        break
                    require(line or capture.poll() is None, 'tcpdump 未成功启动')
            require('listening on' in ''.join(lines), 'tcpdump 没有给出就绪回执')
            all_results += execute(source, [probe('registry-tls', 'http', 'https://harbor.k8s.internal.egon.top/v2/', ca='/ca/ca.crt')], output.parent / (node + '-registry.jsonl'))
            tail, _ = capture.communicate(timeout=25)
            lines.append(tail)
            raw = ''.join(lines)
            (output.parent / (node + '-snat.txt')).write_text(raw)
            addresses = re.findall(r'IP (\d+\.\d+\.\d+\.\d+)\.\d+ > 192\.168\.9\.12\.443:', raw)
            require(capture.returncode == 0 and len(addresses) == 5 and set(addresses) == {ip}, node + ' 出口源地址与预期节点 SNAT 不符；查看 snat.txt')
        finally:
            capture_path = output.parent / (node + '-snat.txt')
            if not capture_path.exists():
                if capture.poll() is None:
                    capture.terminate()
                tail, _ = capture.communicate(timeout=5)
                capture_path.write_text(''.join(lines) + tail)
    # 从 peer 回到主空间，补上跨命名空间的反向路径。
    all_results += execute(peer, [probe('peer-return', 'http', 'http://net-echo.lab-net.svc.cluster.local:8080/')], output.parent / 'peer-return.jsonl')
    save(output.parent / 'pods.json', {'main': main, 'peer': peer, 'service_ip': service})
    groups = {}
    for r in all_results:
        key = r['protocol'] + '/' + r['name']
        groups.setdefault(key, []).append(r['elapsed_ms'])
    return {'passed': True, 'sources': 11, 'main_vm_pairs': 100, 'requests': len(all_results), 'sample_loss': 0,
            'latency_ms': {key: {'samples': len(values), 'min': min(values), 'max': max(values), 'mean': sum(values) / len(values)} for key, values in groups.items()},
            'mtu_note': '1200/1400/4096-byte UDP and 128-KiB HTTP; fragmentation success is not a no-fragment PMTU result'}


def mac(output):
    main, _ = pods()
    target = next(p for p in main if p['spec']['nodeName'].startswith('worker01.'))
    process = subprocess.Popen(K + ['-n', 'lab-net', 'port-forward', '--address=127.0.0.1', 'pod/' + target['metadata']['name'], '0:8080'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    try:
        deadline = time.monotonic() + 15
        port = None
        forward_output = ''
        while time.monotonic() < deadline:
            if select.select([process.stdout], [], [], 1)[0]:
                line = os.read(process.stdout.fileno(), 8192).decode()
                forward_output += line
                match = re.search(r'Forwarding from 127\.0\.0\.1:(\d+)', forward_output)
                if match:
                    port = int(match[1])
                    break
                require(line or process.poll() is None, 'port-forward 提前结束')
        require(port, 'port-forward 没有就绪')
        # 绕过管理端代理；请求完成立即关闭临时通道。
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:' + str(port) + '/', timeout=5) as reply:
            body = json.load(reply)
            require(reply.status == 200 and body['pod'] == target['metadata']['name'], '管理端业务响应不符')
        return {'passed': True, 'route': 'Mac -> API VIP -> kubelet -> Pod port-forward', 'http_status': 200, 'echo': body, 'lan_business_vip_tested': False}
    finally:
        process.terminate()
        process.communicate(timeout=5)


def cleanup_plan(records):
    context = json.loads((records / 'context.json').read_text())
    names = []
    for name in ['lab-net', 'lab-net-peer']:
        raw = call(K + ['get', 'namespace', name, '--ignore-not-found', '-o', 'json']).strip()
        if not raw:
            continue
        ns = json.loads(raw)
        require(ns['metadata'].get('labels', {}).get(LABEL) == context['run'], '拒绝清理外来 Namespace')
        saved = records / 'state' / (name + '.json')
        if saved.exists():
            require(json.loads(saved.read_text())['uid'] == ns['metadata']['uid'], 'Namespace UID 已改变')
        objects = get('pods,ds,deploy,sts,rs,rc,svc,cm,networkpolicy,ciliumnetworkpolicy,role,rolebinding,secret,job,cronjob,sa,pvc,resourcequota,limitrange,ingress,hpa', namespace=name)['items']
        for obj in objects:
            if (obj['kind'], obj['metadata']['name']) in [('ConfigMap', 'kube-root-ca.crt'), ('ServiceAccount', 'default')]:
                continue
            require(obj['metadata'].get('labels', {}).get(LABEL) == context['run'], '空间有外来资源，停止清理：' + obj['kind'] + '/' + obj['metadata']['name'])
        names.append(name)
    return {'namespaces': names, 'run': context['run']}


def rollback_policy(records):
    original = records / 'state/hubble.json'
    if original.exists() and not json.loads(original.read_text())['owned']:
        return {'remove': False}
    path = records / 'state/hubble-access.json'
    if not path.exists():
        return {'remove': False}
    saved = json.loads(path.read_text())
    raw = call(K + ['get', 'ciliumnetworkpolicy', 'cnpl-hubble-relay-access', '-n', 'kube-system', '--ignore-not-found', '-o', 'json']).strip()
    if not raw or not saved['created']:
        return {'remove': False}
    policy = json.loads(raw)
    require(policy['metadata']['uid'] == saved['uid'] and policy['metadata'].get('labels', {}).get('cnpl.io/component') == 'phase02-hubble', 'Relay 策略归属已改变')
    return {'remove': True}


def scenario(case, output):
    main, peer = pods()
    source = next(p for p in main if p['spec']['nodeName'].startswith('worker01.'))
    target = 'http://' + peer['status']['podIP'] + ':8080/' + ('delay' if case == 'timeout' else '')
    expected = 'timeout' if case in ['timeout', 'deny'] else peer['spec']['nodeName']
    observation = output.with_name(output.stem + '-' + uuid.uuid4().hex[:8] + output.suffix)
    values = execute(source, [probe(case, 'http', target, expected, count=1, timeout=1000 if expected == 'timeout' else 3000)], observation)
    return {'passed': True, 'source': source['metadata']['name'], 'destination': peer['status']['podIP'], 'request': values[0]}


def flows(case, since, output):
    main, peer = pods()
    source = next(p for p in main if p['spec']['nodeName'].startswith('worker01.'))
    agents = get('pods', namespace='kube-system')['items']
    agent = next(p for p in agents if p['metadata'].get('labels', {}).get('k8s-app') == 'cilium' and p['spec']['nodeName'] == source['spec']['nodeName'])
    relay = get('service', 'hubble-relay', 'kube-system')['spec']['clusterIP']
    prefix = K[:-1] + ['--request-timeout=0', '-n', 'kube-system', 'exec', agent['metadata']['name'], '-c', 'cilium-agent', '--', 'hubble', '--server', relay + ':80']
    status = call(prefix + ['status'], timeout=25)
    require(re.search(r'Connected Nodes:\s*10/10', status), 'Relay 未连接全部十台 VM：' + status)
    verdict = 'DROPPED' if case == 'deny' else 'FORWARDED'
    for _ in range(10):
        raw = call(prefix + ['observe', '--since', since, '--last', '200', '--from-pod', 'lab-net/' + source['metadata']['name'], '--to-ip', peer['status']['podIP'], '--to-port', '8080', '--protocol', 'tcp', '-o', 'json'], timeout=25)
        output.write_text(raw)
        envelopes = [json.loads(line) for line in raw.splitlines()]
        require(not any(e.get('lost_events') or e.get('lostEvents') for e in envelopes), 'Hubble 丢事件，不能据空白判定')
        observed = [e['flow'] for e in envelopes if 'flow' in e and e['flow'].get('verdict') == verdict]
        if case == 'deny':
            observed = [f for f in observed if f.get('drop_reason_desc', f.get('dropReasonDesc')) == 'POLICY_DENIED']
        if observed:
            return {'passed': True, 'case': case, 'verdict': verdict, 'matching_flows': len(observed), 'relay_status': status}
        time.sleep(2)
    raise ValueError('没有本次 ' + case + ' 对应流量；保留记录，不视为无流量')


def validate(manifest, output):
    documents = [d for d in yaml.safe_load_all(manifest.read_text()) if d]
    for doc in documents:
        # 尚未创建 lab-net；在既有 restricted 空间执行同一对象的服务端准入，绝不落地。
        copy = json.loads(json.dumps(doc))
        if copy['kind'] != 'Namespace':
            copy['metadata']['namespace'] = 'lab-core'
        call(K + ['apply', '--dry-run=server', '--validate=strict', '-f', '-'], json.dumps(copy))
    return {'passed': True, 'documents': len(documents), 'admission_namespace': 'lab-core', 'persisted': False}


def chart():
    lock = yaml.safe_load((ROOT / 'ops/versions.lock.yaml').read_text())['components']
    helm = [BIN / 'helm', '--kubeconfig', CONFIG]
    values = call(helm + ['get', 'values', 'cilium', '-n', 'kube-system', '-o', 'json'])
    # 渲染包含 CA 私钥的 Secret；仅在内存解析，绝不将 manifest 或 values 写入公开记录。
    with tempfile.TemporaryDirectory(prefix='cnpl-hubble-render-') as folder:
        private_values = Path(folder) / 'values.json'
        private_values.write_text(values)
        private_values.chmod(0o600)
        raw = call(helm + ['template', 'cilium', lock['cilium']['chart']['local_source'], '-n', 'kube-system', '--kube-version', '1.36.5', '-f', private_values, '-f', PHASE / 'networking/hubble-values.yaml'])
    documents = {(d['kind'], d['metadata']['name']): d for d in yaml.safe_load_all(raw) if d}
    config = documents['ConfigMap', 'cilium-config']['data']
    require(config['routing-mode'] == 'tunnel' and config['tunnel-protocol'] == 'vxlan' and config['kube-proxy-replacement'] == 'false', '渲染改变了主网络模式')
    require(config['enable-hubble'] == 'true' and config['hubble-disable-tls'] == 'false', '渲染未开启 Hubble mTLS')
    require(str(config['hubble-event-buffer-capacity']) == '4095' and str(config['hubble-event-queue-size']) == '8192', 'Hubble 缓冲预算不符')
    relay = documents['Deployment', 'hubble-relay']['spec']['template']['spec']
    image = relay['containers'][0]['image']
    require(relay_image_matches(image, lock['hubble_relay']) and relay['containers'][0]['imagePullPolicy'] == 'Never', 'Relay 渲染与离线物料不符')
    require(relay['nodeSelector']['kubernetes.io/hostname'] == 'worker01.k8s.internal.egon.top', 'Relay VM 约束不符')
    require(documents['Service', 'hubble-relay']['spec']['type'] == 'ClusterIP', 'Relay 暴露类型不符')
    return {'passed': True, 'relay_image': image, 'cri_image': lock['hubble_relay']['source'], 'routing_mode': 'tunnel/vxlan', 'kube_proxy_replacement': False, 'hubble_mtls': True, 'secret_manifests_saved': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['preflight', 'identity', 'build', 'relay', 'chart', 'matrix', 'mac', 'timeout', 'deny', 'recovery', 'flows', 'validate', 'source', 'cleanup-plan', 'rollback-policy'])
    parser.add_argument('--records', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--case', choices=['timeout', 'deny', 'recovery'])
    parser.add_argument('--since')
    args = parser.parse_args()
    if args.mode in ['preflight', 'identity']:
        value = preflight(args.records, args.mode == 'identity')
    elif args.mode == 'build':
        value = build(args.output)
    elif args.mode == 'relay':
        value = relay(args.output)
    elif args.mode == 'chart':
        value = chart()
    elif args.mode == 'matrix':
        value = matrix(args.output)
    elif args.mode == 'mac':
        value = mac(args.output)
    elif args.mode == 'cleanup-plan':
        value = cleanup_plan(args.records)
    elif args.mode == 'rollback-policy':
        value = rollback_policy(args.records)
    elif args.mode in ['timeout', 'deny', 'recovery']:
        value = scenario(args.mode, args.output.with_suffix('.jsonl'))
    elif args.mode == 'flows':
        require(args.case and args.since, 'flows 需要 case/since')
        value = flows(args.case, args.since, args.output.with_suffix('.jsonl'))
    elif args.mode == 'validate':
        value = validate(args.manifest, args.output)
    else:
        value = {'source_sha256': sources()}
    save(args.output, value)
    print(json.dumps(value, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, StopIteration, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
