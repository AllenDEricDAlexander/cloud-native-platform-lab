#!/usr/bin/env python3
"""持有批次锁；在 Ansible 启动前一次性签发叶证书，不传递 CA 口令。"""
import fcntl
import getpass
import os
from pathlib import Path
import sys

import check


def main():
    mode, records, invocation = sys.argv[1:]
    directory = Path(records).resolve()
    check.require(mode in ['all', 'validate', 'run', 'cleanup', 'recover'], '未知模式')
    check.require(directory.parent == check.PHASE / 'records' and directory.name.startswith('02.04-'), '批次目录越界')
    guard = check.PHASE / 'records/components/.gateway-batch.lock'
    guard.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(guard, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit('已有 Gateway 批次运行，请先确认原进程状态。')
    check.require(mode not in ['all', 'run'] or not any((directory / p).exists() for p in ['passed.json', 'state/closed.json']), '正式运行不能覆盖已通过或已关闭批次')
    context = check.preflight(directory, mode in ['cleanup', 'recover'])
    if mode in ['all', 'run']:
        auth = check.pki.authority()
        if not check.pki.existing(directory, auth):
            check.require(sys.stdin.isatty(), '首次签发需要交互终端安全输入一次中间 CA 口令')
            password = getpass.getpass('现有中间 CA 口令（不回显、不保存）：').encode()
            try:
                check.pki.issue(directory, context, password)
            finally:
                del password
        print('TLS MATERIALS READY；仅保存叶证书私钥和公开签发回执。', flush=True)
    os.set_inheritable(fd, True)
    ansible = Path.home() / '.venvs/cnpl-ansible/bin/ansible-playbook'
    os.execv(str(ansible), [str(ansible), str(check.PHASE / 'ansible/playbooks/gateway.yml'), '-e', '@' + invocation])


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        sys.exit(str(error))
