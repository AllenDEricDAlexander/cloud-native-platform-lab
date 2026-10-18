#!/usr/bin/env python3
"""私有备份的纯文件校验、索引和公开回执；所有备份/恢复动作由 Ansible 执行。"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tarfile
import yaml


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check_bundle(directory, context):
    required = {'etc/kubernetes/pki/ca.key', 'etc/kubernetes/pki/ca.crt',
                'etc/kubernetes/enc/encryption-config.yaml', 'etc/kubernetes/audit/policy.yaml',
                'etc/kubernetes/manifests/etcd.yaml', 'etc/kubernetes/manifests/kube-apiserver.yaml'}
    cfg = yaml.safe_load((Path.home()/'.cnpl-secrets/kubeconfig-lab-primary').read_text())
    ca = next(c['cluster']['certificate-authority-data'] for c in cfg['clusters'] if c['name']=='kubernetes') if any(c['name']=='kubernetes' for c in cfg['clusters']) else cfg['clusters'][0]['cluster']['certificate-authority-data']
    ca_sha = hashlib.sha256(base64.b64decode(ca)).hexdigest()
    infos = []
    for node in ['cp01', 'cp02', 'cp03']:
        folder=directory/'nodes'/node;info=json.loads((folder/'metadata.json').read_text());infos.append(info)
        require(info['run']==context['run'] and info['node']==node, '备份归属错误')
        require(info['ca_sha256']==ca_sha, 'CA 不匹配')
        archive=folder/'host-files.tar.gz';require(digest(archive)==info['archive_sha256'], '归档传输 SHA 不符')
        with tarfile.open(archive) as source:
            names={n.rstrip('/') for n in source.getnames()};require(required<=names, '归档缺少恢复材料')
            for name in required:
                entry=source.getmember(name);require(entry.isfile(), '必要材料不是普通文件')
                data=source.extractfile(entry).read()
                require(hashlib.sha256(data).hexdigest()==info['file_sha256']['/'+name], '归档内部材料 SHA 不符')
    require(len({i['encryption_sha256'] for i in infos})==1, '三控制平面加密配置不一致')
    require(infos[0]['offline_restore_verified'] and (directory/'nodes/cp01/snapshot.db').is_file(), '缺少快照及离线目录恢复证据')
    return {'ca_sha256':ca_sha,'snapshot_status':infos[0]['snapshot_status']}


def manifest(directory, context):
    info=check_bundle(directory, context)
    return {'schema_version':2,'run':context['run'],'cluster_uid':context['cluster_uid'],
            'created_utc':datetime.now(timezone.utc).isoformat(),**info,
            'implementation_sha256':context['implementation'],'offline_restore_verified':True,
            'files':{str(p.relative_to(directory)):digest(p) for p in directory.rglob('*') if p.is_file() and p.name!='manifest.json'}}


def verify(directory, restored, context):
    require((directory/'manifest.json').read_bytes()==(restored/'manifest.json').read_bytes(), '取回的索引不同')
    value=json.loads((directory/'manifest.json').read_text())
    for relative,sha in value['files'].items():
        target=restored/relative;require(target.resolve().is_relative_to(restored.resolve()), '索引越界')
        require(digest(target)==sha, '集群外取回材料 SHA 不符：'+relative)
    check_bundle(restored,context)
    return {'verified':True,'files':len(value['files'])}


def receipt(directory, snapshot):
    require(re.fullmatch('[a-f0-9]{64}',snapshot), '缺少精确 restic 快照 ID')
    m=json.loads((directory/'manifest.json').read_text())
    result={k:m[k] for k in ['schema_version','run','cluster_uid','ca_sha256','created_utc','implementation_sha256','snapshot_status','offline_restore_verified']}
    return {**result,'status':'verified','restic_snapshot':snapshot,'manifest_sha256':digest(directory/'manifest.json'),'off_cluster_restore_verified':True}


def validate_receipt(value, context):
    require(value.get('schema_version')==2 and value.get('status')=='verified' and value.get('offline_restore_verified') is True and value.get('off_cluster_restore_verified') is True,'必须先完成新流程完整备份及取回验证')
    require(value['cluster_uid']==context['cluster_uid'] and value['run']==context['run'],'备份不属于本批/本集群')
    for key in ['restic_snapshot','manifest_sha256']:
        require(re.fullmatch('[a-f0-9]{64}',value.get(key,'')),'备份凭据缺少 SHA')
    age=(datetime.now(timezone.utc)-datetime.fromisoformat(value['created_utc'])).total_seconds()
    require(-300<=age<=86400,'备份超过24小时或时间异常，请使用新批次重新备份')
    return {'valid':True,'snapshot':value['restic_snapshot']}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['manifest','verify','receipt','validate-receipt'])
    p.add_argument('--directory',type=Path);p.add_argument('--restored',type=Path);p.add_argument('--context',type=Path,required=True)
    p.add_argument('--snapshot');p.add_argument('--input',type=Path);p.add_argument('--output',type=Path)
    a=p.parse_args();c=json.loads(a.context.read_text())
    try:
        if a.action=='manifest':value=manifest(a.directory,c)
        elif a.action=='verify':value=verify(a.directory,a.restored,c)
        elif a.action=='receipt':value=receipt(a.directory,a.snapshot)
        else:value=validate_receipt(json.loads(a.input.read_text()),c)
        if a.output:
            a.output.write_text(json.dumps(value,indent=2)+'\n');a.output.chmod(0o600)
        print(json.dumps(value if a.action!='manifest' else {'indexed':len(value['files'])}))
    except (ValueError,KeyError,OSError,tarfile.TarError) as e:
        raise SystemExit('BACKUP CHECK FAIL: '+str(e))


if __name__=='__main__':main()
