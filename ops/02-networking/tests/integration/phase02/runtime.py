"""02.07–10 共用的批次、前序回执和原 UID 边界；写操作返回给 Ansible 执行。"""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import time
import uuid
import yaml
from jinja2 import Environment, StrictUndefined


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


HERE = Path(__file__).resolve().parent
pol = module('phase02_policies', HERE.parent / 'policies/check.py')
ROOT, PHASE, K = pol.ROOT, pol.PHASE, pol.K
require, call, save, get, optional = pol.require, pol.call, pol.save, pol.get, pol.optional
LABEL = 'cnpl.io/phase-run'
WORKERS = ['worker01.k8s.internal.egon.top', 'worker02.k8s.internal.egon.top']
RESOURCE = {'Namespace': ('v1', 'namespaces'), 'Pod': ('v1', 'pods'), 'Service': ('v1', 'services'),
    'ConfigMap': ('v1', 'configmaps'), 'ServiceAccount': ('v1', 'serviceaccounts'),
    'Deployment': ('apps/v1', 'deployments'), 'ResourceQuota': ('v1', 'resourcequotas'),
    'LimitRange': ('v1', 'limitranges'), 'PodDisruptionBudget': ('policy/v1', 'poddisruptionbudgets'),
    'PriorityClass': ('scheduling.k8s.io/v1', 'priorityclasses'),
    'CustomResourceDefinition': ('apiextensions.k8s.io/v1', 'customresourcedefinitions'),
    'Gateway': ('gateway.networking.k8s.io/v1', 'gateways'),
    'EnvoyProxy': ('gateway.envoyproxy.io/v1alpha1', 'envoyproxies'),
    'HTTPRoute': ('gateway.networking.k8s.io/v1', 'httproutes'),
    'CiliumLoadBalancerIPPool': ('cilium.io/v2', 'ciliumloadbalancerippools'),
    'CiliumL2AnnouncementPolicy': ('cilium.io/v2alpha1', 'ciliuml2announcementpolicies'),
    'CiliumBGPClusterConfig': ('cilium.io/v2', 'ciliumbgpclusterconfigs'),
    'CiliumBGPPeerConfig': ('cilium.io/v2', 'ciliumbgppeerconfigs'),
    'CiliumBGPNodeConfigOverride': ('cilium.io/v2', 'ciliumbgpnodeconfigoverrides'),
    'CiliumBGPAdvertisement': ('cilium.io/v2', 'ciliumbgpadvertisements')}


def quantity(value):
    value = str(value)
    units = {'m': .001, 'Ki': 1024, 'Mi': 1024**2, 'Gi': 1024**3, 'Ti': 1024**4, 'k': 1000, 'M': 1000**2, 'G': 1000**3}
    match = re.fullmatch(r'([0-9.]+)(m|Ki|Mi|Gi|Ti|k|M|G)?', value)
    require(match, '不支持的资源数量：' + value)
    return float(match[1]) * units.get(match[2], 1)


def previous(stage, uid, required):
    prior = '02.' + str(int(stage.split('.')[1]) - 1).zfill(2)
    candidates = []
    for folder in (PHASE / 'records').glob(prior + '-*'):
        if not (folder / 'passed.json').is_file() or not (folder / 'state/closed.json').is_file():
            continue
        passed = json.loads((folder / 'passed.json').read_text())
        closed = json.loads((folder / 'state/closed.json').read_text())
        if passed.get('cluster_uid') == closed.get('cluster_uid') == uid and passed.get('run') == closed.get('run') and closed.get('cleanup_passed') and (passed.get('available_cases_passed') or passed.get('passed')):
            candidates.append((folder, passed, closed))
    if not candidates:
        require(not required, '先完成 ' + prior + ' all 及清理；不需要手动编辑交接文件。')
        return {'stage': prior, 'status': 'RUNTIME_PENDING'}
    folder, passed, closed = sorted(candidates, key=lambda row: row[0].name)[-1]
    return {'stage': prior, 'records': str(folder), 'run': passed['run'],
        'passed_sha256': hashlib.sha256((folder / 'passed.json').read_bytes()).hexdigest(),
        'closed_sha256': hashlib.sha256((folder / 'state/closed.json').read_bytes()).hexdigest(),
        'phase_complete': passed.get('phase_complete', True)}


class Session:
    def __init__(self, topic, stage, records, attempt, namespaces):
        self.topic, self.stage = topic, stage
        self.records, self.attempt = Path(records).resolve(), Path(attempt).resolve()
        require(self.records.parent == PHASE / 'records' and self.records.name.startswith(stage + '-'), '批次路径越界')
        require(self.attempt.is_relative_to(self.records / 'attempts'), 'attempt 路径越界')
        self.namespaces = namespaces
        self.path = self.records / 'context.json'
        self.context = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.k = K
        self.attempt.mkdir(parents=True, exist_ok=True)

    def prepare(self, mode):
        if mode in ['cleanup', 'recover']:
            require(self.context.get('stage') == self.stage, '没有本步骤原上下文')
            require(get('namespace', 'kube-system')['metadata']['uid'] == self.context['cluster_uid'], '恢复集群 UID 不同')
            return self.context
        context = pol.base.preflight(self.records)
        require(context.get('stage', self.stage) == self.stage, '批次步骤不符')
        context.update(stage=self.stage, topic=self.topic, mac_ip='192.168.9.200')
        context['previous'] = previous(self.stage, context['cluster_uid'], mode == 'all')
        for ns in self.namespaces:
            obj = optional('Namespace', ns)
            require(not obj, '专用空间已经存在；先用原批次 recover：' + ns)
        self.context = context
        save(self.path, context)
        if mode == 'all':
            require(not (self.records / 'state/protected.json').exists(), '批次已使用，需要 recover 后换新目录')
            save(self.records / 'state/protected.json', self.protected())
        return context

    def protected(self):
        values = pol.protected()
        return {key: value for key, value in values.items() if key.split('/')[1] not in self.namespaces}

    @property
    def run(self):
        return self.context['run']

    def render(self, values):
        env = Environment(undefined=StrictUndefined, keep_trailing_newline=True)
        files = []
        for path in sorted((PHASE / 'networking' / self.topic).glob('*.yaml.j2')):
            target = self.attempt / path.name.removesuffix('.j2')
            target.write_text(env.from_string(path.read_text()).render(run=self.run, **values))
            files.append(str(target))
        return files

    def sources(self):
        files = list(HERE.glob('*.py')) + list((HERE.parent / self.topic).glob('*.py'))
        for directory, pattern in [('ansible/playbooks', self.topic + '*.yml'), ('ansible/tasks', 'phase02-*.yml'),
                                   ('networking/' + self.topic, '*'), ('examples/' + self.topic, '*')]:
            files += [p for p in (PHASE / directory).glob(pattern) if p.is_file()]
        files += [PHASE / ('scripts/' + self.topic + '.sh'), PHASE / 'scripts/phase02.sh', PHASE / 'ansible/playbooks/phase02.yml',
                  PHASE / 'ansible/vars/phase02.yml', ROOT / 'ops/versions.lock.yaml', Path(pol.__file__),
                  Path(pol.base.__file__), Path(pol.gw.__file__), Path(pol.gw.l2.__file__),
                  Path(pol.gw.l2.common.__file__)]
        if self.topic=='mesh':
            files += list((PHASE/'examples/mesh-identity').glob('*'))
            files += [PHASE/'tests/integration/dataplane/materials.py',
                      PHASE/'tests/integration/resource-governance/materials.py']
            files=[p for p in files if p.is_file()]
        return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))}

    def bind_sources(self, mode):
        value = self.sources()
        save(self.attempt / 'source.json', value)
        if mode == 'all':
            save(self.records / 'state/source.json', value)
        return value

    def document(self, kind, name, namespace=None):
        return {'kind': kind, 'metadata': {'name': name, **({'namespace': namespace} if namespace else {})}}

    def key(self, obj):
        m = obj['metadata']
        return obj['kind'] + '/' + m.get('namespace', '') + '/' + m['name']

    def receipt(self, obj):
        return self.records / 'state' / ('object-' + self.key(obj).replace('/', '-') + '.json')

    def owned(self, obj):
        m, kind = obj['metadata'], obj['kind']
        require(kind in RESOURCE, '对象类型越界：' + kind)
        require((kind == 'Namespace' and m['name'] in self.namespaces)
            or (kind == 'PriorityClass' and m['name'].startswith('cnpl-' + self.stage.replace('.', '') + '-'))
            or (kind not in ['Namespace', 'PriorityClass'] and m.get('namespace') in self.namespaces), '对象范围越界')
        require(m.get('labels', {}).get(LABEL) == self.run, '对象 run 不同')

    def apply(self, filename):
        commands = []
        for obj in yaml.safe_load_all((self.attempt / filename).read_text()):
            if not obj:
                continue
            self.owned(obj)
            m = obj['metadata']
            current = optional(obj['kind'], m['name'], m.get('namespace'))
            path = self.receipt(obj)
            saved = json.loads(path.read_text()) if path.exists() else None
            require(not current or (saved and saved.get('uid') == current['metadata']['uid'] and current['metadata'].get('labels', {}).get(LABEL) == self.run), '拒绝覆盖同名对象：' + self.key(obj))
            if not path.exists():
                save(path, {'key': self.key(obj), 'uid': None, 'run': self.run})
            file = self.attempt / ('input-' + self.key(obj).replace('/', '-') + '.json')
            save(file, obj)
            apply = ['apply'] + (['--server-side', '--field-manager=cnpl-gateway-crds'] if obj['kind'] == 'CustomResourceDefinition' else [])
            commands += [self.command(self.k + apply + ['--dry-run=server', '--validate=strict', '-f', file]),
                         self.command(self.k + apply + ['--validate=strict', '-f', file, '-o', 'json'], self.key(obj))]
        return commands

    def command(self, argv, key=None, allowed_rc=None):
        return {'argv': [str(a) for a in argv], 'key': key, 'allowed_rc': allowed_rc or [0]}

    def record(self, results):
        for result in results:
            key = result.get('phase_command', result.get('item', {})).get('key')
            if key and result.get('rc') == 0:
                obj = json.loads(result['stdout'])
                require(self.key(obj) == key and obj['metadata'].get('labels', {}).get(LABEL) == self.run, '实际对象归属不符')
                save(self.receipt(obj), {'key': key, 'uid': obj['metadata']['uid'], 'run': self.run})

    def validate(self):
        count = 0
        for file in sorted(self.attempt.glob('*.yaml')):
            for obj in yaml.safe_load_all(file.read_text()):
                if not obj:
                    continue
                clone = json.loads(json.dumps(obj))
                if clone['kind'] not in ['Namespace', 'PriorityClass']:
                    clone['metadata']['namespace'] = 'lab-core'
                    clone['metadata']['name'] = 'cnpl-preview-' + clone['metadata']['name']
                call(K + ['apply', '--dry-run=server', '--validate=strict', '-f', '-'], json.dumps(clone))
                count += 1
        return {'passed': True, 'server_dry_run_objects': count, 'persisted': False}

    def wait(self, name, check, seconds=90):
        deadline, errors = time.monotonic() + seconds, []
        while time.monotonic() < deadline:
            try:
                value = check()
                save(self.attempt / (name + '.json'), value)
                return value
            except (ValueError, KeyError) as error:
                errors.append(str(error))
                time.sleep(1)
        save(self.attempt / (name + '-errors.json'), errors)
        raise ValueError(name + ' 未收敛：' + errors[-1])

    def pod(self, name, ns=None):
        ns = ns or self.namespaces[0]
        value = get('pod', name, ns)
        require(value['metadata'].get('labels', {}).get(LABEL) == self.run, 'Pod 归属不同')
        return value

    def ready(self, name, node=None, ns=None):
        value = self.pod(name, ns)
        require(pol.base.ready(value) and not value['metadata'].get('deletionTimestamp'), name + ' 尚未 Ready')
        require(not node or value['spec']['nodeName'] == node, 'Pod 在错误 VM')
        return {'passed': True, 'uid': value['metadata']['uid'], 'node': value['spec']['nodeName'], 'pod': name}

    def pending(self, name, reason, ns=None):
        value = self.pod(name, ns)
        conditions = value.get('status', {}).get('conditions') or []
        require(any(c['type'] == 'PodScheduled' and c['status'] == 'False' and c['reason'] == 'Unschedulable' for c in conditions), name + ' 不是 Unschedulable')
        events = get('events', namespace=ns or self.namespaces[0])['items']
        matched = [e for e in events if e.get('involvedObject', {}).get('uid') == value['metadata']['uid'] and e.get('reason') == 'FailedScheduling' and reason.lower() in e.get('message', '').lower()]
        require(matched, '缺少本次 UID 对应的调度事件：' + name)
        return {'passed': True, 'pod_uid': value['metadata']['uid'], 'conditions': conditions, 'events': matched}

    def delete(self, obj):
        m, kind = obj['metadata'], obj['kind']
        current = optional(kind, m['name'], m.get('namespace'))
        if not current:
            return []
        self.owned(current)
        path = self.receipt(obj)
        require(path.exists(), '缺少创建意图')
        saved = json.loads(path.read_text())
        require(not saved.get('uid') or saved['uid'] == current['metadata']['uid'], '删除前 UID 改变')
        api, plural = RESOURCE[kind]
        url = ('/api/' if api == 'v1' else '/apis/') + api + '/'
        url += ('namespaces/' + m['namespace'] + '/' if m.get('namespace') else '') + plural + '/' + m['name']
        body = self.attempt / ('delete-' + self.key(obj).replace('/', '-') + '.json')
        save(body, {'apiVersion': 'v1', 'kind': 'DeleteOptions', 'preconditions': {'uid': current['metadata']['uid']}, 'propagationPolicy': 'Foreground'})
        args = self.k + ['wait', '--for=delete', kind + '/' + m['name'], '--timeout=120s'] + (['-n', m['namespace']] if m.get('namespace') else [])
        return [self.command(self.k + ['delete', '--raw', url, '-f', body]), self.command(args)]

    def cleanup(self):
        commands = []
        for ns in self.namespaces:
            obj = optional('Namespace', ns)
            if not obj:
                continue
            for kind in ['pods','deployments','services','configmaps','resourcequotas','limitranges','poddisruptionbudgets','serviceaccounts','jobs','roles','rolebindings','persistentvolumeclaims']:
                for item in get(kind, namespace=ns)['items']:
                    if (kind, item['metadata']['name']) in [('serviceaccounts','default'),('configmaps','kube-root-ca.crt')]:
                        continue
                    require(item['metadata'].get('labels', {}).get(LABEL) == self.run, '存在外来对象，停止清理：' + self.key(item))
            require(not pol.gw.secret_list(ns), '存在外来 Secret，停止清理')
            commands += self.delete(obj)
        for path in (self.records / 'state').glob('object-PriorityClass-*.json'):
            name = json.loads(path.read_text())['key'].split('/')[-1]
            commands += self.delete(self.document('PriorityClass', name))
        return commands

    def accept(self, names, blocked=None):
        values = {name: json.loads((self.attempt / (name + '.json')).read_text()) for name in names}
        require(all(value.get('passed') for value in values.values()), '缺少必需结果')
        require(self.sources() == json.loads((self.records / 'state/source.json').read_text()), '执行中源码变化')
        value = {'stage': self.stage, 'run': self.run, 'cluster_uid': self.context['cluster_uid'],
            'available_cases_passed': True, 'passed': not blocked, 'phase_complete': not blocked,
            'results': values, 'blocked': blocked or {}, 'attempt': str(self.attempt)}
        save(self.records / 'passed.json', value)
        return value

    def final(self):
        require(all(optional('Namespace', ns) is None for ns in self.namespaces), '实验空间未清理')
        baseline = self.records / 'state/protected.json'
        require(not baseline.exists() or self.protected() == json.loads(baseline.read_text()), '既有资源 UID/spec 变化')
        value = {'stage': self.stage, 'run': self.run, 'cluster_uid': self.context['cluster_uid'], 'cleanup_passed': True,
            'temporary_namespaces_absent': True, 'existing_resources_unchanged': True}
        save(self.records / 'state/closed.json', value)
        return value
