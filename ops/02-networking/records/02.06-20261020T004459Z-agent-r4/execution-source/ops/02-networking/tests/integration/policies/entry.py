#!/usr/bin/env python3
"""正式/恢复入口持有原有网络批次锁；validate 只读，不抢运行锁。"""
import fcntl
import os
from pathlib import Path
import sys
import check


def main():
    mode, record_arg, invocation = sys.argv[1:]
    check.require(not Path(record_arg).is_symlink(), '不允许符号链接批次')
    records = Path(record_arg).resolve()
    check.require(mode in ['all', 'validate', 'cleanup', 'recover'], '模式不支持')
    check.require(records.parent == check.PHASE / 'records' and records.name.startswith('02.06-'), '证据目录越界')
    if mode != 'validate':
        lock = check.PHASE / 'records/components/.gateway-batch.lock'
        fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            sys.exit('另一个网络/网关/证书批次正在运行；等待其结束后再运行。')
        os.set_inheritable(fd, True)
    if mode == 'all':
        check.require(not any((records / p).exists() for p in ['passed.json', 'state/closed.json', 'state/protected.json']),
            '正式批次已使用；先 recover 原批次，再选择全新证据目录。')
    if mode in ['recover', 'cleanup']:
        check.require((records / 'context.json').exists(), '缺少原始上下文，不能猜测清理目标')
    ansible = Path.home() / '.venvs/cnpl-ansible/bin/ansible-playbook'
    os.execv(str(ansible), [str(ansible), str(check.PHASE / 'ansible/playbooks/policies.yml'), '-e', '@' + invocation])


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        sys.exit(str(error))
