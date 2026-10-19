"""02.05 的锁定 Helm/CRD 和无额外依赖的 Go TLS 客户端。"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[5]
PHASE = ROOT / 'ops/02-networking'
HELM = Path.home() / '.cnpl/bin/helm'
GO = Path.home() / '.cnpl/toolchains/go1.27.2/go/bin/go'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def lock():
    return yaml.safe_load((ROOT / 'ops/versions.lock.yaml').read_text())['components']['cert_manager']


def call(args, payload=None, timeout=90):
    reply = subprocess.run([str(a) for a in args], input=payload, capture_output=True, text=True, timeout=timeout)
    require(reply.returncode == 0, Path(str(args[0])).name + ': ' + reply.stderr[-1600:])
    return reply.stdout


def chart():
    item = lock()['chart']
    path = Path(item['local_source'])
    require(hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256'], 'cert-manager Chart 摘要不匹配')
    return path


def crds():
    raw = call([HELM, 'template', 'cnpl-cert-manager', chart(), '-n', 'cert-manager', '--set', 'crds.enabled=true'])
    result = [d for d in yaml.safe_load_all(raw) if d and d['kind'] == 'CustomResourceDefinition']
    require(len(result) == 6 and {d['spec']['names']['kind'] for d in result} == {'Certificate', 'CertificateRequest', 'Issuer', 'ClusterIssuer', 'Order', 'Challenge'}, 'cert-manager CRD 包不完整')
    return result


def build(output):
    folder = PHASE / 'examples/certificates'
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, CGO_ENABLED='0', GOOS='darwin', GOARCH='arm64', GOTOOLCHAIN='local', GOPROXY='off', GOSUMDB='off')
    subprocess.run([str(GO), 'build', '-trimpath', '-buildvcs=false', '-ldflags=-s -w', '-o', str(output), '.'], cwd=folder, env=env, check=True, timeout=90)
    return {'path': str(output), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'source_sha256': hashlib.sha256(b''.join((folder / n).read_bytes() for n in ['main.go', 'go.mod'])).hexdigest(), 'go': '1.27.2'}
