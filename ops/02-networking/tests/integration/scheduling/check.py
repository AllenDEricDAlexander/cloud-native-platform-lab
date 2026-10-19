#!/usr/bin/env python3
"""VM 调度实验；只生成受原 UID/字段保护的写入计划，由 Ansible 执行。"""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'phase02'))
import runtime as r
import cli
import yaml

TOPIC, STAGE = 'scheduling', '02.07'
NAMESPACES = ['lab-scheduling']
COLOR, DOMAIN, RUN, ROLE = 'cnpl.io/sched-color', 'cnpl.io/vm-domain', 'cnpl.io/scheduling-run', 'cnpl.io/scheduling-role'
STORAGE = 'storage03.k8s.internal.egon.top'
TAINT = 'cnpl.io/scheduling-test'


def tolerates(tolerations, key, value, effect):
    return any(t.get('tolerationSeconds') is None and (not t.get('effect') or t['effect'] == effect)
        and ((t.get('operator', 'Equal') == 'Exists' and (not t.get('key') or t['key'] == key))
             or (t.get('operator', 'Equal') == 'Equal' and t.get('key') == key and t.get('value', '') == value)) for t in tolerations)


def noexecute_safe(s):
    pods = json.loads(r.call(r.K + ['get','pods','-A','--field-selector','spec.nodeName=' + STORAGE,'-o','json']))['items']
    others = [p for p in pods if p['metadata']['namespace'] not in NAMESPACES and p['status'].get('phase') not in ['Succeeded','Failed']]
    r.require(all(tolerates(p['spec'].get('tolerations') or [], TAINT, s.run, 'NoExecute') for p in others),
        'storage03 有不无限容忍该 NoExecute 的现有 Pod，拒绝添加污点')
    return [{'namespace':p['metadata']['namespace'],'name':p['metadata']['name'],'uid':p['metadata']['uid']} for p in others]


def prepare(s):
    nodes = [r.get('node', n) for n in r.WORKERS + [STORAGE]]
    before = {}
    for node in nodes:
        name, meta = node['metadata']['name'], node['metadata']
        r.require(RUN not in meta.get('labels', {}) and not any(t['key'] == TAINT for t in node['spec'].get('taints', [])), '有未恢复的调度字段，请先原批 recover')
        before[name] = {'uid':meta['uid'], 'labels':{key:meta.get('labels', {}).get(key) for key in [COLOR,DOMAIN,RUN,ROLE]},
                        'taints':node['spec'].get('taints', [])}
    s.context['node_original'] = before
    r.save(s.path, s.context)
    noexecute_safe(s)
    image = yaml.safe_load((r.ROOT / 'ops/versions.lock.yaml').read_text())['components']['policy_fixture']['internal_source']
    oversized = str(int(r.quantity(nodes[0]['status']['allocatable']['cpu'])) + 1)
    s.render({'image':image, 'oversized_cpu':oversized})


def steps(s):
    return yaml.safe_load((r.PHASE / 'networking/scheduling/cases.yml').read_text())


def node_patch(s, name, labels=None, effect=None, clear_taint=False):
    node = r.get('node', name)
    original = s.context['node_original'][name]
    r.require(node['metadata']['uid'] == original['uid'], 'Node UID 改变')
    patches = [{'op':'test','path':'/metadata/uid','value':original['uid']}]
    for key, value in (labels or {}).items():
        path = '/metadata/labels/' + key.replace('~','~0').replace('/','~1')
        current = node['metadata'].get('labels', {}).get(key)
        allowed = [original['labels'].get(key)] + {RUN:[s.run],DOMAIN:[name.split('.')[0]],ROLE:['worker'],COLOR:['blue','red']}[key]
        r.require(current in allowed, '节点标签被其他操作修改：' + key)
        if current == value:
            continue
        if current is not None:
            patches.append({'op':'test','path':path,'value':current})
        else:
            patches.append({'op':'test','path':'/metadata/resourceVersion','value':node['metadata']['resourceVersion']})
        patches.append({'op':'remove','path':path} if value is None else {'op':'add','path':path,'value':value})
    if effect or clear_taint:
        taints = node['spec'].get('taints', [])
        mine = [t for t in taints if t['key'] == TAINT]
        r.require(all(t.get('value') == s.run for t in mine), '测试污点已属于其他操作')
        wanted = [t for t in taints if t['key'] != TAINT]
        if effect:
            if effect == 'NoExecute':
                noexecute_safe(s)
            wanted.append({'key':TAINT,'value':s.run,'effect':effect})
        if wanted != taints:
            if 'taints' in node['spec']:
                patches.append({'op':'test','path':'/spec/taints','value':taints})
            else:
                patches.append({'op':'test','path':'/metadata/resourceVersion','value':node['metadata']['resourceVersion']})
            patches.append({'op':'add','path':'/spec/taints','value':wanted})
    if len(patches) == 1:
        return []
    file = s.attempt / ('patch-node-' + name + '-' + str(len(list(s.attempt.glob('patch-node-*')))) + '.json')
    r.save(file, patches)
    return [s.command(r.K + ['patch','node',name,'--type=json','--patch-file',file,'-o','json'])]


def plan(s, name):
    if name == 'vm-labels':
        return [cmd for node in r.WORKERS for cmd in node_patch(s,node,{RUN:s.run,DOMAIN:node.split('.')[0],ROLE:'worker', **({COLOR:'blue'} if node == r.WORKERS[0] else {})})]
    if name in ['label-red','label-blue']:
        return node_patch(s,r.WORKERS[0],{COLOR:name.split('-')[1]})
    if name in ['no-schedule','prefer','no-execute']:
        return node_patch(s,STORAGE,effect={'no-schedule':'NoSchedule','prefer':'PreferNoSchedule','no-execute':'NoExecute'}[name])
    if name == 'untaint':
        return node_patch(s,STORAGE,clear_taint=True)
    return []


def observe(s, name):
    if name == 'vm-labels':
        values = {node:r.get('node',node)['metadata']['labels'] for node in r.WORKERS}
        r.require(all(values[n].get(RUN) == s.run and values[n].get(DOMAIN) == n.split('.')[0] and values[n].get(ROLE) == 'worker' for n in r.WORKERS), 'VM 标签未生效')
        return {'passed':True,'vm_domains':{n:values[n][DOMAIN] for n in r.WORKERS},'physical_awareness':False}
    if name == 'selector':
        return {'passed':True,'required':s.ready('required',r.WORKERS[0]),
            'preferred':s.ready('preferred'),'unmatched':s.pending('selector-pending','affinity'),
            'insufficient':s.pending('cpu-pending','Insufficient cpu')}
    if name == 'label-red':
        row = s.ready('required',r.WORKERS[0])
        r.require(row['uid'] == json.loads(s.receipt(s.document('Pod','required',NAMESPACES[0])).read_text())['uid'], 'IgnoredDuringExecution Pod 被重建')
        label = r.get('node',r.WORKERS[0])['metadata']['labels'][COLOR]
        r.require(label == 'red', '标签没有变为 red')
        return {'passed':True,'original_pod':row,'label':label}
    if name == 'ignored-new':
        return s.pending('ignored-new','affinity')
    if name == 'label-blue':
        return s.ready('ignored-new',r.WORKERS[0])
    if name in ['taint-base','no-schedule']:
        return s.ready('base-notol',STORAGE)
    if name == 'taint-pending':
        return s.pending('taint-pending','taint')
    if name == 'taint-tolerated':
        return s.ready('taint-tolerated',STORAGE)
    if name == 'prefer':
        r.require(any(t['key'] == TAINT and t.get('value') == s.run and t['effect'] == 'PreferNoSchedule' for t in r.get('node',STORAGE)['spec'].get('taints', [])), '软污点没有生效')
        return {'passed':True,'effect':'PreferNoSchedule'}
    if name == 'prefer-run':
        return s.ready('prefer-run',STORAGE)
    if name == 'noexecute-base':
        return {'passed':True,'forever':s.ready('forever',STORAGE),'timed':s.ready('timed',STORAGE)}
    if name == 'no-execute':
        for pod in ['base-notol','timed']:
            r.require(r.optional('Pod',pod,NAMESPACES[0]) is None, '等待本批 NoExecute 驱逐：' + pod)
        return {'passed':True,'untolerated_removed':True,'five_second_toleration_removed':True,'forever':s.ready('forever',STORAGE)}
    if name == 'untaint':
        r.require(not any(t['key'] == TAINT for t in r.get('node',STORAGE)['spec'].get('taints', [])), '测试污点未撤销')
        return {'passed':True}
    if name == 'affinity':
        anchor, colocated = s.ready('anchor',r.WORKERS[0]), s.ready('colocated',r.WORKERS[0])
        hard = [s.pod('hard-' + str(i)) for i in range(3)]
        running = [p for p in hard if r.pol.base.ready(p)]
        pending = [p for p in hard if not p['spec'].get('nodeName')]
        r.require(len(running) == 2 and len({p['spec']['nodeName'] for p in running}) == 2 and len(pending) == 1, '硬反亲和应为两个不同 VM 就绪、一个 Pending')
        denied = s.pending(pending[0]['metadata']['name'],'anti-affinity')
        soft = [s.ready('soft-' + str(i)) for i in range(3)]
        return {'passed':True,'anchor':anchor,'colocated':colocated,'hard_pending':denied,'soft_nodes':[p['node'] for p in soft]}
    if name == 'spread':
        rows = [s.ready('spread-' + str(i)) for i in range(3)]
        counts = {n:sum(p['node'] == n for p in rows) for n in r.WORKERS}
        r.require(sorted(counts.values()) == [1,2], 'maxSkew=1 分布不符')
        limited = [s.pod('limited-' + str(i)) for i in range(2)]
        r.require(sum(r.pol.base.ready(p) for p in limited) == 1, 'minDomains=2 只有一个 VM 时应限制第二副本')
        pending = next(p for p in limited if not p['spec'].get('nodeName'))
        denied = s.pending(pending['metadata']['name'],'topology spread')
        soft = [s.ready('anywhere-' + str(i),r.WORKERS[0]) for i in range(3)]
        return {'passed':True,'distribution':counts,'min_domains_pending':denied,'schedule_anyway':soft}
    raise ValueError('未定义观察：' + name)


def restore(s):
    commands = []
    for node, original in s.context.get('node_original', {}).items():
        commands += node_patch(s,node,original['labels'],clear_taint=node == STORAGE)
    return commands


def final(s):
    for node, original in s.context.get('node_original', {}).items():
        current = r.get('node',node)
        r.require(current['metadata']['uid'] == original['uid'] and current['spec'].get('taints', []) == original['taints'], '节点污点或 UID 没有恢复')
        r.require(all(current['metadata'].get('labels', {}).get(k) == v for k,v in original['labels'].items()), '节点标签没有恢复')


if __name__ == '__main__':
    cli.run(sys.modules[__name__])
