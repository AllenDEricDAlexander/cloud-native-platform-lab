"""沿用既有标准库 Go + 确定性 OCI 布局，根证书只从公开材料复制。"""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import yaml

ROOT = Path(__file__).resolve().parents[5]
PHASE = ROOT / 'ops/02-networking'
GO = Path.home() / '.cnpl/toolchains/go1.27.2/go/bin/go'


def build(output, ca_path):
    output.parent.mkdir(parents=True, exist_ok=True)
    folder = PHASE / 'examples/policies'
    source = hashlib.sha256(b''.join((folder / n).read_bytes() for n in ['main.go', 'go.mod'])).hexdigest()
    ca = ca_path.read_bytes()
    assert b'BEGIN CERTIFICATE' in ca and b'PRIVATE KEY' not in ca
    binary = output.parent / 'policy-lab-linux-amd64'
    version = subprocess.check_output([str(GO), 'version'], text=True)
    assert version.startswith('go version go1.27.2 ')
    env = dict(os.environ, CGO_ENABLED='0', GOOS='linux', GOARCH='amd64', GOTOOLCHAIN='local', GOPROXY='off', GOSUMDB='off')
    subprocess.run([str(GO), 'build', '-trimpath', '-buildvcs=false', '-ldflags=-s -w', '-o', str(binary), '.'], cwd=folder, env=env, check=True, timeout=180)
    assert binary.read_bytes()[:4] == b'\x7fELF'
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for name, data, mode in [('policy-lab', binary.read_bytes(), 0o555), ('etc/ssl/certs/ca-certificates.crt', ca, 0o444)]:
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), mode
            archive.addfile(info, io.BytesIO(data))
    raw = buffer.getvalue()
    layer = gzip.compress(raw, mtime=0)
    sha = lambda value: 'sha256:' + hashlib.sha256(value).hexdigest()
    encode = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
    desc = lambda kind, value: {'mediaType': 'application/vnd.oci.' + kind, 'size': len(value), 'digest': sha(value)}
    config = encode({'architecture': 'amd64', 'os': 'linux', 'config': {'User': '1000:1000', 'Entrypoint': ['/policy-lab'],
        'Env': ['SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt'], 'Labels': {'cnpl.io/source-sha256': source}},
        'rootfs': {'type': 'layers', 'diff_ids': [sha(raw)]}})
    manifest = encode({'schemaVersion': 2, 'mediaType': 'application/vnd.oci.image.manifest.v1+json', 'config': desc('image.config.v1+json', config),
        'layers': [desc('image.layer.v1.tar+gzip', layer)]})
    layout = output.parent / 'policy-oci'
    blobs = layout / 'blobs/sha256'
    blobs.mkdir(parents=True, exist_ok=True)
    for value in [config, layer, manifest]:
        (blobs / sha(value)[7:]).write_bytes(value)
    (layout / 'oci-layout').write_text('{"imageLayoutVersion":"1.0.0"}')
    descriptor = desc('image.manifest.v1+json', manifest)
    descriptor['platform'] = {'os': 'linux', 'architecture': 'amd64'}
    (layout / 'index.json').write_bytes(encode({'schemaVersion': 2, 'manifests': [descriptor]}))
    value = {'source_sha256': source, 'manifest_digest': sha(manifest), 'binary_sha256': sha(binary.read_bytes())[7:],
        'ca_path': str(ca_path), 'ca_sha256': sha(ca)[7:], 'oci_layout': str(layout), 'go_version': 'go1.27.2'}
    output.write_text(json.dumps(value, indent=2) + '\n')
    return value


def verify(output):
    lock = yaml.safe_load((ROOT / 'ops/versions.lock.yaml').read_text())['components']['policy_fixture']
    built = build(output, Path(lock['ca_path']))
    for name in ['source_sha256', 'manifest_digest', 'binary_sha256', 'ca_sha256']:
        if built[name] != lock[name]:
            raise ValueError('确定性重建不匹配：' + name)
    result = subprocess.run(['/opt/homebrew/bin/crane', 'digest', '--platform', 'linux/amd64', lock['internal_source']],
        capture_output=True, text=True, timeout=40)
    if result.returncode or result.stdout.strip() != lock['manifest_digest']:
        raise ValueError('Harbor 物料摘要不匹配：' + result.stderr[-800:])
    return {'passed': True, **built, 'image': lock['internal_source']}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['build', 'verify'])
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--ca', type=Path)
    args = p.parse_args()
    print(json.dumps(build(args.output, args.ca) if args.action == 'build' else verify(args.output)))
