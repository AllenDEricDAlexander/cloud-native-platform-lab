#!/usr/bin/env python3
"""构建标准库静态应用及确定性的 OCI 归档；不调用 Docker、不启动应用。"""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import tarfile
import tempfile
import urllib.request

HERE = Path(__file__).resolve().parent
VERSION = 'go1.27.2'
GO_SHA = '76812b213b1b2302c978d28fa52fa92d541704b9e7d9d5db8002c50e4018c4c5'
HOME = Path.home() / '.cnpl'
GO_ROOT = HOME / 'toolchains' / VERSION
GO = GO_ROOT / 'go/bin/go'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def source_hash():
    return digest(b''.join(name.encode() + b'\0' + (HERE / name).read_bytes() for name in ['go.mod', 'main.go']))


def entry(archive, name, data, mode=0o644):
    info = tarfile.TarInfo(name); info.size = len(data); info.mode = mode
    archive.addfile(info, io.BytesIO(data))


def oci(binary, source):
    layer = io.BytesIO()
    with tarfile.open(fileobj=layer, mode='w') as tar:
        entry(tar, 'probe-lab', binary, 0o555)
    raw = layer.getvalue(); compressed = gzip.compress(raw, mtime=0)
    config = json.dumps({'architecture': 'amd64', 'os': 'linux',
                         'config': {'User': '1000:1000', 'WorkingDir': '/work', 'Entrypoint': ['/probe-lab'],
                                    'Labels': {'cnpl.io/source-sha256': source}},
                         'rootfs': {'type': 'layers', 'diff_ids': ['sha256:' + digest(raw)]}}, sort_keys=True).encode()
    def descriptor(kind, data):
        return {'mediaType': 'application/vnd.oci.image.' + kind + '.v1+json', 'digest': 'sha256:' + digest(data), 'size': len(data)}
    manifest = json.dumps({'schemaVersion': 2, 'mediaType': 'application/vnd.oci.image.manifest.v1+json',
                           'config': descriptor('config', config),
                           'layers': [{'mediaType': 'application/vnd.oci.image.layer.v1.tar+gzip', 'digest': 'sha256:' + digest(compressed), 'size': len(compressed)}]}, sort_keys=True).encode()
    image = 'cnpl.local/phase01/probe-lab:sha256-' + digest(binary)
    desc = descriptor('manifest', manifest)
    desc['annotations'] = {'io.containerd.image.name': image, 'org.opencontainers.image.ref.name': image}
    desc['platform'] = {'architecture': 'amd64', 'os': 'linux'}
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w') as tar:
        entry(tar, 'oci-layout', b'{"imageLayoutVersion":"1.0.0"}')
        entry(tar, 'index.json', json.dumps({'schemaVersion': 2, 'manifests': [desc]}).encode())
        for data in [compressed, config, manifest]:
            entry(tar, 'blobs/sha256/' + digest(data), data)
    return output.getvalue(), image, 'sha256:' + digest(manifest)


def toolchain():
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('此物料锁定管理 Mac arm64；其他管理机需另行核验编译器来源')
    GO_ROOT.mkdir(parents=True, exist_ok=True)
    archive = GO_ROOT / 'download.tar.gz'
    if not archive.exists():
        with tempfile.NamedTemporaryFile(dir=GO_ROOT, delete=False) as stream:
            temporary = Path(stream.name)
            try:
                with urllib.request.urlopen(f'https://go.dev/dl/{VERSION}.darwin-arm64.tar.gz', timeout=60) as response:
                    while chunk := response.read(1024 * 1024): stream.write(chunk)
                stream.close(); temporary.replace(archive)
            finally: temporary.unlink(missing_ok=True)
    if digest(archive.read_bytes()) != GO_SHA:
        raise ValueError('Go 下载包 SHA256 不匹配，停止，不执行编译器')
    if not GO.exists():
        with tarfile.open(archive) as tar: tar.extractall(GO_ROOT, filter='data')
    actual = subprocess.check_output([GO, 'version'], text=True).strip()
    if actual != 'go version ' + VERSION + ' darwin/arm64': raise ValueError('本地编译器版本漂移：' + actual)


def build(destination):
    toolchain()
    source = source_hash()
    cache = HOME / 'cache/01.05' / source; cache.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, GOTOOLCHAIN='local', GOPROXY='off', GOSUMDB='off', CGO_ENABLED='0')
    # 本机有限单元测试只使用 httptest Recorder / net.Pipe，不创建监听端口。
    subprocess.run([GO, 'test', '-count=1', '-v', '.'], cwd=HERE, env=env, check=True, timeout=180)
    binary = cache / 'probe-lab'
    subprocess.run([GO, 'build', '-trimpath', '-buildvcs=false', '-ldflags=-s -w -buildid=', '-o', binary, '.'],
                   cwd=HERE, env=dict(env, GOOS='linux', GOARCH='amd64', GOAMD64='v1'), check=True, timeout=180)
    data, tag, manifest = oci(binary.read_bytes(), source)
    archive = cache / 'probe-lab.oci.tar'; archive.write_bytes(data)
    result = {'schema_version': 1, 'source_sha256': source, 'go_version': VERSION, 'go_archive_sha256': GO_SHA,
              'archive': str(archive), 'archive_sha256': digest(data), 'image': tag.split(':')[0] + '@' + manifest,
              'import_tag': tag, 'manifest_digest': manifest,
              'binary_sha256': digest(binary.read_bytes())}
    destination.parent.mkdir(parents=True, exist_ok=True); destination.write_text(json.dumps(result, indent=2) + '\n')
    print('PROBE BUILD PASS；静态 linux/amd64 OCI 已生成；没有启动应用。')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', required=True, type=Path)
    build(parser.parse_args().output)
