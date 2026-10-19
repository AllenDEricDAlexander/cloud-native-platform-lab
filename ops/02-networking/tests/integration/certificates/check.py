#!/usr/bin/env python3
"""02.05 的身份、准入、续期、TLS 故障与清理验收；不读取集群 Secret 私钥。"""
import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import re
import socket
import ssl
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
gw = module('tls_gateway', HERE.parent / 'gateway/check.py')
mat = module('tls_materials', HERE / 'materials.py')
pki = module('tls_pki', HERE / 'pki.py')
ROOT, PHASE, K = gw.ROOT, gw.PHASE, gw.K
require, call, save, get = gw.require, gw.call, gw.save, gw.get
LABEL, COMPONENT = 'cnpl.io/tls-run', 'phase02-certificates'
REGISTRY = PHASE / 'records/components/certificates.json'
CM_NS, NS, PLATFORM = 'cert-manager', 'lab-tls', 'cnpl-gateway'
CERT_KINDS = {'Certificate': 'certificates.cert-manager.io', 'Issuer': 'issuers.cert-manager.io', 'CertificateRequest': 'certificaterequests.cert-manager.io'}
POLICIES = ['cnpl-tls-' + n for n in ['certificates', 'requests', 'issuers', 'public-routes', 'kube-csr']]


def registry(context):
    value = json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {'cluster_uid': context['cluster_uid'], 'objects': {}}
    require(value['cluster_uid'] == context['cluster_uid'], '签发器登记属于其他集群')
    return value


def object_key(obj):
    return obj['kind'] + '/' + obj['metadata'].get('namespace', '') + '/' + obj['metadata']['name']


def optional(kind, name, namespace=None):
    if kind == 'Secret':
        return gw.secret_meta(name, namespace)
    if kind in CERT_KINDS and CERT_KINDS[kind] not in gw.crd_names():
        return None
    return gw.optional(kind, name, namespace)


def source():
    files = list(HERE.glob('*.py'))
    files += list((PHASE / 'ansible/playbooks').glob('certificates*.yml'))
    files += list((PHASE / 'ansible/tasks').glob('certificates*.yml'))
    files += list((PHASE / 'networking/certificates').glob('*'))
    files += [PHASE / p for p in ['scripts/certificates.sh', 'ansible/vars/certificates.yml', 'examples/certificates/README.md', 'examples/certificates/main.go', 'examples/certificates/main_test.go', 'examples/certificates/go.mod', 'records/completed/02.04.json']]
    files += [Path(gw.__file__), Path(gw.mat.__file__), Path(gw.probe.__file__), Path(gw.l2.__file__), Path(gw.l2.common.__file__), Path(gw.l2.common.base.__file__)]
    files += [ROOT / p for p in ['ops/versions.lock.yaml', 'ops/inventory/networks.yaml', 'ops/inventory/vips.yaml', 'ops/00-preparation/ansible/ansible.cfg', 'ops/00-preparation/ansible/inventories/lab/hosts.yml', 'ops/00-preparation/ansible/inventories/lab/group_vars/all.yml', 'ops/00-preparation/pki/public/cnpl-lab-root-ca.crt']]
    require(all(p.is_file() for p in files), '缺少完整的 02.05 剧本、模板或输入')
    return {'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))}}


def previous(uid):
    value = json.loads((PHASE / 'records/completed/02.04.json').read_text())
    require(value['passed'] and value['cleanup_passed'] and value['cluster_uid'] == uid, '需要同集群完整 02.04 交接')
    folder = Path(value['records'])
    require(folder.resolve().is_relative_to(PHASE / 'records'), '交接路径越界')
    for file, digest in [('passed_receipt', 'passed_receipt_sha256'), ('cleanup_receipt', 'cleanup_receipt_sha256')]:
        require(hashlib.sha256((folder / value[file]).read_bytes()).hexdigest() == value[digest], '02.04 原始回执改变')
    return value


def protected():
    return {key: value for key, value in gw.protected().items() if key.split('/')[1] not in [CM_NS, NS]}


def binding(records, context, obj):
    local = Path(records) / 'state' / ('object-' + object_key(obj).replace('/', '-') + '.json')
    return json.loads(local.read_text()) if local.exists() else registry(context)['objects'].get(object_key(obj))


def main_objects(context):
    main = gw.data_plane(context, laboratory=False)
    return {kind: get(kind, name, namespace) for kind, name, namespace in [('Gateway', 'primary', PLATFORM), ('Deployment', 'cnpl-primary', 'envoy-gateway-system'), ('Service', 'cnpl-primary', 'envoy-gateway-system'), ('EnvoyProxy', 'primary', PLATFORM), ('GatewayClass', 'cnpl-envoy', None), ('HTTPRoute', 'primary-redirect', PLATFORM)]}, main


def preflight(records, identity=False):
    path = Path(records) / 'context.json'
    if identity:
        value = json.loads(path.read_text())
        require(get('namespace', 'kube-system')['metadata']['uid'] == value['cluster_uid'], '恢复目标不是原集群')
        return value
    context = gw.l2.common.base.preflight(Path(records))
    require(context.get('stage', '02.05') == '02.05', '批次属于其他步骤')
    context.update(stage='02.05', previous=previous(context['cluster_uid']))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect(('192.168.9.100', 6443))
        context['mac_ip'] = sock.getsockname()[0]
    require(context['mac_ip'] == '192.168.9.200', '管理端来源与入口限制不同')
    require(not yaml.safe_load((PHASE / 'networking/certificates/public-boundary.yaml').read_text())['enabled'], '本轮公网能力明确阻塞，不能创建公网入口')
    for name in [CM_NS, NS]:
        ns = optional('Namespace', name)
        if ns:
            meta = ns['metadata']
            require(meta.get('labels', {}).get('cnpl.io/component') == COMPONENT and meta['labels'].get('cnpl.io/cluster-uid') == context['cluster_uid'], '拒绝接管外来 Namespace ' + name)
            bound = binding(records, context, ns)
            require(bound and bound['uid'] == meta['uid'], 'Namespace 原 UID 不符')
            require(name != NS or meta['labels'].get(LABEL) == context['run'], '实验空间属于其他批次')
    for name in [d['metadata']['name'] for d in mat.crds()]:
        if name in gw.crd_names():
            obj = get('crd', name)
            bound = registry(context)['objects'].get(object_key(obj))
            require(bound and bound['uid'] == obj['metadata']['uid'], '已有 cert-manager CRD 未登记，拒绝接管')
    for kind, name in [('Secret', 'cnpl-internal-issuer-ca'), ('Secret', 'primary-managed-tls'), ('Issuer', 'cnpl-internal'), ('Certificate', 'primary-auto'), ('Role', 'certificate-editor'), ('RoleBinding', 'certificate-editor'), ('ServiceAccount', 'certificate-editor')]:
        obj = optional(kind, name, PLATFORM)
        if obj:
            bound = binding(records, context, obj)
            require(bound and bound['uid'] == obj['metadata']['uid'], '平台空间存在未登记或替换的同名对象：' + kind + '/' + name)
    objects, main = main_objects(context)
    prior = context['previous']['retained_main']
    require(all(main[k] == prior[k] for k in ['gateway_uid', 'service_uid', 'deployment_uid']), '主入口 UID 与 02.04 不同')
    if 'main_original' not in context:
        context['main_original'] = {kind: {'uid': obj['metadata']['uid'], 'spec_sha256': gw.l2.digest(obj.get('spec'))} for kind, obj in objects.items()}
        context['gateway_original_refs'] = objects['Gateway']['spec']['listeners'][1]['tls']['certificateRefs']
        context['data_pod_uids'] = sorted(p['uid'] for p in main['data_pods'])
    row = gw.probe.http('192.168.9.201', '/not-routed')
    require(row['status'] == 404, '主入口已有其他应用路由，先核对使用范围')
    refs = objects['Gateway']['spec']['listeners'][1]['tls']['certificateRefs']
    require(refs in [context['gateway_original_refs'], [{'group': '', 'kind': 'Secret', 'name': 'primary-managed-tls'}]], '主证书引用被其他操作改变')
    if refs == context['gateway_original_refs'] and not registry(context).get('internal_passed'):
        require(row['tls_peer_sha256'] == prior['tls_peer_sha256'], '主证书身份与前序交接不同')
    context['root_ca_sha256'] = pki.fingerprint(pki.authority()[1])
    save(path, context)
    return context


def object_plan(records, context, doc):
    kind, meta = doc['kind'], doc['metadata']
    name, ns = meta['name'], meta.get('namespace')
    if kind == 'Namespace':
        require(name in [CM_NS, NS] and not ns, '空间范围越界')
    elif kind == 'CustomResourceDefinition':
        expected = next((d for d in mat.crds() if d['metadata']['name'] == name), None)
        require(expected and gw.l2.digest(expected['spec']) == gw.l2.digest(doc['spec']), 'CRD 不是锁定包')
    elif kind in ['ValidatingAdmissionPolicy', 'ValidatingAdmissionPolicyBinding']:
        require(name in POLICIES, '策略范围越界')
    else:
        allowed = {'Issuer': ['cnpl-internal'], 'Certificate': ['primary-auto'], 'Secret': ['cnpl-internal-issuer-ca', 'primary-managed-tls'] + ['tls-test-' + n for n in ['valid', 'san', 'unknown', 'incomplete', 'expired']], 'ServiceAccount': ['certificate-editor'], 'Role': ['certificate-editor'], 'RoleBinding': ['certificate-editor'], 'Deployment': ['fault-backend'], 'Service': ['fault-backend'], 'ConfigMap': ['backend-root'], 'HTTPRoute': ['tls-faults'], 'BackendTLSPolicy': ['fault-backend']}
        require(kind in allowed and name in allowed[kind] and ns in [PLATFORM, NS], '对象范围越界')
        require((ns == NS) == (name in ['fault-backend', 'backend-root', 'tls-faults'] or name.startswith('tls-test-')), '对象空间与职责不同')
    labels = meta.get('labels', {})
    temporary = ns == NS or (kind == 'Namespace' and name == NS)
    require(labels.get(LABEL) == context['run'] if temporary else labels.get('cnpl.io/cluster-uid') == context['cluster_uid'] and labels.get('cnpl.io/component') == COMPONENT, '对象归属标签不符')
    obj = optional(kind, name, ns)
    if obj:
        bound = binding(records, context, obj)
        require(bound and bound['uid'] == obj['metadata']['uid'], '拒绝接管未登记或已替换的对象')
    return {'exists': bool(obj), 'temporary': temporary}


def record(records, context, obj):
    require(obj['kind'] != 'Secret' or not ({'data', 'stringData'} & obj.keys()), 'Secret 私有数据禁止写入证据')
    meta = obj['metadata']
    value = {'uid': meta['uid'], 'kind': obj['kind'], 'name': meta['name'], 'namespace': meta.get('namespace', ''), 'run': context['run'], 'cluster_uid': context['cluster_uid'], 'spec_sha256': gw.l2.digest(obj.get('spec'))}
    save(Path(records) / 'state' / ('object-' + object_key(obj).replace('/', '-') + '.json'), value)
    if meta.get('namespace') != NS and not (obj['kind'] == 'Namespace' and meta['name'] == NS):
        saved = registry(context)
        saved['objects'][object_key(obj)] = value
        save(REGISTRY, saved)
    return value


def materials(records):
    return json.loads((Path(records) / 'state/materials.json').read_text())


def public_certificate(name, namespace):
    raw = call(K + ['get', 'secret', name, '-n', namespace, '-o', r'jsonpath={.data.tls\.crt}'])
    pem = base64.b64decode(raw)
    chain = [pki.x509.load_pem_x509_certificate(x.encode()) for x in re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', pem.decode(), re.S)]
    require(chain, 'Secret 不含公开证书链')
    cert = chain[0]
    try:
        sans = cert.extensions.get_extension_for_class(pki.x509.SubjectAlternativeName).value.get_values_for_type(pki.x509.DNSName)
    except pki.x509.ExtensionNotFound:
        sans = []
    return {'sha256': pki.fingerprint(cert), 'spki_sha256': hashlib.sha256(pki.public(cert.public_key())).hexdigest(), 'serial': str(cert.serial_number), 'not_before': cert.not_valid_before_utc.isoformat(), 'not_after': cert.not_valid_after_utc.isoformat(), 'chain_sha256': [pki.fingerprint(c) for c in chain], 'sans': sans}


def secret_plan(records, context, path):
    require(path.resolve().is_relative_to(pki.PRIVATE.resolve()), 'Secret 只能位于 Mac 私有目录')
    doc = json.loads(path.read_text())
    require(doc['kind'] == 'Secret' and set(doc['data']) == {'tls.crt', 'tls.key'}, '私有材料字段不符')
    cert = pki.x509.load_pem_x509_certificate(base64.b64decode(doc['data']['tls.crt']))
    key = pki.serialization.load_pem_private_key(base64.b64decode(doc['data']['tls.key']), password=None)
    require(pki.public(cert.public_key()) == pki.public(key.public_key()), 'Secret 证书私钥不匹配')
    name = doc['metadata']['name']
    expected = materials(records)['issuer'] if name == 'cnpl-internal-issuer-ca' else materials(records)['profiles'][name.removeprefix('tls-test-')]
    require(pki.fingerprint(cert) == expected['sha256'], 'Secret 公开证书与准备回执不同')
    return object_plan(records, context, doc)


def record_secret(records, context, name, namespace):
    obj = gw.secret_meta(name, namespace)
    value = public_certificate(name, namespace)
    record(records, context, obj)
    return dict(value, uid=obj['metadata']['uid'])


def gateway_patch(records, context, restore=False):
    obj = get('Gateway', 'primary', PLATFORM)
    require(obj['metadata']['uid'] == context['main_original']['Gateway']['uid'], '主 Gateway 原 UID 改变')
    require(obj['spec']['listeners'][1]['name'] == 'https', 'HTTPS listener 顺序不同')
    refs = obj['spec']['listeners'][1]['tls']['certificateRefs']
    auto = [{'group': '', 'kind': 'Secret', 'name': 'primary-managed-tls'}]
    original = context['gateway_original_refs']
    require(refs in [original, auto], '证书引用已被其他操作改变')
    target = original if restore else auto
    return {'patch': [] if refs == target else [{'op': 'test', 'path': '/metadata/uid', 'value': obj['metadata']['uid']}, {'op': 'test', 'path': '/spec/listeners/1/tls/certificateRefs', 'value': refs}, {'op': 'replace', 'path': '/spec/listeners/1/tls/certificateRefs', 'value': target}]}


def certificate_state(records, context):
    cert = get('Certificate', 'primary-auto', PLATFORM)
    bound = binding(records, context, cert)
    require(bound and bound['uid'] == cert['metadata']['uid'], 'Certificate 原 UID 改变')
    require(gw.condition(cert, cert.get('status', {}).get('conditions'), 'Ready', 'True'), '等待本代 Certificate Ready')
    secret = gw.secret_meta('primary-managed-tls', PLATFORM)
    require(secret and secret['metadata'].get('labels', {}).get('cnpl.io/cluster-uid') == context['cluster_uid'], '自动叶证书 Secret 身份不同')
    owners = json.loads(call(K + ['get', 'secret', 'primary-managed-tls', '-n', PLATFORM, '-o', r'jsonpath={.metadata.ownerReferences}']) or '[]')
    require(any(o.get('uid') == cert['metadata']['uid'] and o.get('kind') == 'Certificate' for o in owners), '自动 Secret 不属于当前 Certificate')
    leaf = public_certificate('primary-managed-tls', PLATFORM)
    require(set(leaf['sans']) == set(pki.NAMES) and materials(records)['issuer']['sha256'] in leaf['chain_sha256'], '自动叶证书 SAN 或签发链不同')
    issuer = get('Issuer', 'cnpl-internal', PLATFORM)
    require(any(c.get('type') == 'Ready' and c.get('status') == 'True' for c in issuer.get('status', {}).get('conditions') or []), 'Issuer 未 Ready')
    return dict(leaf, passed=True, certificate_uid=cert['metadata']['uid'], secret_uid=secret['metadata']['uid'], revision=cert['status'].get('revision'), renewal_time=cert['status']['renewalTime'])


def backend(context):
    dep = get('deployment', 'fault-backend', NS)
    require(dep['status'].get('observedGeneration') == dep['metadata']['generation'] and dep['status'].get('readyReplicas') == 1, '等待故障后端本代单副本 Ready')
    sets = get('replicasets', namespace=NS)['items']
    owners = {s['metadata']['uid'] for s in sets if any(o.get('uid') == dep['metadata']['uid'] for o in s['metadata'].get('ownerReferences', []))}
    pods = [p for p in get('pods', namespace=NS)['items'] if not p['metadata'].get('deletionTimestamp') and any(o.get('uid') in owners for o in p['metadata'].get('ownerReferences', []))]
    require(len(pods) == 1 and gw.ready(pods[0]) and pods[0]['metadata'].get('labels', {}).get(LABEL) == context['run'], '后端 Pod 归属或就绪不同')
    pod = pods[0]
    require(pod['spec']['containers'][0]['image'] == gw.mat.lock()['gateway_fixture']['internal_source'] and pod['spec']['nodeName'] in gw.l2.WORKERS, '后端镜像或 VM 不同')
    return {'pod': pod['metadata']['name'], 'uid': pod['metadata']['uid'], 'version': pod['metadata']['labels']['version'], 'node': pod['spec']['nodeName']}


def render_chart(values):
    raw = mat.call([mat.HELM, 'template', 'cnpl-cert-manager', mat.chart(), '-n', CM_NS, '--kube-version', '1.36.5', '--skip-crds', '-f', values])
    docs = [d for d in yaml.safe_load_all(raw) if d]
    require(all(d['kind'] not in ['Secret', 'CustomResourceDefinition'] for d in docs), '控制器 Chart 不能夹带私钥或另行管理 CRD')
    allowed = {a['internal_source'] for a in mat.lock()['artifacts']}
    images = [c['image'] for d in docs if d['kind'] in ['Deployment', 'Job'] for c in d['spec']['template']['spec']['containers']]
    require(len(images) == 4 and all(image in allowed for image in images), '控制器镜像没有全部锁定')
    return docs, images


def helm_guard(records, context, values):
    docs, images = render_chart(values)
    ns = optional('Namespace', CM_NS)
    if ns:
        bound = binding(records, context, ns)
        require(bound and bound['uid'] == ns['metadata']['uid'], 'cert-manager Namespace UID 改变')
    releases = json.loads(call([str(mat.HELM), '--kubeconfig', str(Path.home() / '.cnpl-secrets/kubeconfig-lab-primary'), 'list', '-n', CM_NS, '--deployed', '--failed', '--pending', '--uninstalling', '--uninstalled', '--superseded', '-o', 'json']))
    require(all(r['name'] == 'cnpl-cert-manager' and r['chart'] == 'cert-manager-v1.21.2' for r in releases), '已有其他 release 或版本，不能接管')
    for doc in docs:
        meta = doc['metadata']
        existing = optional(doc['kind'], meta['name'], meta.get('namespace'))
        if existing:
            annotations = existing['metadata'].get('annotations') or {}
            require(annotations.get('meta.helm.sh/release-name') == 'cnpl-cert-manager' and annotations.get('meta.helm.sh/release-namespace') == CM_NS, '同名 Chart 资源不是本项目 release')
    return {'passed': True, 'images': images, 'release_exists': bool(releases)}


def validate_all(context, attempt):
    definitions = mat.crds()
    for item in definitions:
        item['metadata'].setdefault('labels', {}).update({'cnpl.io/component': COMPONENT, 'cnpl.io/cluster-uid': context['cluster_uid']})
        call(K + ['apply', '--server-side', '--field-manager=cnpl-certificates', '--dry-run=server', '--validate=strict', '-f', '-'], json.dumps(item))
    (attempt / 'crds.yaml').write_text(yaml.safe_dump_all(definitions, sort_keys=False))
    documents = [d for path in attempt.glob('*.yaml') if path.name not in ['controller-values.yaml', 'crds.yaml'] for d in yaml.safe_load_all(path.read_text()) if d]
    require({'Certificate', 'Issuer', 'BackendTLSPolicy', 'HTTPRoute', 'ValidatingAdmissionPolicy'} <= {d['kind'] for d in documents}, '整组缺少必需清单')
    structure = gw.mat.validate_custom(documents, definitions + gw.mat.crds())
    custom = {'Certificate', 'Issuer', 'BackendTLSPolicy', 'HTTPRoute'}
    count = 0
    for doc in documents:
        if doc['kind'] in custom:
            continue
        preview = json.loads(json.dumps(doc))
        if preview['metadata'].get('namespace'):
            preview['metadata']['namespace'] = 'lab-core'
        call(K + ['apply', '--dry-run=server', '--validate=strict', '-f', '-'], json.dumps(preview))
        count += 1
    docs, images = render_chart(attempt / 'controller-values.yaml')
    (attempt / 'controller-rendered.yaml').write_text(yaml.safe_dump_all(docs, sort_keys=False))
    for doc in docs:
        preview = json.loads(json.dumps(doc))
        if preview['metadata'].get('namespace'):
            preview['metadata']['namespace'] = 'lab-core'
        call(K + ['apply', '--dry-run=server', '--validate=strict', '-f', '-'], json.dumps(preview))
    return {'passed': True, 'cert_manager': '1.21.2', 'crds_server_dry_run': len(definitions), 'builtin_server_dry_run': count + len(docs), 'custom_structure': structure, 'images': images, 'root_decryption_or_issuance_performed': False}


def controller_ready(context):
    images = {a['name']: a['internal_source'] for a in mat.lock()['artifacts']}
    objects = {}
    for suffix, component in [('', 'controller'), ('-webhook', 'webhook'), ('-cainjector', 'cainjector')]:
        obj = get('deployment', 'cnpl-cert-manager' + suffix, CM_NS)
        require(obj['status'].get('readyReplicas') == obj['spec']['replicas'] == 1 and obj['status'].get('observedGeneration') == obj['metadata']['generation'], 'cert-manager 控制器尚未就绪')
        require(obj['spec']['template']['spec']['containers'][0]['image'] == images[component], '控制器镜像改变')
        objects[component] = obj['metadata']['uid']
    return {'passed': True, 'deployments': objects}


def policies_ready():
    for name in POLICIES:
        obj = get('ValidatingAdmissionPolicy', name)
        status = obj.get('status') or {}
        require(status.get('observedGeneration') == obj['metadata']['generation'] and not (status.get('typeChecking') or {}).get('expressionWarnings'), '准入策略尚未完成本代类型检查：' + name)
    return {'passed': True}


def main_tls(records, context, path='/tls-probe'):
    leaf = certificate_state(records, context)
    row = gw.probe.http('192.168.9.201', path)
    require(row['tls_peer_sha256'] == leaf['sha256'], 'Gateway 尚未加载当前自动证书')
    if path == '/tls-probe':
        pod = backend(context)
        gw.probe.identity(row, {pod['pod']: {'uid': pod['uid'], 'version': pod['version']}}, version='valid', nonce=row['nonce'])
    else:
        require(row['status'] == 404, '实验路由未清理')
    return dict(leaf, passed=True, request=row)


def rotation(records, context, attempt):
    first = json.loads((attempt / 'certificate-initial.json').read_text())
    current = main_tls(records, context)
    require(current['certificate_uid'] == first['certificate_uid'] and current['secret_uid'] == first['secret_uid'], '续期重建了 Certificate 或 Secret')
    require(current['sha256'] != first['sha256'] and current['spki_sha256'] != first['spki_sha256'] and current['revision'] > first['revision'], '等待定时续期同时更新叶证书和密钥')
    require(datetime.fromisoformat(current['not_before']) >= datetime.fromisoformat(first['renewal_time']) - timedelta(seconds=5), '新证书早于原定续期时间')
    current['automatic_timer_renewal'] = True
    return current


def steady(records, context):
    value = main_tls(records, context)
    span = datetime.fromisoformat(value['not_after']) - datetime.fromisoformat(value['not_before'])
    require(167 * 3600 <= span.total_seconds() <= 169 * 3600, '等待稳定七天证书重新签发')
    require(datetime.fromisoformat(value['renewal_time']) > datetime.now(timezone.utc) + timedelta(days=4), '续期仍处在短周期实验模式')
    return value


def metrics(context, attempt, label):
    main = gw.data_plane(context, False)
    total = 0.0
    for pod in main['data_pods']:
        with gw.probe.forwarded(K, pod['name'], [19001], attempt / (label + '-' + pod['name'] + '-forward.txt')) as ports:
            connection = http.client.HTTPConnection('127.0.0.1', ports[19001], timeout=4)
            try:
                connection.request('GET', '/stats/prometheus')
                response = connection.getresponse()
                text = response.read(4 * 1024 * 1024).decode()
                require(response.status == 200, '无法读取 Envoy TLS 验证指标')
            finally:
                connection.close()
        (attempt / (label + '-' + pod['name'] + '-metrics.txt')).write_text(text)
        total += sum(float(v) for v in re.findall(r'^envoy_cluster_ssl_fail_verify_(?:error|san)(?:\{[^\n]*\})?\s+([0-9.eE+-]+)\s*$', text, re.M))
    return total


def fault(records, context, attempt, profile):
    pod = backend(context)
    require(pod['version'] == profile, '等待指定故障材料进入新的后端 Pod')
    expected = materials(records)['profiles'][profile]
    before = metrics(context, attempt, profile + '-before') if profile != 'valid' else 0
    with gw.probe.forwarded(K, pod['pod'], [8443], attempt / ('backend-' + profile + '-forward.txt'), namespace=NS) as ports:
        port = ports[8443]
        diag = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        diag.check_hostname, diag.verify_mode = False, ssl.CERT_NONE
        with socket.create_connection(('127.0.0.1', port), timeout=4) as raw:
            with diag.wrap_socket(raw, server_hostname=pki.NAMES[0]) as stream:
                peer = hashlib.sha256(stream.getpeercert(binary_form=True)).hexdigest()
                chain_count = len(stream.get_unverified_chain())
        require(peer == expected['sha256'] and chain_count == (1 if profile == 'incomplete' else 2), '后端未实际加载指定叶证书或链')
        python = None
        try:
            row = gw.probe.http('127.0.0.1', '/v1', port=port)
            require(profile == 'valid', '错误证书被 Python 信任')
            python = {'tls_valid': True, 'request': row}
        except ssl.SSLCertVerificationError as error:
            allowed = {'san': [62], 'unknown': [18, 19, 20, 21], 'incomplete': [20, 21], 'expired': [10]}
            require(profile in allowed and error.verify_code in allowed[profile], 'TLS 拒绝原因与实验不同：' + str(error))
            python = {'tls_valid': False, 'verify_code': error.verify_code, 'reason': error.verify_message}
        nonce = uuid.uuid4().hex
        reply = subprocess.run([mat.lock()['client']['path'], '--target', '127.0.0.1:' + str(port), '--name', pki.NAMES[0], '--ca', str(pki.PUBLIC), '--nonce', nonce], capture_output=True, text=True, timeout=10)
        go = json.loads(reply.stdout)
        classes = {'valid': '', 'san': 'hostname', 'unknown': 'unknown_authority', 'incomplete': 'unknown_authority', 'expired': 'validity'}
        require(reply.returncode == (0 if profile == 'valid' else 1) and go.get('tls_valid') == (profile == 'valid') and go.get('error_class', '') == classes[profile], 'Go TLS 验证结果不同')
        if profile == 'valid':
            require(go['body']['nonce'] == nonce and go['body']['uid'] == pod['uid'], 'Go 没有命中当前后端身份')
    route = gw.route_condition('HTTPRoute', 'tls-faults', namespace=NS)
    policy = get('BackendTLSPolicy', 'fault-backend', NS)
    require(any(gw.condition(policy, a.get('conditions'), 'Accepted', 'True') for a in policy.get('status', {}).get('ancestors') or []), '后端 TLS 策略未被接受')
    requests = [gw.probe.http('192.168.9.201', '/tls-probe?case=' + profile + '&nonce=' + uuid.uuid4().hex) for _ in range(3)]
    require(all(r['tls_peer_sha256'] == certificate_state(records, context)['sha256'] for r in requests), '主入口有效 TLS 身份改变')
    if profile == 'valid':
        for row in requests:
            gw.probe.identity(row, {pod['pod']: {'uid': pod['uid'], 'version': 'valid'}}, nonce=row['nonce'])
        after = before
    else:
        require(all(r['status'] == 503 and (not isinstance(r.get('body'), dict) or not r['body'].get('uid')) for r in requests), '网关未拒绝错误后端证书')
        after = metrics(context, attempt, profile + '-after')
        require(after > before, '缺少网关实际上游证书验证失败计数')
    return {'passed': True, 'profile': profile, 'pod': pod, 'python': python, 'go': go, 'actual_peer_sha256': peer, 'actual_chain_length': chain_count, 'diagnostic_unverified_handshake_only_no_application_request': True, 'gateway_requests': requests, 'gateway_verify_fail_before': before, 'gateway_verify_fail_after': after}


def authorization(records, context, attempt):
    account = 'system:serviceaccount:cnpl-gateway:certificate-editor'
    checks = [('patch', 'certificates.cert-manager.io/primary-auto', PLATFORM, True), ('get', 'secrets/cnpl-internal-issuer-ca', PLATFORM, False), ('create', 'issuers.cert-manager.io', PLATFORM, False), ('create', 'certificaterequests.cert-manager.io', PLATFORM, False), ('create', 'pods', PLATFORM, False), ('patch', 'gateways.gateway.networking.k8s.io/primary', PLATFORM, False), ('delete', 'certificates.cert-manager.io/primary-auto', PLATFORM, False)]
    for verb, resource, namespace, expected in checks:
        reply = subprocess.run(K + ['auth', 'can-i', verb, resource, '-n', namespace, '--as', account], capture_output=True, text=True, timeout=25)
        require(reply.returncode == (0 if expected else 1) and reply.stdout.strip() == ('yes' if expected else 'no'), '证书编辑者权限与边界不符：' + verb + '/' + resource)
    live = get('Certificate', 'primary-auto', PLATFORM)
    original = {'apiVersion': 'cert-manager.io/v1', 'kind': 'Certificate', 'metadata': {'name': 'primary-auto', 'namespace': PLATFORM}, 'spec': live['spec']}
    positive = subprocess.run(K + ['apply', '--server-side', '--force-conflicts', '--field-manager=cnpl-tls-boundary-preview', '--dry-run=server', '--validate=strict', '--as', account, '-f', '-'], input=json.dumps(original), capture_output=True, text=True, timeout=30)
    require(positive.returncode == 0, '受限编辑者的合法 Certificate 更新被拒绝：' + positive.stderr[-900:])
    cases = []
    for label, change in [('public-san', {'dnsNames': ['demo.apps.egon.top']}), ('CA', {'isCA': True}), ('client-auth', {'usages': ['digital signature', 'client auth']})]:
        doc = json.loads(json.dumps(original))
        doc['spec'].update(change)
        cases.append((label, doc, account))
    requests = get('CertificateRequest', namespace=PLATFORM)['items']
    owned = next(r for r in requests if any(o.get('uid') == live['metadata']['uid'] for o in r['metadata'].get('ownerReferences', [])))
    cases.append(('direct-request', {'apiVersion': 'cert-manager.io/v1', 'kind': 'CertificateRequest', 'metadata': {'name': 'cnpl-denied-direct', 'namespace': PLATFORM}, 'spec': owned['spec']}, None))
    cases.append(('cluster-issuer', {'apiVersion': 'cert-manager.io/v1', 'kind': 'ClusterIssuer', 'metadata': {'name': 'cnpl-internal'}, 'spec': {'ca': {'secretName': 'cnpl-internal-issuer-ca'}}}, None))
    cases.append(('kube-csr-bypass', {'apiVersion': 'certificates.k8s.io/v1', 'kind': 'CertificateSigningRequest', 'metadata': {'name': 'cnpl-denied-kube-csr'}, 'spec': {'request': owned['spec']['request'], 'signerName': 'issuers.cert-manager.io/cnpl-gateway.cnpl-internal', 'usages': ['digital signature', 'server auth'], 'expirationSeconds': 3600}}, None))
    for host in ['demo.apps.egon.top', 'harbor.k8s.internal.egon.top']:
        cases.append(('route-' + host, {'apiVersion': 'gateway.networking.k8s.io/v1', 'kind': 'HTTPRoute', 'metadata': {'name': 'cnpl-denied-public', 'namespace': NS}, 'spec': {'parentRefs': [{'name': 'primary', 'namespace': PLATFORM, 'sectionName': 'https'}], 'hostnames': [host], 'rules': [{'backendRefs': [{'name': 'fault-backend', 'port': 8443}]}]}}, None))
    results = []
    for name, doc, actor in cases:
        args = K + ['apply', '--server-side', '--force-conflicts', '--field-manager=cnpl-tls-boundary-preview', '--dry-run=server', '--validate=strict', '-f', '-'] + (['--as', actor] if actor else [])
        reply = subprocess.run(args, input=json.dumps(doc), capture_output=True, text=True, timeout=30)
        require(reply.returncode != 0 and 'CNPL_TLS_BOUNDARY' in reply.stderr, '未按指定准入策略拒绝：' + name + ': ' + reply.stderr[-900:])
        results.append({'name': name, 'denied_by_policy': True, 'stderr': reply.stderr})
    return {'passed': True, 'rbac': [{'verb': v, 'resource': r, 'allowed': e} for v, r, _, e in checks], 'admission_denials': results, 'dry_run_only': True}


def cleanup_plan(records, context):
    ns = optional('Namespace', NS)
    if not ns:
        return {'exists': False}
    bound = binding(records, context, ns)
    require(bound and bound['uid'] == ns['metadata']['uid'] and ns['metadata'].get('labels', {}).get(LABEL) == context['run'], '实验空间 UID 或批次改变')
    kinds = ['pods','deployments','replicasets','daemonsets','statefulsets','services','configmaps','serviceaccounts','roles','rolebindings','networkpolicies','ciliumnetworkpolicies','jobs','cronjobs','persistentvolumeclaims','ingresses','horizontalpodautoscalers','resourcequotas','limitranges','httproutes','grpcroutes','tcproutes','udproutes','backendtlspolicies','referencegrants']
    kinds += [name.split('.')[0] for name in gw.crd_names() if name.endswith(('.cert-manager.io', '.acme.cert-manager.io'))]
    objects = get(','.join(kinds), namespace=NS)['items'] + gw.secret_list(NS)
    for obj in objects:
        if (obj['kind'], obj['metadata']['name']) in [('ConfigMap', 'kube-root-ca.crt'), ('ServiceAccount', 'default')]:
            continue
        require(obj['metadata'].get('labels', {}).get(LABEL) == context['run'], '实验空间出现外来资源，拒绝删除')
    services = {obj['metadata']['uid'] for obj in objects if obj['kind'] == 'Service'}
    for obj in get('endpointslices', namespace=NS)['items']:
        require(any(owner.get('uid') in services for owner in obj['metadata'].get('ownerReferences', [])), '实验空间存在外来 EndpointSlice')
    return {'exists': True, 'uid': ns['metadata']['uid']}


def main_unchanged(context):
    objects, state = main_objects(context)
    for kind, obj in objects.items():
        original = context['main_original'][kind]
        require(obj['metadata']['uid'] == original['uid'], '原有主入口资源 UID 改变：' + kind)
        spec = json.loads(json.dumps(obj['spec']))
        if kind == 'Gateway':
            spec['listeners'][1]['tls']['certificateRefs'] = context['gateway_original_refs']
        require(gw.l2.digest(spec) == original['spec_sha256'], '主入口非证书字段改变：' + kind)
    require(sorted(p['uid'] for p in state['data_pods']) == context['data_pod_uids'], '证书更新不应重启主入口 Pod')
    return state


def accept(records, context, attempt):
    required = ['compatibility', 'controller-ready', 'policies-ready', 'authorization', 'certificate-initial', 'rotation', 'steady', 'fault-valid', 'fault-san', 'fault-unknown', 'fault-incomplete', 'fault-expired', 'fault-restored']
    results = {n: json.loads((attempt / (n + '.json')).read_text()) for n in required}
    require(all(v['passed'] for v in results.values()), '内部证书验收存在缺项')
    require(json.loads((attempt / 'public.json').read_text())['status'] == 'BLOCKED', '公网必须保留明确阻塞')
    require(protected() == json.loads((Path(records) / 'state/protected.json').read_text()), '既有工作负载或配置改变')
    require(source() == json.loads((Path(records) / 'state/source.json').read_text()), '执行期间受检输入改变')
    main = main_unchanged(context)
    require(steady(records, context)['passed'], '主入口未保留稳定自动证书')
    return {'stage': '02.05', 'internal_passed': True, 'passed': False, 'phase_complete': False, 'run': context['run'], 'cluster_uid': context['cluster_uid'], 'steps': {'02.05.01': 'PASS', '02.05.02': 'PASS', '02.05.03': 'BLOCKED'}, 'public': json.loads((attempt / 'public.json').read_text()), 'results': results, 'main': main, 'attempt': str(attempt)}


def final(records, context, attempt):
    require(optional('Namespace', NS) is None, 'TLS 故障实验空间尚未清理')
    baseline = Path(records) / 'state/protected.json'
    require(not baseline.exists() or protected() == json.loads(baseline.read_text()), '原有工作负载改变')
    formal = Path(records) / 'passed.json'
    internal = formal.exists() and json.loads(formal.read_text()).get('internal_passed')
    if 'main_original' not in context:
        require(not internal and not baseline.exists(), '缺少变更前入口上下文')
        return {'cleanup_passed': True, 'internal_passed': False, 'phase_complete': False, 'main_state': 'no_mutation_started', 'public_status': 'BLOCKED'}
    main = main_unchanged(context)
    refs = get('Gateway', 'primary', PLATFORM)['spec']['listeners'][1]['tls']['certificateRefs']
    row = gw.probe.http('192.168.9.201', '/tls-probe')
    require(row['status'] == 404, '实验路由仍然生效')
    auto = refs == [{'group': '', 'kind': 'Secret', 'name': 'primary-managed-tls'}]
    if internal:
        require(auto, '内部验收后主入口没有使用自动证书')
        leaf = certificate_state(records, context)
        require(row['tls_peer_sha256'] == leaf['sha256'], '实际 TLS 与自动证书不同')
        saved = registry(context)
        saved.update(internal_passed=True, public_status='BLOCKED', primary=main, certificate=leaf, issuer_sha256=materials(records)['issuer']['sha256'])
        save(REGISTRY, saved)
    else:
        require(refs == context['gateway_original_refs'], '失败恢复没有回到原证书引用')
    return {'cleanup_passed': True, 'stage': '02.05', 'run': context['run'], 'cluster_uid': context['cluster_uid'], 'internal_passed': bool(internal), 'phase_complete': False, 'public_status': 'BLOCKED', 'main_state': 'automated_ready' if internal else 'original_restored', 'main': main, 'tls_peer_sha256': row['tls_peer_sha256'], 'temporary_namespace_absent': True, 'existing_workloads_unchanged': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['preflight', 'identity', 'source', 'protected', 'build', 'validate', 'object-plan', 'record', 'secret-plan', 'record-secret', 'helm-guard', 'controller-ready', 'policies-ready', 'certificate', 'backend', 'gateway-plan', 'gateway-restore-plan', 'main-tls', 'rotation', 'steady', 'fault', 'authorization', 'cleanup-plan', 'accept', 'final', 'public', 'stabilize-plan'])
    parser.add_argument('--records', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--attempt', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--values', type=Path)
    parser.add_argument('--name')
    parser.add_argument('--namespace')
    parser.add_argument('--profile', choices=['valid', 'san', 'unknown', 'incomplete', 'expired'], default='valid')
    args = parser.parse_args()
    records, attempt = args.records.resolve(), args.attempt
    if attempt:
        require(attempt.resolve().is_relative_to(records / 'attempts'), 'attempt 目录越界')
    if args.mode in ['preflight', 'identity']:
        value = preflight(records, args.mode == 'identity')
    elif args.mode == 'source':
        value = source()
    elif args.mode == 'protected':
        value = protected()
    elif args.mode == 'build':
        binary = args.output.parent / 'tls-probe-darwin-arm64'
        value = mat.build(binary)
        require(value['sha256'] == mat.lock()['client']['sha256'] and value['source_sha256'] == mat.lock()['client']['source_sha256'], 'Go TLS 客户端构建摘要不同')
    elif args.mode == 'public':
        value = yaml.safe_load((PHASE / 'networking/certificates/public-boundary.yaml').read_text())
        require(not value['enabled'] and value['status'] == 'BLOCKED' and not value['approved_domains'], '公网边界输入与批准范围不同')
        value['public_passed'] = False
    else:
        context = json.loads((records / 'context.json').read_text())
        if args.mode == 'validate':
            value = validate_all(context, attempt)
        elif args.mode == 'object-plan':
            value = object_plan(records, context, json.loads(args.manifest.read_text()))
        elif args.mode == 'record':
            value = record(records, context, json.loads(args.manifest.read_text()))
        elif args.mode == 'secret-plan':
            value = secret_plan(records, context, args.manifest)
        elif args.mode == 'record-secret':
            value = record_secret(records, context, args.name, args.namespace)
        elif args.mode == 'helm-guard':
            value = helm_guard(records, context, args.values)
        elif args.mode == 'controller-ready':
            value = controller_ready(context)
        elif args.mode == 'policies-ready':
            value = policies_ready()
        elif args.mode == 'stabilize-plan':
            obj = optional('Certificate', 'primary-auto', PLATFORM)
            if obj:
                bound = binding(records, context, obj)
                require(bound and bound['uid'] == obj['metadata']['uid'], '不能稳定化外来 Certificate')
            value = {'exists': bool(obj)}
        elif args.mode == 'certificate':
            value = certificate_state(records, context)
            record_secret(records, context, 'primary-managed-tls', PLATFORM)
        elif args.mode == 'backend':
            value = dict(backend(context), passed=True)
        elif args.mode in ['gateway-plan', 'gateway-restore-plan']:
            value = gateway_patch(records, context, args.mode == 'gateway-restore-plan') if 'main_original' in context else {'patch': []}
        elif args.mode == 'main-tls':
            value = main_tls(records, context)
        elif args.mode == 'rotation':
            value = rotation(records, context, attempt)
        elif args.mode == 'steady':
            value = steady(records, context)
        elif args.mode == 'fault':
            value = fault(records, context, attempt, args.profile)
        elif args.mode == 'authorization':
            value = authorization(records, context, attempt)
        elif args.mode == 'cleanup-plan':
            value = cleanup_plan(records, context)
        elif args.mode == 'accept':
            value = accept(records, context, attempt)
        else:
            value = final(records, context, attempt)
    save(args.output, value)
    print(json.dumps(value, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.SubprocessError, http.client.HTTPException) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
