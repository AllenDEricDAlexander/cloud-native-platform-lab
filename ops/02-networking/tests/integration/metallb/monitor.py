"""有界 HTTP/ARP 观测。单独记录新连接、原有连接及重连，不执行集群变更。"""
from datetime import datetime, timezone
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time


def require(value, reason):
    if not value:
        raise ValueError(reason)


def mac_address(text):
    match = re.search(r'[0-9a-f]{1,2}(?::[0-9a-f]{1,2}){5}', text, re.I)
    return ':'.join(part.zfill(2) for part in match[0].lower().split(':')) if match else None


def arp(vip, macs):
    reply = subprocess.run([shutil.which('arp'), '-n', vip], capture_output=True, text=True, timeout=3)
    value = mac_address(reply.stdout)
    return {'mac': value, 'vm': next((name for name, address in macs.items() if address == value), None), 'text': reply.stdout.strip(), 'rc': reply.returncode, 'observed_mono': time.monotonic()}


def request(connection, backends, kind, epoch=0):
    started = time.monotonic()
    row = {'kind': kind, 'epoch': epoch, 'started_mono': started, 'at': datetime.now(timezone.utc).isoformat(), 'passed': False}
    try:
        if connection.sock is not None:
            row['local'] = list(connection.sock.getsockname())
        connection.request('GET', '/', headers={'Connection': 'keep-alive' if kind == 'existing' else 'close'})
        row['local'] = list(connection.sock.getsockname())
        reply = connection.getresponse()
        row['status'] = reply.status
        data = reply.read(8193)
        row['connection_close'] = reply.will_close
        require(len(data) <= 8192 and reply.status == 200, 'HTTP 状态或响应长度不符')
        body = json.loads(data)
        require(isinstance(body, dict) and isinstance(body.get('pod'), str) and body['pod'] in backends and backends[body['pod']] == body.get('uid'), 'HTTP 后端不是本批当前 Pod UID')
        row.update(passed=True, response=body)
    except (OSError, http.client.HTTPException, ValueError) as error:
        row.update(error_type=type(error).__name__, error=str(error), errno=error.errno if isinstance(error, OSError) else None)
    row['finished_mono'] = time.monotonic()
    row['elapsed_ms'] = round((row['finished_mono'] - started) * 1000, 3)
    return row


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    os.replace(temporary, path)


def observe(attempt, vip, macs, backends, seconds=210):
    require(10 <= seconds <= 210, '观测时长越界')
    attempt = Path(attempt)
    deadline = time.monotonic() + seconds
    existing = http.client.HTTPConnection(vip, 8080, timeout=1)
    epoch, warmed, initial_local, rows = 0, 0, None, 0
    try:
        with (attempt / 'traffic.jsonl').open('x') as output:
            while time.monotonic() < deadline and not (attempt / 'monitor.stop').exists():
                before = arp(vip, macs)
                fresh = http.client.HTTPConnection(vip, 8080, timeout=1)
                try:
                    new = request(fresh, backends, 'new')
                finally:
                    fresh.close()
                neighbor = arp(vip, macs)
                new['arp'] = neighbor if before['vm'] == neighbor['vm'] and before['mac'] == neighbor['mac'] else dict(neighbor, vm=None, changed_during_sample=True)
                old = request(existing, backends, 'existing', epoch)
                old['arp'] = arp(vip, macs)
                for row in [new, old]:
                    output.write(json.dumps(row, ensure_ascii=False) + '\n')
                    rows += 1
                output.flush()
                if old['passed'] and not old['connection_close']:
                    if not (attempt / 'monitor.ready.json').exists():
                        if old['local'] != initial_local:
                            warmed, initial_local = 0, old['local']
                        warmed = warmed + 1 if new['passed'] and new['arp']['vm'] else 0
                        if warmed >= 5:
                            atomic_json(attempt / 'monitor.ready.json', {'ready': True, 'initial_local': initial_local, 'initial_epoch': epoch, 'backend_uid': old['response']['uid'], 'at_mono': time.monotonic()})
                else:
                    existing.close()
                    existing = http.client.HTTPConnection(vip, 8080, timeout=1)
                    epoch += 1
                    warmed = 0
                time.sleep(0.2)
    finally:
        existing.close()
    stopped = (attempt / 'monitor.stop').exists()
    value = {'stopped_by_controller': stopped, 'bounded_seconds': seconds, 'rows': rows, 'existing_connection_epochs': epoch + 1}
    atomic_json(attempt / 'monitor-summary.json', value)
    require(stopped, '观测达到时限，未收到正常停止标记')
    return value


def analyse(attempt, before, during):
    attempt = Path(attempt)
    summary = json.loads((attempt / 'monitor-summary.json').read_text())
    warm = json.loads((attempt / 'monitor.ready.json').read_text())
    marker = json.loads((attempt / 'fault-start.json').read_text())
    rows = [json.loads(line) for line in (attempt / 'traffic.jsonl').read_text().splitlines()]
    require(summary['stopped_by_controller'] and warm['ready'] and len(rows) == summary['rows'], '观测未完整结束或原有连接没有预热')
    require(before['entry_vm'] != during['entry_vm'], 'VIP 未迁移到另一 VM')
    changed = [r for r in rows if r['kind'] == 'new' and r['passed'] and r['started_mono'] >= marker['mono'] and r['arp']['vm'] == during['entry_vm']]
    require(len(changed) >= 3, '缺少迁移后至少三个实际成功的新连接/ARP 样本')
    elapsed = max(changed[0]['finished_mono'], changed[0]['arp']['observed_mono']) - marker['mono']
    require(0 <= elapsed <= 90, 'VIP 数据面恢复超出 90 秒观察上限')
    existing = [r for r in rows if r['kind'] == 'existing' and r['started_mono'] >= marker['mono'] and r['epoch'] == warm['initial_epoch'] and r.get('local') == warm['initial_local']]
    return {'passed': True, 'from_vm': before['entry_vm'], 'to_vm': during['entry_vm'], 'first_observed_new_connection_recovery_seconds': round(elapsed, 3), 'new_connection_samples': sum(r['kind'] == 'new' for r in rows), 'new_connection_failed_samples': sum(r['kind'] == 'new' and not r['passed'] for r in rows), 'original_connection_local': warm['initial_local'], 'original_connection_successes_after_fault': sum(r['passed'] for r in existing), 'original_connection_failed_samples_after_fault': sum(not r['passed'] for r in existing), 'existing_connection_epochs': summary['existing_connection_epochs'], 'note': '定时应用请求与 ARP 采样；失败样本不是网络丢包率，已有连接按实际断开/重连记录。'}
