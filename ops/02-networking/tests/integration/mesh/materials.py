"""VM 网格的 amd64 离线物料；只使用 Go/crane，不调用容器引擎。"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile
import yaml

ROOT = Path(__file__).resolve().parents[5]
PHASE = ROOT / 'ops/02-networking'
SEED = Path('/Users/mario/Downloads/cloud-native-lab-seed-2026-10-14/phase02-mesh-vm')
CRANE = '/opt/homebrew/bin/crane'


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


archive = module('mesh_archive', PHASE / 'tests/integration/dataplane/materials.py')
fixture = module('mesh_fixture', PHASE / 'tests/integration/resource-governance/materials.py')


def verify_charts(lock):
    value = lock['installer']
    if archive.file_sha(value['path']) != value['sha256']:
        raise ValueError('Istio 安装包摘要不同')
    if archive.file_sha(lock['tools']['istioctl']['path']) != lock['tools']['istioctl']['sha256']:
        raise ValueError('istioctl 摘要不同')
    root = Path(value['path']).parent
    prefix = 'istio-' + lock['version'] + '/manifests/'
    with tarfile.open(value['path']) as stream:
        expected = {m.name for m in stream.getmembers() if m.isfile() and m.name.startswith(prefix)}
        actual = {str(p.relative_to(root)) for p in Path(lock['manifests']).rglob('*') if p.is_file()}
        if expected != actual:
            raise ValueError('Istio Chart 文件集合不同')
        for name in expected:
            if hashlib.sha256(stream.extractfile(name).read()).hexdigest() != archive.file_sha(root / name):
                raise ValueError('Istio Chart 内容不同：' + name)
    return len(expected)


def verify(value):
    for name, image in value['images'].items():
        if image['architecture'] != 'amd64' or archive.file_sha(image['archive']) != image['archive_sha256']:
            raise ValueError('VM 镜像缺失或摘要不同：' + name)
        with tarfile.open(image['archive']) as stream:
            manifest = json.loads(stream.extractfile('manifest.json').read())
            if len(manifest) != 1 or manifest[0]['RepoTags'] != [image['runtime_image']]:
                raise ValueError('镜像别名不同：' + name)
            config = stream.extractfile(manifest[0]['Config']).read()
            if 'sha256:' + hashlib.sha256(config).hexdigest() != image['config_digest'] or json.loads(config)['architecture'] != 'amd64':
                raise ValueError('镜像平台/配置摘要不同：' + name)
    source = PHASE / 'examples/mesh-identity'
    digest = hashlib.sha256(b''.join((source / name).read_bytes() for name in ['main.go', 'go.mod', 'go.sum'])).hexdigest()
    if digest != value['identity_build']['source_sha256']:
        raise ValueError('身份程序源码已改变，需要重建物料')
    return {'passed': True, 'architecture': 'amd64', 'images': len(value['images'])}


def prepare():
    SEED.mkdir(parents=True, exist_ok=True)
    components = yaml.safe_load((ROOT / 'ops/versions.lock.yaml').read_text())['components']
    old = components['mesh']
    verify_charts(old)
    catalog = SEED / 'catalog.json'
    saved = json.loads(catalog.read_text()) if catalog.exists() else {}
    images = {}
    for name in ['pilot', 'proxyv2', 'install-cni', 'ztunnel', 'spire-server', 'spire-agent']:
        source = old['images'][name]['source']
        previous = saved.get(name, {})
        if previous.get('source') == source and previous.get('architecture') == 'amd64' and Path(previous.get('archive', '')).is_file() and archive.file_sha(previous['archive']) == previous.get('archive_sha256'):
            images[name] = previous
            print(name + ' amd64 archive verified', flush=True)
            continue
        digest = subprocess.check_output([CRANE, 'digest', '--platform', 'linux/amd64', source], text=True, timeout=60).strip()
        pinned = source.split('@')[0] + '@' + digest
        manifest = json.loads(subprocess.check_output([CRANE, 'manifest', pinned], text=True, timeout=60))
        version = old['spire_version'] if name.startswith('spire-') else old['version']
        value = {'source': source, 'manifest_digest': digest, 'config_digest': manifest['config']['digest'],
                 'runtime_image': 'cnpl.local/' + name + ':' + version + '-amd64', 'architecture': 'amd64',
                 'archive': str(SEED / (name + '-amd64.tar'))}
        if all(previous.get(k) == v for k, v in value.items()):
            value = previous
        images[name] = archive.export_image(name, value)
        saved[name] = images[name]
        catalog.write_text(json.dumps(saved, indent=2) + '\n')
        print(name + ' amd64 archive verified', flush=True)
    identity = fixture.build('amd64', SEED / 'identity', PHASE / 'examples/mesh-identity', 'identity-lab')
    identity['internal_source'] = 'cnpl.local/identity@' + identity['manifest_digest']
    images['identity'] = archive.export_fixture(identity, SEED / 'identity-amd64.tar', 'cnpl.local/identity:' + identity['manifest_digest'][7:23] + '-amd64')
    resource = components['resource_fixture']['platforms']['amd64']
    images['resource'] = archive.export_fixture(resource, SEED / 'resource-amd64.tar', 'cnpl.local/mesh-resource:' + resource['manifest_digest'][7:23] + '-amd64')
    for name in ['identity', 'resource']:
        images[name]['architecture'] = 'amd64'
    value = {'target': 'existing-primary-vms', 'architecture': 'amd64', 'images': images, 'identity_build': identity,
             'status': 'prepared_runtime_pending'}
    verify(value)
    (SEED / 'mesh-vm.json').write_text(json.dumps(value, indent=2) + '\n')
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'verify'])
    args = parser.parse_args()
    if args.action == 'prepare':
        value = prepare()
        print(json.dumps({'passed': True, 'catalog': str(SEED / 'mesh-vm.json'), 'images': len(value['images'])}))
    else:
        locks = yaml.safe_load((ROOT / 'ops/versions.lock.yaml').read_text())['components']
        print(json.dumps(verify(locks['mesh_vm']) | {'chart_files': verify_charts(locks['mesh'])}))
