#!/usr/bin/env python3
"""共享主入口批次锁；只在首次创建独立签发器时安全输入根 CA 口令。"""
import fcntl
import getpass
import os
from pathlib import Path
import sys
import check


def main():
    mode, records, invocation = sys.argv[1:]
    records = Path(records).resolve()
    check.require(mode in ['all', 'run', 'validate', 'cleanup', 'recover'], '模式不支持')
    check.require(records.parent == check.PHASE / 'records' and records.name.startswith('02.05-'), '批次路径越界')
    lock = check.PHASE / 'records/components/.gateway-batch.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit('另一个网关/证书批次正在执行，请先等待原进程结束。')
    check.require(mode not in ['all', 'run'] or not any((records / p).exists() for p in ['passed.json', 'state/closed.json']), '不能覆盖已验收或关闭的批次')
    context = check.preflight(records, mode in ['cleanup', 'recover'])
    if mode in ['all', 'run']:
        password = None
        if not check.pki.existing_issuer(context):
            check.require(sys.stdin.isatty(), '首次创建专用签发器需要交互终端')
            password = getpass.getpass('离线根 CA 口令（只在 Mac 签专用中间 CA，不回显、不保存）：').encode()
        try:
            check.pki.prepare(records, context, password)
        finally:
            del password
        print('TLS MATERIALS READY；根 CA 与原中间 CA 私钥未上传。', flush=True)
    os.set_inheritable(fd, True)
    ansible = Path.home() / '.venvs/cnpl-ansible/bin/ansible-playbook'
    os.execv(str(ansible), [str(ansible), str(check.PHASE / 'ansible/playbooks/certificates.yml'), '-e', '@' + invocation])


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        sys.exit(str(error))
