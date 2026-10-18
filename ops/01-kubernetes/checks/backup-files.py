#!/usr/bin/env python3
"""节点备份材料的只读逐文件 SHA；不备份、快照、恢复、删除或调用外部程序。"""
import hashlib
import json
from pathlib import Path

PATHS = ['/etc/kubernetes', '/var/lib/kubelet/config.yaml', '/var/lib/kubelet/kubeadm-flags.env',
         '/var/lib/kubelet/pki', '/etc/systemd/system/kubelet.service.d',
         '/etc/selinux/targeted/contexts/files/file_contexts.local']


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inventory():
    files = []
    for name in PATHS:
        path = Path(name)
        if not path.exists():
            raise ValueError('缺少必要恢复路径：' + name)
        files.extend([path] if path.is_file() else [p for p in path.rglob('*') if p.is_file()])
    return {'file_sha256': {str(p): digest(p) for p in sorted(files)},
            'ca_sha256': digest('/etc/kubernetes/pki/ca.crt'),
            'encryption_sha256': digest('/etc/kubernetes/enc/encryption-config.yaml')}


if __name__ == '__main__':
    print(json.dumps(inventory()))
