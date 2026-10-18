#!/usr/bin/env python3
"""复用已核验 Go 工具链，构建三个固定版本的本地 OCI 镜像；不启动应用。"""
import argparse
import gzip
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
sp = importlib.util.spec_from_file_location('probe_build', HERE.parent / 'probes/build.py')
previous = importlib.util.module_from_spec(sp); sp.loader.exec_module(previous)
digest, entry = previous.digest, previous.entry
REPOSITORY = 'cnpl.local/phase01/controller-lab'


def oci(binary, source, version):
    if version not in ['v1', 'v2', 'bad']: raise ValueError('未知实验版本')
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as tar: entry(tar, 'controller-app', binary, 0o555)
    raw = stream.getvalue(); layer = gzip.compress(raw, mtime=0)
    config = json.dumps({'architecture': 'amd64', 'os': 'linux',
                         'config': {'User': '1000:1000', 'WorkingDir': '/work', 'Entrypoint': ['/controller-app'],
                                    'Env': ['APP_VERSION=' + version],
                                    'Labels': {'cnpl.io/source-sha256': source, 'cnpl.io/controller-version': version}},
                         'rootfs': {'type': 'layers', 'diff_ids': ['sha256:' + digest(raw)]}}, sort_keys=True).encode()
    def desc(media, data): return {'mediaType': media, 'size': len(data), 'digest': 'sha256:' + digest(data)}
    manifest = json.dumps({'schemaVersion': 2, 'mediaType': 'application/vnd.oci.image.manifest.v1+json',
                           'config': desc('application/vnd.oci.image.config.v1+json', config),
                           'layers': [desc('application/vnd.oci.image.layer.v1.tar+gzip', layer)]}, sort_keys=True).encode()
    sha = digest(manifest); tag = REPOSITORY + ':' + version + '-sha256-' + sha
    descriptor = desc('application/vnd.oci.image.manifest.v1+json', manifest)
    descriptor.update(platform={'os': 'linux', 'architecture': 'amd64'},
                      annotations={'io.containerd.image.name': tag, 'org.opencontainers.image.ref.name': tag})
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode='w') as tar:
        entry(tar, 'oci-layout', b'{"imageLayoutVersion":"1.0.0"}')
        entry(tar, 'index.json', json.dumps({'schemaVersion': 2, 'manifests': [descriptor]}, sort_keys=True).encode())
        for data in [config, layer, manifest]: entry(tar, 'blobs/sha256/' + digest(data), data)
    return result.getvalue(), {'version': version, 'image': REPOSITORY + '@sha256:' + sha, 'import_tag': tag, 'manifest_digest': 'sha256:' + sha}


def build(destination):
    previous.toolchain()
    source = digest(b''.join(name.encode() + b'\0' + (HERE / name).read_bytes() for name in ['go.mod', 'main.go']))
    cache = Path.home() / '.cnpl/cache/01.06' / source; cache.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, GOTOOLCHAIN='local', GOPROXY='off', GOSUMDB='off', CGO_ENABLED='0')
    subprocess.run([previous.GO, 'test', '-count=1', '-timeout=30s', '-v', '.'], cwd=HERE, env=env, check=True, timeout=180)
    binary = cache / 'controller-app'
    subprocess.run([previous.GO, 'build', '-trimpath', '-buildvcs=false', '-ldflags=-s -w -buildid=', '-o', binary, '.'],
                   cwd=HERE, env=dict(env, GOOS='linux', GOARCH='amd64', GOAMD64='v1'), check=True, timeout=180)
    images = {}
    for version in ['v1', 'v2', 'bad']:
        data, image = oci(binary.read_bytes(), source, version)
        archive = cache / (version + '.oci.tar'); archive.write_bytes(data)
        image.update(archive=str(archive), archive_sha256=digest(data)); images[version] = image
    bundle = {'schema_version': 1, 'source_sha256': source, 'go_version': previous.VERSION,
              'go_archive_sha256': previous.GO_SHA, 'binary_sha256': digest(binary.read_bytes()), 'images': images}
    destination.parent.mkdir(parents=True, exist_ok=True); destination.write_text(json.dumps(bundle, indent=2) + '\n')
    print('CONTROLLER BUILD PASS；v1/v2/bad OCI 已生成，未启动应用。')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
