"""锁定物料、确定性诊断镜像及未安装 CRD 的离线结构校验。"""
import copy
import gzip
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[5]
PHASE = ROOT / 'ops/02-networking'
GO = Path.home() / '.cnpl/toolchains/go1.27.2/go/bin/go'
HELM = Path.home() / '.cnpl/bin/helm'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def call(args, payload=None, timeout=90):
    reply = subprocess.run([str(x) for x in args], input=payload, capture_output=True, text=True, timeout=timeout)
    require(reply.returncode == 0, Path(str(args[0])).name + ': ' + reply.stderr[-1800:])
    return reply.stdout


def lock():
    return yaml.safe_load((ROOT / 'ops/versions.lock.yaml').read_text())['components']


def source_hash():
    folder = PHASE / 'examples/gateway'
    return hashlib.sha256(b''.join((folder / name).read_bytes() for name in ['main.go', 'go.mod', 'go.sum'])).hexdigest()


def build(output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    folder = PHASE / 'examples/gateway'
    require(call([GO, 'version']).startswith('go version go1.27.2 '), 'Go 构建器版本不同')
    source = source_hash()
    binaries = {}
    for platform, os_name, arch in [('linux-amd64', 'linux', 'amd64'), ('darwin-arm64', 'darwin', 'arm64')]:
        binary = output.parent / ('gateway-' + platform)
        env = dict(os.environ, CGO_ENABLED='0', GOOS=os_name, GOARCH=arch, GOTOOLCHAIN='local', GOPROXY='off', GOSUMDB='off')
        subprocess.run([str(GO), 'build', '-trimpath', '-buildvcs=false', '-ldflags=-s -w', '-o', str(binary), '.'], cwd=folder, env=env, check=True, timeout=180)
        binaries[platform] = {'path': str(binary), 'sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
    binary = Path(binaries['linux-amd64']['path']).read_bytes()
    require(binary[:4] == b'\x7fELF', '后端不是 Linux ELF')
    content = io.BytesIO()
    with tarfile.open(fileobj=content, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        entry = tarfile.TarInfo('gateway-fixture')
        entry.size, entry.mode = len(binary), 0o555
        archive.addfile(entry, io.BytesIO(binary))
    raw = content.getvalue()
    layer = gzip.compress(raw, mtime=0)
    sha = lambda data: 'sha256:' + hashlib.sha256(data).hexdigest()
    encode = lambda value: json.dumps(value, separators=(',', ':'), sort_keys=True).encode()
    descriptor = lambda kind, data: {'mediaType': 'application/vnd.oci.' + kind, 'digest': sha(data), 'size': len(data)}
    config = encode({'architecture': 'amd64', 'os': 'linux', 'config': {'User': '1000:1000', 'Entrypoint': ['/gateway-fixture', 'serve'], 'Labels': {'cnpl.io/source-sha256': source}}, 'rootfs': {'type': 'layers', 'diff_ids': [sha(raw)]}})
    manifest = encode({'schemaVersion': 2, 'mediaType': 'application/vnd.oci.image.manifest.v1+json', 'config': descriptor('image.config.v1+json', config), 'layers': [descriptor('image.layer.v1.tar+gzip', layer)]})
    layout = output.parent / 'gateway-oci'
    blobs = layout / 'blobs/sha256'
    blobs.mkdir(parents=True, exist_ok=True)
    for data in [config, layer, manifest]:
        (blobs / sha(data)[7:]).write_bytes(data)
    (layout / 'oci-layout').write_text('{"imageLayoutVersion":"1.0.0"}')
    index = descriptor('image.manifest.v1+json', manifest)
    index['platform'] = {'os': 'linux', 'architecture': 'amd64'}
    (layout / 'index.json').write_bytes(encode({'schemaVersion': 2, 'manifests': [index]}))
    result = {'source_sha256': source, 'manifest_digest': sha(manifest), 'go_version': 'go1.27.2', 'binaries': binaries, 'oci_layout': str(layout)}
    output.write_text(json.dumps(result, indent=2) + '\n')
    return result


def checked_chart(name):
    info = lock()[name]['chart']
    path = Path(info['local_source'])
    require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == info['sha256'], name + ' Chart 摘要不同')
    return path


def crds():
    path = checked_chart('gateway_api')
    raw = call([HELM, 'template', 'cnpl-crds', path, '--set', 'crds.gatewayAPI.enabled=true', '--set', 'crds.gatewayAPI.channel=standard', '--set', 'crds.envoyGateway.enabled=true'])
    documents = [d for d in yaml.safe_load_all(raw) if d]
    for doc in documents:
        if doc['kind'] == 'CustomResourceDefinition' and doc['spec']['group'] == 'gateway.networking.k8s.io':
            annotations = doc['metadata'].get('annotations', {})
            require(annotations.get('gateway.networking.k8s.io/bundle-version') == 'v1.6.1' and annotations.get('gateway.networking.k8s.io/channel') == 'standard', 'Gateway API 不是锁定的 Standard 1.6.1')
    names = {d['spec']['names']['kind'] for d in documents if d['kind'] == 'CustomResourceDefinition' and any(v['name'] == 'v1' and v['served'] for v in d['spec']['versions'])}
    require({'GatewayClass', 'Gateway', 'HTTPRoute', 'GRPCRoute', 'TCPRoute', 'UDPRoute', 'BackendTLSPolicy', 'ReferenceGrant'} <= names, 'Standard CRD 未提供完整实验所需的 v1 API')
    return documents


def schema(value):
    result = copy.deepcopy(value)
    if result.get('nullable') and isinstance(result.get('type'), str):
        result['type'] = [result['type'], 'null']
    if result.get('type') == 'object' and result.get('properties') and 'additionalProperties' not in result and not result.get('x-kubernetes-preserve-unknown-fields'):
        result['additionalProperties'] = False
    for key in ['properties', 'patternProperties', '$defs']:
        if key in result:
            result[key] = {name: schema(child) for name, child in result[key].items()}
    for key in ['items', 'additionalProperties', 'not']:
        if isinstance(result.get(key), dict):
            result[key] = schema(result[key])
    for key in ['oneOf', 'anyOf', 'allOf']:
        if key in result:
            result[key] = [schema(child) for child in result[key]]
    return result


def validate_custom(documents, definitions):
    require(importlib.metadata.version('jsonschema') == '4.26.0', 'JSON Schema 校验器版本不同')
    models = {}
    for doc in definitions:
        if doc['kind'] != 'CustomResourceDefinition':
            continue
        for version in doc['spec']['versions']:
            if version['served']:
                models[(doc['spec']['group'] + '/' + version['name'], doc['spec']['names']['kind'])] = schema(version['schema']['openAPIV3Schema'])
    count = 0
    for doc in documents:
        key = (doc['apiVersion'], doc['kind'])
        if key not in models:
            continue
        validator = jsonschema.Draft202012Validator(models[key])
        errors = sorted(validator.iter_errors(doc), key=lambda e: str(list(e.absolute_path)))
        require(not errors, doc['kind'] + '/' + doc['metadata']['name'] + ' 字段 ' + (str(list(errors[0].absolute_path)) + ': ' + errors[0].message if errors else ''))
        count += 1
    return {'passed': True, 'custom_documents': count, 'scope': 'OpenAPI structure; CEL and actual admission are checked after CRD installation before apply'}
