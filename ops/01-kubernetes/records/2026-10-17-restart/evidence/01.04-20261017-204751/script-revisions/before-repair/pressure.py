#!/usr/bin/env python3
"""01.04.05 worker02 的软阈值驱逐；默认 check。run 后无论成败都恢复原配置并核对节点。"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

import yaml

import lab


SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'ConnectTimeout=5',
       '-i', str(Path.home() / '.ssh/cnpl_lab_ed25519'), 'root@192.168.9.110']


def remote(script, payload=None):
    return lab.command(SSH + [script], payload, timeout=100).stdout


def preflight():
    current = lab.check()
    pods = json.loads(lab.api('get', 'pods', '-A', '--field-selector=spec.nodeName=' + lab.PRESSURE_WORKER, '-o', 'json'))['items']
    for pod in pods:
        if pod['status'].get('phase') in ['Succeeded', 'Failed']:
            continue
        if pod['metadata']['namespace'] != 'kube-system' or pod['spec'].get('priority', 0) < 2000000000:
            raise ValueError('worker02 存在非系统关键负载，先迁移/清理它：' + pod['metadata']['name'])
    raw = remote('cat /var/lib/kubelet/config.yaml')
    config = yaml.safe_load(raw)
    if config.get('evictionSoft') or config.get('evictionSoftGracePeriod'):
        raise ValueError('已有软驱逐策略，拒绝覆盖')
    if config.get('evictionHard', {}).get('memory.available') != '500Mi':
        raise ValueError('硬驱逐基线有漂移')
    return current, raw, config


def helper(state, mode, payload=None):
    if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}', state['run']) or state['helper'] != '/root/cnpl-pod-pressure-' + state['run'] + '.py':
        raise ValueError('节点恢复入口格式错误')
    return json.loads(remote('/usr/bin/python3 ' + state['helper'] + ' ' + mode + ' --run ' + state['run'], payload))


def system_health():
    lab.check()
    pods = json.loads(lab.api('-n', 'kube-system', 'get', 'pods', '-o', 'json'))['items']
    if any(p['status'].get('phase') != 'Succeeded' and not lab.condition(p, 'Ready', 'True') for p in pods if not p['metadata'].get('deletionTimestamp')):
        raise ValueError('系统 Pod 尚未恢复 Ready')


def restore(args, state):
    if state.get('armed'):
        try:
            result = helper(state, 'restore')
        except (ValueError, subprocess.SubprocessError):
            # arm 可能在安装回退/修改前就失败；只有远端仍是原始字节才允许继续。
            if hashlib.sha256(remote('cat /var/lib/kubelet/config.yaml').encode()).hexdigest() != state['original_sha256']:
                raise ValueError('自动恢复未确认，保持 cordon；先重跑 pressure.py restore')
            if remote('systemctl is-active kubelet').strip() != 'active':
                raise ValueError('原配置已还原但 kubelet 未运行，保持 cordon')
            result = {'sha256': state['original_sha256']}
        if result.get('sha256') != state['original_sha256']:
            raise ValueError('恢复后的配置 SHA 不匹配')
        unit = 'cnpl-pod-pressure-' + state['run'].lower() + '.timer'
        if remote('systemctl show ' + unit + ' --property=LoadState --value').strip() != 'not-found':
            remote('systemctl stop ' + unit)
        state['config_restored'] = True
        save(args, state)
    # Mac 中断时独立定时器只恢复 kubelet，保留 cordon；本入口检查健康后恢复可调度。
    deadline = time.monotonic() + 420
    while time.monotonic() < deadline:
        node = lab.get('node', lab.PRESSURE_WORKER)
        if lab.condition(node, 'Ready', 'True') and all(lab.condition(node, name, 'False') for name in ['MemoryPressure', 'DiskPressure', 'PIDPressure']):
            break
        time.sleep(3)
    else:
        raise ValueError('worker02 恢复超时，保持 cordon；查看 pressure.json 并重跑 restore')
    if state.get('cordoned'):
        lab.api('uncordon', lab.PRESSURE_WORKER, platform=True)
        state['cordoned'] = False
    deadline = time.monotonic() + 120
    while True:
        try:
            system_health()
            break
        except ValueError:
            if time.monotonic() > deadline:
                raise
            time.sleep(3)
    state['restored'] = True
    save(args, state)
    print('WORKER02 RESTORE PASS；原 kubelet SHA、可调度、无压力及系统 Pod 健康均确认', flush=True)


def save(args, state):
    lab.write_state(args.records / 'pressure.json', state)


def experiment(args, lab_state):
    lab.require(lab_state, 'memory')
    current, raw, config = preflight()
    if current['cluster_uid'] != lab_state['cluster_uid']:
        raise ValueError('运行状态不属于当前集群')
    if (args.records / 'pressure.json').exists():
        raise ValueError('已有压力实验记录；先 restore，不覆盖失败证据')
    state = {'run': lab_state['run'], 'cluster_uid': current['cluster_uid'],
             'node_uid': lab.get('node', lab.PRESSURE_WORKER)['metadata']['uid'],
             'original_sha256': hashlib.sha256(raw.encode()).hexdigest(), 'armed': False, 'cordoned': False,
             'restored': False, 'helper': '/root/cnpl-pod-pressure-' + lab_state['run'] + '.py'}
    save(args, state)
    try:
        lab.create(lab.objects()['p04-pressure'], lab_state)
        victim = lab.wait('pressure', lambda x: lab.condition(x, 'Ready', 'True'))
        # 保存后 cordon；写入意图在操作前，连接中断也能通过 restore 解除本次维护。
        state['cordoned'] = True
        save(args, state)
        lab.api('cordon', lab.PRESSURE_WORKER, platform=True)
        deadline = time.monotonic() + 45
        while True:
            sample = json.loads(lab.api('get', '--raw=/api/v1/nodes/' + lab.PRESSURE_WORKER + '/proxy/stats/summary', platform=True))
            usage = next((p.get('memory', {}).get('workingSetBytes', 0) for p in sample.get('pods', [])
                          if p['podRef']['uid'] == victim['metadata']['uid']), 0)
            if usage >= 64 * 1024 ** 2:
                break
            if time.monotonic() > deadline:
                raise ValueError('测试 Pod 内存用量尚未计入 kubelet 统计，拒绝选择过期阈值')
            time.sleep(2)
        available = sample['node']['memory']['availableBytes']
        if available < 4 * 1024 ** 3:
            raise ValueError('真实可用内存不足 4GiB，拒绝实验')
        threshold = available + 16 * 1024 ** 2
        config.update(evictionSoft={'memory.available': str(threshold)}, evictionSoftGracePeriod={'memory.available': '45s'},
                      evictionMaxPodGracePeriod=5)
        state.update(available_bytes=available, threshold_bytes=threshold)
        lab.command(['scp', '-q', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-i', str(Path.home() / '.ssh/cnpl_lab_ed25519'),
                     lab.HERE / 'node-pressure.py', 'root@192.168.9.110:' + state['helper']])
        # 先标记可能已 arm，SSH 响应丢失也不能跳过恢复。
        state['armed'] = True
        save(args, state)
        result = helper(state, 'arm', {'original_sha256': state['original_sha256'], 'config': config})
        if result.get('armed') is not True:
            raise ValueError('独立回退定时器没有确认')
        print('只临时调高 worker02 memory.available 软阈值；45 秒宽限，150 秒独立自动回退。', flush=True)
        deadline = time.monotonic() + 100
        saw_pressure = False
        while time.monotonic() < deadline:
            node = lab.get('node', lab.PRESSURE_WORKER)
            pod = lab.get('pod', 'p04-pressure')
            saw_pressure |= lab.condition(node, 'MemoryPressure', 'True')
            with (args.records / 'pressure-timeline.jsonl').open('a') as stream:
                stream.write(json.dumps({'utc': datetime.now(timezone.utc).isoformat(), 'conditions': node['status']['conditions'],
                                         'pod_phase': pod['status'].get('phase'), 'pod_reason': pod['status'].get('reason')}) + '\n')
            if pod['status'].get('reason') == 'Evicted':
                state['evicted'] = lab.capture('pressure', args, 'evicted')['status']
                if 'memory' not in pod['status'].get('message', '').lower() or not saw_pressure:
                    raise ValueError('未取得 MemoryPressure 及 memory 驱逐完整证据')
                state['observed_memory_pressure'] = True
                save(args, state)
                break
            time.sleep(2)
        else:
            raise ValueError('没有观察到真实 Evicted；不把 API 删除或超时冒充驱逐')
    finally:
        restore(args, state)
    lab.delete('pressure', lab_state)
    lab.mark(args, lab_state, 'pressure')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', nargs='?', default='check', choices=['check', 'run', 'restore'])
    parser.add_argument('--records', type=Path, required=True)
    args = parser.parse_args()
    args.records = args.records.resolve()
    if args.mode == 'check':
        preflight()
        print('WORKER02 PRESSURE PREFLIGHT PASS；没有修改配置或施加压力')
        return
    state = json.loads((args.records / 'state.json').read_text())
    if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}', state['run']):
        raise ValueError('运行编号格式错误')
    if args.mode == 'run':
        experiment(args, state)
    else:
        pressure_state = json.loads((args.records / 'pressure.json').read_text())
        if pressure_state['cluster_uid'] != lab.get('namespace', 'kube-system')['metadata']['uid'] or pressure_state['node_uid'] != lab.get('node', lab.PRESSURE_WORKER)['metadata']['uid']:
            raise ValueError('集群或 worker02 身份变化，拒绝自动恢复')
        restore(args, pressure_state)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        raise SystemExit('PRESSURE LAB FAIL: ' + str(error))
