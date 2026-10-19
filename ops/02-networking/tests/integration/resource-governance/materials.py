"""标准库诊断程序的 amd64/arm64 确定性 OCI；复用现有 Go 工具和公开 CA。"""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import yaml

ROOT=Path(__file__).resolve().parents[5]
PHASE=ROOT/'ops/02-networking'
SEED=Path('/Users/mario/Downloads/cloud-native-lab-seed-2026-10-14/phase02-resource')
GO=Path.home()/'.cnpl/toolchains/go1.27.2/go/bin/go'


def build(arch, output, folder=None, entrypoint='phase-lab'):
    if arch not in ['amd64','arm64']:raise ValueError('平台不支持')
    output.mkdir(parents=True,exist_ok=True)
    folder=Path(folder) if folder else PHASE/'examples/resource-governance'
    inputs=['main.go','go.mod']+(['go.sum'] if (folder/'go.sum').exists() else [])
    source=hashlib.sha256(b''.join((folder/p).read_bytes() for p in inputs)).hexdigest()
    ca=Path('/Users/mario/Downloads/cloud-native-lab-seed-2026-10-14/policies/public-ca-bundle.crt').read_bytes()
    if b'PRIVATE KEY' in ca:raise ValueError('CA 文件包含私钥')
    env=dict(os.environ,GOOS='linux',GOARCH=arch,CGO_ENABLED='0',GOTOOLCHAIN='local',GOPROXY='off',GOSUMDB='off')
    binary=output/entrypoint
    subprocess.run([str(GO),'build','-trimpath','-buildvcs=false','-ldflags=-s -w','-o',str(binary),'.'],cwd=folder,env=env,check=True,timeout=120)
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w',format=tarfile.USTAR_FORMAT) as tar:
        for name,data,mode in [(entrypoint,binary.read_bytes(),0o555),('etc/ssl/certs/ca-certificates.crt',ca,0o444)]:
            item=tarfile.TarInfo(name);item.size,item.mode=len(data),mode;tar.addfile(item,io.BytesIO(data))
    raw=stream.getvalue();layer=gzip.compress(raw,mtime=0)
    sha=lambda b:'sha256:'+hashlib.sha256(b).hexdigest()
    encode=lambda v:json.dumps(v,sort_keys=True,separators=(',',':')).encode()
    desc=lambda k,b:{'mediaType':'application/vnd.oci.'+k,'digest':sha(b),'size':len(b)}
    config=encode({'architecture':arch,'os':'linux','config':{'User':'1000:1000','Entrypoint':['/'+entrypoint],'Env':['SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt'],'Labels':{'cnpl.io/source-sha256':source}},'rootfs':{'type':'layers','diff_ids':[sha(raw)]}})
    manifest=encode({'schemaVersion':2,'mediaType':'application/vnd.oci.image.manifest.v1+json','config':desc('image.config.v1+json',config),'layers':[desc('image.layer.v1.tar+gzip',layer)]})
    layout=output/'oci';blobs=layout/'blobs/sha256';blobs.mkdir(parents=True,exist_ok=True)
    for b in [config,layer,manifest]:(blobs/sha(b)[7:]).write_bytes(b)
    (layout/'oci-layout').write_text('{"imageLayoutVersion":"1.0.0"}')
    index=desc('image.manifest.v1+json',manifest);index['platform']={'os':'linux','architecture':arch}
    (layout/'index.json').write_bytes(encode({'schemaVersion':2,'manifests':[index]}))
    value={'source_sha256':source,'manifest_digest':sha(manifest),'config_digest':sha(config),'binary_sha256':sha(binary.read_bytes())[7:],'oci_layout':str(layout),'architecture':arch,'ca_sha256':sha(ca)[7:]}
    (output/'build.json').write_text(json.dumps(value,indent=2)+'\n')
    return value


def verify(output):
    lock=yaml.safe_load((ROOT/'ops/versions.lock.yaml').read_text())['components']['resource_fixture']
    values={}
    for arch in ['amd64','arm64']:
        actual=build(arch,output/arch);expected=lock['platforms'][arch]
        for field in ['manifest_digest','binary_sha256','source_sha256','ca_sha256']:
            if actual[field]!=expected[field]:raise ValueError('物料重建不符 '+arch+' '+field)
        with tempfile.TemporaryDirectory(prefix='cnpl-anonymous-check-') as folder:
            env=dict(os.environ,DOCKER_CONFIG=folder)
            reply=subprocess.run(['/opt/homebrew/bin/crane','digest','--platform','linux/'+arch,expected['internal_source']],env=env,capture_output=True,text=True,timeout=30)
            if reply.returncode or reply.stdout.strip()!=expected['manifest_digest']:raise ValueError('匿名镜像拉取摘要未通过：'+arch)
        values[arch]=actual
    return {'passed':True,'platforms':values}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['build','verify']);p.add_argument('--arch',default='amd64');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(build(a.arch,a.output) if a.action=='build' else verify(a.output)))
