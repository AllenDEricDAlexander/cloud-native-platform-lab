"""有界、无代理的实际协议请求；TLS始终验证既有公开根证书和SNI。"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import http.client as http_client
import json
import math
import os
from pathlib import Path
import re
import select
import socket
import ssl
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[5]
CA = ROOT / 'ops/00-preparation/pki/public/cnpl-lab-root-ca.crt'
DEMO, GRPC = 'demo.svc.internal.egon.top', 'grpc-demo.svc.internal.egon.top'


def require(value, reason):
    if not value:
        raise ValueError(reason)


class TLSConnection(http_client.HTTPSConnection):
    def __init__(self, address, host, port=443, timeout=5, ca=CA):
        context = ssl.create_default_context(cafile=str(ca))
        context.set_alpn_protocols(['http/1.1'])
        super().__init__(host, port=port, timeout=timeout, context=context)
        self.address = address

    def connect(self):
        raw = socket.create_connection((self.address, self.port), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def http(address, path, host=DEMO, tls=True, port=None, headers=None, timeout=5, ca=CA):
    connection = TLSConnection(address, host, port=port or 443, timeout=timeout, ca=ca) if tls else http_client.HTTPConnection(address, port or 80, timeout=timeout)
    nonce = uuid.uuid4().hex
    request_headers = {'Host': host, 'X-Cnpl-Nonce': nonce, 'Connection': 'close'}
    request_headers.update(headers or {})
    start = time.monotonic()
    try:
        connection.request('GET', path, headers=request_headers)
        peer = hashlib.sha256(connection.sock.getpeercert(binary_form=True)).hexdigest() if tls else None
        response = connection.getresponse()
        data = response.read(32769)
        require(len(data) <= 32768, 'HTTP响应超出证据上限')
        text = data.decode('utf-8', errors='replace')
        try:
            body = json.loads(text)
        except ValueError:
            body = None
        return {'at': datetime.now(timezone.utc).isoformat(), 'started_mono': start, 'finished_mono': time.monotonic(), 'elapsed_ms': round((time.monotonic() - start) * 1000, 3), 'address': address, 'host': host, 'path': path, 'nonce': nonce, 'status': response.status, 'headers': {k.lower(): v for k, v in response.getheaders()}, 'body': body, 'text': text[:2048] if body is None else '', 'tls_peer_sha256': peer}
    finally:
        connection.close()


def identity(row, backends, version=None, nonce=None, protocol=None):
    body = row.get('body') if 'body' in row else row
    require(isinstance(body, dict) and isinstance(body.get('pod'), str) and body['pod'] in backends and backends[body['pod']]['uid'] == body.get('uid'), '响应未命中当前就绪后端UID')
    expected = backends[body['pod']]['version']
    require(body.get('version') == expected and (version is None or version == expected), '命中错误版本后端')
    if nonce is not None:
        require(body.get('nonce') == nonce, '后端没有返回本次请求nonce')
    if protocol:
        require(body.get('protocol') == protocol, '实际后端协议不同')
    if 'body' in row:
        require(row['status'] == 200, 'HTTP请求失败')
    return body


def exchange(address, protocol, backends):
    nonce = uuid.uuid4().hex
    require(protocol in ['tcp', 'udp'], '传输协议越界')
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM if protocol == 'tcp' else socket.SOCK_DGRAM)
    connection.settimeout(3)
    try:
        connection.connect((address, 9000 if protocol == 'tcp' else 9001))
        connection.sendall((nonce + ('\n' if protocol == 'tcp' else '')).encode())
        if protocol == 'tcp':
            with connection.makefile('rb') as stream:
                data = stream.readline(8193)
        else:
            data = connection.recv(8193)
        require(len(data) <= 8192, '传输响应过大')
        value = json.loads(data)
        identity(value, backends, version='v1', nonce=nonce, protocol=protocol)
        return {'passed': True, 'protocol': protocol, 'response': value, 'nonce': nonce}
    finally:
        connection.close()


def grpc(client, address, backends, port=443, ca=CA):
    direct = {name: value for name, value in os.environ.items() if name.lower() not in ['http_proxy', 'https_proxy', 'all_proxy']}
    result = subprocess.run([str(client), 'grpc', '--target', address + ':' + str(port), '--name', GRPC, '--ca', str(ca)], capture_output=True, text=True, timeout=8, env=direct)
    require(result.returncode == 0, '真实gRPC调用失败：' + result.stderr[-1000:])
    value = json.loads(result.stdout)
    require(value.get('passed') and value.get('status') == 'SERVING' and value.get('authority') == GRPC, 'gRPC状态或authority不同')
    identity(value, backends, version='v1', protocol='grpc')
    return value


@contextmanager
def forwarded(k, pod, ports, evidence):
    process = subprocess.Popen(k[:-1] + ['--request-timeout=0', '-n', 'envoy-gateway-system', 'port-forward', '--address=127.0.0.1', 'pod/' + pod, *['0:' + str(p) for p in ports]], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output, mapped = '', {}
    try:
        deadline = time.monotonic() + 20
        while set(mapped) != set(ports):
            require(time.monotonic() < deadline and process.poll() is None, '临时Pod通道未就绪：' + output[-1000:])
            if select.select([process.stdout], [], [], 0.5)[0]:
                chunk = os.read(process.stdout.fileno(), 8192).decode()
                require(chunk, '临时Pod通道已结束')
                output += chunk
                for local, remote in re.findall(r'Forwarding from 127\.0\.0\.1:(\d+) -> (\d+)', output):
                    mapped[int(remote)] = int(local)
        yield mapped
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            remainder = process.communicate(timeout=5)[0]
        except subprocess.TimeoutExpired:
            process.kill()
            remainder = process.communicate(timeout=5)[0]
        Path(evidence).write_text(output + remainder.decode(errors='replace'))


def xds_metrics(text):
    names = ['envoy_listener_manager_lds_update_rejected', 'envoy_cluster_manager_cds_update_rejected', 'envoy_listener_manager_lds_update_success', 'envoy_cluster_manager_cds_update_success']
    values = {}
    for name in names:
        rows = re.findall(r'^' + name + r'(?:\{[^\n]*\})?\s+([0-9.eE+-]+)\s*$', text, re.M)
        require(rows, '缺少必要的xDS指标：' + name)
        values[name] = sum(float(v) for v in rows)
        require(math.isfinite(values[name]) and values[name] >= 0, 'xDS指标不是有限非负值')
    require(all(value == 0 if name.endswith('rejected') else value >= 1 for name, value in values.items()), '出现xDS拒绝或尚未接受LDS/CDS配置')
    return values


def observe(attempt, backends, fingerprint):
    attempt = Path(attempt)
    (attempt / 'observer-pid.json').write_text(json.dumps({'pid': os.getpid()}))
    deadline, successes, samples = time.monotonic() + 600, 0, 0
    with (attempt / 'traffic.jsonl').open('x') as output:
        while time.monotonic() < deadline and not (attempt / 'observer.stop').exists():
            start = time.monotonic()
            try:
                row = http('192.168.9.201', '/v1', timeout=1)
                identity(row, backends, version='v1', nonce=row['nonce'])
                require(row['tls_peer_sha256'] == fingerprint, '观测TLS身份改变')
                row['passed'] = True
                successes += 1
            except (OSError, http_client.HTTPException, ValueError) as error:
                row = {'started_mono': start, 'finished_mono': time.monotonic(), 'passed': False, 'error_type': type(error).__name__, 'error': str(error)}
            output.write(json.dumps(row, ensure_ascii=False) + '\n')
            output.flush()
            samples += 1
            if successes >= 5 and not (attempt / 'observer.ready').exists():
                (attempt / 'observer.ready').write_text('ready')
            time.sleep(0.2)
    value = {'stopped': (attempt / 'observer.stop').exists(), 'samples': samples, 'successes': successes, 'window_seconds': 600}
    (attempt / 'observer-summary.json').write_text(json.dumps(value, indent=2) + '\n')
    require(value['stopped'], '观测窗口结束但未收到正常停止标记')
    return value
