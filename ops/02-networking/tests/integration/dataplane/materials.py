"""隔离集群物料：公开镜像按平台摘要导出，归档只改本地 RepoTags。"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import urllib.request
import yaml

ROOT=Path(__file__).resolve().parents[5]
PHASE=ROOT/'ops/02-networking'
SEED=Path('/Users/mario/Downloads/cloud-native-lab-seed-2026-10-14/phase02-advanced')
CRANE='/opt/homebrew/bin/crane'


def file_sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def export_image(name, value):
    archive=Path(value['archive']);raw=archive.with_suffix('.upstream.tar')
    if archive.is_file() and value.get('archive_sha256')==file_sha(archive):
        return value
    source=value['source'].split('@')[0]+'@'+value['manifest_digest']
    subprocess.run([CRANE,'pull','--platform','linux/'+value['architecture'],'--format','legacy',source,str(raw)],check=True,capture_output=True,text=True,timeout=600)
    staged=archive.with_suffix('.new.tar')
    with tarfile.open(raw) as old,tarfile.open(staged,'w',format=tarfile.PAX_FORMAT) as new:
        manifests=json.loads(old.extractfile('manifest.json').read())
        if len(manifests)!=1:raise ValueError('归档必须单一平台 '+name)
        config=old.extractfile(manifests[0]['Config']).read()
        if 'sha256:'+hashlib.sha256(config).hexdigest()!=value['config_digest']:raise ValueError('归档配置摘要不符 '+name)
        manifests[0]['RepoTags']=[value['runtime_image']]
        for member in old.getmembers():
            if member.name=='manifest.json':
                content=json.dumps(manifests,separators=(',',':')).encode();member.size=len(content)
                new.addfile(member,io.BytesIO(content))
            elif member.isfile():
                new.addfile(member,old.extractfile(member))
            else:
                new.addfile(member)
    staged.replace(archive)
    raw.unlink()
    value.update(archive_sha256=file_sha(archive))
    return value


def export_fixture(value, destination, alias):
    layout=Path(value['oci_layout']);index=json.loads((layout/'index.json').read_text())
    descriptor=index['manifests'][0];manifest=json.loads((layout/'blobs/sha256'/descriptor['digest'][7:]).read_text())
    config=(layout/'blobs/sha256'/manifest['config']['digest'][7:]).read_bytes()
    if descriptor['digest']!=value['manifest_digest'] or 'sha256:'+hashlib.sha256(config).hexdigest()!=value['config_digest']:
        raise ValueError('自建镜像配置/清单摘要不符')
    # Docker legacy archive 的 layer 必须是未压缩 tar；校验 diffID 与解压内容。
    import gzip
    layers=[]
    with tarfile.open(destination,'w') as archive:
        name='config.json';info=tarfile.TarInfo(name);info.size=len(config);archive.addfile(info,io.BytesIO(config))
        for i,layer in enumerate(manifest['layers']):
            compressed=(layout/'blobs/sha256'/layer['digest'][7:]).read_bytes()
            if 'sha256:'+hashlib.sha256(compressed).hexdigest()!=layer['digest']:raise ValueError('层摘要不同')
            raw=gzip.decompress(compressed)
            if 'sha256:'+hashlib.sha256(raw).hexdigest()!=json.loads(config)['rootfs']['diff_ids'][i]:raise ValueError('未压缩层 diffID 不符')
            name='layer-'+str(i)+'.tar';layers.append(name)
            info=tarfile.TarInfo(name);info.size=len(raw);archive.addfile(info,io.BytesIO(raw))
        content=json.dumps([{'Config':'config.json','RepoTags':[alias],'Layers':layers}]).encode()
        info=tarfile.TarInfo('manifest.json');info.size=len(content);archive.addfile(info,io.BytesIO(content))
    return {'source':value['internal_source'],'manifest_digest':value['manifest_digest'],'config_digest':manifest['config']['digest'],
        'runtime_image':alias,'architecture':'arm64','archive':str(destination),'archive_sha256':file_sha(destination)}


def verify(lock):
    for name,value in lock['images'].items():
        path=Path(value['archive'])
        if not path.is_file() or file_sha(path)!=value['archive_sha256']:
            raise ValueError('离线镜像缺失或损坏：'+name+'；需要先重新准备物料')
    for name,value in lock['tools'].items():
        if hashlib.sha256(Path(value['path']).read_bytes()).hexdigest()!=value['sha256']:raise ValueError('工具摘要不同：'+name)
    for name in ['cilium_chart','gateway_chart']:
        value=lock.get(name)
        if value and file_sha(value['local_source'])!=value['sha256']:raise ValueError('Chart 摘要不同：'+name)
    return {'passed':True,'images':len(lock['images']),'tools':len(lock['tools'])}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['export','verify']);p.add_argument('--catalog',type=Path,required=True);a=p.parse_args()
    values=json.loads(a.catalog.read_text())
    if a.action=='export':
        for name,value in values.items():
            values[name]=export_image(name,value);a.catalog.write_text(json.dumps(values,indent=2)+'\n')
            print(name,'verified',flush=True)
    else:
        print(json.dumps(verify(values)))
